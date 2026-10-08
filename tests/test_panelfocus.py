import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_panelfocus as pf


class ModeTests(unittest.TestCase):
    def test_parse_mode_defaults_to_docked(self):
        self.assertEqual(pf.parse_mode("summoned\n"), pf.SUMMONED)
        for bad in (None, "", "exclusive", "SUMMONED!", "docked"):
            self.assertEqual(pf.parse_mode(bad), pf.DOCKED)

    def test_toggle(self):
        self.assertEqual(pf.toggle_action(False, pf.DOCKED), "start-summoned")
        self.assertEqual(pf.toggle_action(False, pf.SUMMONED), "start-summoned")
        self.assertEqual(pf.toggle_action(True, pf.DOCKED), "summon")
        self.assertEqual(pf.toggle_action(True, pf.SUMMONED), "stop")

    def test_toggle_accepts_the_shells_strings(self):
        self.assertEqual(pf.toggle_action("0", pf.DOCKED), "start-summoned")
        self.assertEqual(pf.toggle_action("false", pf.SUMMONED), "start-summoned")
        self.assertEqual(pf.toggle_action("1", pf.DOCKED), "summon")
        self.assertEqual(pf.toggle_action("True", pf.SUMMONED), "stop")

    def test_idle_dock(self):
        self.assertFalse(pf.should_dock(pf.DOCKED, 0, 10_000))
        self.assertFalse(pf.should_dock(pf.SUMMONED, 100.0, 100.0 + pf.IDLE_DOCK_S - 0.1))
        self.assertTrue(pf.should_dock(pf.SUMMONED, 100.0, 100.0 + pf.IDLE_DOCK_S))
        self.assertTrue(pf.should_dock(pf.SUMMONED, 100.0, 50.0), "a clock that went backwards must not hold the grab")

    def test_idle_limit_is_clamped(self):
        self.assertEqual(pf.idle_limit(None), pf.IDLE_DOCK_S)
        self.assertEqual(pf.idle_limit("nonsense"), pf.IDLE_DOCK_S)
        self.assertEqual(pf.idle_limit("nan"), pf.IDLE_DOCK_S)
        self.assertEqual(pf.idle_limit("0"), 3.0)
        self.assertEqual(pf.idle_limit("1"), 3.0)
        self.assertEqual(pf.idle_limit("9999"), 300.0)
        self.assertEqual(pf.idle_limit("12"), 12.0)

    def test_release_keys(self):
        self.assertTrue(pf.release_on("escape", False))
        self.assertFalse(pf.release_on("escape", True), "Esc first clears a search")
        self.assertTrue(pf.release_on("q", True))
        self.assertFalse(pf.release_on("j", False))
        self.assertFalse(pf.release_on("", False))

    def test_policies_are_kittys_names(self):
        self.assertEqual(pf.POLICY, {"summoned": "exclusive", "docked": "on-demand"})


if __name__ == "__main__":
    unittest.main()
