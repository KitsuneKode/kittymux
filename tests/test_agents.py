import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_agents as A  # noqa: E402


class AgentTests(unittest.TestCase):
    def test_finds_agent_by_basename(self):
        self.assertEqual(A.agent_in(["/usr/bin/node", "/home/u/.local/bin/claude"]), "claude")

    def test_none_for_shell(self):
        self.assertIsNone(A.agent_in(["zsh"]))

    def test_case_insensitive(self):
        self.assertEqual(A.agent_in(["/opt/Codex"]), "codex")

    def test_brands_are_rgb_ints(self):
        for name, agent in A.AGENTS.items():
            self.assertTrue(0 <= agent.brand <= 0xFFFFFF, name)
            self.assertTrue(agent.glyph, name)


class ResolveStatusTests(unittest.TestCase):
    NOW = 1000.0

    def test_no_agent_is_blank_even_with_status(self):
        self.assertEqual(A.resolve_status({"status": "working"}, False, self.NOW), "")

    def test_explicit_beats_fresh_title(self):
        self.assertEqual(A.resolve_status({"status": "waiting", "ts_title": self.NOW - 1}, True, self.NOW), "waiting")

    def test_explicit_done_and_idle(self):
        self.assertEqual(A.resolve_status({"status": "done"}, True, self.NOW), "done")
        self.assertEqual(A.resolve_status({"status": "idle"}, True, self.NOW), "idle")

    def test_unknown_explicit_falls_back(self):
        self.assertEqual(A.resolve_status({"status": "bogus", "ts_title": self.NOW - 1}, True, self.NOW), "working")

    def test_missing_entry_is_working(self):
        self.assertEqual(A.resolve_status(None, True, self.NOW), "working")

    def test_stale_title_is_waiting(self):
        self.assertEqual(A.resolve_status({"ts_title": self.NOW - 16}, True, self.NOW), "waiting")

    def test_fresh_title_is_working(self):
        self.assertEqual(A.resolve_status({"ts_title": self.NOW - 3}, True, self.NOW), "working")

    def test_zero_title_ts_is_working(self):
        self.assertEqual(A.resolve_status({"ts_title": 0}, True, self.NOW), "working")


class MsgTests(unittest.TestCase):
    def test_msg_only_for_waiting_and_done(self):
        e = {"msg": "needs approval"}
        self.assertEqual(A.resolve_msg(e, "waiting"), "needs approval")
        self.assertEqual(A.resolve_msg(e, "done"), "needs approval")
        self.assertEqual(A.resolve_msg(e, "working"), "")
        self.assertEqual(A.resolve_msg(e, ""), "")

    def test_missing(self):
        self.assertEqual(A.resolve_msg(None, "waiting"), "")

    def test_state_glyphs_distinct(self):
        self.assertEqual(len(set(A.STATE_GLYPH.values())), 3)


if __name__ == "__main__":
    unittest.main()
