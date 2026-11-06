"""Confirm closing a busy agent (Rex adoption): one line in the pane's title bar, the same key again closes."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_closeguard as G  # noqa: E402


class GuardTests(unittest.TestCase):
    def setUp(self):
        G.clear()

    def test_nothing_busy_closes_at_once(self):
        self.assertEqual(G.busy_windows({"1": "idle", "2": "done", "3": ""}, [1, 2, 3]), [])
        self.assertEqual(G.decide("window", 1, [], now=10.0), "close")

    def test_working_and_needs_you_are_busy(self):
        self.assertEqual(G.busy_windows({"1": "working", "2": "waiting", "3": "limited", "4": "error", "5": "done"}, [1, 2, 3, 4, 5]), [1, 2, 3])

    def test_a_busy_agent_asks_then_the_same_key_again_closes(self):
        self.assertEqual(G.decide("window", 7, [7], now=10.0), "ask")
        self.assertTrue(G.asking(7, now=11.0))
        self.assertFalse(G.asking(8, now=11.0))
        self.assertEqual(G.decide("window", 7, [7], now=12.0), "close")
        self.assertFalse(G.asking(7, now=12.1))

    def test_the_question_lapses(self):
        self.assertEqual(G.decide("window", 7, [7], now=10.0), "ask")
        self.assertFalse(G.asking(7, now=10.0 + G.CONFIRM_S + 0.01))
        self.assertEqual(G.decide("window", 7, [7], now=10.0 + G.CONFIRM_S + 0.01), "ask")   # asks again, never a silent close

    def test_another_target_or_kind_does_not_confirm(self):
        G.decide("window", 7, [7], now=10.0)
        self.assertEqual(G.decide("window", 8, [8], now=10.5), "ask")
        self.assertEqual(G.decide("tab", 8, [8], now=10.6), "ask")
        self.assertEqual(G.decide("tab", 8, [8], now=10.7), "close")

    def test_a_tab_asks_on_every_busy_pane(self):
        G.decide("tab", 3, [7, 9], now=10.0)
        self.assertTrue(G.asking(7, now=10.1) and G.asking(9, now=10.1))

    def test_the_lapse_timer_drops_an_expired_question_and_keeps_a_live_one(self):
        import time
        G.decide("window", 7, [7], now=time.monotonic() - G.CONFIRM_S - 1)
        G.set_text("q")
        G.lapse(1)                                              # no kitty here: the redraw is skipped, never raised
        self.assertEqual(G.text(), "")
        G.decide("window", 8, [8])
        G.lapse(2)
        self.assertTrue(G.asking(8))

    def test_the_question_is_one_line_and_names_the_key(self):
        q = G.question("Claude Code", "working", "ctrl+shift+w")
        self.assertEqual(q, "Close Claude Code? It is working · ctrl+shift+w again")
        self.assertNotIn("\n", q)
        t = G.question("Codex", "waiting", "ctrl+shift+q", "tab", others=1)
        self.assertEqual(t, "Close this tab? Codex (+1 more): it needs you · ctrl+shift+q again")
        self.assertIn("this agent", G.question("", "working", "x"))


if __name__ == "__main__":
    unittest.main()
