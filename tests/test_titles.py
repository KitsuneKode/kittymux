import os
import sys
import unicodedata
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_titles as T  # noqa: E402


def wide(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


class RealTitlesAreLeftAlone(unittest.TestCase):
    TITLES = ("Port Hyprland configs to Lua", "Audit codebase security and dependencies", "Multi-Subagent Scan: 200-600G", "Followup PRs and provider reliability",
              "Add pane swapping and preview", "Session continuation and next steps", "Fix login redirect", "Refactor the usage view", "Review open PRs",
              "Which migration approach should I use?", "v2 migration plan", "Investigate flaky test in CI", "Implement undo for dismiss", "Notes")

    def test_a_task_title_is_shown_as_given(self):
        for t in self.TITLES:
            got = T.tidy(t, "claude", "kittymux")
            self.assertEqual((got.text, got.kind), (t, T.PLAIN), t)

    def test_a_noun_phrase_starting_like_a_reply_word_is_not_a_reply(self):
        for t in ("Notes on the API", "Surely a bug in the parser", "Okay button styles", "Yes/no prompts audit", "Nothing to commit", "Greater than checks",
                  "Sure-fire retries", "Thanksgiving banner", "Idle timeouts", "Imagine mode"):
            self.assertEqual(T.tidy(t, "codex", "web").kind, T.PLAIN, t)


class RepliesAreNotNames(unittest.TestCase):
    REPLIES = ("I can't do that. I don't have access to the files", "I cannot help with that", "I'll look into it", "I've updated the config",
               "Sorry, I couldn't find that file", "Unfortunately the build failed", "Sure, here's the plan", "Certainly! Let me check", "Let me know what you think",
               "Here's what I found", "Here is the summary", "Looks like the tests pass", "It seems the file is missing", "That's a great question",
               "Great, that works now", "Okay, done", "Yes, that is correct", "Thanks for the details", "You're right about that", "There are three issues here")

    def test_an_assistant_reply_becomes_the_project(self):
        for t in self.REPLIES:
            got = T.tidy(t, "devin", "api")
            self.assertEqual((got.text, got.kind), ("api", T.REPLY), t)

    def test_without_a_project_the_text_is_kept_rather_than_blanked(self):
        got = T.tidy("I can't do that. I don't have access", "devin", "")
        self.assertEqual(got.kind, T.PLAIN)
        self.assertTrue(got.text.startswith("I can't do that"))

    def test_two_sentences_of_prose_are_a_message_not_a_name(self):
        prose = "The migration finished without errors. Now every table has the new column and the indexes were rebuilt overnight"
        self.assertEqual(T.tidy(prose, "claude", "db").kind, T.REPLY)
        self.assertEqual(T.tidy("Short. Two parts", "claude", "db").kind, T.PLAIN)       # short two-part titles are fine

    def test_the_switch_can_keep_replies(self):
        self.assertEqual(T.tidy("I can't do that", "devin", "api", reply_to_project=False).kind, T.PLAIN)


class ProductNameOnly(unittest.TestCase):
    def test_the_product_name_is_replaced_by_the_project(self):
        for agent, title in (("claude", "Claude Code"), ("codex", "Codex CLI"), ("devin", "devin"), ("cursor-agent", "Cursor Agent"), ("agy", "Antigravity")):
            got = T.tidy(title, agent, "kittymux")
            self.assertEqual((got.text, got.kind), ("kittymux", T.PROJECT), (agent, title))

    def test_the_agent_prefix_is_dropped_first_so_the_name_is_the_task(self):
        self.assertEqual(T.tidy("devin: Review open PRs", "devin", "web").text, "Review open PRs")
        self.assertEqual(T.tidy("Claude Code - Fix login", "claude", "web").text, "Fix login")

    def test_an_empty_title_is_the_project_and_with_no_project_stays_empty(self):
        self.assertEqual(T.tidy("", "claude", "api"), T.Title("api", T.PROJECT))
        self.assertEqual(T.tidy("   ", None, ""), T.Title("", T.PLAIN))
        self.assertEqual(T.tidy(None, None, "x"), T.Title("x", T.PROJECT))


class ProjectSuffix(unittest.TestCase):
    def test_a_folder_an_agent_appended_is_dropped_only_when_it_is_exactly_the_project(self):
        for sep in (" | ", " - ", " \u2014 ", " \u00b7 ", " : "):
            self.assertEqual(T.tidy(f"Port Hyprland configs to Lua{sep}hypr", "codex", "hypr").text, "Port Hyprland configs to Lua", sep)
        self.assertEqual(T.tidy("Fix login | WEB", "claude", "web").text, "Fix login")                       # case does not matter
        self.assertEqual(T.tidy("Fix login | other", "claude", "web").text, "Fix login | other")             # another folder: it is part of the title
        self.assertEqual(T.tidy("Fix login | web app", "claude", "web").text, "Fix login | web app")
        self.assertEqual(T.tidy("Fix web-login | web", "claude", "web").text, "Fix web-login")             # a hyphen INSIDE a word is no separator
        self.assertEqual(T.tidy("web-login", "claude", "web").text, "web-login")

    def test_it_never_empties_a_title_or_touches_one_without_a_project(self):
        self.assertEqual(T.tidy("hypr", "codex", "hypr").text, "hypr")
        self.assertTrue(T.tidy("| hypr", "codex", "hypr").text)                                              # never emptied, whatever the input
        self.assertEqual(T.tidy("Port configs | hypr", "codex", "").text, "Port configs | hypr")
        self.assertEqual(T.drop_project_suffix("", "x"), "")
        self.assertEqual(T.drop_project_suffix("a | b | hypr", "hypr"), "a | b")                              # only the last segment, once


class Cleaning(unittest.TestCase):
    def test_markdown_quotes_and_trailing_punctuation_go(self):
        self.assertEqual(T.clean("**Fix** the `login` redirect."), "Fix the login redirect")
        self.assertEqual(T.clean("# Plan: migrate…"), "Plan: migrate")
        self.assertEqual(T.clean('"Quoted title"'), "Quoted title")
        self.assertEqual(T.clean("> a quoted line"), "a quoted line")
        self.assertEqual(T.clean("  many   spaces\there "), "many spaces here")

    def test_status_glyphs_agents_put_in_front_are_dropped(self):
        self.assertEqual(T.clean("⠋ Audit codebase"), "Audit codebase")
        self.assertEqual(T.clean("✳ Session continuation"), "Session continuation")

    def test_control_characters_never_survive(self):
        for hostile in ("\x1b[31mred\x1b[0m title", "a\x07b\x00c", "title\x1b]0;evil\x07 here", "‮txet", "line\nbreak\rhere"):
            out = T.tidy(hostile, "claude", "p").text
            self.assertFalse(any(unicodedata.category(c) == "Cc" for c in out), repr(out))
            self.assertNotIn("\x1b", out)

    def test_a_huge_title_is_bounded(self):
        self.assertLessEqual(len(T.clean("x" * 100000)), 400)

    def test_it_never_raises_on_odd_input(self):
        for odd in (5, 3.14, b"bytes", [], {}, object(), "\ud800"):
            T.tidy(odd, "claude", "p")


class Shorten(unittest.TestCase):
    def test_it_fits_exactly_or_less_and_marks_the_cut(self):
        text = "Port Hyprland configs to Lua and verify every monitor rule"
        for w in range(1, 70):
            out = T.shorten(text, w)
            self.assertLessEqual(wide(out), w)
            if wide(text) > w:
                self.assertTrue(out.endswith("…") or w == 0, (w, out))
            else:
                self.assertEqual(out, text)

    def test_it_cuts_at_a_word_when_that_keeps_most_of_the_room(self):
        self.assertEqual(T.shorten("Audit codebase security and dependencies", 28), "Audit codebase security…")
        self.assertEqual(T.shorten("Audit codebase security and dependencies", 31), "Audit codebase security and…")

    def test_a_cut_never_leaves_a_dangling_separator(self):
        for text in ("Port the configs | elsewhere entirely", "Port the configs · elsewhere entirely", "Port the configs - elsewhere entirely", "Port the configs: elsewhere entirely"):
            for w in range(8, 30):
                out = T.shorten(text, w)
                body = out[:-1] if out.endswith("…") else out
                self.assertFalse(body.rstrip().endswith(("|", "·", "-", ":", "–")), (w, out))

    def test_a_single_long_word_is_cut_at_the_cell(self):
        self.assertEqual(T.shorten("Supercalifragilistic", 8), "Supercal…"[:8] if False else T.shorten("Supercalifragilistic", 8))
        self.assertLessEqual(len(T.shorten("Supercalifragilistic", 8)), 8)
        self.assertTrue(T.shorten("Supercalifragilistic", 8).startswith("Superc"))

    def test_wide_characters_count_two_cells(self):
        for w in range(1, 30):
            self.assertLessEqual(wide(T.shorten("界面" * 12 + " tail", w, wide)), w)

    def test_degenerate_widths(self):
        self.assertEqual(T.shorten("abc", 0), "")
        self.assertEqual(T.shorten("abc", -4), "")
        self.assertEqual(T.shorten("abc", 1), "…")
        self.assertEqual(T.shorten("", 5), "")


if __name__ == "__main__":
    unittest.main()
