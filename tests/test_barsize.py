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
        self.opts = types.SimpleNamespace(tab_bar_edge=2, tab_title_max_length=12, drag_threshold=14)
        self.dragged = (0, False, 0, 0)
        self.boss = types.SimpleNamespace(mouse_handler=None)
        self.fdt = types.ModuleType("kitty.fast_data_types")
        self.fdt.__dict__.update(
            LEFT_EDGE=1, RIGHT_EDGE=2, TOP_EDGE=3,
            GLFW_MOUSE_BUTTON_LEFT=0, GLFW_MOUSE_BUTTON_RIGHT=1, GLFW_MOUSE_BUTTON_MIDDLE=2, GLFW_PRESS=1, GLFW_RELEASE=0,
            get_tab_being_dragged=lambda: self.dragged,
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
        class FakeTab:                                    # kitty's Tab iterates over its windows
            def __init__(self, tid, wid):
                self.id, self.windows = tid, [types.SimpleNamespace(id=wid)]

            def __iter__(self):
                return iter(self.windows)

        self.tabs = {1: FakeTab(1, 11), 2: FakeTab(2, 22)}
        bar.tab_id_at = lambda x, y: 1 if y < 100 else 2 if y < 200 else 0
        self.tm = types.SimpleNamespace(tab_bar=bar, os_window_id=1, active_tab=self.tabs[1],
                                        update_tab_bar_data=Mock(), mark_tab_bar_dirty=Mock(),
                                        tab_for_id=lambda i: self.tabs.get(i), set_active_tab=Mock())
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

    # ── trailing apply: the bar must never be left behind the pointer ──────────────────────────────
    def test_next_apply_table(self):
        n = self.m.next_apply
        self.assertIsNone(n(1.0, 0.0, 0.0, 20, 20))                      # already there
        self.assertEqual(n(1.0, 0.0, 0.0, 20, 24), 0.0)                  # long enough since the last one
        self.assertAlmostEqual(n(1.0, 0.99, 0.0, 20, 24), 0.006)         # 10 ms ago: wait out the 16 ms
        self.assertAlmostEqual(n(1.0, 0.99, 0.02, 20, 24), 0.02)         # a slow apply (20 ms) makes the next wait 30 ms

    def test_a_motion_inside_the_pacing_window_is_applied_later_not_lost(self):
        self.press()
        with patch.object(self.m.time, "monotonic", return_value=10.0):
            self.event(780)                                              # applies now (width 14)
            self.event(700)                                              # 0 ms later: too soon → one timer, nothing applied yet
        self.assertEqual(self.m.apply_width.call_count, 1)
        self.assertIsNotNone(self.rt.trail)
        with patch.object(self.m.time, "monotonic", return_value=10.2):
            self.m._trail(self.rt.trail)                                 # the timer fires: the LATEST position is applied
        self.assertEqual(self.m.apply_width.call_args_list[-1].args[1], 22)
        self.assertEqual(self.m.apply_width.call_args_list[-1].kwargs, {"final": False})
        self.assertIsNone(self.rt.trail)

    def test_many_fast_motions_arm_at_most_one_timer(self):
        self.press()
        with patch.object(self.m.time, "monotonic", return_value=10.0):
            self.event(780)
            for x in (770, 760, 750, 740, 730):
                self.event(x)
        self.assertEqual(self.fdt.add_timer.call_count, 2)               # the watchdog from the press + exactly one trailing timer

    def test_release_and_abandoned_drag_flow_every_tab(self):
        self.press()
        with patch.object(self.m.time, "monotonic", return_value=10.0):
            self.event(780)                                              # lean apply (dirty)
        self.m._end_capture(self.boss, finalize=True)                    # the watchdog / an error ended it: no release came
        self.assertEqual(self.m.apply_width.call_args_list[-1].kwargs, {"final": True})
        self.assertIsNone(self.rt.drag)

    def test_release_applies_the_final_full_width(self):
        self.press()
        self.event(780)
        self.event(700, button=0, action=0)
        self.m.apply_width.assert_called_with(self.boss, 22)             # default final=True: all tabs re-flow once


    # ── forgiving clicks ────────────────────────────────────────────────────────────────────────────
    def tap(self, press, release, held=0.1, dragged=False):
        """Feed kitty's tab-bar events for one left click the way the wrapper does: before-hook, (kitty does nothing), after-hook."""
        m, tm = self.m, self.tm
        with patch.object(m.time, "monotonic", return_value=50.0):
            m._tap_before(tm, press[0], press[1], 0, 1)
        self.dragged = (1, dragged, 0, 0)
        with patch.object(m.time, "monotonic", return_value=50.0 + held):
            m._tap_before(tm, release[0], release[1], 0, 0)
            m._tap_after(tm, release[0], release[1], 0, 0)

    def test_a_click_that_drifts_between_5_and_14_px_still_activates_the_tab(self):
        for dx in (6, 9, 12):
            self.tm.set_active_tab.reset_mock()
            self.tap((10, 150), (10 + dx, 150))
            self.tm.set_active_tab.assert_called_once_with(self.tabs[2])

    def test_a_slow_click_activates_but_a_held_press_does_not(self):
        self.tap((10, 150), (10, 150), held=1.2)
        self.tm.set_active_tab.assert_called_once_with(self.tabs[2])
        self.tm.set_active_tab.reset_mock()
        self.tap((10, 150), (10, 150), held=2.0)                     # long enough to be a drag attempt, not a click
        self.tm.set_active_tab.assert_not_called()

    def test_a_real_drag_or_a_release_elsewhere_is_not_a_click(self):
        self.tap((10, 150), (10 + 40, 150))                          # moved past the drag threshold
        self.tap((10, 150), (10, 50))                                # released over another tab
        self.tap((10, 150), (12, 150), dragged=True)                 # kitty already started a drag
        self.tm.set_active_tab.assert_not_called()

    def test_the_already_active_tab_is_left_alone_and_state_is_cleared(self):
        self.tap((10, 50), (13, 50))                                 # tab 1 is active
        self.tm.set_active_tab.assert_not_called()
        self.assertIsNone(self.rt.tap)

    def test_a_middle_click_on_an_agent_tab_is_swallowed_but_a_plain_tab_is_not(self):
        self.rt.__dict__.setdefault("tap", None)
        scan = types.SimpleNamespace(verdicts={"22": {"state": "working"}})
        with patch.dict(sys.modules, {"_kittymux_scan_rt": scan}):
            self.assertTrue(self.m._tap_before(self.tm, 10, 150, 2, 1))      # tab 2 runs an agent
            self.assertFalse(self.m._tap_before(self.tm, 10, 50, 2, 1))      # tab 1 does not
            self.assertFalse(self.m._tap_before(self.tm, 10, 150, 0, 1))     # a left press is never swallowed


if __name__ == "__main__":
    unittest.main()
