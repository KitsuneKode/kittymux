"""`kittymux answer`: answer an agent's prompt from outside its pane (the rice notch's Allow / Deny), only while that exact
prompt is still on screen. kittymux_answer.plan is the whole decision; nothing is typed unless it returns keys."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kittymux_answer as A  # noqa: E402
import test_state as T       # noqa: E402  (real screens, captured)

ROW = {"agent": "claude", "state": "waiting", "question": "Do you want to proceed?"}


class PlanTests(unittest.TestCase):
    def plan(self, how, screen, row=ROW, expect=None, text=""):
        return A.plan(how, row, screen, expect=expect, text=text)

    def test_allow_and_deny_on_claudes_permission_menu(self):
        self.assertEqual(self.plan("allow", T.CLAUDE_PERMISSION), ("1", ""))
        self.assertEqual(self.plan("deny", T.CLAUDE_PERMISSION), ("\x1b", ""))

    def test_codex_confirms_with_enter(self):
        row = {"agent": "codex", "state": "waiting", "question": "Would you like to run the following command?"}
        self.assertEqual(self.plan("allow", T.CODEX_APPROVAL, row), ("\r", ""))
        self.assertEqual(self.plan("deny", T.CODEX_APPROVAL, row), ("\x1b", ""))

    def test_the_prompt_must_still_be_on_screen(self):
        keys, why = self.plan("allow", T.CLAUDE_WORKING)
        self.assertIsNone(keys)
        self.assertIn("no longer", why)

    def test_a_changed_question_is_refused(self):
        keys, why = self.plan("allow", T.CLAUDE_PERMISSION, expect="Delete the database?")
        self.assertIsNone(keys)
        self.assertIn("changed", why)
        self.assertEqual(self.plan("allow", T.CLAUDE_PERMISSION, expect="  Do you want to   proceed? ")[0], "1")   # spacing differs only

    def test_an_agent_whose_prompt_is_not_verified_is_refused(self):
        row = {"agent": "opencode", "state": "waiting", "question": "Should the new file be called alpha.txt or beta.txt?"}
        keys, why = self.plan("allow", T.OPENCODE_QUESTION, row)
        self.assertIsNone(keys)
        self.assertIn("not verified", why)

    def test_a_plain_question_takes_a_text_answer(self):
        row = {"agent": "claude", "state": "waiting", "question": "Should I also update the docs?"}
        self.assertEqual(self.plan("text", "Done.\n\n> \n", row, expect="Should I also update the docs?", text="yes, please"),
                         ("yes, please\r", ""))

    def test_text_is_refused_while_a_menu_is_on_screen_or_nothing_is_asked(self):
        self.assertIsNone(self.plan("text", T.CLAUDE_PERMISSION, text="yes")[0])          # a menu takes allow/deny, not typing
        idle = {"agent": "claude", "state": "done", "question": None}
        self.assertIsNone(self.plan("text", "Done.\n> \n", idle, text="yes")[0])

    def test_text_is_one_plain_line(self):
        row = {"agent": "claude", "state": "waiting", "question": "Which branch?"}
        self.assertEqual(self.plan("text", "> \n", row, text="main\nrm -rf /\x1b[0m")[0], "main rm -rf /[0m\r")
        self.assertIsNone(self.plan("text", "> \n", row, text="   ")[0])

    def test_unknown_requests_are_refused(self):
        self.assertIsNone(self.plan("approve-all", T.CLAUDE_PERMISSION)[0])


if __name__ == "__main__":
    unittest.main()
