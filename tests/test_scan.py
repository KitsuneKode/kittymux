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
        self.agent = mock.patch.object(KS, "agent_of", side_effect=lambda w: w.agent)
        self.agent.start()

    def tearDown(self):
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
        data = json.load(open(KS.scan_path()))
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

    def test_a_long_run_that_finishes_unseen_notifies(self):
        notify, state = self.finish(worked=40)
        self.assertEqual(state, "done")
        notify.assert_called_once()
        self.assertEqual(notify.call_args[0][1], "done")

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
        steps = [(0, self.WORKING), (20, self.WORKING)] + [(22 + i, IDLE) for i in range(0, 14)]
        self.assertEqual(len(self.run_screens(steps)), 1)

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
