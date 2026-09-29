import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_theme as T  # noqa: E402

GRUVBOX = {
    "background": 0x272727, "foreground": 0xebdbb2,
    "active_border_color": 0xd3869b,
    "color9": 0xfb4833, "color10": 0xb8ba25, "color11": 0xfabc2e,
    "color12": 0x83a597, "color14": 0x8ec07b,
}


class BlendTests(unittest.TestCase):
    def test_endpoints(self):
        self.assertEqual(T.blend(0xffffff, 0x000000, 0), 0x000000)
        self.assertEqual(T.blend(0xffffff, 0x000000, 1), 0xffffff)

    def test_midpoint(self):
        self.assertEqual(T.blend(0xffffff, 0x000000, 0.5), 0x808080)

    def test_clamped(self):
        self.assertEqual(T.blend(0x102030, 0x000000, 5), 0x102030)


class ContrastTests(unittest.TestCase):
    def test_extremes(self):
        self.assertAlmostEqual(T.contrast(0xffffff, 0x000000), 21.0, places=2)

    def test_ensure_raises_low_contrast(self):
        out = T.ensure_contrast(0x3c3836, 0x272727, 3.0)
        self.assertGreaterEqual(T.contrast(out, 0x272727), 3.0)

    def test_ensure_leaves_sufficient_alone(self):
        self.assertEqual(T.ensure_contrast(0xffffff, 0x000000, 3.0), 0xffffff)

    def test_ensure_on_light_theme_darkens(self):
        out = T.ensure_contrast(0xdddddd, 0xffffff, 3.0)
        self.assertGreaterEqual(T.contrast(out, 0xffffff), 3.0)
        self.assertLess(T.luminance(out), T.luminance(0xdddddd))


class DimTests(unittest.TestCase):
    def test_dim_scales_channels(self):
        self.assertEqual(T.dim(0x10a37f), (int(0x10 * .55) << 16) | (int(0xa3 * .55) << 8) | int(0x7f * .55))

    def test_dim_stays_untagged_rgb(self):
        self.assertLessEqual(T.dim(0xffffff), 0xffffff)


class ParseTests(unittest.TestCase):
    def test_parse(self):
        got = T.parse_kitty_colors("background #272727\nforeground #ebdbb2\ncursor none\nbad line here\n")
        self.assertEqual(got, {"background": 0x272727, "foreground": 0xebdbb2})


class PaletteTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("KITTYMUX_ACCENT", None)

    def test_gruvbox(self):
        p = T.from_colors(GRUVBOX)
        self.assertEqual(p.accent, 0xd3869b)
        self.assertNotEqual(p.surface, p.bg)
        self.assertNotEqual(p.surface_hi, p.surface)
        # elevation steps: pane < bar < hover < active row, separator visible
        lum = T.luminance
        self.assertLess(lum(p.bg), lum(p.bar))
        self.assertLess(lum(p.bar), lum(p.surface))
        self.assertLess(lum(p.surface), lum(p.surface_hi))
        self.assertLess(lum(p.bar), lum(p.line))
        for name in ("working", "waiting", "done", "alert", "info", "accent"):
            self.assertGreaterEqual(T.contrast(getattr(p, name), p.bg), 3.0, name)

    def test_accent_env_override(self):
        os.environ["KITTYMUX_ACCENT"] = "#89b4fa"
        try:
            self.assertEqual(T.from_colors(GRUVBOX).accent, 0x89b4fa)
        finally:
            os.environ.pop("KITTYMUX_ACCENT")

    def test_missing_keys_do_not_raise(self):
        p = T.from_colors({})
        self.assertIsInstance(p.accent, int)

    def test_light_theme_readable(self):
        p = T.from_colors({"background": 0xfbf1c7, "foreground": 0x3c3836,
                           "color9": 0x9d0006, "color10": 0x79740e, "color11": 0xb57614})
        self.assertGreaterEqual(T.contrast(p.muted, p.bg), 2.0)
        self.assertGreaterEqual(T.contrast(p.waiting, p.bg), 3.0)


class FzfTests(unittest.TestCase):
    def test_args_use_palette(self):
        p = T.from_colors(GRUVBOX)
        args = T.fzf_args(p)
        self.assertTrue(all(a.startswith("--color=") for a in args))
        self.assertIn("--color=bg:#272727", args)
        self.assertIn("--color=hl:#d3869b", args)
        self.assertIn("--color=bg+:" + "#%06x" % p.surface_hi, args)

    def test_cli_reads_get_colors(self):
        import subprocess
        text = "background #272727\nforeground #ebdbb2\ncolor11 #fabc2e\n"
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(T.__file__), "kittymux_theme.py"), "--fzf"],
                             input=text, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)
        self.assertIn("--color=bg:#272727", out.stdout.splitlines())

    def test_cli_usage_error(self):
        import subprocess
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(T.__file__), "kittymux_theme.py")],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)


if __name__ == "__main__":
    unittest.main()
