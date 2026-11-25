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


class ActivityReviewTest(unittest.TestCase):
    """Fable's review of #57: Linux bullets, stale or wrong activities, secrets. Screens retyped from the formats it read."""

    def test_claude_on_linux_draws_a_dot(self):
        # Claude Code picks ⏺ on macOS and ● elsewhere
        screen = "● Bash(npm test)\n  ⎿  Running…\n\n✻ Pondering… (3s · esc to interrupt)\n\n> \n"
        self.assertEqual(act(screen), "Bash: npm test")

    def test_a_finished_call_followed_by_prose_is_not_what_it_does_now(self):
        screen = ("● Bash(npm test)\n  ⎿  42 passed\n\n● All tests pass. Now I'll think about the cache.\n\n"
                  "✻ Pondering… (3s · esc to interrupt)\n")
        self.assertEqual(act(screen), "Pondering…")

    def test_the_newest_call_speaks_even_an_mcp_one(self):
        screen = ("● Read(src/a.py)\n  ⎿  Read 10 lines\n\n● github - create_issue (MCP)(title: \"Cache\")\n  ⎿  Running…\n\n"
                  "✻ Pondering… (3s · esc to interrupt)\n")
        self.assertEqual(act(screen), 'github - create_issue (MCP): title: "Cache"')

    def test_a_mode_footer_or_key_hints_are_not_an_activity(self):
        for screen in ("✻ Pondering… (3s)\n> \n  ⏵⏵ accept edits on (shift+tab to cycle) · esc to interrupt\n",
                       "┃ build ┃\n  esc interrupt  ctrl+p commands  tab agents\n"):
            self.assertNotIn("shift+tab", act(screen))
            self.assertNotIn("ctrl+p", act(screen))

    def test_only_the_lowest_busy_line_counts(self):
        # a bare "Working" is the answer: an older line that merely mentions the hint is not
        screen = "The docs say press esc to interrupt the agent at any time.\n\n• Working (4s • esc to interrupt)\n\n› \n"
        self.assertEqual(act(screen), "")

    def test_a_quoted_call_inside_a_reply_is_not_a_call(self):
        screen = "● Here is what not to run:\n    ● Bash(rm -rf /)\n\n✻ Pondering… (3s · esc to interrupt)\n"
        self.assertEqual(act(screen), "Pondering…")

    def test_a_secret_never_reaches_the_bar(self):
        # every sample secret is built at run time from filler (AGENTS.md: nothing credential-shaped in the repository)
        token, pw, flag = "sk-" + "x" * 30, "z" * 12, "--pass" + "word"
        for args in (f"curl -H 'Authorization: Bearer {token}' https://api.example.invalid",
                     f"deploy --api-key {token}", f"psql postgres://u:{pw}@db.example.invalid/x {flag} {pw}"):
            out = act(f"● Bash({args})\n  ⎿  Running…\n\n✻ Pondering… (3s · esc to interrupt)\n")
            self.assertNotIn(token, out)
            self.assertNotIn(pw, out)
            self.assertTrue(out.startswith("Bash: "), out)

    def test_no_busy_line_no_activity(self):
        self.assertEqual(S.activity("Do you want to proceed?\n❯ 1. Yes\n", "Do you want to proceed?"), "")


if __name__ == "__main__":
    unittest.main()
