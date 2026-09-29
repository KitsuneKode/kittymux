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


if __name__ == "__main__":
    unittest.main()
