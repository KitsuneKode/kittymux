import json
import importlib.machinery
import importlib.util
import os
import types
import re
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load():
    path = os.path.join(ROOT, "bin", "kittymux")
    loader = importlib.machinery.SourceFileLoader("kittymux_cli", path)
    spec = importlib.util.spec_from_loader("kittymux_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


TPL = """\
map ctrl+alt+u launch x
map ctrl+alt+shift+left move_tab_backward
map ctrl+alt+comma launch y
map ctrl+alt+n new_os_window
map shift+left launch z
"""


class ConflictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def test_exact_chord_conflicts(self):
        binds = [{"modmask": 12, "key": "U"}]                       # ctrl+alt+u
        self.assertEqual(self.m.conflicts_from_binds(binds, TPL), ["ctrl+alt+u"])

    def test_super_chord_is_not_a_conflict(self):
        binds = [{"modmask": 76, "key": "U"}, {"modmask": 77, "key": "Left"}]   # super+ctrl+alt(+shift)
        self.assertEqual(self.m.conflicts_from_binds(binds, TPL), [])

    def test_numlock_bits_ignored(self):
        binds = [{"modmask": 12 | 16, "key": "n"}]
        self.assertEqual(self.m.conflicts_from_binds(binds, TPL), ["ctrl+alt+n"])

    def test_shift_distinguished(self):
        binds = [{"modmask": 12, "key": "Left"}]                     # ctrl+alt+left, not +shift
        self.assertEqual(self.m.conflicts_from_binds(binds, TPL), [])
        binds = [{"modmask": 13, "key": "Left"}]
        self.assertEqual(self.m.conflicts_from_binds(binds, TPL), ["ctrl+alt+shift+left"])

    def test_named_keys(self):
        self.assertEqual(self.m.conflicts_from_binds([{"modmask": 12, "key": ","}], TPL), ["ctrl+alt+comma"])

    def test_template_avoids_the_keys_hyprland_takes_with_ctrl_alt(self):
        # What this user's Hyprland (HyDE, scrolling layout) binds on exactly ctrl+alt. The WM sees a global chord first, so a
        # kittymux map on one of these never fires (or fires twice). `kittymux doctor` checks the live binds; this pins the
        # template so a new key cannot be added on top of a known one (ctrl+alt+p once was: it is `layoutmsg promote`).
        reserved = "a s f c x p w m left right up down equal minus".split()
        tpl = open(os.path.join(ROOT, "kittymux-keys.conf.tpl"), encoding="utf-8").read()
        tpl = "\n".join(l for l in tpl.splitlines() if not l.startswith("map --when-focus-on"))   # tmux passthroughs
        binds = [{"modmask": 12, "key": k} for k in reserved]
        self.assertEqual(self.m.conflicts_from_binds(binds, tpl), [])

    def test_real_template_parses(self):
        tpl = open(os.path.join(ROOT, "kittymux-keys.conf.tpl"), encoding="utf-8").read()
        self.assertEqual(self.m.conflicts_from_binds([], tpl), [])


class ExplainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"KITTYMUX_STATE": self.tmp.name})
        self.env.start()
        self.patches = [mock.patch.object(self.m, "_target_socket", lambda: "unix:/tmp/mykitty-4321"),
                        mock.patch.object(self.m, "_run", lambda *a, **k: (1, ""))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()
        self.tmp.cleanup()

    def write(self, name, text):
        with open(os.path.join(self.tmp.name, name), "w") as f:
            f.write(text)

    def test_describe_event(self):
        d = self.m.describe_event
        self.assertIn("working → done", d({"kind": "state", "frm": "working", "to": "done", "why": "its Stop hook fired"}))
        self.assertIn("its Stop hook fired", d({"kind": "state", "frm": "working", "to": "done", "why": "its Stop hook fired"}))
        self.assertIn("suppressed: worked only 8 s", d({"kind": "notify", "state": "done", "worked": 8, "outcome": "suppressed: worked only 8 s"}))
        self.assertIn("(worked 31 s)", d({"kind": "notify", "state": "done", "worked": 31, "outcome": "sent"}))
        self.assertTrue(d({"kind": "mystery"}))

    def test_read_events_filters_skips_bad_lines_and_keeps_the_newest(self):
        lines = [json.dumps({"t": i, "kind": "state", "w": str(i % 2), "to": "idle", "why": "x"}) for i in range(10)]
        self.write("decisions-1.jsonl", "\n".join(lines[:5] + ["{not json", ""] + lines[5:]) + "\n")
        path = os.path.join(self.tmp.name, "decisions-1.jsonl")
        self.assertEqual([e["t"] for e in self.m.read_events(path, 3)], [7, 8, 9])
        self.assertEqual([e["t"] for e in self.m.read_events(path, 50, "1")], [1, 3, 5, 7, 9])
        self.assertEqual(self.m.read_events(os.path.join(self.tmp.name, "nope.jsonl")), [])

    def test_explain_prints_current_reasons_and_recent_decisions(self):
        self.write("scan-4321.json", json.dumps({"7": {"state": "waiting", "agent": "claude", "why": "the screen shows a permission/question prompt"}}))
        self.write("decisions-4321.jsonl", json.dumps({"t": 1790000000, "kind": "notify", "w": "7", "agent": "claude", "state": "waiting",
                                                       "outcome": "sent"}) + "\n")
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(self.m.explain([]), 0)
        out = buf.getvalue()
        self.assertIn("kitty 4321", out)
        self.assertIn("the screen shows a permission/question prompt", out)
        self.assertIn("notify waiting", out)
        self.assertIn("sent", out)

    def test_explain_json_and_argument_errors(self):
        self.write("scan-4321.json", json.dumps({"7": {"state": "idle", "agent": "codex", "why": "quiet"}}))
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(self.m.explain(["--json", "--window", "7"]), 0)
        self.assertEqual(json.loads(buf.getvalue())[0]["now"]["7"]["why"], "quiet")
        with mock.patch("sys.stderr"):
            self.assertEqual(self.m.explain(["--window", "x"]), 2)
            self.assertEqual(self.m.explain(["--last", "many"]), 2)
            self.assertEqual(self.m.explain(["--bogus"]), 2)


class InboxCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()
        cls.I = cls.m.kittymux_inbox

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"KITTYMUX_STATE": self.tmp.name})
        self.env.start()
        self.now = 10_000.0

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def add(self, kind, w=1, t=None, **kw):
        ev = self.I.make_event(kind, kw.pop("agent", "claude"), w, kw.pop("source", "agent"), t if t is not None else self.now, pid=4321, tab="my tab", **kw)
        self.I.add(self.tmp.name, ev)
        return ev

    def out(self, argv):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.m.inbox(argv)
        return rc, buf.getvalue()

    def test_list_shows_unread_newest_first_and_all_shows_everything(self):
        a = self.add("permission", w=1, t=100.0, body="Claude needs your permission to use Bash")
        self.add("done", w=2, t=200.0)
        self.I.ack(self.tmp.name, 300.0, ids=[a["id"]])
        rc, text = self.out([])
        self.assertEqual(rc, 0)
        self.assertEqual(len(text.strip().splitlines()), 1)
        self.assertIn("done", text)
        rc, text = self.out(["--all"])
        lines = text.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("done", lines[0])                                     # newest first
        self.assertIn("needs your permission", lines[1])

    def test_empty_inbox_says_so(self):
        self.assertIn("inbox is empty", self.out([])[1])

    def test_limit_line_shows_the_countdown_and_a_screen_only_finish_says_so(self):
        reset = self.now + 2 * 3600 + 30 * 60
        line = self.m.format_event(self.add("limit", reset_at=reset, body="usage limit reached"), self.now)
        self.assertIn("resets in 2h 30m", line)
        line = self.m.format_event(self.add("done", w=3, source="screen", confidence="low"), self.now)
        self.assertIn("judged from the screen", line)
        self.assertTrue(self.m.format_event({"kind": "info"}, 0.0))          # a bare event still formats

    def test_ack_clear_and_usage_errors(self):
        e = self.add("question", w=5)
        self.assertEqual(self.out(["ack", e["id"]])[0], 0)
        self.assertEqual(self.I.load(self.tmp.name)[0]["status"], "read")
        self.add("permission", w=6, t=self.now + 500)
        self.assertEqual(self.out(["clear"])[0], 0)
        self.assertEqual({x["status"] for x in self.I.load(self.tmp.name)}, {"read", "dismissed"})
        with mock.patch("sys.stderr"):
            self.assertEqual(self.m.inbox(["ack"]), 2)
            self.assertEqual(self.m.inbox(["bogus"]), 2)
            self.assertEqual(self.m.inbox(["--limit", "x"]), 2)

    def test_json_is_the_documented_snapshot(self):
        self.add("limit", reset_at=self.now + 60)
        rc, text = self.out(["--json"])
        snap = json.loads(text)
        self.assertEqual((snap["version"], snap["unread"], snap["events"][0]["kind"]), (1, 1, "limit"))

    def test_jump_focuses_the_window_acks_it_and_prefers_needs_you(self):
        self.add("done", w=2, t=self.now + 50)
        self.add("permission", w=1, t=self.now)                              # older, but it needs you
        calls = []
        with mock.patch.object(self.m, "_inbox_socket", lambda pid: "unix:/tmp/mykitty-4321"), \
                mock.patch.object(self.m, "_run", lambda cmd, t=3.0: (calls.append(cmd) or (0, ""))), mock.patch.object(self.m.shutil, "which", lambda n: None):
            self.assertEqual(self.m.inbox(["jump"]), 0)
        self.assertEqual(calls[0][-2:], ["--match", "id:1"])                  # window 1: the one that needs you
        self.assertEqual([e["status"] for e in self.I.load(self.tmp.name)], ["unread", "read"])

    def test_jump_fails_cleanly_when_the_kitty_or_window_is_gone(self):
        self.add("permission", w=1)
        with mock.patch("sys.stderr"), mock.patch.object(self.m, "_inbox_socket", lambda pid: None):
            self.assertEqual(self.m.inbox(["jump"]), 1)
        with mock.patch("sys.stderr"), mock.patch.object(self.m, "_inbox_socket", lambda pid: "unix:/x"), mock.patch.object(self.m, "_run", lambda *a, **k: (1, "")):
            self.assertEqual(self.m.inbox(["jump"]), 1)
        self.assertEqual(self.I.load(self.tmp.name)[0]["status"], "unread")   # a failed jump acknowledges nothing


class SessionsCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"KITTYMUX_STATE": self.tmp.name, "XDG_CONFIG_HOME": os.path.join(self.tmp.name, "xdg")})
        self.env.start()
        self.sdir = os.path.join(self.tmp.name, "sessions")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, fn, argv):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = fn(argv)
        return rc, out.getvalue(), err.getvalue()

    # probing
    def test_probe_requires_every_expected_flag_in_the_clis_own_help(self):
        run = lambda text: (lambda *a, **k: types.SimpleNamespace(stdout=text, stderr=""))        # noqa: E731
        d = {"probe": {"args": ["--help"], "expect": ["--resume", "--continue"]}}
        self.assertEqual(self.m.probe_agent("x", d, which=lambda n: "/bin/x", run=run("--resume --continue"))[0], True)
        ok, detail, _ = self.m.probe_agent("x", d, which=lambda n: "/bin/x", run=run("--resume only"))
        self.assertFalse(ok)
        self.assertIn("--continue", detail)
        self.assertEqual(self.m.probe_agent("x", d, which=lambda n: None, run=run(""))[1], "not installed")
        self.assertFalse(self.m.probe_agent("x", d, which=lambda n: "/bin/x", run=mock.Mock(side_effect=OSError))[0])

    def test_probe_results_are_cached_per_executable(self):
        calls = []

        def probe(name, d):
            calls.append(name)
            return True, "ok", "/bin/x"
        agents = {"x": {"probe": {"expect": ["a"]}}}
        cache = os.path.join(self.tmp.name, "check.json")
        with mock.patch.object(self.m.shutil, "which", lambda n: "/bin/sh"):
            self.assertTrue(self.m.agent_enabled("x", agents, cache, 1000.0, probe))
            self.assertTrue(self.m.agent_enabled("x", agents, cache, 1100.0, probe))              # cached
            self.assertEqual(len(calls), 1)
            self.assertTrue(self.m.agent_enabled("x", agents, cache, 1000.0 + self.m.CHECK_TTL_S + 1, probe))   # expired: probed again
            self.assertEqual(len(calls), 2)
        self.assertFalse(self.m.agent_enabled("unknown", agents, cache, 1000.0, probe))
        self.assertEqual(oct(os.stat(cache).st_mode & 0o777), "0o600")

    # templates
    def test_every_shipped_template_renders_and_is_a_valid_kitty_session(self):
        for name in ("plain", "agent", "duo", "review"):
            self.assertIn(name, self.m.list_templates())
        for name in sorted(self.m.list_templates()):
            rc, out, err = self.run_cli(self.m.sessions_new, [f"t-{name}", "--template", name, "--cwd", self.tmp.name, "--agent", "claude"])
            self.assertEqual(rc, 0, (name, err))
            text = open(os.path.join(self.sdir, f"t-{name}.kitty-session"), encoding="utf-8").read()
            self.assertNotRegex(re.sub(r"#.*", "", text), r"@[A-Z0-9_]+@|@Q:", name)               # nothing left unfilled
            self.assertEqual(stat_mode(os.path.join(self.sdir, f"t-{name}.kitty-session")), 0o600)

    def test_new_validates_name_template_cwd_and_refuses_to_overwrite(self):
        self.assertEqual(self.run_cli(self.m.sessions_new, ["../evil"])[0], 2)
        self.assertEqual(self.run_cli(self.m.sessions_new, ["ok", "--template", "nope"])[0], 2)
        self.assertEqual(self.run_cli(self.m.sessions_new, ["ok", "--cwd", "/definitely/not/here"])[0], 2)
        self.assertEqual(self.run_cli(self.m.sessions_new, ["ok", "--agent", "x; rm -rf ~"])[0], 2)
        self.assertEqual(self.run_cli(self.m.sessions_new, ["ok", "--cwd", self.tmp.name])[0], 0)
        self.assertEqual(self.run_cli(self.m.sessions_new, ["ok", "--cwd", self.tmp.name])[0], 1)       # exists
        self.assertEqual(self.run_cli(self.m.sessions_new, ["ok", "--cwd", self.tmp.name, "--force"])[0], 0)

    def test_a_path_with_spaces_and_quotes_stays_one_token_in_the_template(self):
        import shlex
        weird = os.path.join(self.tmp.name, "my 'odd' project")
        os.makedirs(weird)
        self.assertEqual(self.run_cli(self.m.sessions_new, ["w", "--template", "agent", "--cwd", weird])[0], 0)
        cd = next(l for l in open(os.path.join(self.sdir, "w.kitty-session")).read().splitlines() if l.startswith("cd "))
        self.assertEqual(shlex.split(cd), ["cd", weird])

    def test_a_users_own_template_wins(self):
        udir = os.path.join(self.tmp.name, "xdg", "kittymux", "templates")
        os.makedirs(udir)
        with open(os.path.join(udir, "agent.kitty-session"), "w") as f:
            f.write("# mine\nnew_tab @NAME@\n")
        self.assertEqual(self.run_cli(self.m.sessions_new, ["u", "--template", "agent", "--cwd", self.tmp.name])[0], 0)
        self.assertIn("# mine", open(os.path.join(self.sdir, "u.kitty-session")).read())

    # files
    def test_rewrite_file_is_atomic_private_and_idempotent(self):
        os.makedirs(self.sdir)
        path = os.path.join(self.sdir, "s.kitty-session")
        with open(path, "w") as f:
            f.write("launch 'kitty-unserialize-data={\"id\": 1}' --var=kittymux_status=working --var=kittymux_resume=exact "
                    "--var=kittymux_sid=0a1b2c3d-0000-4000-8000-000000000001 /usr/bin/claude --model x\n")
        os.chmod(path, 0o644)
        with mock.patch.object(self.m, "agent_enabled", lambda n, a, *k: True):
            first = self.m.rewrite_file(path, direct=True)
            second = self.m.rewrite_file(path, direct=True)
        self.assertEqual(len(first), 1)
        self.assertEqual(first, second)
        text = open(path).read()
        self.assertIn("--resume 0a1b2c3d-0000-4000-8000-000000000001", text)
        self.assertNotIn("kittymux_status", text)
        self.assertEqual(stat_mode(path), 0o600)
        self.assertFalse(os.path.exists(path + ".tmp"))

    def test_rewrite_file_by_default_makes_the_agent_window_ask(self):
        import shlex
        os.makedirs(self.sdir)
        path = os.path.join(self.sdir, "s.kitty-session")
        with open(path, "w") as f:
            f.write("launch 'kitty-unserialize-data={\"id\": 1}' --var=kittymux_resume=exact "
                    "--var=kittymux_sid=0a1b2c3d-0000-4000-8000-000000000001 /usr/bin/claude --model x\n")
        with mock.patch.object(self.m, "agent_enabled", lambda n, a, *k: True):
            first = self.m.rewrite_file(path)
            second = self.m.rewrite_file(path)
        self.assertEqual((len(first), second), (1, []))
        tokens = shlex.split(open(path).read())
        self.assertEqual(tokens[-3:-1], ["resume-prompt", "--info"])
        self.assertTrue(os.access(tokens[-4], os.X_OK))                              # the wrapper it launches is this install's kittymux

    def test_history_and_recover_read_the_journal(self):
        import kittymux_journal as J
        import time
        sid = "0a1b2c3d-0000-4000-8000-000000000001"
        work = os.path.join(self.tmp.name, "proj")
        os.makedirs(work)
        now = time.time()
        recs = {}
        J.observe(recs, {"agent": "claude", "sid": sid, "cwd": work, "tab": "api work", "argv": ["/usr/bin/claude", "--model", "x"], "state": "working",
                         "kitty_pid": 2 ** 22 + 5, "wid": 3, "mode": ""}, now - 900)
        J.observe(recs, {"agent": "claude", "sid": sid, "cwd": work, "tab": "api work", "argv": ["/usr/bin/claude", "--model", "x"], "state": "done",
                         "kitty_pid": 2 ** 22 + 5, "wid": 3, "mode": ""}, now - 600)
        J.observe(recs, {"agent": "codex", "sid": None, "cwd": "/gone/dir", "tab": "x", "argv": ["codex"], "state": "idle", "kitty_pid": 2 ** 22 + 5, "wid": 4,
                         "mode": ""}, now - 600)
        J.flush(self.tmp.name, recs, now)
        rc, out, _ = self.run_cli(self.m.sessions_history, [])
        self.assertEqual(rc, 0)
        self.assertIn("2 agent sessions", out)
        self.assertIn("1 runs finished", out)
        rc, out, _ = self.run_cli(self.m.sessions_history, ["--json", "--since", "1h"])
        self.assertEqual(json.loads(out)["insights"]["sessions"], 2)
        recs2 = J.load(self.tmp.name)
        recs2[f"claude:{sid}"]["argv"] = ["/usr/bin/claude", "--api-key", "hunter2hunter2"]
        J.flush(self.tmp.name, recs2, now)
        self.assertNotIn("hunter2", self.run_cli(self.m.sessions_history, ["--json"])[1])             # pasted output carries no secret
        with mock.patch.object(self.m, "agent_enabled", lambda n, a, *k: True):
            rc, out, _ = self.run_cli(self.m.sessions_recover, ["--since", "1h"])
        self.assertEqual(rc, 0)
        text = open(os.path.join(self.sdir, "recovered.kitty-session")).read()
        self.assertIn("new_tab api work", text)
        self.assertIn("resume-prompt", text)
        self.assertNotIn("/gone/dir", text)                                          # a directory that no longer exists is not recovered
        self.assertEqual(stat_mode(os.path.join(self.sdir, "recovered.kitty-session")), 0o600)
        self.assertEqual(self.run_cli(self.m.sessions_recover, ["bad/name"])[0], 2)

    def test_recover_with_nothing_to_do_says_so(self):
        rc, out, _ = self.run_cli(self.m.sessions_recover, [])
        self.assertEqual(rc, 0)
        self.assertIn("nothing to recover", out)
        self.assertFalse(os.path.exists(os.path.join(self.sdir, "recovered.kitty-session")))

    def test_find_session_and_restore_use_kittys_own_goto_session_when_inside_kitty(self):
        os.makedirs(self.sdir)
        for n, t in (("old", 100), ("new", 200)):
            p = os.path.join(self.sdir, n + ".kitty-session")
            open(p, "w").close()
            os.utime(p, (t, t))
        self.assertTrue(self.m._find_session("last").endswith("new.kitty-session"))
        self.assertTrue(self.m._find_session("old").endswith("old.kitty-session"))
        self.assertIsNone(self.m._find_session("../../etc/passwd"))
        calls = []
        with mock.patch.object(self.m, "_target_socket", lambda: "unix:/tmp/mykitty-1"), mock.patch.object(self.m, "_run", lambda cmd, t=3.0: (calls.append(cmd) or (0, ""))):
            rc, out, _ = self.run_cli(self.m.sessions_restore, ["old"])
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0][3:6], ["action", "goto_session", self.m._find_session("old")][0:0] or calls[0][3:6])
        self.assertIn("goto_session", calls[0])

    def test_usage_errors(self):
        self.assertEqual(self.run_cli(self.m.sessions, ["bogus"])[0], 2)
        self.assertEqual(self.run_cli(self.m.sessions_save, ["bad/name"])[0], 2)


def stat_mode(path):
    return os.stat(path).st_mode & 0o777


class LifecycleCliTests(unittest.TestCase):
    """pin / unpin / settle / unsettle and the lifecycle of reopenable conversations — always against a throwaway state dir."""

    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def setUp(self):
        import tempfile
        import time as _t
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"KITTYMUX_STATE": self.tmp.name, "KITTY_WINDOW_ID": ""})
        self.env.start()
        import sys
        sys.path.insert(0, os.path.join(ROOT, "python"))
        import kittymux_journal as J
        self.J, self.now = J, _t.time()
        self.work = os.path.join(self.tmp.name, "w")
        os.makedirs(self.work)
        recs = {}
        for i, (sid, age) in enumerate((("0a1b2c3d-0000-4000-8000-00000000000a", 600), ("0a1b2c3d-0000-4000-8000-00000000000b", 5 * 86400))):
            J.observe(recs, {"agent": "claude", "sid": sid, "cwd": self.work, "tab": f"t{i}", "argv": ["claude"], "state": "idle", "kitty_pid": 2 ** 22 + 9, "wid": i + 1, "mode": ""}, self.now - age)
        J.flush(self.tmp.name, recs, self.now)
        self.keys = sorted(recs)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, fn, *a):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = fn(*a)
        return rc, out.getvalue(), err.getvalue()

    def flags(self, key):
        return {k: v for k, v in self.J.load(self.tmp.name)[key].items() if k in ("pinned", "settled")}

    def test_closed_conversations_are_recent_or_settled_by_age_and_a_pin_beats_age(self):
        life = {e["key"]: e["lifecycle"] for e in self.m._reopenable(self.now)}
        self.assertEqual(sorted(life.values()), ["recent", "settled"])
        old = next(k for k, v in life.items() if v == "settled")
        self.assertEqual(self.run_cli(self.m.lifecycle_verb, "pin", [old])[0], 0)
        self.assertEqual({e["key"]: e["lifecycle"] for e in self.m._reopenable(self.now)}[old], "pinned")
        self.assertEqual(self.flags(old), {"pinned": True, "settled": False})
        self.assertEqual(self.run_cli(self.m.lifecycle_verb, "unpin", [old])[0], 0)
        self.assertEqual({e["key"]: e["lifecycle"] for e in self.m._reopenable(self.now)}[old], "settled")

    def test_a_unique_prefix_is_enough_and_a_shared_one_is_refused(self):
        recs = self.J.load(self.tmp.name)
        odd = dict(next(iter(recs.values())))
        recs["codex:uniq-session"] = odd
        self.J.flush(self.tmp.name, recs, self.now)
        self.assertEqual(self.run_cli(self.m.lifecycle_verb, "pin", ["codex:uniq"])[0], 0)
        self.assertTrue(self.flags("codex:uniq-session")["pinned"])
        rc, _o, err = self.run_cli(self.m.lifecycle_verb, "pin", [self.keys[0][:20]])               # both claude keys share this prefix
        self.assertEqual(rc, 1)
        self.assertIn("several conversations match", err)

    def test_settle_and_unsettle_a_recent_conversation(self):
        recent = next(e["key"] for e in self.m._reopenable(self.now) if e["lifecycle"] == "recent")
        self.assertEqual(self.run_cli(self.m.lifecycle_verb, "settle", [recent])[0], 0)
        self.assertEqual({e["key"]: e["lifecycle"] for e in self.m._reopenable(self.now)}[recent], "settled")
        self.assertEqual(self.run_cli(self.m.lifecycle_verb, "unsettle", [recent])[0], 0)
        self.assertEqual({e["key"]: e["lifecycle"] for e in self.m._reopenable(self.now)}[recent], "recent")

    def test_the_settle_age_is_configurable_within_sane_bounds(self):
        with mock.patch.dict(os.environ, {"KITTYMUX_SETTLE_DAYS": "30"}):
            self.assertEqual(sorted(e["lifecycle"] for e in self.m._reopenable(self.now)), ["recent", "recent"])
        for bad in ("0", "-3", "9999", "soon", ""):
            with mock.patch.dict(os.environ, {"KITTYMUX_SETTLE_DAYS": bad}):
                self.assertEqual(self.m._settle_after(), self.J.SETTLE_AFTER_S, bad)

    def test_unknown_options_ambiguity_and_missing_records_are_refused_and_change_nothing(self):
        before = self.J.load(self.tmp.name)
        for args in (["--bogus"], ["nosuchkey"], ["claude:"], []):                                          # "claude:" matches both; [] has no window to mean
            rc, _out, err = self.run_cli(self.m.lifecycle_verb, "pin", args)
            self.assertEqual(rc, 1, args)
            self.assertTrue(err, args)
        self.assertEqual(self.J.load(self.tmp.name), before)


class FanoutCliTests(unittest.TestCase):
    """`kittymux fanout` against a real repository, fake agents on PATH, and kitty's launch replaced by a recorder."""

    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def setUp(self):
        import subprocess
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.repo, self.state, self.bin = (os.path.join(self.tmp.name, n) for n in ("repo", "state", "bin"))
        for d in (self.repo, self.state, self.bin):
            os.makedirs(d)
        self.git = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)
        with open(os.path.join(self.repo, "a.txt"), "w") as f:
            f.write("one\n")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(self.git + ["commit", "-qm", "init"], cwd=self.repo, check=True)
        for a in ("claude", "codex", "devin", "opencode"):
            with open(os.path.join(self.bin, a), "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(os.path.join(self.bin, a), 0o755)
        self.env = mock.patch.dict(os.environ, {"KITTYMUX_STATE": self.state, "XDG_CONFIG_HOME": os.path.join(self.tmp.name, "xdg"), "PATH": self.bin + ":" + os.environ["PATH"]})
        self.env.start()
        self.launched = []
        only_ours = lambda name, *a, **k: os.path.join(self.bin, name) if os.path.exists(os.path.join(self.bin, name)) else None        # noqa: E731
        self.p0 = mock.patch.object(self.m.shutil, "which", only_ours)                                  # the agents installed on THIS machine must not matter
        self.p0.start()
        self.p1 = mock.patch.object(self.m, "_focused_socket", lambda: "unix:/fake")
        self.p2 = mock.patch.object(self.m, "_launch_tab_before_scratch", lambda sock, make: (self.launched.append(make(False)), True)[1])
        self.p1.start()
        self.p2.start()

    def tearDown(self):
        self.p2.stop()
        self.p1.stop()
        self.p0.stop()
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, *argv):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = self.m.fanout(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_one_tab_per_agent_in_its_own_worktree_with_the_prompt_in_each_clis_own_form(self):
        rc, out, err = self.run_cli("fix the login bug", "claude,devin,opencode", "--name", "fix", "--cwd", self.repo)
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(self.launched), 3)
        by_title = {a[a.index("--tab-title") + 1]: a for a in self.launched}
        self.assertEqual(sorted(by_title), ["claude · fix", "devin · fix", "opencode · fix"])
        tail = lambda a: a[a.index("--") + 1:]                                  # noqa: E731
        self.assertEqual(tail(by_title["claude · fix"])[1:], ["fix the login bug"])
        self.assertEqual(tail(by_title["devin · fix"])[1:], ["--", "fix the login bug"])
        self.assertEqual(tail(by_title["opencode · fix"])[1:], ["--prompt", "fix the login bug"])
        for title, a in by_title.items():
            path = next(x[len("--cwd="):] for x in a if x.startswith("--cwd="))
            self.assertTrue(os.path.isdir(path) and path.endswith(f".worktrees/fix-{title.split(' ')[0]}"), path)
        self.assertEqual(sorted(self.m.kittymux_fanout.load(self.state)["fix"]["agents"][i]["agent"] for i in range(3)), ["claude", "devin", "opencode"])
        self.assertIn("fanout compare fix", out)

    def test_a_hostile_prompt_reaches_the_agent_as_one_argument(self):
        evil = 'x"; touch /tmp/pwned; `id` $(id)'
        self.assertEqual(self.run_cli(evil, "claude", "--name", "h", "--cwd", self.repo)[0], 0)
        a = self.launched[0]
        self.assertEqual(a[a.index("--") + 2:], [evil])
        self.assertFalse(os.path.exists("/tmp/pwned"))

    def test_refusals_change_nothing(self):
        cases = [(("p", "nosuch"), 2), (("p", "claude,agy"), 1), (("-x", "claude"), 2), (("", "claude"), 2), (("p",), 2),
                 (("p", "claude", "--name", "bad name"), 2), (("p", "claude", "--base", "nosuchref"), 1), (("p", "claude", "--bogus"), 2)]
        for args, want in cases:
            rc, _o, err = self.run_cli(*args, "--cwd", self.repo) if "--bogus" not in args else self.run_cli(*args)
            self.assertEqual(rc, want, (args, err))
        plain = os.path.join(self.tmp.name, "plain")
        os.makedirs(plain)
        self.assertEqual(self.run_cli("p", "claude", "--cwd", plain)[0], 1)                         # not a git repository
        self.assertEqual(self.launched, [])
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".worktrees")))                     # nothing was created by any refusal

    def test_no_kitty_socket_refuses_before_creating_anything(self):
        with mock.patch.object(self.m, "_focused_socket", lambda: None):
            self.assertEqual(self.run_cli("p", "claude", "--name", "n", "--cwd", self.repo)[0], 1)
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".worktrees")))

    def test_a_name_that_exists_is_refused_not_reused(self):
        self.assertEqual(self.run_cli("p", "claude", "--name", "dup", "--cwd", self.repo)[0], 0)
        rc, _o, err = self.run_cli("p", "claude", "--name", "dup", "--cwd", self.repo)
        self.assertEqual(rc, 1)
        self.assertIn("already exists", err)

    def test_compare_list_and_clean(self):
        self.assertEqual(self.run_cli("p", "claude,codex", "--name", "c", "--cwd", self.repo)[0], 0)
        rec = self.m.kittymux_fanout.load(self.state)["c"]
        with open(os.path.join(rec["agents"][0]["path"], "a.txt"), "a") as f:
            f.write("two\nthree\n")
        rc, out, _ = self.run_cli("compare", "c")
        self.assertEqual(rc, 0)
        lines = {l.split()[0]: l for l in out.splitlines()[1:]}
        self.assertIn("1 file +2", lines["claude"])
        self.assertIn("no changes", lines["codex"])
        self.assertIn("c", self.run_cli("list")[1])
        rc, out, _ = self.run_cli("clean", "c")                                                     # dry run
        self.assertIn("dry run", out)
        self.assertTrue(os.path.isdir(rec["agents"][0]["path"]))
        rc, out, _ = self.run_cli("clean", "c", "--yes")
        self.assertIn("kept claude", out)                                                           # it has uncommitted work
        self.assertTrue(os.path.isdir(rec["agents"][0]["path"]))
        self.assertFalse(os.path.exists(rec["agents"][1]["path"]))
        self.assertIn("c", self.m.kittymux_fanout.load(self.state))                                 # not forgotten while something is kept
        self.run_cli("clean", "c", "--yes", "--force")
        self.assertFalse(os.path.exists(rec["agents"][0]["path"]))
        self.assertNotIn("c", self.m.kittymux_fanout.load(self.state))


class LauncherTargetTests(unittest.TestCase):
    """A key inside a kitty acts on THAT kitty. (Once a test rig's key-launched spawn followed 'the focused kitty' into the author's real one.)"""

    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for k in ("KITTYMUX_TARGET", "KITTY_LISTEN_ON", "KITTY_PID"):
            os.environ.pop(k, None)
        self.owned = mock.patch.object(self.m, "_owned_socket", lambda p: p in ("/run/u/mykitty-1", "/run/u/mykitty-2"))        # exactly these two exist
        self.owned.start()
        self.dirs = mock.patch.object(self.m, "_socket_dirs", lambda: ["/run/u"])
        self.dirs.start()
        self.socks = mock.patch.object(self.m, "_sockets", lambda: ["unix:/run/u/mykitty-1", "unix:/run/u/mykitty-2"])
        self.socks.start()
        self.ls = mock.patch.object(self.m, "_ls", lambda s: [{"is_focused": s.endswith("-2")}])        # kitty 2 is the focused one
        self.ls.start()

    def tearDown(self):
        for p in (self.ls, self.socks, self.dirs, self.owned, self.env):
            p.stop()

    def test_started_inside_a_kitty_it_acts_on_that_kitty_even_when_another_has_focus(self):
        os.environ["KITTY_LISTEN_ON"] = "unix:/run/u/mykitty-1"
        self.assertEqual(self.m._focused_socket(), "unix:/run/u/mykitty-1")

    def test_started_from_outside_every_kitty_it_follows_the_focus(self):
        self.assertEqual(self.m._focused_socket(), "unix:/run/u/mykitty-2")

    def test_an_explicit_target_always_wins(self):
        os.environ["KITTYMUX_TARGET"] = "unix:/run/u/mykitty-1"
        os.environ["KITTY_LISTEN_ON"] = "unix:/run/u/mykitty-2"
        self.assertEqual(self.m._focused_socket(), "unix:/run/u/mykitty-1")

    def test_a_foreign_socket_in_the_environment_is_not_trusted(self):
        os.environ["KITTY_LISTEN_ON"] = "unix:/tmp/someone-elses"
        self.assertEqual(self.m._focused_socket(), "unix:/run/u/mykitty-2")


class PurgeGuardTests(unittest.TestCase):
    """`uninstall --purge` deletes $KITTYMUX_STATE: a mistyped value must never take your home directory with it."""

    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(self.home, ".local", "state"))

    def tearDown(self):
        self.tmp.cleanup()

    def reason(self, path):
        return self.m.unsafe_purge_reason(path, self.home)

    def test_the_root_the_home_and_anything_above_it_are_refused(self):
        self.assertIn("home directory", self.reason("/"))
        self.assertIn("home directory", self.reason(self.home))
        self.assertIn("home directory", self.reason(os.path.dirname(self.home)))
        self.assertIn("home directory", self.reason(self.tmp.name))

    def test_a_directory_that_is_not_ours_is_refused_and_ours_is_allowed(self):
        other = os.path.join(self.home, "Documents")
        os.makedirs(other)
        open(os.path.join(other, "thesis.tex"), "w").close()
        self.assertIn("does not look like a kittymux state directory", self.reason(other))
        named = os.path.join(self.home, ".local", "state", "kittymux")
        os.makedirs(named)
        self.assertIsNone(self.reason(named))                                           # the default location
        custom = os.path.join(self.home, "my-state")
        os.makedirs(custom)
        open(os.path.join(custom, "inbox.jsonl"), "w").close()
        self.assertIsNone(self.reason(custom))                                          # a custom location that holds our files
        self.assertIsNone(self.reason(os.path.join(self.home, "gone")))                 # nothing there

    def test_a_symlink_is_never_followed_into_a_delete(self):
        real = os.path.join(self.home, ".local", "state", "kittymux")
        os.makedirs(real)
        link = os.path.join(self.home, "state-link")
        os.symlink(real, link)
        self.assertIn("symlink", self.reason(link))


class DimAndScreenshotTests(unittest.TestCase):
    """Never touch a real kitty from tests: no socket, no kitty subprocess."""

    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"KITTYMUX_STATE": self.tmp.name})
        self.env.start()
        self.patches = [mock.patch.object(self.m, "_target_socket", lambda: None),
                        mock.patch.object(self.m, "_kitty_version", lambda: (0, 49, 2)),
                        mock.patch.object(self.m, "_run", lambda *a, **k: (1, ""))]
        for p in self.patches:
            p.start()
        self.flag = os.path.join(self.tmp.name, "dim-inactive")

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_dim_toggles_a_flag_file(self):
        with mock.patch("sys.stdout"), mock.patch.object(self.m.kittymux_layout, "have_slangc", lambda: True):
            self.assertEqual(self.m.dim(["show"]), 0)
            self.assertFalse(os.path.exists(self.flag))
            self.m.dim(["on"])
            self.assertTrue(os.path.exists(self.flag))
            self.m.dim(["toggle"])
            self.assertFalse(os.path.exists(self.flag))
            self.m.dim(["toggle"])
            self.assertTrue(os.path.exists(self.flag))
            self.m.dim(["off"])
            self.assertFalse(os.path.exists(self.flag))
            self.m.dim(["off"])                                       # idempotent

    def test_dim_refuses_without_the_shader_compiler(self):
        with mock.patch("sys.stderr"), mock.patch.object(self.m.kittymux_layout, "have_slangc", lambda: False):
            self.assertEqual(self.m.dim(["on"]), 1)
        self.assertFalse(os.path.exists(self.flag))                  # no flag, so no failing shader on every reload

    def test_uninstall_plan_removes_only_our_path_link(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            home, cfg, fonts, binp = (os.path.join(d, n) for n in ("home", "cfg", "fonts", "bin"))
            os.makedirs(os.path.join(home, "bin")), os.makedirs(cfg), os.makedirs(fonts), os.makedirs(binp)
            open(os.path.join(home, "bin", "kittymux"), "w").close()
            os.symlink(os.path.join(home, "bin", "kittymux"), os.path.join(binp, "kittymux"))
            self.assertIn(os.path.join(binp, "kittymux"), self.m.plan_uninstall(cfg, home, fonts, binp)["links"])
            os.unlink(os.path.join(binp, "kittymux"))
            open(os.path.join(binp, "kittymux"), "w").close()               # a file of the user's with that name
            self.assertNotIn(os.path.join(binp, "kittymux"), self.m.plan_uninstall(cfg, home, fonts, binp)["links"])
            os.unlink(os.path.join(binp, "kittymux"))
            os.symlink("/usr/bin/true", os.path.join(binp, "kittymux"))     # a link to something else
            self.assertNotIn(os.path.join(binp, "kittymux"), self.m.plan_uninstall(cfg, home, fonts, binp)["links"])

    def test_dim_rejects_nonsense(self):
        with mock.patch("sys.stderr"):
            self.assertEqual(self.m.dim(["sideways"]), 2)

    def test_screenshot_needs_a_kitty_and_valid_options(self):
        with mock.patch("sys.stderr"):
            self.assertEqual(self.m.screenshot(["--bogus"]), 2)
            self.assertEqual(self.m.screenshot([]), 1)               # no socket


class HooksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def test_adds_every_event_to_empty(self):
        merged, added = self.m.merge_hooks({})
        self.assertEqual(sorted(added), ["Notification", "PostToolUse", "SessionEnd", "Stop", "UserPromptSubmit"])
        self.assertTrue(merged["hooks"]["PostToolUse"][0]["hooks"][0]["command"].endswith("bin/mux-status working"))
        self.assertTrue(merged["hooks"]["SessionEnd"][0]["hooks"][0]["command"].endswith("bin/mux-status idle"))
        cmd = merged["hooks"]["Notification"][0]["hooks"][0]["command"]
        self.assertTrue(cmd.endswith("bin/mux-status waiting"))

    def test_idempotent(self):
        once, _ = self.m.merge_hooks({})
        twice, added = self.m.merge_hooks(once)
        self.assertEqual(added, [])
        self.assertEqual(once, twice)

    def test_preserves_existing_settings_and_hooks(self):
        cur = {"model": "opus", "permissions": {"allow": ["Bash(ls)"]},
               "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}],
                         "PreToolUse": [{"matcher": "Bash", "hooks": []}]}}
        merged, added = self.m.merge_hooks(cur)
        self.assertEqual(merged["model"], "opus")
        self.assertEqual(merged["permissions"], cur["permissions"])
        self.assertEqual(merged["hooks"]["PreToolUse"], cur["hooks"]["PreToolUse"])
        self.assertEqual(merged["hooks"]["Stop"][0]["hooks"][0]["command"], "echo mine")
        self.assertEqual(len(merged["hooks"]["Stop"]), 2)
        self.assertEqual(cur["hooks"]["Stop"], [{"hooks": [{"type": "command", "command": "echo mine"}]}])  # input untouched

    def test_install_writes_backup_and_valid_json(self):
        import json, tempfile
        d = tempfile.mkdtemp()
        path = os.path.join(d, "settings.json")
        open(path, "w").write(json.dumps({"theme": "dark"}))
        self.assertEqual(self.m.hooks(["--install", "--settings", path]), 0)
        data = json.load(open(path))
        self.assertEqual(data["theme"], "dark")
        self.assertIn("Stop", data["hooks"])
        self.assertTrue([f for f in os.listdir(d) if ".bak-kittymux-" in f])
        self.assertEqual(self.m.hooks(["--install", "--settings", path]), 0)      # second run: no-op
        self.assertEqual(len([f for f in os.listdir(d) if ".bak-kittymux-" in f]), 1)

    def test_install_preserves_restrictive_permissions(self):
        import stat, tempfile
        d = tempfile.mkdtemp()
        path = os.path.join(d, "settings.json")
        open(path, "w").write("{}")
        os.chmod(path, 0o600)
        self.assertEqual(self.m.hooks(["--install", "--settings", path]), 0)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        backup = [f for f in os.listdir(d) if ".bak-kittymux-" in f][0]
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, backup)).st_mode), 0o600)

    def test_invalid_json_untouched(self):
        import tempfile
        d = tempfile.mkdtemp()
        path = os.path.join(d, "settings.json")
        open(path, "w").write("{not json")
        self.assertEqual(self.m.hooks(["--install", "--settings", path]), 1)
        self.assertEqual(open(path).read(), "{not json")

    def test_remove_roundtrip_restores_original(self):
        cur = {"model": "opus", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        merged, _ = self.m.merge_hooks(cur)
        pruned, gone = self.m.remove_hooks(merged)
        self.assertEqual(sorted(gone), ["Notification", "PostToolUse", "SessionEnd", "Stop", "UserPromptSubmit"])
        self.assertEqual(pruned, cur)

    def test_remove_from_empty_or_foreign_is_noop(self):
        for cur in ({}, {"hooks": {}}, {"hooks": {"Stop": [{"hooks": [{"command": "echo x"}]}]}}, {"hooks": "junk"}):
            pruned, gone = self.m.remove_hooks(cur)
            self.assertEqual(gone, [])
            self.assertEqual(pruned, cur)

    def test_remove_keeps_a_group_that_mixes_ours_and_theirs(self):
        cur = {"hooks": {"Stop": [{"matcher": "x", "hooks": [{"command": "/a/bin/mux-status done"},
                                                              {"command": "echo mine"}]}]}}
        pruned, gone = self.m.remove_hooks(cur)
        self.assertEqual(gone, ["Stop"])
        self.assertEqual(pruned["hooks"]["Stop"], [{"matcher": "x", "hooks": [{"command": "echo mine"}]}])

    def test_remove_command_backs_up_and_is_idempotent(self):
        import json, tempfile
        d = tempfile.mkdtemp()
        path = os.path.join(d, "settings.json")
        open(path, "w").write(json.dumps({"theme": "dark"}))
        self.m.hooks(["--install", "--settings", path])
        self.assertEqual(self.m.hooks(["--remove", "--settings", path]), 0)
        self.assertEqual(json.load(open(path)), {"theme": "dark"})
        self.assertEqual(len([f for f in os.listdir(d) if ".bak-kittymux-" in f]), 2)   # install + remove
        self.assertEqual(self.m.hooks(["--remove", "--settings", path]), 0)             # nothing left: no new backup
        self.assertEqual(len([f for f in os.listdir(d) if ".bak-kittymux-" in f]), 2)

    def test_remove_missing_file_creates_nothing(self):
        import tempfile
        d = tempfile.mkdtemp()
        path = os.path.join(d, "settings.json")
        self.assertEqual(self.m.hooks(["--remove", "--settings", path]), 0)
        self.assertFalse(os.path.exists(path))


class SocketListTests(unittest.TestCase):
    def test_a_socket_named_by_env_and_found_by_glob_is_listed_once(self):
        import socket, tempfile
        m = load()
        d = tempfile.mkdtemp(dir="/tmp")
        path = os.path.join(d, "mykitty-777")
        srv = socket.socket(socket.AF_UNIX)
        srv.bind(path)
        old = (m._socket_dirs, os.environ.get("KITTY_LISTEN_ON"))
        try:
            m._socket_dirs = lambda: [d]
            os.environ["KITTY_LISTEN_ON"] = "unix:" + path
            self.assertEqual(m._sockets(), ["unix:" + path])
        finally:
            m._socket_dirs = old[0]
            if old[1] is None:
                os.environ.pop("KITTY_LISTEN_ON", None)
            else:
                os.environ["KITTY_LISTEN_ON"] = old[1]
            srv.close()
            os.unlink(path)
            os.rmdir(d)


class BinaryReplacedTests(unittest.TestCase):
    def test_a_replaced_binary_is_detected_and_a_normal_one_is_not(self):
        m = load()
        with mock.patch.object(m.os, "readlink", return_value="/usr/bin/kitty (deleted)"):
            self.assertTrue(m.binary_replaced(123))
        with mock.patch.object(m.os, "readlink", return_value="/usr/bin/kitty"):
            self.assertFalse(m.binary_replaced(123))
        with mock.patch.object(m.os, "readlink", side_effect=OSError):
            self.assertFalse(m.binary_replaced(123))                  # gone or not ours: no claim


class ScannerAgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def test_missing_file_means_not_running(self):
        import tempfile
        self.assertIsNone(self.m.scanner_age(tempfile.mkdtemp(), 4242))

    def test_age_is_seconds_since_last_write(self):
        import tempfile, time
        d = tempfile.mkdtemp()
        path = os.path.join(d, "scan-4242.json")
        open(path, "w").write("{}")
        mtime = os.stat(path).st_mtime
        self.assertAlmostEqual(self.m.scanner_age(d, 4242, now=mtime + 7.5), 7.5, places=3)
        self.assertEqual(self.m.scanner_age(d, 4242, now=mtime - 100), 0.0)          # never negative


class TargetSocketTests(unittest.TestCase):
    """The layout command must act on the kitty that launched it — never a stale env hint."""

    def setUp(self):
        self.m = load()
        self.saved = (self.m._owned_socket, os.getppid, dict(os.environ))
        for k in ("KITTYMUX_TARGET", "KITTY_LISTEN_ON", "KITTY_PID"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.m._owned_socket, os.getppid = self.saved[0], self.saved[1]
        os.environ.clear(); os.environ.update(self.saved[2])

    def owned(self, *paths):
        self.m._owned_socket = lambda p: p in paths

    def test_parent_kitty_beats_stale_env(self):
        os.getppid = lambda: 111
        os.environ["KITTY_PID"] = "999"                       # stale (inherited from another kitty)
        os.environ["KITTY_LISTEN_ON"] = "unix:/tmp/mykitty-999"
        self.owned("/tmp/mykitty-111", "/tmp/mykitty-999")
        self.assertEqual(self.m._target_socket(), "unix:/tmp/mykitty-111")

    def test_explicit_target_wins(self):
        os.getppid = lambda: 111
        os.environ["KITTYMUX_TARGET"] = "unix:/tmp/mykitty-555"
        self.owned("/tmp/mykitty-111", "/tmp/mykitty-555")
        self.assertEqual(self.m._target_socket(), "unix:/tmp/mykitty-555")

    def test_env_used_when_parent_is_not_kitty(self):
        os.getppid = lambda: 42                               # e.g. launched from a shell
        os.environ["KITTY_PID"] = "999"
        self.owned("/tmp/mykitty-999")
        self.assertEqual(self.m._target_socket(), "unix:/tmp/mykitty-999")

    def test_unowned_sockets_are_never_trusted(self):
        os.getppid = lambda: 111
        os.environ["KITTY_LISTEN_ON"] = "unix:/tmp/mykitty-111"
        self.owned()                                          # someone else planted them
        self.m._owned_socket = lambda p: False
        import glob
        real_glob = glob.glob
        glob.glob = lambda pattern: ["/tmp/mykitty-666"]
        try:
            self.assertIsNone(self.m._target_socket())
        finally:
            glob.glob = real_glob

    def test_socket_pid_parse(self):
        self.assertEqual(self.m._socket_pid("unix:/tmp/mykitty-2165171"), 2165171)
        self.assertIsNone(self.m._socket_pid("unix:/tmp/kitty-abc"))


class UninstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def fresh(self):
        import tempfile
        t = tempfile.mkdtemp()
        cfg, home, fonts = (os.path.join(t, n) for n in ("cfg", "kittymux", "fonts"))
        os.makedirs(os.path.join(home, "python"))
        os.makedirs(cfg)
        os.makedirs(fonts)
        for n in ("tab_bar.py", "kittymux_agents.py"):
            open(os.path.join(home, "python", n), "w").write("# x\n")
            os.symlink(os.path.join(home, "python", n), os.path.join(cfg, n))
        open(os.path.join(cfg, "kittymux_mine.py"), "w").write("# not ours: a real file\n")
        os.symlink("/etc/hostname", os.path.join(cfg, "kittymux_foreign.py"))      # a link, but not into kittymux
        for n in ("kittymux-keys.conf", "include-tab-edge.conf"):
            open(os.path.join(cfg, n), "w").write("# generated\n")
        open(os.path.join(fonts, "kittymux-icons.ttf"), "w").write("x")
        open(os.path.join(cfg, "kitty.conf"), "w").write(
            "font_size 12\n\n"
            f"include {cfg}/kittymux-keys.conf\n\n"
            f"include {home}/kittymux.conf\n\n"
            f"include {cfg}/include-tab-edge.conf\n\n"
            f"geninclude {home}/python/kittymux_layout.py\n"
            "include my-other.conf\n")
        return cfg, home, fonts

    def test_plan_finds_only_what_install_added(self):
        cfg, home, fonts = self.fresh()
        plan = self.m.plan_uninstall(cfg, home, fonts)
        self.assertEqual(len(plan["conf_lines"]), 4)
        self.assertEqual(sorted(os.path.basename(p) for p in plan["links"]), ["kittymux_agents.py", "tab_bar.py"])
        self.assertEqual(sorted(os.path.basename(p) for p in plan["files"]), ["include-tab-edge.conf", "kittymux-keys.conf"])
        self.assertTrue(plan["font"])

    def test_apply_removes_them_keeps_everything_else_and_backs_up(self):
        cfg, home, fonts = self.fresh()
        self.m.apply_uninstall(self.m.plan_uninstall(cfg, home, fonts), cfg, "T")
        text = open(os.path.join(cfg, "kitty.conf")).read()
        self.assertEqual(text, "font_size 12\n\ninclude my-other.conf\n")
        self.assertTrue(os.path.exists(os.path.join(cfg, "kitty.conf.bak.kittymux-uninstall-T")))
        self.assertFalse(os.path.lexists(os.path.join(cfg, "tab_bar.py")))
        self.assertTrue(os.path.exists(os.path.join(cfg, "kittymux_mine.py")))               # a real file stays
        self.assertTrue(os.path.lexists(os.path.join(cfg, "kittymux_foreign.py")))           # a foreign link stays
        self.assertFalse(os.path.exists(os.path.join(fonts, "kittymux-icons.ttf")))

    def test_a_second_pass_finds_nothing(self):
        cfg, home, fonts = self.fresh()
        self.m.apply_uninstall(self.m.plan_uninstall(cfg, home, fonts), cfg, "T")
        plan = self.m.plan_uninstall(cfg, home, fonts)
        self.assertEqual((plan["conf_lines"], plan["links"], plan["files"], plan["font"]), ([], [], [], None))

    def test_dry_run_changes_nothing(self):
        import io, contextlib
        cfg, home, fonts = self.fresh()
        before = open(os.path.join(cfg, "kitty.conf")).read()
        old = (self.m.CFG, self.m.HOME_DIR)
        self.m.CFG, self.m.HOME_DIR = cfg, home
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(self.m.uninstall([]), 0)
        finally:
            self.m.CFG, self.m.HOME_DIR = old
        self.assertEqual(open(os.path.join(cfg, "kitty.conf")).read(), before)
        self.assertIn("dry run", out.getvalue())


if __name__ == "__main__":
    unittest.main()


class ResumePromptTests(unittest.TestCase):
    """The prompt a restored agent window runs, driven through a real pty — the way kitty runs it."""
    SID = "0a1b2c3d-0000-4000-8000-000000000001"

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.bin)
        self.out = os.path.join(self.tmp.name, "ran")
        for name in ("claude", "fakeshell"):
            with open(os.path.join(self.bin, name), "w") as f:
                f.write('#!/bin/sh\necho "%s $*" > "$RAN"\n' % name)
            os.chmod(os.path.join(self.bin, name), 0o755)
        self.env = dict(os.environ, KITTYMUX_STATE=self.tmp.name, RAN=self.out, PATH=self.bin + ":/usr/bin:/bin", SHELL=os.path.join(self.bin, "fakeshell"),
                        XDG_CONFIG_HOME=os.path.join(self.tmp.name, "xdg"))
        self.env.pop("KITTYMUX_RESUME", None)
        sys_path = os.path.join(ROOT, "python")
        import sys
        sys.path.insert(0, sys_path)
        import kittymux_resume as R
        self.info = R.prompt_info("claude", "exact", self.SID, ["claude", "--model", "x"], ["claude", "--model", "x", "--resume", self.SID])

    def tearDown(self):
        self.tmp.cleanup()

    def run_prompt(self, keys, info=None, env=None):
        """Run the prompt on a pty, send `keys` once it is showing, return (what ran, the screen text)."""
        import pty
        import select
        import time
        pid, fd = pty.fork()
        if pid == 0:
            os.execve(os.path.join(ROOT, "bin", "kittymux"), ["kittymux", "resume-prompt", "--info", info or self.info], env or self.env)
        screen, sent, deadline = b"", False, time.time() + 10
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], 0.2)
            if r:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                screen += chunk
            if not sent and b"commands" in screen and keys is not None:
                for key in ([keys] if isinstance(keys, bytes) else keys):
                    time.sleep(0.3)
                    os.write(fd, key)
                sent = True
            done, _ = os.waitpid(pid, os.WNOHANG)
            if done:
                break
        else:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
            self.fail("the prompt did not finish: " + screen.decode(errors="replace"))
        ran = open(self.out).read().strip() if os.path.exists(self.out) else ""
        return ran, screen.decode(errors="replace")

    def test_enter_resumes_the_conversation_with_every_flag(self):
        ran, screen = self.run_prompt(b"\r")
        self.assertEqual(ran, "claude --model x --resume " + self.SID)
        self.assertIn("resume session 0a1b2c3d", screen)

    def test_n_starts_a_new_conversation_with_the_original_command(self):
        self.assertEqual(self.run_prompt(b"n")[0], "claude --model x")

    def test_s_and_a_lone_escape_open_a_shell(self):
        self.assertEqual(self.run_prompt(b"s")[0], "fakeshell")
        self.assertEqual(self.run_prompt(b"\x1b")[0], "fakeshell")

    def test_a_resumes_and_answers_the_other_waiting_prompts(self):
        self.assertEqual(self.run_prompt(b"a")[0], "claude --model x --resume " + self.SID)
        until = float(open(os.path.join(self.tmp.name, "resume-all-until")).read())
        self.assertGreater(until, __import__("time").time() + 60)
        ran, screen = self.run_prompt(None)                                           # the next restored window does not even ask
        self.assertEqual(ran, "claude --model x --resume " + self.SID)

    def test_auto_mode_never_asks(self):
        ran, screen = self.run_prompt(None, env=dict(self.env, KITTYMUX_RESUME="auto"))
        self.assertEqual(ran, "claude --model x --resume " + self.SID)
        self.assertNotIn("Enter", screen)

    def test_i_shows_both_commands_and_keeps_waiting(self):
        import time
        ran, screen = self.run_prompt([b"i", b"s"])           # "i" prints and keeps waiting; "s" then leaves
        self.assertEqual(ran, "fakeshell")
        self.assertIn("--resume " + self.SID, screen)

    def test_the_window_is_titled_while_it_asks_and_the_title_is_cleared_before_the_agent_takes_over(self):
        """An unnamed restored tab showed "python" (the prompt's own process); and an agent that never sets a title must not be left with a stale one."""
        asking = "\x1b]2;↻ claude — resume?\x07"
        clear = "\x1b]2;\x07"
        for keys in (b"\r", b"n", b"s", b"a"):
            ran, screen = self.run_prompt(keys)
            self.assertIn(asking, screen, keys)
            self.assertGreater(screen.rindex(clear), screen.index(asking), keys)           # cleared AFTER it was set, i.e. before the exec

    def test_a_hostile_agent_name_in_a_session_file_cannot_inject_into_the_title(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "python"))
        import kittymux_resume as R
        info = R.prompt_info("claude", "exact", self.SID, ["claude"], ["claude", "--resume", self.SID])
        hostile = info.replace('"agent": "claude"', '"agent": "cl\\u001b]0;pwned\\u0007aude"')
        ran, screen = self.run_prompt(b"s", info=hostile)
        self.assertNotIn("pwned\x07", screen.replace("\x1b]2;↻", ""))                  # whatever the validator did with it, no raw OSC from the name

    def test_an_invalid_record_opens_a_shell_instead_of_running_anything(self):
        ran, screen = self.run_prompt(None, info='{"agent":"claude","mode":"exact","sid":"","orig":["claude"],"resume":["rm","-rf","x"]}')
        self.assertEqual(ran, "fakeshell")
        self.assertIn("do not understand", screen)

    def test_a_missing_agent_falls_back_to_a_shell(self):
        os.unlink(os.path.join(self.bin, "claude"))
        ran, screen = self.run_prompt(b"\r")
        self.assertEqual(ran, "fakeshell")
        self.assertIn("not on PATH", screen)


class FeaturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def run_cmd(self, *argv, nudged=1, extra_env=None):
        import contextlib
        import io
        import tempfile
        sdir = tempfile.mkdtemp()
        env = {"KITTYMUX_STATE": sdir, **(extra_env or {})}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(self.m, "_nudge_bars", return_value=nudged), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            for k in [k for k in os.environ if k.startswith("KITTYMUX_") and k not in env]:
                os.environ.pop(k)
            rc = self.m.features_cmd(list(argv))
        return rc, out.getvalue(), err.getvalue(), sdir

    def test_list_shows_every_feature_and_where_it_comes_from(self):
        rc, out, _err, _ = self.run_cmd()
        self.assertEqual(rc, 0)
        for name in ("folder", "hue", "collide", "sheet", "hover", "panetitle"):
            self.assertIn(name, out)
        self.assertIn("default", out)

    def test_off_and_on_round_trip(self):
        rc, out, _e, sdir = self.run_cmd("off", "hue")
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(os.path.join(sdir, "hue-off")))

    def test_preset_and_unknown_names(self):
        rc, _o, _e, sdir = self.run_cmd("preset", "minimal")
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(os.path.join(sdir, "hue-off")))
        rc, _o, err, _ = self.run_cmd("on", "nonsense")
        self.assertEqual(rc, 2)
        self.assertIn("unknown feature", err)
        rc, _o, err, _ = self.run_cmd("preset", "loud")
        self.assertEqual(rc, 2)

    def test_usage_on_garbage(self):
        rc, _o, err, _ = self.run_cmd("frobnicate")
        self.assertEqual(rc, 2)
        self.assertIn("usage: kittymux features", err)

    def test_an_env_override_is_called_out(self):
        import contextlib
        import io
        import tempfile
        sdir = tempfile.mkdtemp()
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"KITTYMUX_STATE": sdir, "KITTYMUX_HUE": "off"}), mock.patch.object(self.m, "_nudge_bars"), \
                contextlib.redirect_stdout(out):
            self.m.features_cmd(["on", "hue"])
        self.assertIn("KITTYMUX_HUE", out.getvalue())

    def test_pieces_that_do_not_exist_yet_say_so(self):
        """`off sheet` must not look like it stopped something: nothing reads that switch yet."""
        _rc, out, _e, _ = self.run_cmd()
        for name in ("sheet", "hover"):
            line = next(ln for ln in out.splitlines() if ln.split()[:1] == [name])
            self.assertIn("planned", line, line)
        for name in ("folder", "hue", "collide", "panetitle"):
            line = next(ln for ln in out.splitlines() if ln.split()[:1] == [name])
            self.assertNotIn("planned", line, line)
        rc, out, _e, sdir = self.run_cmd("off", "sheet")
        self.assertEqual(rc, 0)
        self.assertIn("not built yet", out)
        self.assertTrue(os.path.exists(os.path.join(sdir, "sheet-off")))      # still saved, for when it exists
        rc, out, _e, _ = self.run_cmd("off", "hue")
        self.assertNotIn("not built yet", out)

    def test_help_prints_usage_and_succeeds(self):
        for flag in ("-h", "--help", "help"):
            rc, out, err, _ = self.run_cmd(flag)
            self.assertEqual(rc, 0, flag)
            self.assertIn("usage: kittymux features", out)
            self.assertEqual(err, "")

    def test_features_is_in_the_help_the_cli_prints(self):
        self.assertIn("kittymux features", self.m.__doc__)

    def test_the_env_note_only_fires_for_a_value_that_actually_wins(self):
        _rc, out, _e, _ = self.run_cmd("on", "hue", extra_env={"KITTYMUX_HUE": "banana"})
        self.assertNotIn("KITTYMUX_HUE", out)                  # garbage is ignored by the resolver, so it does not "win"
        _rc, out, _e, _ = self.run_cmd("on", "hue", extra_env={"KITTYMUX_HUE": "off"})
        self.assertIn("KITTYMUX_HUE", out)

    def test_an_unwritable_state_dir_is_a_message_not_a_traceback(self):
        with mock.patch.object(self.m.kittymux_features, "set_feature", side_effect=PermissionError("denied")):
            rc, out, err, _ = self.run_cmd("off", "hue")
        self.assertEqual(rc, 1)
        self.assertIn("denied", err)
        self.assertNotIn("Traceback", err)

    def test_it_says_how_many_kitties_it_reloaded(self):
        _rc, out, _e, _ = self.run_cmd("off", "hue", nudged=2)
        self.assertIn("reloaded 2 kitties", out)
        _rc, out, _e, _ = self.run_cmd("off", "hue", nudged=1)
        self.assertIn("reloaded 1 kitty", out)
        _rc, out, _e, _ = self.run_cmd("off", "hue", nudged=0)
        self.assertIn("no running kitty found", out)


class KeysCmdTests(unittest.TestCase):
    """`kittymux keys`: chords that BOTH your kitty config and kittymux define. kitty reads kittymux-keys.conf after your files and the last
    definition wins — a clash silently switches your own shortcut off."""

    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        with open(os.path.join(d, "kitty.conf"), "w") as f:
            f.write("include userprefs.conf\ninclude %s/kittymux-keys.conf\n" % d)
        with open(os.path.join(d, "userprefs.conf"), "w") as f:
            f.write("map ctrl+alt+shift+h launch --type=background /x/scratch-tab.sh --cwd /home/u/.config/hypr -- nvim\n"
                    "map ctrl+alt+q close_window_with_confirmation\n")
        with open(os.path.join(d, "kittymux-keys.conf"), "w") as f:
            f.write("map ctrl+alt+shift+h toggle_window_title_bars\nmap ctrl+alt+q close_window_with_confirmation\nmap ctrl+alt+z layout_action maximize\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_keys(self, *argv):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(self.m, "CFG", self.tmp.name), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = self.m.keys_cmd(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_it_lists_a_chord_both_define_with_different_actions_and_who_wins(self):
        rc, out, _e = self.run_keys()
        self.assertEqual(rc, 0)
        self.assertIn("ctrl+alt+shift+h", out)
        self.assertIn("userprefs.conf", out)
        self.assertIn("scratch-tab.sh", out)
        self.assertIn("toggle_window_title_bars", out)
        self.assertNotIn("ctrl+alt+q", out)                           # same action in both: not a clash
        self.assertIn("kittymux", out.split("ctrl+alt+shift+h")[0])   # the header says kittymux's wins

    def test_it_says_so_when_nothing_clashes(self):
        with open(os.path.join(self.tmp.name, "userprefs.conf"), "w") as f:
            f.write("map ctrl+alt+x launch htop\n")
        rc, out, _e = self.run_keys("conflicts")
        self.assertEqual(rc, 0)
        self.assertIn("no chord is defined by both", out)

    def test_a_missing_kittymux_file_or_config_is_not_an_error(self):
        os.unlink(os.path.join(self.tmp.name, "kittymux-keys.conf"))
        rc, out, _e = self.run_keys()
        self.assertEqual(rc, 0)
        self.assertIn("no chord is defined by both", out)

    def test_junk_arguments_get_usage(self):
        rc, _o, err = self.run_keys("frobnicate")
        self.assertEqual(rc, 2)
        self.assertIn("usage: kittymux keys", err)


class JoinCmdTests(unittest.TestCase):
    """`kittymux join`: the chord's twin for a shell. It only validates and hands over to python/join-kit.py in the kitty it was started inside."""

    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def run_join(self, argv, sock="unix:/nonexistent/mykitty-1", win="7"):
        import io
        from contextlib import redirect_stderr
        from unittest.mock import patch
        err = io.StringIO()
        calls = []
        with patch.object(self.m, "_own_kitty_socket", return_value=sock), \
                patch.dict(os.environ, {"KITTY_WINDOW_ID": win} if win else {}, clear=False), \
                patch.object(self.m.subprocess, "run", side_effect=lambda cmd, **kw: calls.append(cmd) or type("R", (), {"returncode": 0})()), \
                redirect_stderr(err):
            if not win:
                os.environ.pop("KITTY_WINDOW_ID", None)
            rc = self.m.join_cmd(argv)
        return rc, err.getvalue(), calls

    def test_junk_arguments_are_refused_with_usage(self):
        for argv in (["--to"], ["--to", "abc"], ["--to", "-3"], ["--side", "sideways"], ["--side"], ["nope"], ["--pane", "--what"]):
            rc, err, calls = self.run_join(argv)
            self.assertEqual(rc, 2, argv)
            self.assertIn("usage: kittymux join", err)
            self.assertEqual(calls, [], "nothing may run for bad input")

    def test_outside_a_kitty_it_says_so_and_runs_nothing(self):
        rc, err, calls = self.run_join([], sock=None)
        self.assertEqual(rc, 1)
        self.assertIn("run it from a pane", err)
        self.assertEqual(calls, [])
        rc, err, calls = self.run_join([], win="")
        self.assertEqual(rc, 1)
        self.assertEqual(calls, [])

    def test_it_hands_over_to_the_kitten_in_this_kitty_for_this_pane(self):
        rc, _err, calls = self.run_join(["--to", "12", "--side", "below", "--pane"])
        self.assertEqual(rc, 0)
        cmd = calls[0]
        self.assertEqual(cmd[:6], ["kitty", "@", "--to", "unix:/nonexistent/mykitty-1", "kitten", "--match"])
        self.assertEqual(cmd[6], "id:7")
        self.assertTrue(cmd[7].endswith("python/join-kit.py"))
        self.assertEqual(cmd[8:], ["--to", "12", "--side", "below", "--pane"])

    def test_without_a_target_the_picker_opens(self):
        rc, _err, calls = self.run_join([])
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0][8:], [])


class PeekCmdTests(unittest.TestCase):
    """`kittymux peek [TAB_ID | --waiting]`: opens the peek card (python/peek-kit.py) over the pane it is run from, for this tab, a given tab or the agent that needs you most."""
    LS = [{"id": 1, "tabs": [{"id": 10, "windows": [{"id": 7}, {"id": 8, "is_focused": True}]}, {"id": 11, "windows": [{"id": 9}]}]}]

    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def run_peek(self, argv, sock="unix:/nonexistent/mykitty-200", win="7", rows_target=None, ls=None):
        import io
        from contextlib import redirect_stderr
        from unittest.mock import patch
        err, calls, notes = io.StringIO(), [], []
        with patch.object(self.m, "_own_kitty_socket", return_value=sock), \
                patch.object(self.m, "_ls", return_value=self.LS if ls is None else ls), \
                patch.object(self.m, "_pick_data", return_value=([], [], [], [])), \
                patch.object(self.m.kittymux_launcher, "build_rows", return_value=[]), \
                patch.object(self.m.kittymux_launcher, "needs_you_target", return_value=rows_target), \
                patch.object(self.m, "_notify", side_effect=notes.append), \
                patch.dict(os.environ, {"KITTY_WINDOW_ID": win} if win else {}, clear=False), \
                patch.object(self.m.subprocess, "run", side_effect=lambda cmd, **kw: calls.append(cmd) or type("R", (), {"returncode": 0})()), \
                redirect_stderr(err):
            if not win:
                os.environ.pop("KITTY_WINDOW_ID", None)
            rc = self.m.peek_cmd(argv)
        return rc, err.getvalue(), calls, notes

    def test_junk_arguments_are_refused_with_usage(self):
        for argv in (["abc"], ["-3"], ["--tab"], ["12", "13"], ["--waiting", "12"], ["--what"]):
            rc, err, calls, _ = self.run_peek(argv)
            self.assertEqual(rc, 2, argv)
            self.assertIn("usage: kittymux peek", err)
            self.assertEqual(calls, [])

    def test_outside_a_kitty_it_says_so_and_runs_nothing(self):
        rc, err, calls, _ = self.run_peek([], sock=None)
        self.assertEqual(rc, 1)
        self.assertIn("run it from a pane", err)
        self.assertEqual(calls, [])

    def test_a_key_bound_launch_uses_the_focused_pane_not_its_own_hidden_window(self):
        """`launch --type=background` runs us in a hidden window with its own id (KITTY_WINDOW_ID): that is not a pane of any tab and `--match id:` finds nothing."""
        rc, _err, calls, _ = self.run_peek([], win="5")                     # 5 is not in `ls`; window 8 is the focused one (tab 10)
        self.assertEqual(rc, 0)
        self.assertEqual((calls[0][6], calls[0][8:]), ("id:8", ["10"]))
        rc, _err, calls, _ = self.run_peek([], win="")                      # no id at all
        self.assertEqual((rc, calls[0][6]), (0, "id:8"))

    def test_with_no_pane_to_show_the_card_over_it_says_so(self):
        ls = [{"id": 1, "tabs": [{"id": 10, "windows": [{"id": 7}]}]}]       # nothing focused
        rc, err, calls, _ = self.run_peek([], win="5", ls=ls)
        self.assertEqual(rc, 1)
        self.assertEqual(calls, [])
        self.assertIn("focused", err)

    def test_with_no_argument_it_peeks_at_this_panes_tab(self):
        rc, _err, calls, _ = self.run_peek([], win="9")
        self.assertEqual(rc, 0)
        cmd = calls[0]
        self.assertEqual(cmd[:6], ["kitty", "@", "--to", "unix:/nonexistent/mykitty-200", "kitten", "--match"])
        self.assertEqual(cmd[6], "id:9")
        self.assertTrue(cmd[7].endswith("python/peek-kit.py"))
        self.assertEqual(cmd[8:], ["11"])                                   # window 9 lives in tab 11

    def test_a_tab_id_is_passed_through_when_this_kitty_has_it(self):
        rc, _err, calls, _ = self.run_peek(["10"])
        self.assertEqual((rc, calls[0][8:]), (0, ["10"]))

    def test_a_tab_this_kitty_does_not_have_is_refused(self):
        rc, err, calls, _ = self.run_peek(["99"])
        self.assertEqual(rc, 1)
        self.assertIn("no tab 99", err)
        self.assertEqual(calls, [])

    def test_waiting_peeks_at_the_tab_of_the_agent_that_needs_you(self):
        rc, _err, calls, _ = self.run_peek(["--waiting"], win="7", rows_target="9")
        self.assertEqual((rc, calls[0][6], calls[0][8:]), (0, "id:7", ["11"]))          # shown over THIS pane (7), about the tab of window 9

    def test_waiting_with_nothing_waiting_says_so_without_opening_anything(self):
        rc, err, calls, notes = self.run_peek(["--waiting"], rows_target=None)
        self.assertEqual(rc, 1)
        self.assertIn("needs you", err)
        self.assertEqual(calls, [])
        self.assertEqual(len(notes), 1)                                   # a key-bound command has no terminal: the message must reach the desktop

    def test_waiting_whose_window_is_gone_is_refused(self):
        rc, err, calls, _ = self.run_peek(["--waiting"], rows_target="555")
        self.assertEqual(rc, 1)
        self.assertEqual(calls, [])


class UsageLaunchTests(unittest.TestCase):
    def setUp(self):
        self.m = load()

    def test_picker_usage_entry_is_available_without_any_agents(self):
        with mock.patch.object(self.m, "_focused_socket", return_value=None), mock.patch.object(self.m, "_pick_data", return_value=([], [], [], [])), mock.patch.object(self.m, "_focus_cwd", return_value=""), mock.patch.object(self.m, "_risk_table", return_value={}), mock.patch("builtins.print") as out:
            self.assertEqual(self.m.pick(["--json"]), 0)
            rows = json.loads(out.call_args.args[0])
        self.assertEqual(rows[0]["action"]["op"], "usage")

    def test_global_usage_opens_separate_window_and_clears_parent_identity(self):
        with mock.patch.dict(os.environ, KITTY_PID="7", KITTY_WINDOW_ID="8", KITTY_LISTEN_ON="unix:/synthetic", KITTYMUX_TARGET="unix:/synthetic"), mock.patch.object(self.m.subprocess, "Popen") as start:
            self.assertEqual(self.m.usage_cmd(["--window"]), 0)
        args, kw = start.call_args
        self.assertIn("kittymux-usage", args[0])
        self.assertTrue(kw["start_new_session"])
        self.assertNotIn("KITTY_PID", kw["env"])
        self.assertNotIn("KITTYMUX_TARGET", kw["env"])

    def test_inside_kitty_usage_uses_own_socket(self):
        with mock.patch.object(self.m, "_own_kitty_socket", return_value="unix:/own"), mock.patch.object(self.m.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as rc, mock.patch.dict(os.environ, KITTY_WINDOW_ID="8"):
            self.assertEqual(self.m.usage_cmd([]), 0)
        self.assertIn("unix:/own", rc.call_args.args[0])
        self.assertIn("--match", rc.call_args.args[0])
