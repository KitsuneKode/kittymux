import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

PYTHON = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(PYTHON))
import kittymux_layout as L


class BarsizeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.opts = types.SimpleNamespace(tab_bar_edge=2, tab_title_max_length=12)
        self.boss = types.SimpleNamespace(mouse_handler=None)
        self.fdt = types.ModuleType("kitty.fast_data_types")
        self.fdt.__dict__.update(
            LEFT_EDGE=1, RIGHT_EDGE=2, TOP_EDGE=3,
            GLFW_MOUSE_BUTTON_LEFT=0, GLFW_MOUSE_BUTTON_RIGHT=1, GLFW_PRESS=1, GLFW_RELEASE=0,
            get_options=lambda: self.opts, get_boss=lambda: self.boss,
            get_os_window_size=lambda wid: {"width": 1000},
            redirect_mouse_handling=Mock(), add_timer=Mock(return_value=99), remove_timer=Mock(),
            mark_os_window_dirty=Mock(), wakeup_main_loop=Mock())
        self.rt = types.SimpleNamespace(hot=False, drag=None, last_apply=0.0, installed=False,
                                        toggle_down=False, peek_down=0, watchdog=None)
        p = patch.dict(sys.modules, {"kitty.fast_data_types": self.fdt, "_kittymux_barsize_rt": self.rt})
        p.start()
        self.addCleanup(p.stop)
        p = patch.dict(os.environ, KITTYMUX_STATE=self.temp.name, KITTY_CONFIG_DIRECTORY=str(PYTHON))
        p.start()
        self.addCleanup(p.stop)
        bar = types.SimpleNamespace(is_vertical=True, cell_width=10, cell_height=20, max_tab_title_lines=4,
                                    window_geometry=types.SimpleNamespace(left=800, right=1000, top=0, bottom=600))
        self.tm = types.SimpleNamespace(tab_bar=bar, os_window_id=1,
                                        update_tab_bar_data=Mock(), mark_tab_bar_dirty=Mock())
        self.m = self.load()

    def load(self):
        spec = importlib.util.spec_from_file_location("barsize_under_test", PYTHON / "kittymux_barsize.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.apply_width = Mock()
        return m

    def press(self):
        self.assertTrue(self.m._handle(self.tm, 800, 100, 0, 1))
        self.assertIs(self.boss.mouse_handler, self.m._mouse_handler)

    def event(self, x, button=-1, action=1):
        self.m._mouse_handler(types.SimpleNamespace(x=x, button=button, action=action))

    def test_release_recomputes_final_width_inside_throttle_interval(self):
        self.press()
        with patch.object(self.m.time, "monotonic", return_value=10.0):
            self.event(780)  # 22 columns minus padding = width 14
            self.event(740)  # throttled
            self.event(700, button=0, action=0)  # exact release width 22, not the last applied 14
        self.assertEqual(L.load(self.temp.name, os.getpid()).width, 22)
        self.m.apply_width.assert_called_with(self.boss, 22)
        self.assertIsNone(self.rt.drag)
        self.assertIsNone(self.boss.mouse_handler)
        self.assertIsNone(self.rt.watchdog)

    def test_unsaved_right_edge_survives_drag_and_becomes_unpinned_default(self):
        self.press()
        self.event(780)
        self.event(780, button=0, action=0)
        saved = L.load(self.temp.name, os.getpid())
        self.assertEqual(saved, L.Layout("right", "full", 14))
        self.assertEqual(L.load(self.temp.name, 999999), saved)

    def test_pinned_default_and_full_mode_promotion_are_preserved(self):
        default = L.Layout("right", "compact", 30)
        L.pin_default(self.temp.name, default)
        self.press()
        self.event(780, button=0, action=0)
        self.assertEqual(L.load(self.temp.name, os.getpid()), L.Layout("right", "full", 14))
        self.assertEqual(L.load(self.temp.name, 999999), default)

    def test_reload_retains_drag_and_watchdog_then_release_uses_captured_edge(self):
        self.press()
        drag = self.rt.drag
        self.m = self.load()  # re-execution while dragging must not create fresh runtime state
        self.assertIs(self.m._S.drag, drag)
        self.assertEqual(self.m._S.watchdog, 99)
        self.opts.tab_bar_edge = 1  # geometry/options can change during reload; the drag's edge is captured
        self.event(700, button=0, action=0)
        self.assertEqual(L.load(self.temp.name, os.getpid()), L.Layout("right", "full", 22))
        self.fdt.remove_timer.assert_called_once_with(99)
        self.assertIsNone(self.boss.mouse_handler)


if __name__ == "__main__":
    unittest.main()
