"""A working row says what the agent is doing (plan 016 §2), not just "Working · 6m". Screens are retyped, synthetic."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_state as S  # noqa: E402


def act(screen):
    marker, line = S.classify_screen(screen)
    assert marker == "working", (marker, line, screen)
    return S.activity(screen, line)


class ActivityTest(unittest.TestCase):
    def test_claude_says_its_latest_tool_call(self):
        screen = ("⏺ I'll run the tests first.\n\n⏺ Bash(npm test -- --watch=false)\n  ⎿  Running…\n\n"
                  "✻ Pondering… (12s · ↓ 1.2k tokens · esc to interrupt)\n\n> \n  ? for shortcuts\n")
        self.assertEqual(act(screen), "Bash: npm test -- --watch=false")

    def test_claude_without_a_tool_call_says_its_verb(self):
        screen = "⏺ Let me think about the cache.\n\n✻ Pondering… (12s · ↓ 1.2k tokens · esc to interrupt)\n\n> \n"
        self.assertEqual(act(screen), "Pondering…")

    def test_codex_says_what_its_status_line_says(self):
        self.assertEqual(act("• Ran cargo build\n\n• Running tests (2m 3s • esc to interrupt)\n\n› \n"), "Running tests")

    def test_gemini_and_devin_drop_the_timer_and_the_hint(self):
        self.assertEqual(act("⠋ Reading file src/cache.ts (esc to cancel, 5s)\n\n> \n"), "Reading file src/cache.ts")
        self.assertEqual(act("✓ Read lines 150-320\n\n··· Thinking · 3m 38s (esc twice to interrupt) · (1180c)\n\n> Guide Devin while it works\n"),
                         "Thinking")

    def test_a_line_that_says_nothing_more_than_working_is_empty(self):
        for screen in ("> Guide Devin while it works\n",                       # Devin's placeholder: the marker, not an activity
                       "  esc to interrupt\n",
                       "• Working (12s • esc to interrupt)\n"):
            self.assertEqual(act(screen), "", screen)

    def test_it_is_one_bounded_clean_line(self):
        long = "⏺ Bash(" + "x" * 300 + ")\n✻ Pondering… (2s · esc to interrupt)\n"
        out = act(long)
        self.assertLessEqual(len(out), S.ACTIVITY_MAX)
        self.assertTrue(out.endswith("…"))
        self.assertNotIn("\x1b", act("⏺ Bash(echo \x1b[31mred)\n✻ Pondering… (2s · esc to interrupt)\n"))

    def test_an_old_tool_call_far_above_is_not_today_s_work(self):
        screen = "⏺ Bash(make)\n" + "  output line\n" * 40 + "✻ Pondering… (2s · esc to interrupt)\n"
        self.assertEqual(act(screen), "Pondering…")


if __name__ == "__main__":
    unittest.main()
