import importlib.machinery
import importlib.util
import os
import stat
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load(state_dir):
    os.environ["KITTYMUX_STATE"] = state_dir
    loader = importlib.machinery.SourceFileLoader("pane_state_under_test", os.path.join(ROOT, "python", "pane-state.py"))
    spec = importlib.util.spec_from_loader("pane_state_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class HygieneTests(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(tempfile.mkdtemp(), "state")     # does not exist yet
        self.m = load(self.dir)

    def tearDown(self):
        os.environ.pop("KITTYMUX_STATE", None)

    def test_state_dir_and_file_are_private(self):
        self.m._state[1] = {"title": "secret project", "msg": "token?"}
        self.m._flush(1.0, force=True)
        self.assertEqual(stat.S_IMODE(os.stat(self.dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(self.m.STATE_FILE).st_mode), 0o600)
        self.assertFalse([n for n in os.listdir(self.dir) if n.endswith(".tmp")])

    def test_clean_strips_control_sequences(self):
        out = self.m._clean("a\x1b[2J\x1b]0;x\x07b\r\n\x00c")
        self.assertTrue(all(ord(c) >= 32 and ord(c) != 127 for c in out))
        self.assertEqual(len(self.m._clean("y" * 999)), 120)

    def test_notification_text_is_escaped_and_bounded(self):
        out = self.m._plain("<b>bold</b> & <a href='x'>link</a>", 200)
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)
        self.assertIn("&amp;", out)
        self.assertLessEqual(len(self.m._plain("z" * 500, 60)), 60)

    def test_stale_files_of_dead_kitties_are_removed(self):
        os.makedirs(self.dir, mode=0o700)
        dead, alive = 2 ** 22 + 777, os.getpid()
        keep = os.path.join(self.dir, f"panes-{os.getppid()}.json")
        for name in (f"panes-{dead}.json", f"panes-{dead}.json.tmp", f"panes-{alive}.json", "agent-usage.json", "keep.txt"):
            open(os.path.join(self.dir, name), "w").close()
        open(keep, "w").close()
        self.m._cleanup_stale()
        left = sorted(os.listdir(self.dir))
        self.assertNotIn(f"panes-{dead}.json", left)
        self.assertNotIn(f"panes-{dead}.json.tmp", left)
        for name in (f"panes-{alive}.json", "agent-usage.json", "keep.txt", os.path.basename(keep)):
            self.assertIn(name, left)

    def test_user_var_message_is_sanitized_on_arrival(self):
        class W:                                       # minimal stand-in for a kitty Window
            id = 7
            title = "t"
            def tabref(self):
                return None
        self.m.on_set_user_var(None, W(), {"key": "kittymux_msg", "value": "hi\x1b[31m\x07there"})
        self.assertEqual(self.m._state[7]["msg"], "hi [31m there")
        self.m.on_set_user_var(None, W(), {"key": "unrelated", "value": "x"})
        self.assertNotIn("unrelated", self.m._state[7])


if __name__ == "__main__":
    unittest.main()
