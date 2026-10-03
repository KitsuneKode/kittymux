import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_join as J  # noqa: E402

# Geometries are pixels (left, top, right, bottom). kitty leaves a gap (border + padding) between neighbouring windows: 12 px here.
GAP = 12
W, H = 1000, 600


def left_right():
    return [(1, (0, 0, 494, H)), (2, (494 + GAP, 0, W, H))]


def three_panes():            # a big pane on the left, two stacked on the right
    return [(1, (0, 0, 494, H)), (2, (506, 0, W, 294)), (3, (506, 306, W, H))]


class AdjacencyTests(unittest.TestCase):
    def test_how_two_windows_touch(self):
        a, b = (0, 0, 494, 600), (506, 0, 1000, 600)
        self.assertEqual(J.adjacency(a, b, 40), (600, True, True))            # b is right of a
        self.assertEqual(J.adjacency(b, a, 40), (600, True, False))           # a is left of b
        c = (0, 612, 494, 1200)
        self.assertEqual(J.adjacency(a, c, 40), (494, False, True))           # c is below a
        self.assertEqual(J.adjacency(c, a, 40), (494, False, False))          # a is above c

    def test_windows_that_only_meet_at_a_corner_or_are_far_apart_do_not_touch(self):
        self.assertIsNone(J.adjacency((0, 0, 100, 100), (112, 112, 200, 200), 40))       # diagonal
        self.assertIsNone(J.adjacency((0, 0, 100, 100), (300, 0, 400, 100), 40))          # a gap of 200 px


class PlanTests(unittest.TestCase):
    def test_one_window_goes_next_to_the_targets_active_pane(self):
        self.assertEqual(J.plan([(7, (0, 0, W, H))], horizontal=True), [J.Step(7, None, True, True)])
        self.assertEqual(J.plan([(7, (0, 0, W, H))], horizontal=False), [J.Step(7, None, False, True)])

    def test_the_first_pane_follows_the_chosen_side_and_the_rest_keep_their_neighbours(self):
        steps = J.plan(left_right(), horizontal=False)                         # "below": the first pane goes under the target pane
        self.assertEqual(steps, [J.Step(1, None, False, True), J.Step(2, 1, True, True)])     # …and pane 2 stays to the RIGHT of pane 1

    def test_a_big_pane_and_a_stack_come_out_as_a_big_pane_and_a_stack(self):
        steps = J.plan(three_panes(), horizontal=True)
        self.assertEqual(steps, [J.Step(1, None, True, True), J.Step(2, 1, True, True), J.Step(3, 2, False, True)])

    def test_the_order_windows_are_listed_in_does_not_matter(self):
        shuffled = [three_panes()[2], three_panes()[0], three_panes()[1]]
        self.assertEqual(J.plan(shuffled, horizontal=True), J.plan(three_panes(), horizontal=True))

    def test_a_two_by_two_grid_keeps_its_shape(self):
        grid = [(1, (0, 0, 494, 294)), (2, (506, 0, W, 294)), (3, (0, 306, 494, H)), (4, (506, 306, W, H))]
        steps = J.plan(grid, horizontal=True)
        self.assertEqual([s.window for s in steps], [1, 2, 3, 4])
        by = {s.window: s for s in steps}
        self.assertEqual(by[2], J.Step(2, 1, True, True))        # right of 1
        self.assertEqual(by[3], J.Step(3, 1, False, True))       # below 1
        self.assertIn(by[4].next_to, (2, 3))                     # next to one of its real neighbours…
        self.assertEqual((by[4].horizontal, by[4].after), (False, True) if by[4].next_to == 2 else (True, True))   # …on the right edge of it

    def test_a_window_that_touches_nothing_is_still_placed(self):
        odd = [(1, (0, 0, 100, 100)), (2, (900, 500, 1000, 600))]
        steps = J.plan(odd, horizontal=True)
        self.assertEqual([s.window for s in steps], [1, 2])
        self.assertIsNotNone(steps[1].next_to)

    def test_every_window_is_placed_exactly_once_and_never_next_to_itself(self):
        import random
        rnd = random.Random(7)
        for _ in range(200):
            n = rnd.randint(1, 7)
            geoms = []
            for i in range(n):
                l, t = rnd.randint(0, 900), rnd.randint(0, 500)
                geoms.append((i + 1, (l, t, l + rnd.randint(50, 400), t + rnd.randint(50, 300))))
            steps = J.plan(geoms, horizontal=rnd.random() < 0.5)
            self.assertEqual(sorted(s.window for s in steps), sorted(g[0] for g in geoms))
            seen = set()
            for s in steps:
                self.assertNotEqual(s.next_to, s.window)
                self.assertTrue(s.next_to is None or s.next_to in seen)      # always next to a window that is already in place
                seen.add(s.window)
            self.assertEqual(steps[0].next_to, None)

    def test_nothing_in_nothing_out(self):
        self.assertEqual(J.plan([], horizontal=True), [])


class AutoSideTests(unittest.TestCase):
    def test_a_wide_pane_is_split_to_the_right_and_a_tall_one_below(self):
        self.assertEqual(J.auto_side(1000, 500), "right")
        self.assertEqual(J.auto_side(500, 1000), "below")
        self.assertEqual(J.auto_side(800, 800), "right")                  # a tie reads left to right
        self.assertEqual(J.auto_side(0, 0), "right")

    def test_side_names_map_to_kittys_flags(self):
        self.assertEqual(J.side_flags("right"), (True, True))
        self.assertEqual(J.side_flags("below"), (False, True))
        self.assertEqual(J.side_flags("left"), (True, False))
        self.assertEqual(J.side_flags("above"), (False, False))
        self.assertEqual(J.side_flags("nonsense"), (True, True))


class RowsTests(unittest.TestCase):
    TABS = [
        {"os": 1, "id": 10, "title": "notes", "cwd": "/home/u/notes", "panes": 1, "state": ""},
        {"os": 1, "id": 11, "title": "api", "cwd": "/work/api/src", "panes": 3, "state": "waiting"},
        {"os": 2, "id": 20, "title": "docs", "cwd": "/work/docs", "panes": 2, "state": ""},
        {"os": 1, "id": 12, "title": "web", "cwd": "/work/web", "panes": 1, "state": "working"},
    ]

    def test_the_source_tab_is_never_offered(self):
        ids = [r["id"] for r in J.rows(self.TABS, source_tab=11)]
        self.assertNotIn(11, ids)
        self.assertEqual(sorted(ids), [10, 12, 20])

    def test_a_tab_that_needs_you_comes_first(self):
        self.assertEqual(J.rows(self.TABS, source_tab=99)[0]["id"], 11)

    def test_filtering_matches_title_folder_and_state_in_any_order(self):
        rows = J.rows(self.TABS, source_tab=99)
        self.assertEqual([r["id"] for r in J.filter_rows(rows, "api")], [11])
        self.assertEqual([r["id"] for r in J.filter_rows(rows, "work docs")], [20])
        self.assertEqual([r["id"] for r in J.filter_rows(rows, "waiting")], [11])
        self.assertEqual(len(J.filter_rows(rows, "")), 4)
        self.assertEqual(J.filter_rows(rows, "zzz"), [])

    def test_the_row_knows_which_window_it_lives_in_when_there_are_several(self):
        rows = J.rows(self.TABS, source_tab=99)
        self.assertTrue(next(r for r in rows if r["id"] == 20)["other_window"])
        self.assertFalse(next(r for r in rows if r["id"] == 10)["other_window"])

    def test_nothing_to_join_into(self):
        self.assertEqual(J.rows([{"os": 1, "id": 10, "title": "x", "cwd": "", "panes": 1, "state": ""}], source_tab=10), [])


class RowBudgetTests(unittest.TestCase):
    def test_a_roomy_row_shows_everything(self):
        self.assertEqual(J.row_budget(60, title=4, count=6), (4, 9, 44))

    def test_a_narrow_row_drops_the_pane_count_before_the_folder(self):
        t, c, f = J.row_budget(20, title=10, count=6)
        self.assertEqual((t, c), (10, 0))
        self.assertGreaterEqual(f, 6)

    def test_the_title_is_never_dropped(self):
        for room in range(1, 40):
            self.assertGreater(J.row_budget(room, title=30, count=6)[0], 0)

    def test_a_long_title_leaves_room_for_the_folder(self):
        t, _c, f = J.row_budget(60, title=80, count=6)
        self.assertEqual(t, 30)
        self.assertGreater(f, 6)

    def test_nothing_ever_takes_more_than_the_room(self):
        for room in range(0, 120):
            for title in (1, 4, 12, 40, 90):
                t, c, f = J.row_budget(room, title, 8)
                self.assertLessEqual(t + c + (3 + f if f else 0), max(room, 0), (room, title, t, c, f))
                self.assertLessEqual(t, title)


class StepTests(unittest.TestCase):
    """The picker's keys, as pure state."""

    def test_selection_wraps_and_stays_in_range(self):
        st = J.Picker(n_rows=3)
        st.move(1); st.move(1); st.move(1)
        self.assertEqual(st.index, 0)
        st.move(-1)
        self.assertEqual(st.index, 2)
        st.n_rows = 0
        st.move(1)
        self.assertEqual(st.index, 0)

    def test_side_and_scope_cycle(self):
        st = J.Picker(n_rows=1)
        self.assertEqual(st.side, "auto")
        st.cycle_side()
        self.assertEqual(st.side, "right")
        st.cycle_side()
        self.assertEqual(st.side, "below")
        st.cycle_side()
        self.assertEqual(st.side, "auto")
        self.assertEqual(st.scope, "tab")
        st.toggle_scope()
        self.assertEqual(st.scope, "pane")

    def test_typing_filters_and_resets_the_selection(self):
        st = J.Picker(n_rows=5)
        st.index = 3
        st.type("a")
        self.assertEqual((st.query, st.index), ("a", 0))
        st.backspace()
        self.assertEqual(st.query, "")
        st.backspace()
        self.assertEqual(st.query, "")


if __name__ == "__main__":
    unittest.main()
