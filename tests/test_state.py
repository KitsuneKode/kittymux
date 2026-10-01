import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_state as S  # noqa: E402

DEVIN_THINKING = """\
  Read last 25 lines in ./packages/providers/test/resolve-gate.test.ts

  Thinking · 37m 8s (esc twice to interrupt)
──────────────────────────────────────── 1 queued
○ also let me know how can we actually improve this
❯ Press Enter to send queued messages now
SWE-2 Max                               Context: 99k / 262k tokens (37%)
"""
CLAUDE_PERMISSION = """\
 Bash command
   rm -rf node_modules
 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and don't ask again for rm commands
   3. No, and tell Claude what to do differently (esc)
"""
CLAUDE_WORKING = "✻ Cogitating… (12s · ↓ 1.2k tokens · esc to interrupt)\n"
CLAUDE_WORKING_NEW = ("· Undulating… (6m 52s · ↓ 35.8k tokens)\n  ⎿  Tip: Use /btw to ask a quick side question\n"
                      "──────────\n❯\n──────────\n  [me@host repo:main] [Sonnet 5.5]\n  ⏵⏵ auto mode on (shift+tab to cycle)\n")
CODEX_WORKING = "• Working (3s • esc to interrupt)\n"
CODEX_APPROVAL = "Would you like to run the following command?\nPress enter to confirm or esc to cancel\n"
LIMIT = "Claude usage limit reached. Your limit will reset at 5pm.\n"
IDLE_PROMPT = "╭──────╮\n│ > Try \"fix lint errors\" │\n╰──────╯\n  ? for shortcuts\n"


def marker(text):
    return S.classify_screen(text)[0]


class ClassifyTests(unittest.TestCase):
    def test_devin_thinking_is_working_not_waiting(self):      # the bug in the screenshot
        self.assertEqual(marker(DEVIN_THINKING), "working")

    def test_permission_prompt_is_waiting(self):
        self.assertEqual(marker(CLAUDE_PERMISSION), "waiting")
        self.assertEqual(marker(CODEX_APPROVAL), "waiting")
        self.assertEqual(marker("Overwrite file? (y/n)"), "waiting")

    def test_working_markers(self):
        for text in (CLAUDE_WORKING, CLAUDE_WORKING_NEW, "✻ Pondering… (2h 3m 1s)", CODEX_WORKING, "(esc to cancel, 5s)", "ctrl+c to stop"):
            self.assertEqual(marker(text), "working", text)

    def test_limit_outranks_everything(self):
        self.assertEqual(marker(LIMIT + CLAUDE_WORKING), "limited")
        self.assertEqual(marker("You've hit your usage limit."), "limited")
        self.assertEqual(marker("Resource has been exhausted (e.g. check quota)."), "limited")

    def test_droid_without_a_subscription_is_limited(self):
        self.assertEqual(marker("No active subscription found.\nSubscribe to start using Droid.\n> \n"), "limited")

    def test_waiting_outranks_working(self):
        self.assertEqual(marker(CLAUDE_PERMISSION + CLAUDE_WORKING), "waiting")

    def test_idle_prompt_and_empty(self):
        self.assertEqual(marker(IDLE_PROMPT), "")
        self.assertEqual(marker(""), "")
        self.assertEqual(marker(None), "")

    def test_only_the_bottom_of_the_screen_counts(self):
        old_output = "Do you want to proceed?\n" + "\n".join(f"line {i}" for i in range(40)) + "\n"
        self.assertEqual(marker(old_output), "")                # scrolled-away text is not a live prompt

    def test_returns_the_matching_line(self):
        self.assertIn("Do you want to proceed", S.classify_screen(CLAUDE_PERMISSION)[1])

    def test_elapsed_time_in_prose_is_not_a_spinner(self):
        for text in ("I waited (3s) for it", "see the docs… (section 4)", "Done in 6m 52s", "ok (12s)"):
            self.assertEqual(marker(text), "", text)

    def test_ordinary_prose_is_not_a_marker(self):
        self.assertEqual(marker("I'll allow the user to approve changes later and retry."), "")


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.e = {}
        self.t = 100.0

    def r(self, agent="claude", mk="", dt=0.0, focused=False, **entry):
        self.t += dt
        self.e.update(entry)
        return S.resolve(self.e, agent, mk, self.t, focused)

    def test_not_an_agent(self):
        self.assertEqual(S.resolve({}, None, "working", 1.0, False), "")

    def test_quiet_title_is_never_waiting(self):               # old heuristic: quiet title ⇒ waiting
        self.assertEqual(self.r("devin", "", ts_title=1.0), "idle")
        self.assertEqual(self.r("aider", "", ts_title=1.0), "idle")

    def test_screen_working_then_finish_is_unseen_done_until_focused(self):
        self.assertEqual(self.r(mk="working"), "working")
        self.assertEqual(self.r(mk="", dt=0.5), "working")      # repaint gap is debounced
        self.assertEqual(self.r(mk="", dt=2.0), "done")         # finished while unfocused
        self.assertEqual(self.r(mk="", dt=5.0), "done")         # …and it stays until seen
        self.assertEqual(self.r(mk="", dt=1.0, focused=True), "idle")
        self.assertEqual(self.r(mk="", dt=1.0), "idle")         # cleared for good

    def test_finishing_while_focused_is_idle(self):
        self.r(mk="working", focused=True)
        self.assertEqual(self.r(mk="", dt=3.0, focused=True), "idle")

    def test_new_work_clears_unseen_done(self):
        self.r(mk="working")
        self.r(mk="", dt=3.0)
        self.assertEqual(self.r(mk="working", dt=1.0), "working")
        self.assertFalse(self.e["unseen"])

    def test_prompt_and_limit(self):
        self.assertEqual(self.r(mk="waiting"), "waiting")
        self.assertEqual(self.r(mk="limited", dt=0.5), "limited")

    def test_stale_hook_waiting_is_overridden_by_visible_work(self):
        # user approved in the TUI; Claude fires no hook until the turn ends
        self.assertEqual(self.r(mk="working", status="waiting", ts_status=90.0), "working")

    def test_hook_waiting_stands_when_it_is_a_request_and_nothing_contradicts_it(self):
        self.assertEqual(self.r(mk="", status="waiting", ts_status=90.0, msg="Approve: rm -rf x?"), "waiting")
        self.assertEqual(self.r(mk="", status="waiting", ts_status=90.0,
                                msg="Claude needs your permission to use Bash"), "waiting")

    def test_idle_notification_is_not_a_request(self):
        # focused: you are looking at it, so nothing to flag
        self.assertEqual(
            self.r(mk="", status="waiting", ts_status=90.0, msg="Claude is waiting for your input", focused=True),
            "idle")

    def test_idle_notification_after_finishing_is_an_unseen_completion_not_a_bang(self):
        # Stop hook → done; ~60 s later Claude's idle Notification flips the hook to "waiting"
        self.assertEqual(self.r(mk="", status="done", ts_status=80.0), "done")
        self.assertEqual(
            self.r(mk="", status="waiting", ts_status=140.0, msg="Claude is waiting for your input", dt=60.0), "done")

    def test_waiting_hook_without_a_message_is_not_a_request(self):
        self.assertEqual(self.r(mk="", status="waiting", ts_status=90.0, msg="", focused=True), "idle")
        self.assertEqual(self.r(mk="", status="waiting", ts_status=95.0, msg=""), "done")

    def test_request_wording(self):
        for msg in ("Claude needs your permission to use Bash", "Approve: rm -rf node_modules?",
                    "Do you want to proceed", "Allow this command?"):
            self.assertTrue(S.is_request(msg), msg)
        for msg in ("Claude is waiting for your input", "", None, "Task finished"):
            self.assertFalse(S.is_request(msg), msg)

    def test_interrupted_agent_does_not_spin_forever(self):
        # hook said working; user pressed Esc; no Stop hook ever fires
        self.assertEqual(self.r(mk="", status="working", ts_status=99.0, dt=0.5), "working")   # grace
        self.assertEqual(self.r(mk="", dt=10.0), "idle")

    def test_hook_done_is_unseen_until_focus(self):
        self.assertEqual(self.r(mk="", status="done", ts_status=95.0), "done")
        self.assertEqual(self.r(mk="", focused=True), "idle")
        self.assertEqual(self.r(mk="", focused=False), "idle")  # acknowledged, not resurrected

    def test_unreadable_agents_use_hooks_then_title(self):
        self.assertEqual(self.r("aider", status="waiting"), "waiting")
        self.assertEqual(self.r("aider", status="", ts_title=self.t - 1.0), "working")
        self.assertEqual(self.r("grok", status="", ts_title=self.t - 30.0), "idle")


class RollupTests(unittest.TestCase):
    def test_priority(self):
        self.assertEqual(S.rollup(["idle", "working", "done"]), "working")
        self.assertEqual(S.rollup(["working", "waiting"]), "waiting")
        self.assertEqual(S.rollup(["waiting", "limited"]), "limited")
        self.assertEqual(S.rollup(["done", "idle"]), "done")
        self.assertEqual(S.rollup([]), "")


if __name__ == "__main__":
    unittest.main()
