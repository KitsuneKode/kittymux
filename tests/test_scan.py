import json
import os
import stat
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_scan as KS  # noqa: E402

DEVIN_THINKING = "  Thinking · 37m 8s (esc twice to interrupt)\n❯ Press Enter to send queued messages now\n"
PERMISSION = "Do you want to proceed?\n❯ 1. Yes\n  2. No\n"
IDLE = "╭────╮\n│ >  │\n╰────╯\n? for shortcuts\n"
WORKING = "✻ Cogitating… (12s · ↑ 340 tokens · esc to interrupt)\n"


class FakeBoss:
    def __init__(self):
        self.all_windows = []
        self.window_id_map = {}


class FakeKitty:
    """Stands in for kitty.fast_data_types: records timers instead of arming them."""
    def __init__(self):
        self.boss = FakeBoss()
        self.timers = {}
        self.next_id = 1
        self.removed = []

    def install(self):
        mod = types.ModuleType("kitty.fast_data_types")
        mod.get_boss = lambda: self.boss
        mod.add_timer = self.add_timer
        mod.remove_timer = self.remove_timer
        pkg = types.ModuleType("kitty")
        pkg.fast_data_types = mod
        self._saved = {k: sys.modules.get(k) for k in ("kitty", "kitty.fast_data_types")}
        sys.modules["kitty"], sys.modules["kitty.fast_data_types"] = pkg, mod

    def uninstall(self):
        for k, v in self._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def add_timer(self, fn, interval, repeat=True):
        tid = self.next_id
        self.next_id += 1
        self.timers[tid] = (fn, interval)
        return tid

    def remove_timer(self, tid):
        self.removed.append(tid)
        self.timers.pop(tid, None)


class FakeWindow:
    """`screen` is what the test sets (the visible text); like a real window, `window.screen` also has `.bell()`."""
    def __init__(self, wid, agent, screen, focused=False, title="agent"):
        self.id, self.agent, self.is_focused, self.title = wid, agent, focused, title
        self.child = types.SimpleNamespace(child_fd=None)
        self.text = screen
        self.bells = 0

    @property
    def screen(self):
        return types.SimpleNamespace(bell=self._bell)

    @screen.setter
    def screen(self, text):
        self.text = text

    def _bell(self):
        self.bells += 1

    def as_text(self):
        return self.text

    def tabref(self):
        return None


class ScanBase(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp()
        self._env = mock.patch.dict(os.environ, {"KITTYMUX_STATE": self.state, "KITTYMUX_NOTIFY": "0"})
        self._env.start()
        self.k = FakeKitty()
        self.k.install()
        for attr, val in (("scan_timer", None), ("spin_timer", None), ("interval", 0.0), ("last_sig", ""),
                          ("last_write", 0.0), ("panes", (0.0, {}))):
            setattr(KS._RT, attr, val)
        for d in (KS._RT.book, KS._RT.verdicts, KS._RT.notified, vars(KS._RT).setdefault("alerted", {})):
            d.clear()
        vars(KS._RT).pop("decisions", None)
        vars(KS._RT).pop("attention", None)
        vars(KS._RT).pop("journal", None)
        self._hypr = mock.patch("kittymux_layout.hypr_focus_on_activate", return_value=None)   # never depend on the compositor running the tests
        self._hypr.start()
        self.agent = mock.patch.object(KS, "agent_of", side_effect=lambda w: w.agent)
        self.agent.start()

    def tearDown(self):
        self._hypr.stop()
        self.agent.stop()
        self.k.uninstall()
        self._env.stop()

    def add(self, *wins):
        for w in wins:
            self.k.boss.all_windows.append(w)
            self.k.boss.window_id_map[w.id] = w


class VerdictTests(ScanBase):
    def test_devin_thinking_is_working_not_waiting(self):      # the screenshot bug
        w = FakeWindow(1, "devin", DEVIN_THINKING)
        self.add(w)
        KS.scan_all()
        self.assertEqual(KS._RT.verdicts["1"]["state"], "working")
        self.assertEqual(KS._RT.verdicts["1"]["reason"], "")

    def test_permission_prompt_is_waiting_with_reason(self):
        self.add(FakeWindow(2, "claude", PERMISSION))
        KS.scan_all()
        v = KS._RT.verdicts["2"]
        self.assertEqual(v["state"], "waiting")
        self.assertIn("Do you want to proceed", v["reason"])

    def test_limit_screen(self):
        self.add(FakeWindow(3, "claude", "Claude usage limit reached. Your limit will reset at 5pm.\n"))
        morning = 1_790_000_000 - (1_790_000_000 % 86400) + 10 * 3600          # 10:00 UTC: 5pm is still ahead (the verdict must not depend on the hour the suite runs)
        with mock.patch.object(KS, "_wall", return_value=morning), mock.patch.object(KS, "_tz", return_value=0.0):
            KS.scan_all()
        self.assertEqual(KS._RT.verdicts["3"]["state"], "limited")

    def test_idle_agent_has_a_verdict_but_it_is_idle(self):
        self.add(FakeWindow(4, "codex", IDLE))
        KS.scan_all()
        self.assertEqual(KS._RT.verdicts["4"]["state"], "idle")

    def test_plain_shell_gets_no_verdict(self):
        self.add(FakeWindow(5, None, PERMISSION))                # same text, but no agent here
        KS.scan_all()
        self.assertNotIn("5", KS._RT.verdicts)

    def test_agent_that_exits_is_cleared(self):
        w = FakeWindow(6, "claude", DEVIN_THINKING)
        self.add(w)
        KS.scan_all()
        w.agent = None
        KS.scan_all()
        self.assertEqual(KS._RT.verdicts["6"]["state"], "")

    def test_closed_windows_are_forgotten(self):
        w = FakeWindow(7, "claude", DEVIN_THINKING)
        self.add(w)
        KS.scan_all()
        self.k.boss.all_windows.clear()
        KS.scan_all()
        self.assertNotIn("7", KS._RT.verdicts)
        self.assertNotIn("7", KS._RT.book)

    def test_hook_state_is_an_input(self):
        os.makedirs(self.state, exist_ok=True)
        with open(KS._panes_path(), "w") as f:
            json.dump({"8": {"status": "waiting", "msg": "Approve: rm -rf x?", "ts_status": time.monotonic()}}, f)
        self.add(FakeWindow(8, "claude", IDLE))
        KS.scan_all()
        self.assertEqual(KS._RT.verdicts["8"]["state"], "waiting")

    def test_idle_notification_hook_does_not_cause_waiting(self):
        with open(KS._panes_path(), "w") as f:
            json.dump({"9": {"status": "waiting", "msg": "Claude is waiting for your input", "ts_status": 1.0}}, f)
        self.add(FakeWindow(9, "claude", IDLE, focused=True))
        KS.scan_all()
        self.assertEqual(KS._RT.verdicts["9"]["state"], "idle")

    def test_unfocused_finished_agent_with_idle_notification_is_done_not_waiting(self):
        with open(KS._panes_path(), "w") as f:
            json.dump({"10": {"status": "waiting", "msg": "", "ts_status": time.monotonic()}}, f)
        self.add(FakeWindow(10, "claude", IDLE))
        with mock.patch.object(KS, "_notify") as notify:
            KS.scan_all()
        self.assertEqual(KS._RT.verdicts["10"]["state"], "done")
        notify.assert_not_called()                              # nothing here asks for you


class NotifyTests(ScanBase):
    def test_notifies_once_when_an_unfocused_agent_starts_needing_you(self):
        w = FakeWindow(1, "claude", PERMISSION)
        self.add(w)
        w.screen = IDLE
        KS.scan_all()  # establish a baseline before a new request appears
        w.screen = PERMISSION
        with mock.patch.object(KS, "_notify") as notify:
            KS.scan_all()
            KS.scan_all()
            KS.scan_all()
        self.assertEqual(notify.call_count, 1)
        self.assertEqual(notify.call_args[0][1], "waiting")

    def test_first_seen_attention_does_not_replay_notifications_or_bells(self):
        for wid, text in ((1, PERMISSION), (2, "Claude usage limit reached")):
            w = FakeWindow(wid, "claude", text)
            self.add(w)
        with mock.patch.object(KS, "_notify") as notify:
            KS.scan_all()
        notify.assert_not_called()
        self.assertEqual([w.bells for w in self.k.boss.all_windows], [0, 0])
        self.assertEqual(KS._RT.verdicts["1"]["state"], "waiting")
        self.assertEqual(KS._RT.verdicts["2"]["state"], "limited")

    def test_approved_hook_stays_cleared_across_scanner_ticks(self):
        w = FakeWindow(1, "claude", PERMISSION)
        self.add(w)
        entry = {"status": "waiting", "ts_status": 90.0, "msg": "Approve this command?"}
        with mock.patch.object(KS, "_panes", return_value={"1": entry}):
            KS.scan_window(w, 100.0)
            w.screen = DEVIN_THINKING
            KS.scan_window(w, 101.0)
            w.screen = IDLE
            KS.scan_window(w, 105.0)
            self.assertEqual(KS._RT.verdicts["1"]["state"], "done")
            w.is_focused = True
            KS.scan_window(w, 106.0)
            w.is_focused = False
            KS.scan_window(w, 107.0)
            self.assertEqual(KS._RT.verdicts["1"]["state"], "idle")

    def test_working_does_not_notify(self):
        self.add(FakeWindow(1, "claude", DEVIN_THINKING))
        with mock.patch.object(KS, "_notify") as notify:
            KS.scan_all()
        notify.assert_not_called()

    def test_text_is_escaped_and_bounded(self):
        out = KS._plain("<b>bold</b> & <a href='x'>link</a>", 200)
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)
        self.assertIn("&amp;", out)
        self.assertLessEqual(len(KS._plain("z" * 500, 60)), 60)

    def test_respects_the_off_switch(self):
        with mock.patch.dict(os.environ, {"KITTYMUX_NOTIFY": "0"}), \
             mock.patch("kittymux_scan.subprocess.Popen") as popen, mock.patch("kittymux_scan.shutil.which", return_value="x"):
            KS._notify(FakeWindow(1, "claude", ""), "waiting", "hi")
        popen.assert_not_called()


class DecisionLogTests(ScanBase):
    def events(self):
        return list(vars(KS._RT).get("decisions", []))

    def test_state_changes_are_recorded_with_their_reason(self):
        w = FakeWindow(1, "claude", DEVIN_THINKING)
        self.add(w)
        with mock.patch.object(KS, "_notify", return_value="sent"):
            KS.scan_window(w, 100.0)
            w.screen = PERMISSION
            KS.scan_window(w, 101.0)
        states = [(e["frm"], e["to"], e["why"]) for e in self.events() if e["kind"] == "state"]
        self.assertEqual([(a, b) for a, b, _ in states], [("", "working"), ("working", "waiting")])
        self.assertIn("busy marker", states[0][2])
        self.assertIn("prompt", states[1][2])
        self.assertEqual(KS._RT.verdicts["1"]["why"], states[1][2])                  # the published verdict carries it too

    def test_a_short_run_that_finishes_is_logged_as_held_back_with_its_duration(self):
        w = FakeWindow(1, "claude", DEVIN_THINKING)
        self.add(w)
        KS.scan_window(w, 100.0)
        w.screen = IDLE
        for t in (102.0, 104.0, 108.0):
            KS.scan_window(w, t)
        held = [e for e in self.events() if e["kind"] == "notify" and e["state"] == "done"]
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["outcome"], "inbox only: finish judged from the screen alone and the run was short (< 60 s)")

    def test_notify_reports_why_it_did_not_send(self):
        w = FakeWindow(1, "claude", "")
        with mock.patch.dict(os.environ, {"KITTYMUX_NOTIFY": "1"}), mock.patch("kittymux_scan.shutil.which", return_value="x"), \
                mock.patch("kittymux_scan.subprocess.Popen") as popen:
            w.is_focused = True
            self.assertEqual(KS._notify(w, "waiting", "q"), "suppressed: you are looking at it")
            w.is_focused = False
            self.assertEqual(KS._notify(w, "waiting", "q"), "sent")
            self.assertTrue(KS._notify(w, "waiting", "q").startswith("suppressed: this window was notified less than"))
            self.assertEqual(popen.call_count, 1)
        with mock.patch.dict(os.environ, {"KITTYMUX_NOTIFY": "0"}):
            self.assertEqual(KS._notify(FakeWindow(2, "claude", ""), "waiting", "q"), "suppressed: notifications are switched off")

    def test_the_log_is_bounded_in_memory_and_on_disk_and_private(self):
        for i in range(6000):
            KS._record("state", str(i % 20), "claude", frm="idle", to="working", why="the screen shows a busy marker " + "x" * 40)
        self.assertEqual(len(self.events()), KS.DECISION_KEEP)
        path = KS.decisions_path()
        self.assertLessEqual(os.path.getsize(path), KS.DECISION_FILE_MAX + 400)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        with open(path) as f:
            lines = f.read().splitlines()
        self.assertLessEqual(len(lines), KS.DECISION_FILE_MAX // 100 + 1)
        json.loads(lines[-1])                                                          # still valid JSON lines after rotation

    def test_recording_never_raises(self):
        with mock.patch.object(KS, "_append_decision", side_effect=OSError("disk full")):
            KS._record("state", "1", "claude", frm="", to="idle", why="x")           # must not propagate into kitty
        KS._record("state", "1", "claude", frm="", to=object(), why="x")             # unserialisable: dropped quietly


class TimerTests(ScanBase):
    def test_ensure_started_is_idempotent(self):
        for _ in range(5):
            KS.ensure_started()
        self.assertEqual(len(self.k.timers), 1)

    def test_restart_replaces_instead_of_stacking(self):
        KS.ensure_started()
        for _ in range(4):
            KS.restart()
        self.assertEqual(len(self.k.timers), 1)

    def test_reloading_the_module_does_not_forget_the_timer(self):
        import importlib
        KS.ensure_started()
        importlib.reload(KS)                 # what tab_bar.py does on every config reload
        KS.ensure_started()
        self.assertEqual(len(self.k.timers), 1)

    def test_stop_removes_every_timer(self):
        self.add(FakeWindow(1, "claude", DEVIN_THINKING))
        KS.ensure_started()
        KS.scan_all()
        self.assertEqual(len(self.k.timers), 2)                  # scanner + spinner
        KS.stop()
        self.assertEqual(self.k.timers, {})

    def test_spinner_runs_only_while_something_works(self):
        w = FakeWindow(1, "claude", DEVIN_THINKING)
        self.add(w)
        KS.scan_all()
        self.assertIsNotNone(KS._RT.spin_timer)
        spin = KS._RT.spin_timer
        KS.scan_all()
        self.assertEqual(KS._RT.spin_timer, spin)                # one spinner, not one per scan
        w.screen = IDLE
        w.is_focused = True
        with mock.patch.object(KS.time, "monotonic", return_value=10 ** 6):
            KS.scan_all()
        self.assertIsNone(KS._RT.spin_timer)

    def test_scan_cadence_follows_agent_presence(self):
        KS.scan_all()
        self.assertEqual(KS._RT.interval, KS.SCAN_IDLE)
        self.add(FakeWindow(1, "claude", DEVIN_THINKING))
        KS.scan_all()
        self.assertEqual(KS._RT.interval, KS.SCAN_FAST)

    def test_no_kitty_means_no_timer_and_no_crash(self):
        self.k.boss = None
        self.assertFalse(KS.ensure_started())
        KS.scan_all()


class FileTests(ScanBase):
    def test_verdict_file_is_private(self):
        self.add(FakeWindow(1, "claude", PERMISSION))
        KS.scan_all()
        self.assertEqual(stat.S_IMODE(os.stat(KS.scan_path()).st_mode), 0o600)
        with open(KS.scan_path()) as f:
            data = json.load(f)
        self.assertEqual(data["1"]["state"], "waiting")
        self.assertFalse([n for n in os.listdir(self.state) if n.endswith(".tmp")])

    def test_unchanged_verdicts_are_not_rewritten_within_the_heartbeat(self):
        self.add(FakeWindow(1, "claude", DEVIN_THINKING))
        KS.scan_all()
        with mock.patch("kittymux_scan.os.replace") as replace:
            for _ in range(5):
                KS.scan_all()
        replace.assert_not_called()

    def test_heartbeat_refreshes_an_unchanged_file(self):
        self.add(FakeWindow(1, "claude", DEVIN_THINKING))
        KS.scan_all()
        KS._RT.last_write -= KS.HEARTBEAT + 1
        with mock.patch("kittymux_scan.os.replace") as replace:
            KS.scan_all()
        replace.assert_called_once()

    def test_stored_reason_is_cleaned_and_bounded(self):
        evil = "Do you want to proceed? \x1b[31m" + "x" * 500 + "\x07"
        self.add(FakeWindow(1, "claude", evil))
        KS.scan_all()
        reason = KS._RT.verdicts["1"]["reason"]
        self.assertLessEqual(len(reason), 100)
        self.assertTrue(all(ord(c) >= 32 and ord(c) != 127 for c in reason))


class CompletionNotifyTests(ScanBase):
    def finish(self, worked, focused=False, first_sight=False):
        w = FakeWindow(1, "claude", DEVIN_THINKING if not first_sight else IDLE, focused=focused)
        self.add(w)
        t = 1000.0
        with mock.patch.object(KS.time, "monotonic", return_value=t):
            KS.scan_all()
        w.screen = IDLE
        with mock.patch.object(KS, "_notify") as notify:
            for dt in (worked, worked + KS.DONE_SETTLE + 0.2):          # it turns idle, and STAYS idle
                with mock.patch.object(KS.time, "monotonic", return_value=t + dt):
                    KS.scan_all()
        return notify, KS._RT.verdicts["1"]["state"]

    def test_a_long_run_judged_from_the_screen_alone_notifies_after_a_minute(self):
        notify, state = self.finish(worked=90)
        self.assertEqual(state, "done")
        notify.assert_called_once()
        self.assertEqual(notify.call_args[0][1], "done")

    def test_a_screen_only_finish_under_a_minute_is_inbox_only_not_a_popup(self):
        # inferring "finished" from a quiet screen is the one thing that can be wrong: it never interrupts you for a short run
        notify, state = self.finish(worked=40)
        self.assertEqual(state, "done")                                  # still shown in the bar…
        notify.assert_not_called()                                       # …but no popup
        done = [e for e in KS._inbox().load(self.state) if e["kind"] == "done"]
        self.assertEqual(len(done), 1)                                   # …and it is in the inbox, marked low confidence
        self.assertEqual((done[0]["confidence"], done[0]["sources"]), ("low", ["screen"]))

    def test_a_quick_reply_does_not(self):
        notify, state = self.finish(worked=5)
        self.assertEqual(state, "done")
        notify.assert_not_called()

    def test_a_window_seen_for_the_first_time_never_notifies(self):
        self.add(FakeWindow(2, "claude", IDLE))
        with open(KS._panes_path(), "w") as f:
            json.dump({"2": {"status": "done", "ts_status": time.monotonic()}}, f)
        with mock.patch.object(KS, "_notify") as notify:
            KS.scan_all()
        self.assertEqual(KS._RT.verdicts["2"]["state"], "done")
        notify.assert_not_called()

    def test_finishing_in_front_of_you_does_not(self):
        notify, state = self.finish(worked=40, focused=True)
        self.assertEqual(state, "idle")
        notify.assert_not_called()

    def test_needing_you_rings_the_bell_once_but_finishing_does_not(self):
        w = FakeWindow(1, "claude", PERMISSION)
        self.add(w)
        w.screen = IDLE
        KS.scan_all()
        w.screen = PERMISSION
        with mock.patch.object(KS, "_notify"):
            KS.scan_all()
            KS.scan_all()
        self.assertEqual(w.bells, 1)
        done, _ = self.finish(worked=40)
        self.assertEqual(self.k.boss.window_id_map[1].bells, 0)

    def test_bell_is_silent_when_focused_or_switched_off(self):
        focused = FakeWindow(1, "claude", PERMISSION, focused=True)
        off = FakeWindow(2, "claude", PERMISSION)
        self.add(focused, off)
        with mock.patch.object(KS, "_notify"), mock.patch.dict(os.environ, {"KITTYMUX_BELL": "0"}):
            KS.scan_all()
        self.assertEqual((focused.bells, off.bells), (0, 0))

    def test_done_has_its_own_off_switch(self):
        w = FakeWindow(1, "claude", "")
        with mock.patch("kittymux_scan.subprocess.Popen") as popen, mock.patch("kittymux_scan.shutil.which", return_value="x"):
            with mock.patch.dict(os.environ, {"KITTYMUX_NOTIFY": "1", "KITTYMUX_NOTIFY_DONE": "0"}):
                KS._notify(w, "done", "")
                popen.assert_not_called()
                KS._notify(w, "waiting", "Approve?")
                popen.assert_called_once()

    def test_the_helper_gets_a_safe_argv(self):
        w = FakeWindow(7, "claude", "", title="-rf <b>x</b>")
        with mock.patch("kittymux_scan.subprocess.Popen") as popen, mock.patch("kittymux_scan.shutil.which", return_value="x"), \
                mock.patch.dict(os.environ, {"KITTYMUX_NOTIFY": "1"}):
            KS._notify(w, "done", "")
        argv = popen.call_args[0][0]
        self.assertTrue(argv[0].endswith("bin/mux-notify"))
        self.assertEqual(argv[2], "7")
        self.assertEqual(argv[4:6], ["low", "kittymux.done"])
        self.assertNotIn("<", argv[6])
        self.assertTrue(os.access(argv[0], os.X_OK))


class PromptTests(ScanBase):
    """A plain terminal waiting on you (sudo, ssh, pacman…) is announced like an agent that needs you; the verdict is untouched."""
    SUDO = "resolving dependencies...\n[sudo] password for someone-private: "

    def setUp(self):
        super().setUp()
        for attr in ("prompt", "prompt_seen", "unread", "prompt_on"):
            vars(KS._RT).pop(attr, None)
        self.job = ["sudo", "pacman", "-Syu"]
        self._fg = mock.patch.object(KS, "fg_job", side_effect=lambda w: (self.job, True) if self.job else ([], False))
        self._fg.start()

    def tearDown(self):
        self._fg.stop()
        super().tearDown()

    def events(self):
        return KS._inbox().load(self.state)

    def seen_then(self, w, text, *times):
        """Scan once on a quiet screen (so the window is no longer 'first sight'), then show `text` and scan at each time."""
        w.screen = "$ "
        KS.scan_prompt(w, 0.0)
        w.screen = text
        out = []
        with mock.patch.object(KS, "_notify", return_value="sent") as notify:
            for t in times:
                KS.scan_prompt(w, t)
                out.append(notify.call_count)
        return out

    def test_it_is_announced_once_after_it_has_stayed_a_moment(self):
        w = FakeWindow(1, None, "")
        self.add(w)
        counts = self.seen_then(w, self.SUDO, 0.5, 1.2, 2.0, 5.0)
        self.assertEqual(counts, [0, 0, 1, 1])
        ev = self.events()
        self.assertEqual([(e["kind"], e["agent"], e["severity"]) for e in ev], [("permission", "sudo", "needs-you")])

    def test_the_text_is_fixed_and_the_user_name_never_stored(self):
        w = FakeWindow(1, None, "")
        self.add(w)
        self.seen_then(w, self.SUDO, 1.0, 2.5)
        with open(KS._inbox().store_path(self.state)) as f:
            raw = json.dumps(self.events()) + f.read()
        self.assertNotIn("someone-private", raw)
        self.assertIn("sudo is asking for your password", raw)

    def test_a_prompt_answered_at_once_is_never_announced(self):
        w = FakeWindow(1, None, "")
        self.add(w)
        self.seen_then(w, self.SUDO, 0.4)
        w.screen = "$ "
        KS.scan_prompt(w, 0.6)
        self.assertEqual(self.events(), [])

    def test_it_clears_when_the_prompt_is_gone(self):
        w = FakeWindow(1, None, "")
        self.add(w)
        self.seen_then(w, self.SUDO, 1.0, 2.5)
        self.assertEqual(self.events()[0]["status"], "unread")
        w.screen = "installing...\n"
        KS.scan_prompt(w, 4.0)
        self.assertEqual(self.events()[0]["status"], "read")
        self.assertNotIn("1", vars(KS._RT)["prompt"])

    def test_a_wrong_password_asks_again_and_is_a_second_occurrence(self):
        w = FakeWindow(1, None, "")
        self.add(w)
        self.seen_then(w, self.SUDO, 1.0, 2.5)
        w.screen = "Sorry, try again.\n"
        KS.scan_prompt(w, 3.0)
        w.screen = self.SUDO
        with mock.patch.object(KS, "_notify", return_value="sent") as notify:
            KS.scan_prompt(w, 4.0)
            KS.scan_prompt(w, 5.5)
        self.assertEqual(notify.call_count, 1)

    def test_a_window_seen_for_the_first_time_never_announces(self):
        w = FakeWindow(1, None, self.SUDO)
        self.add(w)
        with mock.patch.object(KS, "_notify", return_value="sent") as notify:
            KS.scan_prompt(w, 0.0)
            KS.scan_prompt(w, 5.0)
        self.assertEqual(notify.call_count, 0)
        self.assertEqual(self.events(), [])

    def test_looking_at_it_acknowledges_it(self):
        w = FakeWindow(1, None, "", focused=True)
        self.add(w)
        self.seen_then(w, self.SUDO, 1.0, 2.5)
        self.assertEqual(self.events()[0]["status"], "read")

    def test_nothing_runs_in_the_foreground_means_nothing_to_look_at(self):
        w = FakeWindow(1, None, "")
        self.add(w)
        self.job = []
        w.screen = "$ "
        KS.scan_prompt(w, 0.0)
        w.screen = self.SUDO
        with mock.patch.object(KS, "as_text", create=True):
            KS.scan_prompt(w, 5.0)
        self.assertEqual(self.events(), [])

    def test_the_screen_is_not_read_unless_a_command_runs(self):
        w = FakeWindow(1, None, "")
        w.as_text = mock.Mock(return_value="$ ")
        self.add(w)
        self.job = []
        KS.scan_prompt(w, 0.0)
        KS.scan_prompt(w, 3.0)
        w.as_text.assert_not_called()

    def test_each_kind_has_its_own_switch(self):
        w = FakeWindow(1, None, "")
        self.add(w)
        open(os.path.join(self.state, "sudo-off"), "w").close()
        self.seen_then(w, self.SUDO, 1.0, 2.5, 3.5)
        self.assertEqual(self.events(), [])
        # ...while another kind still works
        self.job = ["paru", "-Syu"]
        vars(KS._RT).pop("prompt_on", None)
        w2 = FakeWindow(2, None, "")
        self.add(w2)
        self.seen_then(w2, ":: Proceed with installation? [Y/n] ", 1.0, 2.5)
        self.assertEqual([e["kind"] for e in self.events()], ["question"])

    def test_the_scan_loop_runs_it_for_plain_windows_only(self):
        plain, agent = FakeWindow(1, None, self.SUDO), FakeWindow(2, "claude", self.SUDO)
        self.add(plain, agent)
        with mock.patch.object(KS, "scan_prompt") as sp:
            KS.scan_all()
        self.assertEqual([c[0][0].id for c in sp.call_args_list], [1])

    def test_closed_windows_are_forgotten(self):
        w = FakeWindow(1, None, "")
        self.add(w)
        self.seen_then(w, self.SUDO, 1.0, 2.5)
        self.k.boss.all_windows.clear()
        KS.scan_all()
        self.assertEqual(vars(KS._RT)["prompt"], {})
        self.assertNotIn("1", vars(KS._RT)["prompt_seen"])

    def test_a_failing_screen_read_never_raises(self):
        w = FakeWindow(1, None, "")
        w.as_text = mock.Mock(side_effect=RuntimeError("boom"))
        self.add(w)
        KS.scan_prompt(w, 0.0)
        KS.scan_prompt(w, 3.0)


class LimitEpisodeTests(ScanBase):
    """A usage limit is an EPISODE with a reset time (t3code models it as a run state with resetAt): the verdict carries when it lifts,
    the state ends at that time even while the old message is still on screen, and one episode is announced once however often the
    pane flips between a retry and the message again (the live log showed limited⇄working five times in six minutes, a popup each)."""
    DAY = 1_790_000_000 - (1_790_000_000 % 86400)
    MSG = "You've hit your usage limit. Upgrade to Pro, or try again at 9:21 PM.\n› Ask Codex to do anything\n"
    RETRY = "• Working (1s • esc to interrupt)\n› Ask Codex to do anything\n"

    def setUp(self):
        super().setUp()
        self.wall = self.DAY + 21 * 3600            # 21:00, UTC offset 0
        self._w = mock.patch.object(KS, "_wall", side_effect=lambda: self.wall)
        self._z = mock.patch.object(KS, "_tz", return_value=0.0)
        self._w.start()
        self._z.start()

    def tearDown(self):
        self._w.stop()
        self._z.stop()
        super().tearDown()

    def verdict(self):
        return KS._RT.verdicts["1"]

    def test_the_verdict_says_when_the_limit_lifts(self):
        self.add(FakeWindow(1, "codex", self.MSG))
        KS.scan_all()
        self.assertEqual(self.verdict()["state"], "limited")
        self.assertEqual(self.verdict()["reset_at"], self.DAY + 21 * 3600 + 21 * 60)

    def test_after_the_reset_the_old_message_no_longer_counts(self):
        w = FakeWindow(1, "codex", self.MSG)
        self.add(w)
        KS.scan_all()
        self.wall = self.DAY + 21 * 3600 + 22 * 60            # 21:22
        KS.scan_all()
        self.assertEqual(self.verdict()["state"], "idle")
        self.assertIn("reset", self.verdict()["why"])
        self.assertEqual(self.verdict()["reset_at"], self.DAY + 21 * 3600 + 21 * 60)

    def test_a_fresh_message_with_a_later_time_is_limited_again(self):
        w = FakeWindow(1, "codex", self.MSG)
        self.add(w)
        KS.scan_all()
        self.wall = self.DAY + 21 * 3600 + 25 * 60
        KS.scan_all()
        self.assertEqual(self.verdict()["state"], "idle")
        w.screen = self.MSG.replace("9:21 PM", "11:40 PM")
        KS.scan_all()
        self.assertEqual(self.verdict()["state"], "limited")
        self.assertEqual(self.verdict()["reset_at"], self.DAY + 23 * 3600 + 40 * 60)

    def test_without_a_time_the_limit_stays_until_the_screen_changes(self):
        self.add(FakeWindow(1, "claude", "Claude usage limit reached.\n"))
        KS.scan_all()
        self.wall += 5 * 3600
        KS.scan_all()
        self.assertEqual(self.verdict()["state"], "limited")
        self.assertNotIn("reset_at", self.verdict())

    def test_a_relative_time_is_taken_once_per_message_not_pushed_back_every_scan(self):
        w = FakeWindow(1, "claude", "Claude usage limit reached. Resets in 2h 30m\n")
        self.add(w)
        KS.scan_all()
        first = self.verdict()["reset_at"]
        self.assertEqual(first, self.wall + 9000)
        for _ in range(5):
            self.wall += 600
            KS.scan_all()
        self.assertEqual(self.verdict()["reset_at"], first)
        self.assertEqual(self.verdict()["state"], "limited")
        self.wall = first + 5
        KS.scan_all()
        self.assertEqual(self.verdict()["state"], "idle")
        w.screen = "Claude usage limit reached. Resets in 1h 10m\n"           # a NEW message: limited again, with its own end
        KS.scan_all()
        self.assertEqual(self.verdict()["state"], "limited")
        self.assertEqual(self.verdict()["reset_at"], self.wall + 4200)

    def test_a_retry_that_hits_the_same_limit_is_not_announced_again(self):
        w = FakeWindow(1, "codex", self.RETRY)
        self.add(w)
        KS.scan_all()
        with mock.patch.object(KS, "_notify", return_value="sent") as notify:
            for screen in (self.MSG, self.RETRY, self.MSG, self.RETRY, self.MSG):
                w.screen = screen
                self.wall += 40
                KS.scan_all()
        self.assertEqual(notify.call_count, 1)
        self.assertEqual([e["kind"] for e in KS._inbox().load(self.state)], ["limit"])
        self.assertEqual(self.verdict()["state"], "limited")

    def test_a_different_episode_is_announced(self):
        w = FakeWindow(1, "codex", self.RETRY)
        self.add(w)
        KS.scan_all()
        with mock.patch.object(KS, "_notify", return_value="sent") as notify:
            w.screen = self.MSG
            KS.scan_all()
            w.screen = self.RETRY
            self.wall = self.DAY + 22 * 3600
            KS.scan_all()
            w.screen = self.MSG.replace("9:21 PM", "11:40 PM")
            KS.scan_all()
        self.assertEqual(notify.call_count, 2)

    def test_the_decision_log_says_why_it_stayed_quiet(self):
        w = FakeWindow(1, "codex", self.RETRY)
        self.add(w)
        KS.scan_all()
        with mock.patch.object(KS, "_notify", return_value="sent"):
            for screen in (self.MSG, self.RETRY, self.MSG):
                w.screen = screen
                self.wall += 30
                KS.scan_all()
        outcomes = [r.get("outcome", "") for r in vars(KS._RT).get("decisions", []) if r.get("kind") == "notify"]
        self.assertTrue(any("same usage-limit episode" in o for o in outcomes), outcomes)


class SocketLinkTests(ScanBase):
    """The compatibility link at /tmp/mykitty-<pid> (see kittymux_sockets): made once per kitty, never over anything, switchable."""

    def setUp(self):
        super().setUp()
        import socket as _s
        self.dir = tempfile.mkdtemp()
        self.run, self.legacy = os.path.join(self.dir, "run"), os.path.join(self.dir, "tmp")
        os.mkdir(self.run, 0o700)
        os.mkdir(self.legacy)
        self.path = os.path.join(self.run, "mykitty-4242")
        self.sock = _s.socket(_s.AF_UNIX)
        self.sock.bind(self.path)
        self.k.boss.listening_on = "unix:" + self.path
        vars(KS._RT).pop("socklink_done", None)
        self._env2 = mock.patch.dict(os.environ, {"KITTYMUX_LEGACY_SOCKET_DIR": self.legacy})
        self._env2.start()

    def tearDown(self):
        self._env2.stop()
        self.sock.close()
        super().tearDown()

    def link(self):
        return os.path.join(self.legacy, "mykitty-4242")

    def test_starting_the_scanner_links_the_old_path_once(self):
        KS.ensure_started()
        self.assertEqual(os.readlink(self.link()), self.path)
        os.unlink(self.link())
        KS.ensure_started()                                   # the bar calls this on every draw: it must not redo the work
        self.assertFalse(os.path.lexists(self.link()))
        KS.restart()                                          # a config reload does: that re-checks
        self.assertEqual(os.readlink(self.link()), self.path)

    def test_the_decision_log_says_what_happened(self):
        KS.ensure_started()
        rows = [r for r in vars(KS._RT).get("decisions", []) if r.get("kind") == "socketlink"]
        self.assertEqual([r["outcome"] for r in rows], ["linked"])

    def test_the_switch_turns_it_off(self):
        open(os.path.join(self.state, "socketlink-off"), "w").close()
        KS.ensure_started()
        self.assertEqual(os.listdir(self.legacy), [])

    def test_a_kitty_that_is_not_listening_is_left_alone_and_asked_again_later(self):
        self.k.boss.listening_on = ""
        KS.ensure_started()
        self.assertEqual(os.listdir(self.legacy), [])
        self.assertNotIn("socklink_done", vars(KS._RT))
        self.k.boss.listening_on = "unix:" + self.path
        KS.scan_all()                                         # the scanner's own tick retries: the bar does not call ensure_started again
        self.assertTrue(os.path.islink(self.link()))

    def test_links_of_kitties_that_exited_are_removed(self):
        dead = "mykitty-2000000000"
        os.symlink(os.path.join(self.run, dead), os.path.join(self.legacy, dead))
        KS.ensure_started()
        self.assertEqual(sorted(os.listdir(self.legacy)), ["mykitty-4242"])

    def test_a_private_test_kitty_leaves_the_real_tmp_alone(self):
        del os.environ["KITTYMUX_LEGACY_SOCKET_DIR"]
        with mock.patch.object(KS.os, "getuid", return_value=987654):
            KS.ensure_started()
        self.assertEqual(os.listdir(self.legacy), [])
        rows = [r["outcome"] for r in vars(KS._RT).get("decisions", []) if r.get("kind") == "socketlink"]
        self.assertTrue(rows and rows[-1].startswith("not needed"), rows)


class InboxIntegrationTests(ScanBase):
    def inbox(self):
        return KS._inbox().load(self.state)

    def test_a_needs_you_prompt_becomes_one_typed_event_and_one_popup(self):
        w = FakeWindow(1, "claude", IDLE)
        self.add(w)
        KS.scan_all()
        w.screen = PERMISSION
        with mock.patch.object(KS, "_notify", return_value="sent") as notify:
            KS.scan_all()
            KS.scan_all()
        ev = self.inbox()
        self.assertEqual([(e["kind"], e["severity"], e["agent"]) for e in ev], [("permission", "needs-you", "claude")])
        self.assertEqual(notify.call_count, 1)

    def test_the_agents_own_notification_and_the_screen_scan_are_one_occurrence(self):
        w = FakeWindow(1, "claude", IDLE)
        self.add(w)
        KS.scan_all()
        cmd = types.SimpleNamespace(channel_id=1, title="Claude Code", body="Claude needs your permission to use Bash", urgency=None)
        with mock.patch.object(KS, "_notify", return_value="sent") as notify, mock.patch.dict(sys.modules, {}):
            self.k.boss.window_id_map[1] = w
            KS._on_agent_notification(cmd)                       # the agent said it first…
            w.screen = PERMISSION
            KS.scan_all()                                        # …then the scan saw the same prompt
        ev = self.inbox()
        self.assertEqual(len(ev), 1)
        self.assertEqual(sorted(ev[0]["sources"]), ["agent", "screen"])
        self.assertEqual(notify.call_count, 1)                   # one popup for one occurrence, not one per source

    def test_a_usage_limit_carries_its_reset_time_and_a_repeat_in_another_window_is_merged(self):
        a, b = FakeWindow(1, "codex", IDLE), FakeWindow(2, "codex", IDLE)
        self.add(a, b)
        KS.scan_all()
        with mock.patch.object(KS, "_notify", return_value="sent") as notify:
            for w in (a, b):
                self.k.boss.window_id_map[w.id] = w
                KS._on_agent_notification(types.SimpleNamespace(channel_id=w.id, title="Codex", urgency=None,
                                                                body="You've hit your usage limit. Resets in 2h 30m"))
        ev = self.inbox()
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["kind"], "limit")
        self.assertAlmostEqual(ev[0]["reset_at"] - ev[0]["t"], 2.5 * 3600, delta=5)
        self.assertEqual(notify.call_count, 1)

    def test_the_idle_notice_is_kept_in_the_inbox_but_is_not_an_event_to_act_on(self):
        w = FakeWindow(1, "claude", IDLE)
        self.add(w)
        KS.scan_all()
        self.k.boss.window_id_map[1] = w
        with mock.patch.object(KS, "_notify") as notify:
            KS._on_agent_notification(types.SimpleNamespace(channel_id=1, title="Claude Code", body="Claude is waiting for your input", urgency=None))
        notify.assert_not_called()
        self.assertEqual([(e["kind"], e.get("tag")) for e in self.inbox()], [("info", "idle-notice")])

    def test_an_agent_announced_completion_acts_like_a_stop_hook(self):
        w = FakeWindow(1, "codex", IDLE)
        self.add(w)
        KS.scan_all()
        self.k.boss.window_id_map[1] = w
        with mock.patch.object(KS, "_notify", return_value="sent"):
            KS._on_agent_notification(types.SimpleNamespace(channel_id=1, title="Codex", body="Agent turn complete", urgency=None))
            KS.scan_all()
        self.assertEqual(KS._RT.verdicts["1"]["state"], "done")
        self.assertIn("Stop hook", KS._RT.verdicts["1"]["why"])

    def test_notifications_from_non_agent_windows_are_ignored(self):
        w = FakeWindow(1, None, "$ ")
        self.add(w)
        KS.scan_all()
        self.k.boss.window_id_map[1] = w
        KS._on_agent_notification(types.SimpleNamespace(channel_id=1, title="Build", body="Task finished", urgency=None))
        self.assertEqual(self.inbox(), [])

    def test_focusing_the_window_acknowledges_what_it_reported(self):
        w = FakeWindow(1, "claude", IDLE)
        self.add(w)
        KS.scan_all()
        w.screen = PERMISSION
        with mock.patch.object(KS, "_notify", return_value="sent"):
            KS.scan_all()
        self.assertEqual([e["status"] for e in self.inbox()], ["unread"])
        w.is_focused = True
        KS.scan_all()
        self.assertEqual([e["status"] for e in self.inbox()], ["read"])

    def test_private_mode_keeps_the_agents_words_out_of_the_inbox(self):
        w = FakeWindow(1, "claude", IDLE)
        self.add(w)
        KS.scan_all()
        self.k.boss.window_id_map[1] = w
        with mock.patch.object(KS, "_notify", return_value="sent"), mock.patch.dict(os.environ, {"KITTYMUX_NOTIFY_PRIVATE": "1"}):
            KS._on_agent_notification(types.SimpleNamespace(channel_id=1, title="Claude Code", body="Allow `rm -rf ~/secret`?", urgency=None))
        self.assertEqual(self.inbox()[0]["body"], "")

    def test_the_tap_wrapper_never_raises_and_always_delegates(self):
        calls = []

        class NM:
            def is_notification_filtered(self, cmd):
                calls.append(cmd)
                return True

        mod = types.ModuleType("kitty.notifications")
        mod.NotificationManager = NM
        with mock.patch.dict(sys.modules, {"kitty.notifications": mod}), mock.patch.object(KS, "_on_agent_notification", side_effect=RuntimeError("boom")):
            KS._install_notification_tap()
            KS._install_notification_tap()                       # idempotent
            self.assertTrue(NM().is_notification_filtered("cmd"))
        self.assertEqual(calls, ["cmd"])


class AttentionTests(ScanBase):
    """A bell asks the window manager for attention; where the compositor answers that by FOCUSING the window it is a focus steal."""

    def test_no_bell_when_the_compositor_would_turn_it_into_a_focus_steal(self):
        w = FakeWindow(1, "claude", IDLE)
        with mock.patch("kittymux_layout.hypr_focus_on_activate", return_value=True):
            self.assertIn("steal focus", KS._alert(w))
        self.assertEqual(w.bells, 0)

    def test_the_bell_rings_when_it_is_safe_and_is_rate_limited(self):
        w = FakeWindow(1, "claude", IDLE)
        self.assertEqual(KS._alert(w), "rang")
        self.assertTrue(KS._alert(w).startswith("skipped: this window rang less than"))
        self.assertEqual(w.bells, 1)

    def test_the_user_can_force_it_and_a_focused_window_never_rings(self):
        w = FakeWindow(1, "claude", IDLE)
        open(os.path.join(self.state, "attention-on"), "w").close()
        with mock.patch("kittymux_layout.hypr_focus_on_activate", return_value=True):
            self.assertEqual(KS._alert(w), "rang")
        f = FakeWindow(2, "claude", IDLE, focused=True)
        self.assertEqual(KS._alert(f), "skipped: you are looking at it")

    def test_the_decision_is_recorded_with_its_reason(self):
        w = FakeWindow(1, "claude", IDLE)
        self.add(w)
        KS.scan_all()
        w.screen = PERMISSION
        with mock.patch("kittymux_layout.hypr_focus_on_activate", return_value=True), mock.patch.object(KS, "_notify", return_value="sent"):
            KS.scan_all()
        att = [e for e in vars(KS._RT)["decisions"] if e["kind"] == "attention"]
        self.assertEqual(len(att), 1)
        self.assertIn("focus_on_activate", att[0]["outcome"])
        self.assertEqual(w.bells, 0)


class ChangesHookTests(ScanBase):
    """Runs starting and ending trigger the detached checkpoint helper — never on first sight, never in a flood."""

    def setUp(self):
        super().setUp()
        vars(KS._RT).pop("changes", None)
        self.popen = mock.patch("kittymux_scan.subprocess.Popen")
        self.pm = self.popen.start()
        self.pm.return_value.poll.return_value = None                      # "still running"
        self.env4 = mock.patch.dict(os.environ, {"KITTYMUX_CHANGES": "1"})
        self.env4.start()
        self.w = FakeWindow(1, "claude", IDLE)
        self.w.cwd_of_child = "/work/repo"
        self.add(self.w)

    def tearDown(self):
        self.env4.stop()
        self.popen.stop()
        super().tearDown()

    def kinds(self):
        return [c.args[0][c.args[0].index("checkpoint") + 1] for c in self.pm.call_args_list if "checkpoint" in c.args[0]]

    def test_a_run_starting_and_ending_start_and_finish_a_checkpoint(self):
        t = [1000.0]
        with mock.patch.object(KS.time, "monotonic", lambda: t[0]):
            KS.scan_all()                                                  # first sight: idle
            self.w.screen = WORKING
            KS.scan_all()
            self.assertEqual(self.kinds(), ["start"])
            self.w.screen = IDLE
            t[0] += 10
            KS.scan_all()
            KS.scan_all()
        self.assertEqual(self.kinds(), ["start", "finish"])
        argv = self.pm.call_args_list[0].args[0]
        self.assertEqual(argv[argv.index("--cwd") + 1], "/work/repo")
        self.assertEqual(argv[argv.index("--window") + 1], "1")
        self.assertEqual(argv[argv.index("--pid") + 1], str(os.getpid()))
        self.assertEqual(self.pm.call_args_list[0].kwargs["start_new_session"], True)

    def test_first_sight_of_a_window_that_is_already_working_starts_nothing(self):
        self.w.screen = WORKING
        KS.scan_all()
        self.assertEqual(self.kinds(), [])                                 # we did not see the run begin: the summary will compare with HEAD

    def test_a_waiting_run_that_resumes_is_not_a_new_run(self):
        t = [1000.0]
        with mock.patch.object(KS.time, "monotonic", lambda: t[0]):
            KS.scan_all()
            self.w.screen = WORKING
            KS.scan_all()
            self.w.screen = PERMISSION
            t[0] += 10
            KS.scan_all()                                                  # working → waiting: the summary so far
            self.w.screen = WORKING
            t[0] += 10
            KS.scan_all()                                                  # waiting → working: the SAME run (no second baseline)
        self.assertEqual(self.kinds(), ["start", "finish"])

    def test_off_switches_missing_directory_and_the_concurrency_and_gap_limits(self):
        with mock.patch.dict(os.environ, {"KITTYMUX_CHANGES": "0"}):
            self.assertEqual(KS._checkpoint(self.w, "start", 1.0), "off")
        open(os.path.join(self.state, "changes-off"), "w").close()
        self.assertEqual(KS._checkpoint(self.w, "start", 1.0), "off")
        os.unlink(os.path.join(self.state, "changes-off"))
        self.w.cwd_of_child = ""
        self.assertEqual(KS._checkpoint(self.w, "start", 1.0), "no directory")
        self.w.cwd_of_child = "/work/repo"
        self.assertEqual(KS._checkpoint(self.w, "start", 100.0), "started start")
        self.assertEqual(KS._checkpoint(self.w, "start", 101.0), "too soon")        # the same (window, kind) inside the gap
        self.assertEqual(KS._checkpoint(self.w, "finish", 101.0), "started finish")
        other = FakeWindow(2, "claude", IDLE)
        other.cwd_of_child = "/w2"
        self.assertEqual(KS._checkpoint(other, "start", 102.0), "busy")             # two helpers already running

    def test_a_failing_spawn_never_breaks_the_scan(self):
        self.pm.side_effect = OSError("no fork")
        self.assertEqual(KS._checkpoint(self.w, "start", 1.0), "error")


class AgeRefreshTests(ScanBase):
    """A tab showing "waiting 5m" must be redrawn now and then, or the minutes never tick."""

    def setUp(self):
        super().setUp()
        vars(KS._RT).pop("age_refresh", None)
        self.redraws = []
        self.tm = object()
        self.p1 = mock.patch.object(KS, "_tab_manager", lambda w: self.tm)
        self.p2 = mock.patch.object(KS, "refresh_bar", lambda tm: self.redraws.append(tm))
        self.p1.start()
        self.p2.start()

    def tearDown(self):
        self.p2.stop()
        self.p1.stop()
        super().tearDown()

    def test_a_waiting_tab_is_redrawn_every_age_refresh_even_when_nothing_changed(self):
        w = FakeWindow(1, "claude", IDLE)
        self.add(w)
        t = [1000.0]
        with mock.patch.object(KS.time, "monotonic", lambda: t[0]):
            KS.scan_all()
            w.screen = PERMISSION
            KS.scan_all()                                           # the change itself: a redraw
            n = len(self.redraws)
            t[0] += 5
            KS.scan_all()
            self.assertEqual(len(self.redraws), n)                  # quiet, inside the interval: no redraw
            t[0] += KS.AGE_REFRESH
            KS.scan_all()
            self.assertEqual(len(self.redraws), n + 1)              # the interval passed: one redraw so "5m" can become "6m"

    def test_an_idle_tab_never_triggers_age_redraws(self):
        self.add(FakeWindow(1, "claude", IDLE))
        t = [1000.0]
        with mock.patch.object(KS.time, "monotonic", lambda: t[0]):
            KS.scan_all()
            n = len(self.redraws)
            for _ in range(5):
                t[0] += KS.AGE_REFRESH + 1
                KS.scan_all()
        self.assertEqual(len(self.redraws), n)


class QuietTests(ScanBase):
    """`kittymux notify mute` and `kittymux snooze`: quiet the interruption, never lose the news."""

    def setUp(self):
        super().setUp()
        self.w = FakeWindow(1, "claude", "")
        self.w.user_vars = {}
        self.popen = mock.patch("kittymux_scan.subprocess.Popen")
        self.popen_mock = self.popen.start()
        self.which = mock.patch("kittymux_scan.shutil.which", return_value="x")
        self.which.start()
        self.env3 = mock.patch.dict(os.environ, {"KITTYMUX_NOTIFY": "1"})                 # ScanBase switches popups off; these tests are about WHY they are held back
        self.env3.start()
        vars(KS._RT).pop("notify_log", None)
        KS._RT.notified.clear()

    def tearDown(self):
        self.env3.stop()
        self.which.stop()
        self.popen.stop()
        super().tearDown()

    def mute(self, seconds):
        with open(os.path.join(self.state, "notify-mute-until"), "w") as f:
            f.write(str(time.time() + seconds))

    def test_a_global_mute_holds_back_the_popup_with_a_reason_until_it_expires(self):
        self.mute(600)
        self.assertEqual(KS._notify(self.w, "waiting", "q"), "suppressed: muted (kittymux notify unmute); the event is in the inbox")
        self.popen_mock.assert_not_called()
        self.mute(-1)                                                                  # expired
        self.assertEqual(KS._notify(self.w, "waiting", "q"), "sent")

    def test_a_snoozed_window_is_quiet_and_only_that_window(self):
        import kittymux_quiet
        kittymux_quiet.set_snooze(self.state, os.getpid(), 1, 600)
        other = FakeWindow(2, "claude", "")
        self.assertTrue(KS._notify(self.w, "waiting", "q").startswith("suppressed: this window is snoozed"))
        self.assertEqual(KS._notify(other, "waiting", "q"), "sent")
        kittymux_quiet.clear_snooze(self.state, os.getpid(), 1)
        self.assertEqual(KS._notify(self.w, "waiting", "q"), "sent")

    def test_the_windows_own_user_variable_is_not_a_snooze(self):
        self.w.user_vars = {"kittymux_snooze_until": str(time.time() + 600)}          # any program can set this itself: it must not silence its own popup
        self.assertEqual(KS._notify(self.w, "waiting", "q"), "sent")

    def test_the_bell_is_skipped_too(self):
        self.mute(600)
        self.assertTrue(KS._alert(self.w).startswith("skipped: muted"))
        self.assertEqual(self.w.bells, 0)

    def test_a_muted_event_is_still_in_the_inbox(self):
        self.add(self.w)
        self.mute(600)
        KS.scan_all()
        self.w.screen = PERMISSION
        KS.scan_all()
        ev = KS._inbox().load(self.state)
        self.assertEqual([(e["kind"], e["severity"]) for e in ev], [("permission", "needs-you")])
        self.popen_mock.assert_not_called()                                              # nothing popped up, nothing lost


class AutosaveTests(ScanBase):
    def setUp(self):
        super().setUp()
        vars(KS._RT).pop("autosave", None)
        self.k.boss.listening_on = "unix:/tmp/mykitty-9"
        self.popen = mock.patch.object(KS.subprocess, "Popen")
        self.popen_mock = self.popen.start()

    def tearDown(self):
        self.popen.stop()
        super().tearDown()

    def test_the_first_look_is_a_baseline_not_a_save(self):
        self.assertEqual(KS._maybe_autosave(1000.0, [1, 2]), "baseline")
        self.popen_mock.assert_not_called()

    def test_a_change_saves_once_it_has_settled_and_only_once(self):
        KS._maybe_autosave(1000.0, [1, 2])
        self.assertEqual(KS._maybe_autosave(1010.0, [1, 2, 3]), "idle")                    # a new window: wait for it to settle
        self.assertEqual(KS._maybe_autosave(1015.0, [1, 2, 3]), "idle")
        self.assertEqual(KS._maybe_autosave(1070.0, [1, 2, 3]), "started")                  # settled AND the minimum gap has passed
        argv = self.popen_mock.call_args[0][0]
        self.assertEqual(argv[-2:], ["sessions", "autosave"])
        self.assertEqual(self.popen_mock.call_args[1]["env"]["KITTYMUX_TARGET"], "unix:/tmp/mykitty-9")
        self.assertEqual(KS._maybe_autosave(1080.0, [1, 2, 3]), "idle")
        self.assertEqual(self.popen_mock.call_count, 1)

    def test_rapid_changes_are_debounced_into_one_save(self):
        KS._maybe_autosave(1000.0, [1])
        for i, t in enumerate(range(1010, 1060, 5)):                                          # a window opens every 5 s for 50 s
            KS._maybe_autosave(float(t), list(range(i + 2)))
        self.assertEqual(self.popen_mock.call_count, 0)                                       # never stable for 20 s yet
        self.assertEqual(KS._maybe_autosave(1085.0, list(range(11))), "started")          # the set has been stable since 1055

    def test_a_periodic_save_catches_cwd_and_agent_drift(self):
        KS._maybe_autosave(1000.0, [1, 2])
        self.assertEqual(KS._maybe_autosave(1000.0 + KS.AUTOSAVE_PERIOD + 1, [1, 2]), "started")

    def test_off_switches_and_no_windows(self):
        KS._maybe_autosave(1000.0, [1])
        with mock.patch.dict(os.environ, {"KITTYMUX_AUTOSAVE": "0"}):
            self.assertEqual(KS._maybe_autosave(1000.0 + KS.AUTOSAVE_PERIOD + 1, [1]), "idle")
        open(os.path.join(self.state, "autosave-off"), "w").close()
        self.assertEqual(KS._maybe_autosave(1000.0 + 2 * KS.AUTOSAVE_PERIOD + 2, [1]), "idle")
        os.unlink(os.path.join(self.state, "autosave-off"))
        self.assertEqual(KS._maybe_autosave(1000.0 + 3 * KS.AUTOSAVE_PERIOD + 3, []), "idle")   # nothing to save

    def test_a_missing_socket_never_raises(self):
        KS._maybe_autosave(1000.0, [1])
        self.k.boss.listening_on = ""
        self.assertEqual(KS._maybe_autosave(1000.0 + KS.AUTOSAVE_PERIOD + 1, [1]), "no socket")


class JournalIntegrationTests(ScanBase):
    SID = "0a1b2c3d-0000-4000-8000-000000000001"

    def setUp(self):
        super().setUp()
        self.claude = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.claude, "sessions"))
        with open(os.path.join(self.claude, "sessions", "424242.json"), "w") as f:
            json.dump({"pid": 424242, "sessionId": self.SID, "cwd": "/w/a"}, f)
        self._env2 = mock.patch.dict(os.environ, {"KITTYMUX_CLAUDE_HOME": self.claude})
        self._env2.start()

    def tearDown(self):
        self._env2.stop()
        super().tearDown()

    def agent_window(self, wid=1, screen="idle", cmdline=("claude", "--model", "x")):
        w = FakeWindow(wid, "claude", screen)
        w.child = types.SimpleNamespace(child_fd=None, foreground_processes=[{"pid": 424242, "cmdline": list(cmdline)}])
        w.cwd_of_child = "/w/a"
        self.add(w)
        return w

    def records(self):
        import kittymux_journal as J
        return J.load(self.state)

    def test_an_agent_window_is_journaled_with_its_session_id_command_and_cwd(self):
        w = self.agent_window()
        KS.scan_window(w, 1.0)
        KS._journal_tick(self.k.boss, {"1"}, 1000.0)
        rec = self.records()["claude:" + self.SID]
        self.assertEqual((rec["cwd"], rec["argv"], rec["kitty_pid"], rec["wid"]), ("/w/a", ["claude", "--model", "x"], os.getpid(), 1))

    def test_state_changes_feed_turns_and_working_time(self):
        w = self.agent_window(screen="")
        KS.scan_window(w, 1.0)
        rec = lambda: KS._journal_rt()["recs"]["claude:" + self.SID]
        with mock.patch.object(KS.time, "time", return_value=1000.0):
            KS._journal_note(w, "working")
        with mock.patch.object(KS.time, "time", return_value=1090.0):
            KS._journal_note(w, "done")
        self.assertEqual((rec()["turns"], rec()["work_s"]), (1, 90))

    def test_agent_exit_in_a_live_window_closes_its_journal_record(self):
        w = self.agent_window()
        KS.scan_window(w, 1.0)
        KS._journal_tick(self.k.boss, {"1"}, 1000.0)
        with mock.patch.object(KS, "agent_of", return_value=None):
            KS.scan_window(w, 2.0)
        KS._journal_tick(self.k.boss, {"1"}, 1010.0)
        rec = self.records()["claude:" + self.SID]
        self.assertFalse(rec["open"])
        import kittymux_journal as J
        self.assertFalse(J.is_running(rec))
        self.assertTrue(J.recoverable(J.entries({"session": rec}, 1020.0, 3600.0)))

    def test_transient_resume_identification_miss_keeps_a_live_agent_key(self):
        w = self.agent_window()
        KS.scan_window(w, 1.0)
        key = KS._journal_rt()["keys"]["1"]
        with mock.patch("kittymux_resume.identify", return_value=None):
            KS._journal_note(w, "idle", 1000.0)
        self.assertEqual(KS._journal_rt()["keys"]["1"], key)

    def test_a_closed_window_is_marked_closed_and_the_file_survives(self):
        w = self.agent_window()
        KS.scan_window(w, 1.0)
        KS._journal_tick(self.k.boss, {"1"}, 1000.0)
        self.k.boss.all_windows.clear()
        KS._journal_tick(self.k.boss, set(), 1010.0)
        self.assertFalse(self.records()["claude:" + self.SID]["open"])

    def test_writes_are_coalesced(self):
        w = self.agent_window()
        KS.scan_window(w, 1.0)
        with mock.patch("kittymux_journal.flush", return_value=True) as flush:
            for t in (1000.0, 1001.0, 1002.0, 1003.0):
                KS._journal_note(w, "working" if t % 2 else "idle", t)
                KS._journal_tick(self.k.boss, {"1"}, t)
            self.assertEqual(flush.call_count, 1)                                         # JOURNAL_FLUSH_GAP
            KS._journal_note(w, "done", 1010.0)
            KS._journal_tick(self.k.boss, {"1"}, 1010.0)
            self.assertEqual(flush.call_count, 2)

    def test_a_quiet_running_agents_last_seen_still_reaches_disk(self):
        w = self.agent_window()
        KS.scan_window(w, 1.0)
        KS._RT.verdicts["1"]["agent"] = "claude"
        KS._journal_tick(self.k.boss, {"1"}, 1000.0)
        first = self.records()["claude:" + self.SID]["last"]
        KS._journal_tick(self.k.boss, {"1"}, 1030.0)                                   # inside the heartbeat: nothing to write
        self.assertEqual(self.records()["claude:" + self.SID]["last"], first)
        KS._journal_tick(self.k.boss, {"1"}, 1100.0)                                   # a beat later, with no state change at all
        self.assertEqual(self.records()["claude:" + self.SID]["last"], 1100)

    def test_off_switch_records_nothing_and_a_non_agent_window_is_ignored(self):
        w = self.agent_window()
        with mock.patch.dict(os.environ, {"KITTYMUX_JOURNAL": "0"}):
            KS.scan_window(w, 1.0)
            KS._journal_tick(self.k.boss, {"1"}, 1000.0)
        self.assertEqual(self.records(), {})

    def test_a_window_without_an_agent_process_is_ignored(self):
        plain = FakeWindow(2, "claude", "")
        plain.child = types.SimpleNamespace(child_fd=None, foreground_processes=[{"pid": 5, "cmdline": ["zsh"]}])
        self.add(plain)
        KS.scan_window(plain, 1.0)
        KS._journal_tick(self.k.boss, {"2"}, 2000.0)
        self.assertEqual(self.records(), {})

    def test_a_failing_journal_never_breaks_the_scan(self):
        w = self.agent_window()
        with mock.patch("kittymux_journal.observe", side_effect=RuntimeError("boom")):
            KS.scan_window(w, 1.0)
            KS._journal_tick(self.k.boss, {"1"}, 1000.0)


class FalseCompletionTests(ScanBase):
    """Codex 'finished' notifications while it was still working."""

    def run_screens(self, steps, hook=None, agent="codex"):
        """steps: [(seconds_from_start, screen_text)] → how many 'done' notifications fired."""
        w = FakeWindow(1, agent, steps[0][1])
        self.add(w)
        if hook is not None:
            with open(KS._panes_path(), "w") as f:
                json.dump({"1": hook}, f)
        with mock.patch.object(KS, "_notify") as notify:
            for t, text in steps:
                w.screen = text
                with mock.patch.object(KS.time, "monotonic", return_value=1000.0 + t):
                    KS.scan_all()
        return [c for c in notify.call_args_list if c[0][1] == "done"]

    WORKING = "• Working (20s • esc to interrupt)\n› \n"

    def test_a_blink_of_the_working_line_is_not_a_completion(self):
        steps = [(0, self.WORKING), (20, self.WORKING), (20.5, IDLE), (23, IDLE), (24, self.WORKING), (30, self.WORKING)]
        self.assertEqual(self.run_screens(steps), [])

    def test_staying_idle_is_a_completion_and_notifies_once(self):
        steps = [(0, self.WORKING), (80, self.WORKING)] + [(82 + i, IDLE) for i in range(0, 14)]      # a long run, then it stays quiet
        self.assertEqual(len(self.run_screens(steps)), 1)

    def test_a_stop_hook_makes_a_finish_authoritative_so_20_seconds_is_enough(self):
        w = FakeWindow(1, "claude", self.WORKING)
        self.add(w)
        panes = {"1": {"status": "working", "ts_status": 1000.0}}
        with mock.patch.object(KS, "_notify") as notify, mock.patch.object(KS, "_panes", return_value=panes):
            for t, text in ((0, self.WORKING), (20, self.WORKING)):
                w.screen = text
                with mock.patch.object(KS.time, "monotonic", return_value=1000.0 + t):
                    KS.scan_all()
            w.screen = IDLE
            panes["1"] = {"status": "done", "ts_status": 1021.0}                 # the agent's Stop hook
            for t in (21, 23, 29):
                with mock.patch.object(KS.time, "monotonic", return_value=1000.0 + t):
                    KS.scan_all()
        done = [c for c in notify.call_args_list if c[0][1] == "done"]
        self.assertEqual(len(done), 1)
        ev = [e for e in KS._inbox().load(self.state) if e["kind"] == "done"][0]
        self.assertEqual((ev["confidence"], ev["sources"]), ("high", ["agent"]))

    def test_a_leftover_hook_status_does_not_turn_a_gap_into_a_completion(self):
        # a window user var from a previous agent: waiting, hours old, no message
        old_hook = {"status": "waiting", "msg": "", "ts_status": 1.0}
        self.assertEqual(self.run_screens([(0, IDLE), (3, IDLE), (12, IDLE), (20, IDLE)], hook=old_hook), [])
        self.assertEqual(KS._RT.verdicts["1"]["state"], "idle")

    def test_the_title_in_a_notification_has_no_spinner_or_agent_prefix(self):
        w = FakeWindow(4, "codex", "", title="⠸ Codex: Review promotion and reader PRs | kitsu-lab")
        with mock.patch.dict(os.environ, {"KITTYMUX_NOTIFY": "1"}), mock.patch.object(KS.shutil, "which", return_value="x"), \
                mock.patch.object(KS.subprocess, "Popen") as popen:
            KS._notify(w, "done", "", "codex")
        self.assertEqual(popen.call_args[0][0][7], "Review promotion and reader PRs | kitsu-lab finished")


if __name__ == "__main__":
    unittest.main()


class ClosedEventsTests(unittest.TestCase):
    """A vanished tab leaves no record in kitty. The scanner's `closed` decisions are the evidence: which agent, what it was doing, and how many went together."""

    def seen(self):
        return {"2": {"agent": "devin", "state": "working", "tab": 5, "last": 100.0},
                "6": {"agent": "codex", "state": "working", "tab": 5, "last": 100.0},
                "9": {"agent": "claude", "state": "idle", "tab": 7, "last": 100.0}}

    def test_a_tab_closing_is_two_events_that_know_they_went_together(self):
        seen = self.seen()
        evs = KS.closed_events(seen, {"9"}, 101.5)
        self.assertEqual({e["w"] for e in evs}, {"2", "6"})
        for e in evs:
            self.assertEqual((e["together"], e["same_tab"], e["last_state"], e["seen_ago"]), (2, 2, "working", 1.5))
        self.assertEqual(set(seen), {"9"}, "closed windows are forgotten, live ones kept")

    def test_one_agent_quitting_alone_is_one_event(self):
        evs = KS.closed_events(self.seen(), {"2", "6"}, 101.0)
        self.assertEqual([(e["agent"], e["together"], e["same_tab"]) for e in evs], [("claude", 1, 1)])

    def test_nothing_closed_nothing_said_and_a_second_call_is_quiet(self):
        seen = self.seen()
        self.assertEqual(KS.closed_events(seen, {"2", "6", "9"}, 101.0), [])
        KS.closed_events(seen, set(), 101.0)
        self.assertEqual(KS.closed_events(seen, set(), 102.0), [])
