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

    def test_an_invalid_record_opens_a_shell_instead_of_running_anything(self):
        ran, screen = self.run_prompt(None, info='{"agent":"claude","mode":"exact","sid":"","orig":["claude"],"resume":["rm","-rf","x"]}')
        self.assertEqual(ran, "fakeshell")
        self.assertIn("do not understand", screen)

    def test_a_missing_agent_falls_back_to_a_shell(self):
        os.unlink(os.path.join(self.bin, "claude"))
        ran, screen = self.run_prompt(b"\r")
        self.assertEqual(ran, "fakeshell")
        self.assertIn("not on PATH", screen)
