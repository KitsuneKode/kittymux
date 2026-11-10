"""The cards shader pipeline: glass, cell height, and the progress fills stay apart from the bar colour."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_cards as C  # noqa: E402
import kittymux_layout as L  # noqa: E402
import kittymux_theme as T  # noqa: E402

# the two themes tests/shot_bar.sh draws, so a fill that would be mistaken for the bar fails here first
DARK = {"foreground": 0xC0CAF5, "background": 0x1A1B26, "active_border_color": 0xBB9AF7,
        "color9": 0xF7768E, "color10": 0x9ECE6A, "color11": 0xE0AF68, "color12": 0x7AA2F7}
LIGHT = {"foreground": 0x4C4F69, "background": 0xEFF1F5, "active_border_color": 0x1E66F5,
         "color9": 0xD20F39, "color10": 0x40A02B, "color11": 0xDF8E1D, "color12": 0x1E66F5}


def _dist(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


class PipelineTextTests(unittest.TestCase):
    def test_the_shipped_pipeline_is_the_default_text(self):
        shipped = open(L.CARDS_PIPELINE, encoding="utf-8").read()
        self.assertEqual(shipped, C.pipeline_text(False, 0, None))

    def test_glass_and_cell_height_are_vars_the_shader_declares(self):
        text = C.pipeline_text(True, 22, None)
        self.assertIn("var bool GLASS = true", text)
        self.assertIn("var float CELL_H = 22", text)
        self.assertIn("animation_step 0", text)          # the hover rides kitty's own pointer redraws
        self.assertNotIn("animation_start user-activity", text)

    def test_eight_fills_and_unused_slots_stay_negative(self):
        fills = C.fill_rgbs(T.from_colors(DARK))
        self.assertEqual(len(fills), C.FILL_SLOTS)
        text = C.pipeline_text(False, 19, fills[:3])
        self.assertIn("var float3 FILL0 = " + C.srgb_float3(fills[0]), text)
        self.assertIn("var float3 FILL3 = float3(-1.0, -1.0, -1.0)", text)

    def test_fills_stay_clear_of_the_bar_in_both_themes(self):
        """A fill within the shader's match tolerance of the bar would round the bar itself."""
        for colors in (DARK, LIGHT):
            pal = T.from_colors(colors)
            bar = C.linear_rgb(pal.bar)
            for rgb in C.fill_rgbs(pal):
                self.assertGreater(_dist(C.linear_rgb(rgb), bar), 0.03, hex(rgb))

    def test_install_writes_the_pipeline_beside_the_shaders_and_is_quiet_the_second_time(self):
        with tempfile.TemporaryDirectory() as d:
            path = C.install_pipeline(d, os.path.dirname(L.CARDS_PIPELINE), True, 21, [0x112233])
            self.assertTrue(path.endswith(os.path.join("shaders", "kittymux-cards.pipeline")))
            for name in C.SHADER_NAMES:
                link = os.path.join(os.path.dirname(path), name)
                self.assertTrue(os.path.islink(link), name)
                self.assertTrue(os.path.exists(link), name)
            body = open(path, encoding="utf-8").read()
            self.assertIn("var bool GLASS = true", body)
            self.assertIn("var float CELL_H = 21", body)
            first = os.stat(path).st_mtime_ns
            again = C.install_pipeline(d, os.path.dirname(L.CARDS_PIPELINE), True, 21, [0x112233])
            self.assertEqual(again, path)
            self.assertEqual(os.stat(path).st_mtime_ns, first)


class GatedCardsTests(unittest.TestCase):
    def test_glass_is_a_second_flag_on_the_same_shader_line(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, L.CARDS_FLAG), "w").close()
            open(os.path.join(d, L.GLASS_FLAG), "w").close()
            out = L.gated_conf((0, 49, 2), d, True)
            line = [x for x in out.splitlines() if x.startswith("custom_shaders ")]
            self.assertEqual(len(line), 1)
            body = open(line[0].split(" ", 1)[1], encoding="utf-8").read()
            self.assertIn("var bool GLASS = true", body)
            self.assertIn("shaders kittymux-hover-probe", body)

    @unittest.skipUnless(os.path.exists("/usr/lib/kitty/kitty/shaders/slang.py"),
                         "needs an installed kitty with shader-slang (CI's unit job has none; the smoke job does)")
    def test_the_pipeline_parses(self):
        # a child interpreter: importing kitty here would make later tests think they are inside kitty
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = (
            "import os, sys\n"
            "sys.path.insert(0, '/usr/lib/kitty')\n"
            "sys.path.insert(0, 'python')\n"
            "import kittymux_cards as C, kittymux_theme as T\n"
            "from kitty.shaders.slang import parse_pipeline_definition\n"
            "colors = dict(foreground=0xC0CAF5, background=0x1A1B26, active_border_color=0xBB9AF7,\n"
            "              color9=0xF7768E, color10=0x9ECE6A, color11=0xE0AF68, color12=0x7AA2F7)\n"
            "text = C.pipeline_text(True, 18, C.fill_rgbs(T.from_colors(colors)))\n"
            "pipe = parse_pipeline_definition(text.splitlines(), 'kittymux-cards', os.path.join('assets', 'shaders'))\n"
            "assert len(pipe['groups']) == 3\n"
            "assert pipe['groups'][0]['output_texture'] == 'a'\n"
            "assert pipe['groups'][-1]['animation_start'] == ('tab-change',)\n"
        )
        run = subprocess.run([sys.executable, "-c", script], cwd=root, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
