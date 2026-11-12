"""The pixel tab bar's glue: clicks land on the tab drawn under the pointer, never on the blank cells beneath it."""
import os
import sys
import types
import unittest
from collections import namedtuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_agents as A  # noqa: E402
import kittymux_barsize as BS  # noqa: E402
import kittymux_pxbar as PX  # noqa: E402

Hit = namedtuple("Hit", "kind y0 y1 tab_id project")
Geom = namedtuple("Geom", "left top right bottom")


def bar(osw=7):
    return types.SimpleNamespace(is_vertical=True, os_window_id=osw, window_geometry=Geom(0, 0, 300, 900))


class ClickMappingTest(unittest.TestCase):
    def setUp(self):
        self._saved = dict(PX._S.windows)
        PX._S.windows.clear()
        PX._S.windows[7] = {"sig": None, "right": 300, "hits": (
            Hit("header", 0, 40, 0, ""), Hit("group", 40, 64, 0, "rice"),
            Hit("tab", 64, 110, 11, ""), Hit("tab", 110, 142, 12, ""))}

    def tearDown(self):
        PX._S.windows.clear()
        PX._S.windows.update(self._saved)

    def test_a_row_maps_to_its_tab_whatever_cell_is_under_it(self):
        self.assertEqual(BS.pxbar_tab_at(bar(), 100, 80), 11)
        self.assertEqual(BS.pxbar_tab_at(bar(), 100, 141), 12)

    def test_header_label_and_empty_space_activate_nothing(self):
        for y in (10, 50, 500):
            self.assertEqual(BS.pxbar_tab_at(bar(), 100, y), 0)

    def test_without_a_picture_kitty_answers(self):
        self.assertIsNone(BS.pxbar_tab_at(bar(osw=8), 100, 80))

    def test_a_horizontal_bar_is_left_to_kitty(self):
        b = bar()
        b.is_vertical = False
        self.assertIsNone(BS.pxbar_tab_at(b, 100, 80))

    def test_the_wrapper_uses_the_picture_first(self):
        calls = []
        wrapped = BS.make_tab_id_at(lambda self, x, y: calls.append((x, y)) or 99)
        self.assertEqual(wrapped(bar(), 100, 80), 11)
        self.assertEqual(calls, [])


class CloseCrossTest(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        self._cross = patch.object(PX, "cross_shown", return_value=True)
        self._cross.start()
        self.addCleanup(self._cross.stop)
        self._saved = dict(PX._S.windows)
        PX._S.windows.clear()
        sig = ((), None, 300, 900, 1.0, "")
        PX._S.windows[7] = {"sig": sig, "right": 300, "hits": (Hit("tab", 64, 110, 11, ""), Hit("group", 110, 134, 0, "dots"))}

    def tearDown(self):
        PX._S.windows.clear()
        PX._S.windows.update(self._saved)

    def test_the_cross_is_the_row_end_in_its_first_line(self):
        self.assertEqual(PX.close_hit(7, 290, 70), 11)
        self.assertEqual(PX.close_hit(7, 270, 95), 11)

    def test_the_title_and_the_second_line_are_not_the_cross(self):
        self.assertEqual(PX.close_hit(7, 120, 70), 0)
        self.assertEqual(PX.close_hit(7, 290, 100), 0)

    def test_a_label_has_no_cross(self):
        self.assertEqual(PX.close_hit(7, 290, 120), 0)

    def test_without_the_shader_there_is_no_cross_to_click(self):
        from unittest.mock import patch
        with patch.object(PX, "cross_shown", return_value=False):
            self.assertEqual(PX.close_hit(7, 290, 70), 0)

    def test_opened_groups_are_forgotten_once_their_tabs_are_gone(self):
        saved = set(PX._S.expanded)
        try:
            PX._S.expanded.clear()
            PX._S.expanded.update({"dots", "gone", "rice"})
            PX.prune_expanded(["rice", "dots", "kittymux"])
            self.assertEqual(PX.expanded(), frozenset({"rice", "dots"}))
        finally:
            PX._S.expanded.clear()
            PX._S.expanded.update(saved)

    def test_a_group_label_click_opens_and_closes_it(self):
        saved = set(PX._S.expanded)
        try:
            PX._S.expanded.clear()
            PX.toggle_group("dots")
            self.assertEqual(PX.expanded(), frozenset({"dots"}))
            PX.toggle_group("dots")
            self.assertEqual(PX.expanded(), frozenset())
        finally:
            PX._S.expanded.clear()
            PX._S.expanded.update(saved)


class ToolMarksTest(unittest.TestCase):
    def test_every_tool_mark_is_a_real_icon(self):
        icons = os.path.join(os.path.dirname(__file__), "..", "assets", "icons")
        for tool, mark in A.TOOL_MARKS.items():
            self.assertTrue(os.path.exists(os.path.join(icons, f"{mark}.svg")), (tool, mark))

    def test_every_tool_with_a_mark_is_a_tool_the_bar_recognises(self):
        self.assertLessEqual(set(A.TOOL_MARKS), set(A.TOOLS))


if __name__ == "__main__":
    unittest.main()


class CrossShownTest(unittest.TestCase):
    def test_the_cross_follows_the_running_shaders(self):
        on = types.SimpleNamespace(custom_shaders=("/x/assets/shaders/kittymux-pxbar.pipeline",))
        off = types.SimpleNamespace(custom_shaders=("/x/kittymux-cards.pipeline",))
        self.assertTrue(PX.cross_shown(on))
        self.assertFalse(PX.cross_shown(off))
        self.assertFalse(PX.cross_shown(types.SimpleNamespace()))


class BackgroundTest(unittest.TestCase):
    def test_turning_the_picture_off_brings_back_the_configured_image(self):
        opts = types.SimpleNamespace(background_image="/home/u/wall.png", background_image_layout="scaled")
        self.assertEqual(PX.configured_background(opts), ("/home/u/wall.png", "scaled"))

    def test_no_configured_image_clears(self):
        for v in (None, "", "none"):
            self.assertEqual(PX.configured_background(types.SimpleNamespace(background_image=v)), (None, None))

    def test_a_bar_that_left_the_left_edge_drops_its_picture_and_hit_bands(self):
        from unittest.mock import patch
        saved = dict(PX._S.windows)
        try:
            PX._S.windows[9] = {"sig": None, "right": 300, "hits": ()}
            with patch.object(PX, "metrics", return_value=None), patch.object(PX, "clear", wraps=PX.clear) as cl, \
                    patch.dict(sys.modules, {"kitty.fast_data_types": types.SimpleNamespace(
                        get_boss=lambda: types.SimpleNamespace(set_background_image=lambda *a, **k: None),
                        get_options=lambda: types.SimpleNamespace(), mark_os_window_dirty=lambda *_: None, wakeup_main_loop=lambda: None)}):
                self.assertFalse(PX.publish(9, (), None))
            cl.assert_called_once_with(9)
            self.assertFalse(PX.active(9))
        finally:
            PX._S.windows.clear()
            PX._S.windows.update(saved)


class DividerFirstTest(unittest.TestCase):
    def _press(self, in_divider):
        from unittest.mock import patch
        fdt = types.SimpleNamespace(GLFW_PRESS=1, GLFW_RELEASE=0, get_boss=lambda: None)
        tm = types.SimpleNamespace(os_window_id=7)
        BS._S.px_down = None
        with patch.dict(sys.modules, {"kitty.fast_data_types": fdt}), patch.object(PX, "active", return_value=True), \
                patch.object(PX, "close_hit", return_value=11), patch.object(PX, "band_at", return_value=None), \
                patch.object(BS, "_in_divider", return_value=in_divider):
            return BS._pxbar_click(tm, 298, 70, 1), BS._S.px_down

    def test_a_press_in_the_resize_zone_is_the_divider_not_the_cross(self):
        self.assertEqual(self._press(True), (False, None))

    def test_a_press_on_the_cross_outside_the_zone_arms_the_close(self):
        self.assertEqual(self._press(False), (True, ("close", 11)))


class ViewportFollowTest(unittest.TestCase):
    """The picture shows 10 rows here (a fake renderer): the active tab is always in view, a page click scrolls, and the
    view follows the active tab again once you change tab."""
    def setUp(self):
        from unittest.mock import patch
        import kittymux_groups as G
        self.G = G
        self.saved = (dict(PX._S.windows), dict(PX._S.view))
        PX._S.windows.clear()
        PX._S.view.clear()

        def fake_render(groups, pal, width, height, scale, host, resources, start, alpha=1.0):
            total = sum(len(g.rows) for g in groups)
            start = max(0, min(start, total - 1))
            shown = min(10, total - start)
            return types.SimpleNamespace(png=b"", hits=(), start=start, shown=shown, total=total)
        fdt = types.SimpleNamespace(get_boss=lambda: types.SimpleNamespace(set_background_image=lambda *a, **k: None),
                                    mark_os_window_dirty=lambda *_: None, wakeup_main_loop=lambda: None)
        bp = types.SimpleNamespace(render=fake_render)
        for p in (patch.object(PX, "metrics", return_value=(300, 900, 1.0)), patch.object(PX, "_resources", return_value=None),
                  patch.dict(sys.modules, {"kitty.fast_data_types": fdt, "kittymux_barpx": bp})):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        PX._S.windows.clear(); PX._S.windows.update(self.saved[0])
        PX._S.view.clear(); PX._S.view.update(self.saved[1])

    def groups(self, active):
        return self.G.group([self.G.Row(tab_id=i, title="t", project="p", active=(i == active)) for i in range(1, 41)],
                            collapse_after=99)

    def test_the_active_tab_is_scrolled_into_view(self):
        PX.publish(3, self.groups(35), None)
        self.assertEqual(PX._S.view[3]["start"], 27)          # rows 28..37: the active 35th with two more under it

    def test_a_page_click_scrolls_and_stays_until_you_change_tab(self):
        PX.publish(3, self.groups(5), None)
        self.assertEqual(PX._S.view[3]["start"], 0)
        PX.page(3, 1)
        PX.publish(3, self.groups(5), None)
        self.assertEqual(PX._S.view[3]["start"], 9)           # a page is the rows shown less one, so one row carries over
        PX.publish(3, self.groups(2), None)
        self.assertEqual(PX._S.view[3]["start"], 0)           # you went to tab 2 (row index 1): back in view, one row of context above

    def test_clearing_the_picture_forgets_the_view(self):
        PX.publish(3, self.groups(35), None)
        PX.clear(3)
        self.assertNotIn(3, PX._S.view)


class GlassTest(unittest.TestCase):
    def test_the_sidebar_is_a_little_denser_than_the_terminal(self):
        self.assertEqual(PX.glass_alpha(1.0), 1.0)
        self.assertEqual(PX.glass_alpha(0.85), 0.902)
        self.assertGreater(PX.glass_alpha(0.6), 0.6)
        self.assertEqual(PX.glass_alpha("bogus"), 1.0)


class ActionsTest(unittest.TestCase):
    def test_collapse_toggles_and_the_others_run_their_keys_action(self):
        from unittest.mock import patch
        tm = types.SimpleNamespace(active_tab=None)
        ran = []
        boss = types.SimpleNamespace(combine=lambda action, window_for_dispatch=None: ran.append(action))
        with patch.object(BS, "_toggle_collapsed") as tog, \
                patch.dict(sys.modules, {"kitty.fast_data_types": types.SimpleNamespace(get_boss=lambda: boss)}):
            for name in ("collapse", "search", "palette", "inbox", "usage", "keys", "nothing"):
                BS._px_action(tm, name)
        tog.assert_called_once_with(tm)
        self.assertEqual(len(ran), 5)
        self.assertTrue(ran[0].startswith("kitten ") and ran[0].endswith("python/palette-kit.py"))
        self.assertNotIn("@KITTYMUX_HOME@", " ".join(ran))

    def test_every_control_names_a_chord_the_template_maps(self):
        tpl = open(os.path.join(os.path.dirname(__file__), "..", "kittymux-keys.conf.tpl"), encoding="utf-8").read()
        for name, chord in BS.PX_CONTROL_KEYS.items():
            self.assertTrue(BS.mapped_action(chord, tpl, "/h"), f"{name}: {chord} is not mapped in kittymux-keys.conf.tpl")

    def test_the_footer_shows_the_palette_s_real_chord(self):
        import kittymux_barpx as BP
        self.assertEqual(BS.PX_CONTROL_KEYS["palette"], "ctrl+alt+shift+space")
        self.assertEqual(BP.PALETTE_CHORD, "⌃⌥⇧ Space")

    def test_a_control_band_wins_in_the_runtime_too(self):
        Ctl = namedtuple("Ctl", "kind y0 y1 tab_id project x0 x1")
        saved = dict(PX._S.windows)
        try:
            PX._S.windows[5] = {"sig": None, "right": 300, "hits": (
                Ctl("header", 0, 40, 0, "", 0, 0), Ctl("act", 4, 36, 0, "collapse", 260, 290))}
            self.assertEqual(PX.band_at(5, 270, 20).project, "collapse")
            self.assertEqual(PX.band_at(5, 100, 20).kind, "header")
        finally:
            PX._S.windows.clear(); PX._S.windows.update(saved)


class WaveTest(unittest.TestCase):
    """The working loader's animation runs only while a shown row works, motion is on and the shader is there; events fire on changes only."""
    def setUp(self):
        self.saved = dict(PX._S.wave)
        PX._S.wave.clear()

    def tearDown(self):
        PX._S.wave.clear(); PX._S.wave.update(self.saved)

    def groups(self, *states, muted=False):
        import kittymux_groups as G
        return G.group([G.Row(tab_id=i, title="t", project="p", state=s, muted=muted) for i, s in enumerate(states, 1)])

    def test_it_wants_a_working_row_motion_and_the_shader(self):
        self.assertTrue(PX.wants_wave(self.groups("idle", "working"), True, True))
        self.assertFalse(PX.wants_wave(self.groups("idle", "done"), True, True))
        self.assertFalse(PX.wants_wave(self.groups("working"), False, True))        # motion off
        self.assertFalse(PX.wants_wave(self.groups("working"), True, False))        # no shader: nothing to animate
        self.assertFalse(PX.wants_wave(self.groups("working", muted=True), True, True))

    def test_events_fire_only_when_the_answer_changes(self):
        fired = []
        f = lambda name, osw: fired.append((name, osw))
        for on in (True, True, False, False, True):
            PX.wave(4, on, fire=f)
        self.assertEqual(fired, [("kmx-wave-on", 4), ("kmx-wave-off", 4), ("kmx-wave-on", 4)])

    def test_the_pipeline_declares_both_events_and_a_calm_step(self):
        pl = open(os.path.join(os.path.dirname(__file__), "..", "assets", "shaders", "kittymux-pxbar.pipeline"), encoding="utf-8").read()
        self.assertIn("animation_start user:kmx-wave-on", pl)
        self.assertIn("animation_stop user:kmx-wave-off", pl)
        self.assertIn("shaders kittymux-pxwave", pl)
        step = int(pl.split("animation_step 66")[0] and 66)
        self.assertGreaterEqual(step, 50)                                            # 20 fps at most: a loader, not a video
