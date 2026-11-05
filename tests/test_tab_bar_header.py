"""Vertical bar header: focused session name and host line room for attention badges."""
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PYTHON = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(PYTHON))


class RecordingScreen:
    def __init__(self, cols: int = 28):
        self.columns = cols
        self.lines = 40
        self.cursor = types.SimpleNamespace(x=0, y=0, bg=0, fg=0, bold=False)
        self.drawn: list[tuple[int, int, str]] = []
        self.fgs: list[tuple[str, int]] = []

    def draw(self, text: str) -> None:
        self.drawn.append((self.cursor.y, self.cursor.x, text))
        self.fgs.append((text, self.cursor.fg))
        self.cursor.x += len(text)


def load_tab_bar():
    boss = types.SimpleNamespace(window_id_map={}, os_window_map={})
    fdt = types.ModuleType("kitty.fast_data_types")
    fdt.__dict__.update(
        Screen=RecordingScreen,
        get_boss=lambda: boss,
        get_options=lambda: types.SimpleNamespace(),
        wcswidth=len,
    )
    tbar = types.ModuleType("kitty.tab_bar")
    tbar.__dict__.update(DrawData=object, ExtraData=object, TabBarData=object, as_rgb=lambda x: x)
    utils = types.ModuleType("kitty.utils")
    utils.color_as_int = lambda x: x
    stubs = {
        "kitty.fast_data_types": fdt,
        "kitty.tab_bar": tbar,
        "kitty.utils": utils,
    }
    spec = importlib.util.spec_from_file_location("tab_bar_under_test", PYTHON / "tab_bar.py")
    mod = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs), patch.dict(os.environ, KITTY_CONFIG_DIRECTORY=str(PYTHON), KITTYMUX_STATE="/tmp/kmx-tab-bar-test"), \
         patch.object(spec.loader, "exec_module", wraps=spec.loader.exec_module):
        with patch("kittymux_scan.restart", create=True), patch("kittymux_barsize.install", create=True):
            spec.loader.exec_module(mod)
    return mod, boss


class HeaderSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tb, cls.boss = load_tab_bar()

    def test_the_header_names_the_focused_session_not_tab_one(self):
        tab = types.SimpleNamespace(
            tab_id=1,
            session_name="session-alpha",
            active_session_name="session-beta",
        )
        with patch.object(self.tb, "_session_stats", return_value=(3, {"waiting": 1})), \
             patch.object(self.tb, "_host", return_value="box"), \
             patch.object(self.tb, "_mascot_ready", return_value=False):
            screen = RecordingScreen(28)
            pal = types.SimpleNamespace(
                bar=1, text=2, faint=3, waiting=4, alert=5, done=6, working=4, limited=5,
                bg=7, accent=8, surface_hi=9, muted=10,
            )
            self.tb._draw_header(screen, 0, 2, 28, tab, pal, 1, False)
        line0 = "".join(t for y, _x, t in screen.drawn if y == 0)
        self.assertIn("session-beta", line0)
        self.assertNotIn("session-alpha", line0)

    def test_a_long_host_line_is_clipped_so_attention_badges_stay(self):
        tab = types.SimpleNamespace(tab_id=1, session_name="work", active_session_name="work")
        long_host = "verylonghostname" + "x" * 40
        with patch.object(self.tb, "_session_stats", return_value=(12, {"waiting": 2, "done": 1})), \
             patch.object(self.tb, "_host", return_value=long_host), \
             patch.object(self.tb, "_mascot_ready", return_value=False):
            screen = RecordingScreen(28)
            pal = types.SimpleNamespace(
                bar=1, text=2, faint=3, waiting=4, alert=5, done=6, working=4, limited=5,
                bg=7, accent=8, surface_hi=9, muted=10,
            )
            self.tb._draw_header(screen, 0, 2, 28, tab, pal, 1, False)
        line1 = [t for y, _x, t in screen.drawn if y == 1]
        joined = "".join(line1)
        self.assertIn("!", joined)
        self.assertIn("✓", joined)
        self.assertIn("…", joined)

    def _draw(self, tab, mascot=False):
        with patch.object(self.tb, "_session_stats", return_value=(2, {})), \
             patch.object(self.tb, "_host", return_value="calm-otter"), \
             patch.object(self.tb, "_mascot_ready", return_value=mascot):
            screen = RecordingScreen(28)
            pal = types.SimpleNamespace(
                bar=1, text=2, faint=3, waiting=4, alert=5, done=6, working=4, limited=5,
                bg=7, accent=8, surface_hi=9, muted=10,
            )
            self.tb._draw_header(screen, 0, 2, 28, tab, pal, 1, False)
        return screen

    def test_without_a_session_the_machine_names_the_bar_and_the_count_sits_under_it(self):
        screen = self._draw(types.SimpleNamespace(tab_id=1, session_name="", active_session_name=""))
        line0 = "".join(t for y, _x, t in screen.drawn if y == 0)
        line1 = "".join(t for y, _x, t in screen.drawn if y == 1)
        self.assertIn("calm-otter", line0)
        self.assertNotIn("Tabs", line0)
        self.assertIn("2 tabs", line1)
        self.assertNotIn("calm-otter", line1)            # said once, not twice

    def test_the_mascot_is_drawn_in_the_text_colour_not_the_accent(self):
        screen = self._draw(types.SimpleNamespace(tab_id=1, session_name="work", active_session_name="work"), mascot=True)
        mascot = self.tb.kittymux_agents.MASCOT_GLYPH
        colours = [fg for t, fg in screen.fgs if t == mascot]
        self.assertEqual(colours, [self.tb._rgb(2)])        # pal.text; the accent (8) is for selection and focus
    def test_tab_one_is_labelled_when_it_is_not_the_focused_session(self):
        tab = types.SimpleNamespace(session_name="alpha", active_session_name="beta")
        other = types.SimpleNamespace(session_name="beta", active_session_name="beta")
        self.assertEqual(self.tb._group_label(1, tab, None), "alpha")
        self.assertIsNone(self.tb._group_label(1, other, None))
        self.assertEqual(self.tb._group_label(2, tab, other), "alpha")
        self.assertIsNone(self.tb._group_label(2, other, other))


if __name__ == "__main__":
    unittest.main()
