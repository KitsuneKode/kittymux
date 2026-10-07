import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_features as F  # noqa: E402


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.sdir = tempfile.mkdtemp()

    def test_defaults(self):
        self.assertEqual(F.resolve_all(self.sdir, {}), F.DEFAULTS)
        self.assertTrue(F.enabled("hue", self.sdir, {}))
        self.assertFalse(F.enabled("hover", self.sdir, {}))

    def test_flag_files_flip_the_default(self):
        open(os.path.join(self.sdir, "hue-off"), "w").close()
        open(os.path.join(self.sdir, "hover-on"), "w").close()
        self.assertEqual(F.source("hue", self.sdir, {}), (False, "flag"))
        self.assertEqual(F.source("hover", self.sdir, {}), (True, "flag"))

    def test_env_beats_flag(self):
        open(os.path.join(self.sdir, "hue-off"), "w").close()
        self.assertEqual(F.source("hue", self.sdir, {"KITTYMUX_HUE": "on"}), (True, "env"))
        self.assertEqual(F.source("folder", self.sdir, {"KITTYMUX_FOLDER": "0"}), (False, "env"))

    def test_garbage_env_is_ignored(self):
        self.assertEqual(F.source("hue", self.sdir, {"KITTYMUX_HUE": "banana"}), (True, "default"))

    def test_off_flag_wins_over_on_flag(self):
        for n in ("sheet-off", "sheet-on"):
            open(os.path.join(self.sdir, n), "w").close()
        self.assertFalse(F.enabled("sheet", self.sdir, {}))

    def test_unknown_feature_is_rejected(self):
        for call in (lambda: F.enabled("nope", self.sdir, {}), lambda: F.set_feature(self.sdir, "nope", True)):
            with self.assertRaises(ValueError):
                call()

    def test_set_feature_round_trip_leaves_no_file_at_the_default(self):
        F.set_feature(self.sdir, "hue", False)
        self.assertEqual(os.listdir(self.sdir), ["hue-off"])
        F.set_feature(self.sdir, "hue", True)
        self.assertEqual(os.listdir(self.sdir), [])
        F.set_feature(self.sdir, "hover", True)
        self.assertEqual(os.listdir(self.sdir), ["hover-on"])
        F.set_feature(self.sdir, "hover", False)
        self.assertEqual(os.listdir(self.sdir), [])

    def test_presets(self):
        F.apply_preset(self.sdir, "minimal")
        self.assertEqual(F.resolve_all(self.sdir, {}),
                         {"folder": True, "hue": False, "collide": False, "sheet": False, "hover": False, "panetitle": False, "motion": True, "titles": True})
        F.apply_preset(self.sdir, "full")
        self.assertTrue(all(F.resolve_all(self.sdir, {}).values()))
        F.apply_preset(self.sdir, "default")
        self.assertEqual(F.resolve_all(self.sdir, {}), F.DEFAULTS)
        self.assertEqual(os.listdir(self.sdir), [])
        with self.assertRaises(ValueError):
            F.apply_preset(self.sdir, "loud")

    def test_state_dir_precedence(self):
        self.assertEqual(F.state_dir({"KITTYMUX_STATE": "/a"}), "/a")
        self.assertEqual(F.state_dir({"XDG_STATE_HOME": "/x"}), "/x/kittymux")

    def test_pieces_that_are_not_built_yet_are_marked_planned(self):
        self.assertEqual(F.PLANNED, frozenset({"sheet", "hover"}))
        self.assertTrue(F.PLANNED <= set(F.FEATURES))
        self.assertTrue(F.live().isdisjoint(F.PLANNED))
        self.assertEqual(F.live(), frozenset({"folder", "hue", "collide", "panetitle", "motion", "titles"}))

    def test_motion_is_on_by_default_and_a_preset_that_turns_things_off_leaves_the_spinner_alone(self):
        self.assertTrue(F.enabled("motion", self.sdir, {}))
        self.assertIn("motion", F.PRESETS["minimal"])
        F.set_feature(self.sdir, "motion", False)
        self.assertEqual(os.listdir(self.sdir), ["motion-off"])
        self.assertFalse(F.enabled("motion", self.sdir, {}))
        self.assertTrue(F.enabled("motion", self.sdir, {"KITTYMUX_MOTION": "on"}))        # the environment beats the file

    def test_pane_title_bars_are_on_by_default_because_they_only_show_when_you_turn_the_bars_on(self):
        self.assertTrue(F.DEFAULTS["panetitle"])
        self.assertTrue(F.enabled("panetitle", self.sdir, {}))
        self.assertIn("panetitle", F.PRESETS["default"])
        self.assertNotIn("panetitle", F.PRESETS["minimal"])


if __name__ == "__main__":
    unittest.main()
