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

    def test_invalid_json_untouched(self):
        import tempfile
        d = tempfile.mkdtemp()
        path = os.path.join(d, "settings.json")
        open(path, "w").write("{not json")
        self.assertEqual(self.m.hooks(["--install", "--settings", path]), 1)
        self.assertEqual(open(path).read(), "{not json")


if __name__ == "__main__":
    unittest.main()
