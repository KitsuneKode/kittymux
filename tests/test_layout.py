import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_layout as L  # noqa: E402


class RenderTests(unittest.TestCase):
    def test_full_vertical_uses_width(self):
        conf = L.render_conf(L.Layout("left", "full", 24))
        self.assertIn("tab_bar_edge left", conf)
        self.assertIn("tab_title_max_length 24", conf)
        self.assertIn("tab_bar_min_tabs 2", conf)

    def test_compact_is_a_slim_rail(self):
        conf = L.render_conf(L.Layout("left", "compact", 30))
        self.assertIn("tab_title_max_length 1", conf)       # 1 + 8 = a 9-column rail

    def test_hidden_never_shows_bar(self):
        conf = L.render_conf(L.Layout("left", "hidden"))
        self.assertIn("tab_bar_min_tabs 9999", conf)
        self.assertNotIn("tab_bar_min_tabs 2", conf)

    def test_horizontal_ignores_width(self):
        conf = L.render_conf(L.Layout("bottom", "full", 40))
        self.assertIn("tab_bar_edge bottom", conf)
        self.assertIn("tab_title_max_length 0", conf)

    def test_garbage_is_normalized_not_crashing(self):
        conf = L.render_conf(L.Layout("sideways", "loud", "wide"))
        self.assertIn("tab_bar_edge left", conf)
        self.assertIn("tab_title_max_length %d" % L.DEFAULT_WIDTH, conf)

    def test_every_preset_renders(self):
        for name, (layout, desc) in L.PRESETS.items():
            self.assertTrue(desc)
            self.assertIn("tab_bar_edge", L.render_conf(layout), name)


class TransitionTests(unittest.TestCase):
    def test_mode_cycle_is_full_compact_hidden(self):
        lay = L.Layout("left", "full")
        seen = []
        for _ in range(4):
            lay = L.next_mode(lay)
            seen.append(lay.mode)
        self.assertEqual(seen, ["compact", "hidden", "full", "compact"])

    def test_edge_cycle_visits_every_edge(self):
        lay = L.Layout("left")
        seen = []
        for _ in range(5):
            lay = L.next_edge(lay)
            seen.append(lay.edge)
        self.assertEqual(seen, ["bottom", "top", "right", "left", "bottom"])

    def test_top_is_part_of_the_cycle(self):
        self.assertEqual(L.next_edge(L.Layout("bottom")).edge, "top")
        self.assertEqual(L.next_edge(L.Layout("top")).edge, "right")

    def test_width_clamped_and_leaves_compact(self):
        lay = L.adjust_width(L.Layout("left", "compact", 20), +2)
        self.assertEqual((lay.mode, lay.width), ("full", 22))
        self.assertEqual(L.adjust_width(L.Layout("left", "full", L.WIDTH_MAX), +2).width, L.WIDTH_MAX)
        self.assertEqual(L.adjust_width(L.Layout("left", "full", L.WIDTH_MIN), -2).width, L.WIDTH_MIN)

    def test_preset_lookup(self):
        self.assertEqual(L.preset("zen").mode, "hidden")
        self.assertIsNone(L.preset("nope"))


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_fallback_chain_instance_default_none(self):
        self.assertIsNone(L.load(self.dir, 111))          # never chose one → hands off
        L.pin_default(self.dir, L.Layout("bottom", "full"))
        self.assertEqual(L.load(self.dir, 111).edge, "bottom")
        L.save(self.dir, 111, L.Layout("right", "compact"))
        self.assertEqual(L.load(self.dir, 111).edge, "right")
        self.assertEqual(L.load(self.dir, 222).edge, "bottom")

    def test_files_are_private(self):
        path = L.save(self.dir, 5, L.Layout())
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_corrupt_file_falls_back(self):
        open(os.path.join(self.dir, "layout-9.json"), "w").write("{nope")
        self.assertIsNone(L.load(self.dir, 9))

    def test_no_temp_files_left_behind(self):
        L.save(self.dir, 3, L.Layout())
        self.assertFalse([n for n in os.listdir(self.dir) if n.endswith(".tmp")])

    def test_cleanup_removes_only_dead_instances(self):
        L.save(self.dir, os.getpid(), L.Layout())            # alive
        L.save(self.dir, 2 ** 22 + 12345, L.Layout())        # not a live pid
        L.save(self.dir, None, L.Layout("top"))              # default: never removed
        self.assertEqual(L.cleanup_stale(self.dir), 1)
        names = sorted(os.listdir(self.dir))
        self.assertIn(f"layout-{os.getpid()}.json", names)
        self.assertIn("layout-default.json", names)

    def test_main_prints_nothing_when_user_never_chose(self):
        os.environ["KITTYMUX_STATE"] = self.dir
        os.environ["KITTYMUX_LAYOUT_PID"] = str(os.getpid())
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                L.main()
        finally:
            os.environ.pop("KITTYMUX_STATE"); os.environ.pop("KITTYMUX_LAYOUT_PID")
        self.assertEqual(buf.getvalue(), "")

    def test_legacy_edge_and_base_layout(self):
        cfg = tempfile.mkdtemp()
        open(os.path.join(cfg, "include-tab-edge.conf"), "w").write("# managed\ntab_bar_edge bottom\n")
        self.assertEqual(L.legacy_edge(cfg), "bottom")
        base = L.base_layout(self.dir, 1, cfg)
        self.assertEqual((base.edge, base.mode), ("bottom", "full"))
        L.save(self.dir, 1, L.Layout("right", "compact"))
        self.assertEqual(L.base_layout(self.dir, 1, cfg).edge, "right")
        self.assertIsNone(L.legacy_edge(tempfile.mkdtemp()))
        self.assertEqual(L.base_layout(self.dir, 2, tempfile.mkdtemp()).edge, "right")    # a new kitty follows the last choice

    def test_main_prints_conf_for_forced_pid(self):
        live = os.getpid()      # cleanup_stale() rightly deletes files of dead pids
        L.save(self.dir, live, L.Layout("bottom", "hidden"))
        os.environ["KITTYMUX_STATE"] = self.dir
        os.environ["KITTYMUX_LAYOUT_PID"] = str(live)
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                L.main()
        finally:
            os.environ.pop("KITTYMUX_STATE"); os.environ.pop("KITTYMUX_LAYOUT_PID")
        self.assertIn("tab_bar_edge bottom", buf.getvalue())
        self.assertIn("tab_bar_min_tabs 9999", buf.getvalue())


class CommandTests(unittest.TestCase):
    base = L.Layout("left", "full", 20)

    def test_mode_and_edge(self):
        self.assertEqual(L.apply_command(self.base, "mode", "zen" if False else "hidden").mode, "hidden")
        self.assertEqual(L.apply_command(self.base, "mode").mode, "compact")
        self.assertEqual(L.apply_command(self.base, "edge", "top").edge, "top")
        self.assertEqual(L.apply_command(self.base, "edge").edge, "bottom")

    def test_width_forms(self):
        self.assertEqual(L.apply_command(self.base, "width", "+2").width, 22)
        self.assertEqual(L.apply_command(self.base, "width", "-4").width, 16)
        self.assertEqual(L.apply_command(self.base, "width", "30").width, 30)
        self.assertEqual(L.apply_command(self.base, "width", "999").width, L.WIDTH_MAX)

    def test_preset(self):
        self.assertEqual(L.apply_command(self.base, "preset", "rail").mode, "compact")

    def test_bad_input_raises_helpfully(self):
        for cmd, arg in (("mode", "loud"), ("edge", "diagonal"), ("width", "wide"), ("preset", "nope"), ("bogus", "")):
            with self.assertRaises(ValueError):
                L.apply_command(self.base, cmd, arg)

    def test_describe(self):
        self.assertIn("rail", L.describe(L.Layout("left", "compact")))
        self.assertIn("hidden", L.describe(L.Layout("left", "hidden")))
        self.assertIn("width", L.describe(L.Layout("left", "full", 24)))
        self.assertNotIn("width", L.describe(L.Layout("bottom", "full")))


class DragMathTests(unittest.TestCase):
    def test_left_edge_width_follows_pointer(self):
        # cell 10px: pointer at 280px → 28 cols → tab_title_max_length 20
        self.assertEqual(L.width_from_pointer(280, 10, 1300, "left"), 20)
        self.assertEqual(L.width_from_pointer(380, 10, 1300, "left"), 30)

    def test_right_edge_measures_from_the_other_side(self):
        self.assertEqual(L.width_from_pointer(1020, 10, 1300, "right"), 20)

    def test_minimum_never_goes_compact_or_negative(self):
        self.assertEqual(L.width_from_pointer(0, 10, 1300, "left"), L.WIDTH_MIN)
        self.assertEqual(L.width_from_pointer(-500, 10, 1300, "left"), L.WIDTH_MIN)

    def test_maximum_is_a_third_of_the_window_and_hard_cap(self):
        # 130 cols wide window → a third = 43 cols → 35 after padding (measured against real kitty)
        self.assertEqual(L.max_width_for(130), 35)
        self.assertEqual(L.width_from_pointer(1290, 10, 1300, "left"), 35)
        self.assertLessEqual(L.max_width_for(400), L.WIDTH_MAX)       # huge window: hard cap applies
        # a narrow 60-col window: a third = 20 cols → 12
        self.assertEqual(L.max_width_for(60), 12)
        self.assertGreaterEqual(L.max_width_for(10), L.WIDTH_MIN)     # never below the minimum

    def test_grab_zone(self):
        # bar's inner edge at 280, 10 px cells: the divider is the seam at 270, the hit area ±12 px around it
        self.assertTrue(L.in_grab_zone(270, 280, 10))
        self.assertTrue(L.in_grab_zone(280, 280, 10))
        self.assertTrue(L.in_grab_zone(258, 280, 10))
        self.assertFalse(L.in_grab_zone(257, 280, 10))
        self.assertFalse(L.in_grab_zone(300, 280, 10))
        self.assertFalse(L.in_grab_zone(200, 280, 10))

    def test_bad_cell_width_is_safe(self):
        self.assertEqual(L.width_from_pointer(100, 0, 1300, "left"), L.DEFAULT_WIDTH)

class SnapTabIdTests(unittest.TestCase):
    # two-line tabs with one spacer row between them, header row on tab 11: rows 0-2 | 4-5 | 7-8
    EXT = [(11, 0, 2), (12, 4, 5), (13, 7, 8)]

    def test_rows_inside_a_tab_are_that_tab(self):
        for row, want in ((0, 11), (2, 11), (4, 12), (5, 12), (7, 13), (8, 13)):
            self.assertEqual(L.snap_tab_id(self.EXT, row), want)

    def test_spacer_rows_snap_to_the_nearer_tab(self):
        self.assertEqual(L.snap_tab_id([(11, 0, 1), (12, 3, 4)], 2), 12)          # tie → lower tab
        self.assertEqual(L.snap_tab_id([(11, 0, 1), (12, 4, 5)], 2), 11)          # nearer the upper one
        self.assertEqual(L.snap_tab_id([(11, 0, 1), (12, 4, 5)], 3), 12)          # nearer the lower one

    def test_the_gap_never_means_the_last_tab(self):                               # the actual bug
        self.assertEqual(L.snap_tab_id(self.EXT, 3), 12)
        self.assertEqual(L.snap_tab_id(self.EXT, 6), 13)
        self.assertNotEqual(L.snap_tab_id(self.EXT, 3), 13)

    def test_outside_the_list_is_no_tab(self):
        self.assertEqual(L.snap_tab_id(self.EXT, 9), 0)
        self.assertEqual(L.snap_tab_id(self.EXT, 30), 0)
        self.assertEqual(L.snap_tab_id([(11, 2, 3)], 0), 0)

    def test_synthetic_tabs_are_ignored(self):
        ext = [(11, 0, 1), (12, 3, 4), (-1, 6, 6)]                                 # "+" new-tab button
        self.assertEqual(L.snap_tab_id(ext, 5), 0)                                  # between last tab and "+"
        self.assertEqual(L.snap_tab_id(ext, 6), 0)

    def test_empty(self):
        self.assertEqual(L.snap_tab_id([], 3), 0)
        self.assertEqual(L.snap_tab_id([(0, 0, 5)], 2), 0)


class CollapseButtonTests(unittest.TestCase):
    def test_toggle_flips_between_full_and_rail_and_restores_from_hidden(self):
        full = L.Layout("left", "full", 24)
        self.assertEqual(L.toggle_collapsed(full), L.Layout("left", "compact", 24))
        self.assertEqual(L.toggle_collapsed(L.toggle_collapsed(full)), full)
        self.assertEqual(L.toggle_collapsed(L.Layout("right", "hidden", 20)).mode, "full")

    def test_the_button_is_a_comfortable_target(self):
        # bar 0..420 px, cell 15×22 px: header = 2 rows (44 px), zone starts 5 cells (75 px) from the edge
        z = lambda x, y, **kw: L.in_toggle_zone(x, y, 0, 420, 0, 15, 22, kw.pop("compact", False), **kw)
        self.assertTrue(z(350, 10))
        self.assertTrue(z(380, 40))                  # the second header row counts too
        self.assertFalse(z(300, 10))                 # the title area is not a button
        self.assertFalse(z(400, 10))                 # inner edge: the resize grab zone wins
        self.assertFalse(z(380, 50))                 # below the header
        zone_w = 420 - 1.5 * 15 - (420 - 5 * 15)
        self.assertGreaterEqual(zone_w, 45)          # at least ~44 px wide

    def test_a_one_row_header_only_counts_one_row(self):
        self.assertFalse(L.in_toggle_zone(380, 30, 0, 420, 0, 15, 22, False, 1))

    def test_release_slop_forgives_a_wobbly_click(self):
        self.assertFalse(L.in_toggle_zone(335, 20, 0, 420, 0, 15, 22, False))
        self.assertTrue(L.in_toggle_zone(335, 20, 0, 420, 0, 15, 22, False, slop=11))
        self.assertFalse(L.in_toggle_zone(400, 20, 0, 420, 0, 15, 22, False, slop=11))   # never into the resize edge

    def test_header_is_two_rows_only_when_the_bar_and_kittys_per_tab_cap_allow(self):
        self.assertEqual(L.header_rows(30, 4), 2)
        self.assertEqual(L.header_rows(5, 4), 1)                  # short bar
        self.assertEqual(L.header_rows(30, 3), 1)                 # tab_title_max_lines 3: header+title+subtitle must fit
        self.assertEqual(L.header_rows(30, 3, compact=True), 2)   # the rail's tab 1 is header + one row

    def test_the_whole_rail_header_is_the_expand_button(self):
        z = lambda x, y: L.in_toggle_zone(x, y, 0, 135, 0, 15, 22, True)
        self.assertTrue(z(10, 5))
        self.assertTrue(z(100, 30))
        self.assertFalse(z(10, 50))


class DefaultFollowsLastChoiceTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_an_instances_choice_becomes_the_default_for_new_kitties(self):
        L.save(self.d, 111, L.Layout("right", "compact", 24))
        self.assertEqual(L.load(self.d, 222), L.Layout("right", "compact", 24))     # a different, new kitty
        L.save(self.d, 333, L.Layout("top", "full", 20))                            # the latest choice wins
        self.assertEqual(L.load(self.d, 444), L.Layout("top", "full", 20))
        self.assertEqual(L.load(self.d, 111), L.Layout("right", "compact", 24))     # a running one keeps its own

    def test_a_pinned_default_is_not_overwritten(self):
        L.pin_default(self.d, L.Layout("left", "full", 28))
        L.save(self.d, 111, L.Layout("bottom", "full", 20))
        self.assertEqual(L.load(self.d, 999), L.Layout("left", "full", 28))
        self.assertEqual(L.load(self.d, 111), L.Layout("bottom", "full", 20))

    def test_clearing_unpins_and_forgets(self):
        L.pin_default(self.d, L.Layout("left", "full", 28))
        L.clear_default(self.d)
        self.assertIsNone(L.load(self.d, 999))
        L.save(self.d, 111, L.Layout("top", "full", 20))
        self.assertEqual(L.load(self.d, 999), L.Layout("top", "full", 20))


class DragTargetTests(unittest.TestCase):
    # tab 1 is tall (header): rows 2-5; tab 2 rows 7-8; tab 3 rows 10-11; tab 4 rows 13-14
    E = [(1, 2, 5), (2, 7, 8), (3, 10, 11), (4, 13, 14)]

    def test_dragging_down_a_tab_counts_only_past_its_midpoint(self):
        # dragging tab 2 down over tab 3 (rows 10-11, midpoint 11.0)
        self.assertEqual(L.drag_target(self.E, 2, 3, 10.2), 2)       # just touched it: nothing yet
        self.assertEqual(L.drag_target(self.E, 2, 3, 10.9), 2)
        self.assertEqual(L.drag_target(self.E, 2, 3, 11.1), 3)       # past the middle: swap

    def test_dragging_up_mirrors_it(self):
        # dragging tab 3 up over tab 2 (rows 7-8, midpoint 8.0)
        self.assertEqual(L.drag_target(self.E, 3, 2, 8.8), 3)
        self.assertEqual(L.drag_target(self.E, 3, 2, 7.9), 2)

    def test_a_tall_tab_needs_the_pointer_past_its_own_middle(self):
        # dragging tab 2 up over the tall tab 1 (rows 2-5, midpoint 4.0)
        self.assertEqual(L.drag_target(self.E, 2, 1, 5.5), 2)
        self.assertEqual(L.drag_target(self.E, 2, 1, 3.5), 1)

    def test_over_itself_nothing_or_unknown_ids_pass_through(self):
        self.assertEqual(L.drag_target(self.E, 2, 2, 7.5), 2)
        self.assertEqual(L.drag_target(self.E, 2, 0, 9.0), 0)
        self.assertEqual(L.drag_target(self.E, 2, -1, 9.0), -1)     # the "+" button
        self.assertEqual(L.drag_target(self.E, 99, 3, 10.5), 3)     # dragged tab not in the bar (another window's)


class HitAreaTests(unittest.TestCase):
    def test_hit_area_is_the_two_divider_columns_and_nothing_else(self):
        edge, cw = 390.0, 15.0
        self.assertTrue(L.in_grab_zone(edge - 2 * cw, edge, cw))                 # left end: the first divider column
        self.assertFalse(L.in_grab_zone(edge - 2 * cw - 1, edge, cw))            # the column of tab numbers / state marks is NOT grabbable
        self.assertTrue(L.in_grab_zone(edge - 1, edge, cw))                      # right end: the bar's last pixel

    def test_hit_area_is_centred_on_the_visible_lines(self):
        edge, cw = 390.0, 15.0
        centre = edge - L.DIVIDER_CELLS * cw
        for dx in (-14, -7, 0, 7, 14):
            self.assertTrue(L.in_grab_zone(centre + dx, edge, cw), dx)
        self.assertEqual(sum(L.in_grab_zone(x, edge, cw) for x in range(0, 400)), 2 * int(cw) + 1)   # ~30 px: a comfortable target

    def test_small_cells_still_get_a_usable_target(self):
        edge, cw = 200.0, 8.0
        width = sum(L.in_grab_zone(x, edge, cw) for x in range(0, 300))
        self.assertGreaterEqual(width, 2 * int(L.GRAB_MIN_PX))

    def test_collapse_button_stops_where_the_hit_area_starts(self):
        edge, cw = 390.0, 15.0
        for x in range(0, 400):
            self.assertFalse(L.in_grab_zone(x, edge, cw) and L.in_toggle_zone(x, 30, edge - 200, edge, 0, cw, 20, False, 2, 0.0), x)


if __name__ == "__main__":
    unittest.main()
