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
        self.assertEqual(len(set(A.STATE_GLYPH.values())), len(A.STATE_GLYPH))


class SpinnerTests(unittest.TestCase):
    def test_working_animates_through_all_frames(self):
        frames = {A.state_glyph("working", t / A.SPINNER_FPS) for t in range(len(A.SPINNER))}
        self.assertEqual(frames, set(A.SPINNER))

    def test_frame_is_a_pure_function_of_time(self):
        self.assertEqual(A.state_glyph("working", 3.14), A.state_glyph("working", 3.14))

    def test_static_states(self):
        self.assertEqual(A.state_glyph("waiting"), "!")
        self.assertEqual(A.state_glyph("done"), "✓")
        self.assertEqual(A.state_glyph("unread"), "•")
        self.assertEqual(A.state_glyph(""), "")
        self.assertEqual(A.state_glyph("idle"), "")

    def test_spinner_uses_braille_block(self):
        self.assertTrue(all(0x2800 <= ord(c) <= 0x28FF for c in A.SPINNER))


class ToolTests(unittest.TestCase):
    def test_plain_shell_has_no_glyph(self):
        self.assertIsNone(A.tool_in([["zsh"], ["-zsh"]]))

    def test_editor_wins_over_node_child(self):
        self.assertEqual(A.tool_in([["node", "x.js"], ["nvim", "a.py"]]), "nvim")

    def test_only_program_counts_not_arguments(self):
        self.assertEqual(A.tool_in([["git", "commit", "-m", "vim"]]), "git")
        self.assertIsNone(A.tool_in([["zsh", "-c", "echo nvim"]]))

    def test_wrapper_separator(self):
        self.assertEqual(A.tool_in([["zsh", "/x/trmw", "--profile", "font", "--", "nvim", "f"]]), "nvim")

    def test_env_sudo_wrappers(self):
        self.assertEqual(A.tool_in([["sudo", "-E", "htop"]]) or A.tool_in([["sudo", "htop"]]), "htop")
        self.assertEqual(A.tool_in([["env", "docker", "ps"]]), "docker")

    def test_full_paths_and_case(self):
        self.assertEqual(A.tool_in([["/usr/bin/SSH", "host"]]), "ssh")

    def test_all_glyphs_are_single_codepoints_in_nerd_ranges(self):
        for name, glyph in A.TOOLS.items():
            self.assertEqual(len(glyph), 1, name)
            cp = ord(glyph)
            self.assertTrue(0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD, f"{name} U+{cp:X}")

    def test_agents_and_tools_dont_collide(self):
        self.assertFalse(set(A.TOOLS) & set(A.AGENTS))


class SanitizeTests(unittest.TestCase):
    def test_control_and_escape_sequences_neutralised(self):
        evil = "ok\x1b[2J\x1b]0;pwned\x07\x9b31m\r\nnext\x00"
        out = A.sanitize_text(evil)
        self.assertFalse(any(ord(c) < 32 or ord(c) == 127 or 0x80 <= ord(c) < 0xA0 for c in out))
        self.assertIn("ok", out)

    def test_bounded_and_single_line(self):
        self.assertEqual(len(A.sanitize_text("x" * 500)), 120)
        self.assertNotIn("\n", A.sanitize_text("a\nb\tc"))

    def test_resolve_msg_applies_it(self):
        self.assertEqual(A.resolve_msg({"msg": "hi\x1b[31m"}, "waiting"), "hi [31m")

    def test_printable_unicode_survives(self):
        self.assertEqual(A.sanitize_text("Approve: rm -rf node_modules? ✓ 日本"), "Approve: rm -rf node_modules? ✓ 日本")


if __name__ == "__main__":
    unittest.main()
