import importlib.machinery
import importlib.util
import os
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

    def test_real_template_parses(self):
        tpl = open(os.path.join(ROOT, "kittymux-keys.conf.tpl"), encoding="utf-8").read()
        self.assertEqual(self.m.conflicts_from_binds([], tpl), [])


class HooksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def test_adds_three_events_to_empty(self):
        merged, added = self.m.merge_hooks({})
        self.assertEqual(sorted(added), ["Notification", "Stop", "UserPromptSubmit"])
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
        self.assertEqual(sorted(gone), ["Notification", "Stop", "UserPromptSubmit"])
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
