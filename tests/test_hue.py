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
# each theme's state colours: (waiting, alert, working, done) — Catppuccin-like for dark/light, a plain set for grey
STATUS = {
    "dark": (0xF9E2AF, 0xF38BA8, 0x89B4FA, 0xA6E3A1),
    "light": (0xDF8E1D, 0xD20F39, 0x1E66F5, 0x40A02B),
    "grey": (0xCCAA44, 0xDD5555, 0x6699CC, 0x66BB66),
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

    def test_a_projects_hue_never_lands_on_a_status_colour(self):
        """Spec 3b.3: the hue never uses the alert/waiting colours (and stays off the working/done ones): a project's
        folder glyph must not read as "needs you" or "running"."""
        import colorsys

        def hue_of(rgb):
            return colorsys.rgb_to_hls(((rgb >> 16) & 255) / 255, ((rgb >> 8) & 255) / 255, (rgb & 255) / 255)[0]

        def gap(a, b):
            d = abs(a - b) % 1.0
            return min(d, 1.0 - d) * 360

        for theme, (accent, _bg, row) in THEMES.items():
            status = STATUS[theme]                            # (waiting, alert, working, done)
            seen = set()
            for i in range(200):
                rgb = T.project_hue(f"p{i}", accent, row, avoid=status)
                seen.add(rgb)
                self.assertGreaterEqual(T.contrast(rgb, row), 4.5, (theme, i, hex(rgb)))
                for colour in status:
                    self.assertGreaterEqual(gap(hue_of(rgb), hue_of(colour)), 18, (theme, i, hex(rgb), hex(colour)))
            self.assertGreaterEqual(len(seen), 9, theme)      # still a family of distinguishable colours, even with the state hues kept clear

    def test_a_project_colour_is_a_calm_tint_not_a_second_accent(self):
        """Taste: the colour sits between the muted and the bright text — on a dark theme never lighter than L 0.75
        (the old pastel at L 0.79 outshone the text beside it; 4.5:1 on the highlighted row needs ~0.73 for some hues, so
        0.75 is as calm as readability allows), and never as saturated as the state colours."""
        import colorsys
        for theme, (accent, bg, row) in THEMES.items():
            dark = T.luminance(bg) < 0.4
            for i in range(200):
                rgb = T.project_hue(f"p{i}", accent, row, avoid=STATUS[theme])
                _h, light, sat = colorsys.rgb_to_hls(((rgb >> 16) & 255) / 255, ((rgb >> 8) & 255) / 255, (rgb & 255) / 255)
                self.assertLessEqual(sat, 0.5, (theme, i, hex(rgb)))       # the state colours are 0.5-0.9
                if dark:
                    self.assertLessEqual(light, 0.75, (theme, i, hex(rgb)))

    def test_a_grey_status_colour_has_no_hue_to_avoid(self):
        accent, _bg, row = THEMES["dark"]
        self.assertEqual(T.project_hue("kittymux", accent, row, avoid=(0x808080,)), T.project_hue("kittymux", accent, row))


if __name__ == "__main__":
    unittest.main()
