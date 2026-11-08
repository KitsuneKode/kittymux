"""The attention ring: a split pane whose agent needs you gets kitty's bell colour on its divider (needs_attention), set without a bell."""
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_scan as KS  # noqa: E402


class Win:
    def __init__(self, wid, tab):
        self.id = wid
        self.needs_attention = False
        self._tab = tab

    def tabref(self):
        return self._tab


class RingTests(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, KITTYMUX_STATE=self.state)
        self.env.start()
        self.addCleanup(self.env.stop)
        KS._RT.verdicts.clear()
        vars(KS._RT).pop("rings", None)
        self.tab = types.SimpleNamespace(relayouts=0)
        self.tab.relayout_borders = lambda: setattr(self.tab, "relayouts", self.tab.relayouts + 1)
        self.here, self.there = Win(1, self.tab), Win(2, self.tab)
        self.boss = types.SimpleNamespace(all_windows=[self.here, self.there], active_window=self.here)

    def verdict(self, wid, state):
        KS._RT.verdicts[str(wid)] = {"state": state}

    def sync(self):
        KS._sync_rings(self.boss, {"1", "2"})

    def test_the_rule(self):
        self.assertTrue(KS.ring_wanted("waiting", False, False))
        self.assertTrue(KS.ring_wanted("limited", False, False))
        for args in (("working", False, False), ("done", False, False), ("waiting", True, False), ("waiting", False, True), ("waiting", False, False, False)):
            self.assertFalse(KS.ring_wanted(*args), args)

    def test_a_split_pane_that_asks_is_marked_and_unmarked_when_it_stops(self):
        self.verdict(2, "waiting")
        self.sync()
        self.assertTrue(self.there.needs_attention)
        self.assertFalse(self.here.needs_attention)               # the pane you are in is never marked
        self.assertEqual(self.tab.relayouts, 1)
        self.sync()
        self.assertEqual(self.tab.relayouts, 1)                   # no change, no relayout
        self.verdict(2, "working")
        self.sync()
        self.assertFalse(self.there.needs_attention)
        self.assertEqual(self.tab.relayouts, 2)

    def test_a_real_bell_mark_is_never_taken_away(self):
        self.there.needs_attention = True                         # kitty set it: a bell rang there
        self.verdict(2, "working")
        self.sync()
        self.assertTrue(self.there.needs_attention)
        self.assertEqual(self.tab.relayouts, 0)

    def test_focusing_the_pane_lets_kitty_clear_it(self):
        self.verdict(2, "waiting")
        self.sync()
        self.there.needs_attention = False                        # you focused it: kitty cleared the flag
        self.boss.active_window = self.there
        self.sync()
        self.assertFalse(self.there.needs_attention)
        self.assertNotIn("2", vars(KS._RT)["rings"])

    def test_muted_and_switched_off_are_never_marked(self):
        self.verdict(2, "waiting")
        with mock.patch.object(KS, "_switch", return_value=False):
            self.sync()
        self.assertFalse(self.there.needs_attention)
        import kittymux_quiet
        kittymux_quiet.set_muted(self.state, os.getpid(), 2, True)
        self.sync()
        self.assertFalse(self.there.needs_attention)


if __name__ == "__main__":
    unittest.main()
