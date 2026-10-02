import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_theme as T  # noqa: E402

# (accent, background, row background) — a dark theme, a light theme and a theme whose accent is grey
THEMES = {
    "dark": (0x89B4FA, 0x1E1E2E, T.blend(0xCDD6F4, 0x1E1E2E, 0.15)),
    "light": (0x1E66F5, 0xEFF1F5, T.blend(0x4C4F69, 0xEFF1F5, 0.15)),
    "grey": (0x888888, 0x101010, T.blend(0xDDDDDD, 0x101010, 0.15)),
}


class HueTests(unittest.TestCase):
    def test_a_project_keeps_its_slot_across_processes(self):
        here = T.hue_slot("kittymux")
        code = "import sys; sys.path.insert(0, %r); import kittymux_theme as T; print(T.hue_slot('kittymux'))" % \
               os.path.join(os.path.dirname(__file__), "..", "python")
        for seed in ("1", "2"):
            out = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, PYTHONHASHSEED=seed),
                                 capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(int(out), here)

    def test_slots_are_in_range_and_spread(self):
        slots = {T.hue_slot(f"project-{i}") for i in range(200)}
        self.assertTrue(slots <= set(range(T.HUE_SLOTS)))
        self.assertGreaterEqual(len(slots), 10)

    def test_every_slot_is_readable_on_every_theme(self):
        for theme, (accent, _bg, row) in THEMES.items():
            seen = set()
            for i in range(200):
                rgb = T.project_hue(f"p{i}", accent, row)
                self.assertGreaterEqual(T.contrast(rgb, row), 4.5, (theme, i, hex(rgb)))
                seen.add(rgb)
            self.assertGreaterEqual(len(seen), 8, theme)          # the slots are visibly different colours

    def test_it_follows_the_theme(self):
        a = T.project_hue("kittymux", THEMES["dark"][0], THEMES["dark"][2])
        b = T.project_hue("kittymux", THEMES["light"][0], THEMES["light"][2])
        self.assertNotEqual(a, b)

    def test_same_project_same_colour(self):
        accent, _bg, row = THEMES["dark"]
        self.assertEqual(T.project_hue("kittymux", accent, row), T.project_hue("kittymux", accent, row))


if __name__ == "__main__":
    unittest.main()
