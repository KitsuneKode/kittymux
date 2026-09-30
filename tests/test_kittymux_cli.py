import importlib.machinery
import importlib.util
import os
import unittest

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


if __name__ == "__main__":
    unittest.main()
