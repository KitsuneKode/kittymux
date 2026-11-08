"""Mute an agent (Rex adoption): no notifications, no needs-you chip, still listed with a quiet bell-slash; every event still reaches the inbox."""
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_quiet as Q  # noqa: E402


class MuteStoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_mute_and_unmute_one_window(self):
        self.assertEqual(Q.load_mutes(self.dir, 4242), set())
        self.assertTrue(Q.set_muted(self.dir, 4242, 7, True))
        self.assertEqual(Q.load_mutes(self.dir, 4242), {"7"})
        self.assertFalse(Q.set_muted(self.dir, 4242, 7, True))          # already muted: no change
        self.assertTrue(Q.is_muted(self.dir, 4242, 7))
        self.assertFalse(Q.is_muted(self.dir, 4243, 7))                 # another kitty's window 7 is another window
        self.assertTrue(Q.set_muted(self.dir, 4242, 7, False))
        self.assertFalse(Q.is_muted(self.dir, 4242, 7))

    def test_the_file_is_private_and_a_bad_one_mutes_nothing(self):
        Q.set_muted(self.dir, 4242, 7, True)
        self.assertEqual(stat.S_IMODE(os.stat(Q.mutes_path(self.dir, 4242)).st_mode), 0o600)
        with open(Q.mutes_path(self.dir, 4242), "w") as f:
            f.write("{not json")
        self.assertEqual(Q.load_mutes(self.dir, 4242), set())
        with open(Q.mutes_path(self.dir, 4242), "w") as f:
            f.write('["7", "x", 9]')
        self.assertEqual(Q.load_mutes(self.dir, 4242), {"7", "9"})

    def test_prune_keeps_only_live_windows(self):
        for w in (1, 2, 3):
            Q.set_muted(self.dir, 4242, w, True)
        Q.prune_mutes(self.dir, 4242, {"2", "5"})
        self.assertEqual(Q.load_mutes(self.dir, 4242), {"2"})

    def test_a_muted_window_is_quiet_and_says_why(self):
        self.assertIsNone(Q.quiet_reason(self.dir, 4242, 7))
        Q.set_muted(self.dir, 4242, 7, True)
        why = Q.quiet_reason(self.dir, 4242, 7)
        self.assertIn("muted", why)
        self.assertIn("inbox", why)                                     # kept quiet is not lost
        self.assertIsNone(Q.quiet_reason(self.dir, 4242, 8))


if __name__ == "__main__":
    unittest.main()


class TabWindowsTests(unittest.TestCase):
    """`kittymux mute [TAB]`: which windows a tab names."""

    def ls(self):
        def w(i, agent=None):
            return {"id": i, "foreground_processes": [{"cmdline": [agent] if agent else ["zsh"]}]}
        return [{"id": 1, "is_focused": False, "tabs": [{"id": 9, "title": "elsewhere", "windows": [w(90, "claude")]}]},
                {"id": 2, "is_focused": True, "tabs": [
                    {"id": 3, "title": "api server", "windows": [w(30)]},
                    {"id": 4, "title": "Pricing review", "windows": [w(40, "codex"), w(41), w(42, "opencode")]}]}]

    def test_no_tab_is_the_tab_you_run_it_in_and_only_its_agents(self):
        self.assertEqual(Q.tab_windows(self.ls(), "", 41), ("Pricing review", [40, 42]))

    def test_a_number_is_the_tab_in_the_focused_os_window(self):
        self.assertEqual(Q.tab_windows(self.ls(), "2", None), ("Pricing review", [40, 42]))
        self.assertEqual(Q.tab_windows(self.ls(), "1", None), ("api server", [30]))      # no agent: the tab's windows
        self.assertIsNone(Q.tab_windows(self.ls(), "7", None))

    def test_an_id_or_a_title(self):
        self.assertEqual(Q.tab_windows(self.ls(), "id:9", None), ("elsewhere", [90]))
        self.assertEqual(Q.tab_windows(self.ls(), "pricing", None), ("Pricing review", [40, 42]))
        self.assertIsNone(Q.tab_windows(self.ls(), "nothing like it", None))
        self.assertIsNone(Q.tab_windows(self.ls(), "", None))                           # outside kitty with no TAB: nothing to guess
