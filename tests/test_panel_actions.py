"""The deck's actions (jump, promote with `t`, absorb with `a`) go through one helper that, in the docked panel, runs the remote-control calls off the UI
thread and gives the keyboard grab back afterwards. Before it, `t` and `a` ran each call (4 s timeout) on the UI thread and never released an exclusive grab,
so after pulling a pane out the panel froze for seconds and the next keys went to the panel, not to the window that had just been focused.
sidebar-kit.py is a kitten (hyphenated name, run by kitty), so these read its source, like the timer rule's test does."""
import ast
import os
import unittest

SRC = os.path.join(os.path.dirname(__file__), "..", "python", "sidebar-kit.py")


def _methods():
    tree = ast.parse(open(SRC, encoding="utf-8").read())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Sidebar")
    return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}


def _calls(node, name):
    return [c for c in ast.walk(node) if isinstance(c, ast.Call) and getattr(c.func, "id", getattr(c.func, "attr", None)) == name]


class DeckActionTests(unittest.TestCase):
    def test_actions_use_the_one_helper_and_never_call_rc_directly(self):
        m = _methods()
        for name in ("_jump", "_promote", "_absorb"):
            self.assertTrue(_calls(m[name], "_act"), f"{name} must run its calls through _act")
            self.assertFalse(_calls(m[name], "_rc"), f"{name} must not call _rc on the UI thread")

    def test_panel_actions_run_on_a_worker_and_release_the_grab(self):
        m = _methods()
        self.assertTrue(_calls(m["_act"], "Thread"), "_act runs the calls on a worker in panel mode")
        self.assertTrue(_calls(m["_after_action"], "_release_grab"), "the keyboard goes back once the focus has moved")
        self.assertTrue(_calls(m["_after_action"], "_request_refresh"))

    def test_the_overlay_deck_still_closes_itself(self):
        self.assertTrue(_calls(_methods()["_act"], "quit_loop"))


if __name__ == "__main__":
    unittest.main()
