import os
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_deck as D  # noqa: E402


def mk(n, session, **kw):
    return [D.RowData(tab_id=i, win_id=i, session=session, title=f"{session}{i}", **kw) for i in range(n)]


class LatestWorkerTests(unittest.TestCase):
    def test_numbered_layout_includes_middle_and_focused_pane(self):
        rects = tuple((i + 1, 0, i * 100, 100, (i + 1) * 100) for i in range(3))
        drawing = "\n".join(D.numbered_layout(rects, 24, 10, 2))
        for label in ("1", "[2]", "3"):
            self.assertIn(label, drawing)
        self.assertTrue(all(len(line) <= 24 for line in drawing.splitlines()))

    def test_wrapped_details_are_sanitized_and_preserve_long_values(self):
        text = "long/path/" * 8
        lines = D.wrap_detail(text + "\x1b[31m", 20)
        self.assertTrue(all(len(line) <= 20 for line in lines))
        self.assertNotIn("\x1b", "".join(lines))
        self.assertIn(text, "".join(lines))

    def test_overview_never_silently_omits_a_pane(self):
        rects = tuple((i + 1, 0, i * 100, 100, (i + 1) * 100) for i in range(3))
        self.assertIsNone(D.complete_minimap(rects, 8, 1))
        self.assertIsNotNone(D.complete_minimap(rects, 8, 3))
        tiny = ((1, 0, 0, 1, 100), (2, 1, 0, 100, 100))
        self.assertIsNone(D.complete_minimap(tiny, 8, 1))

    def test_cached_geometry_is_immutable_and_bounded(self):
        rects = ((1, 0, 0, 50, 40), (2, 50, 0, 100, 40))
        a = D.complete_minimap(rects, 8, 1)
        self.assertIs(a, D.complete_minimap(rects, 8, 1))
        self.assertIsInstance(a, tuple)
        self.assertLessEqual(D.cached_minimap.cache_info().maxsize, 256)

    def test_blocked_worker_coalesces_and_generations_reject_aba(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        calls, results = [], []

        def work(value):
            calls.append(value)
            if len(calls) == 1:
                entered.set()
                self.assertTrue(release.wait(2))
            return value

        def complete(generation, value):
            results.append((generation, value))
            if len(results) == 2:
                finished.set()

        worker = D.LatestWorker(work, complete)
        first = worker.submit("A")
        self.assertTrue(entered.wait(1))
        worker.submit("B")
        last = worker.submit("A")
        for _ in range(100):
            last = worker.submit("A")
        self.assertEqual(calls, ["A"])
        release.set()
        self.assertTrue(finished.wait(1))
        self.assertEqual(calls, ["A", "A"])
        self.assertFalse(worker.is_current(first))
        self.assertTrue(worker.is_current(last))
        worker.close()
        self.assertFalse(worker.is_current(last))

    def test_close_discards_preview_but_can_drain_final_resize(self):
        for drain in (False, True):
            entered, release, ended = threading.Event(), threading.Event(), threading.Event()
            calls = []

            def work(value):
                calls.append(value)
                if value == 1:
                    entered.set()
                    release.wait(2)
                else:
                    ended.set()

            worker = D.LatestWorker(work, lambda *args: ended.set() if not drain else None)
            worker.submit(1)
            self.assertTrue(entered.wait(1))
            worker.submit(2)
            worker.close(drain=drain)
            self.assertIsNone(worker.submit(3))
            release.set()
            self.assertTrue(ended.wait(1))
            self.assertEqual(calls, [1, 2] if drain else [1])

    def test_pending_final_write_obligation_survives_newer_motion(self):
        entered, release, ended = threading.Event(), threading.Event(), threading.Event()
        calls = []

        def work(request):
            calls.append(request)
            if len(calls) == 1:
                entered.set()
                release.wait(2)
            else:
                ended.set()

        worker = D.LatestWorker(work, lambda *args: None,
                                coalesce=lambda old, new: (new[0], old[1] or new[1]), daemon=False)
        worker.submit((20, False))
        self.assertTrue(entered.wait(1))
        worker.submit((30, True))
        worker.submit((40, False))
        worker.close(drain=True)
        release.set()
        self.assertTrue(ended.wait(1))
        self.assertEqual(calls, [(20, False), (40, True)])

    def test_exception_does_not_strand_pending_work(self):
        ended = threading.Event()
        results = []

        def fail(value):
            raise RuntimeError("failed request")

        def complete(generation, result):
            results.append(result)
            ended.set()

        worker = D.LatestWorker(fail, complete)
        worker.submit(1)
        self.assertTrue(ended.wait(1))
        self.assertEqual(results, [None])
        worker.close()


class TargetOwnerTests(unittest.TestCase):
    def test_pane_pid_is_a_child_not_the_kitty_owner(self):
        data = [{"id": 1, "tabs": [{"windows": [{"pid": 501}, {"pid": 502}]}]}]
        self.assertEqual(D.target_owner(data, {501: 123, 502: 123}, {123}), 123)

    def test_proc_verification_handles_custom_socket_without_guessing_owner_ids(self):
        data = [{"id": 999, "tabs": [{"windows": [{"id": 1, "pid": 501}]}]}]
        with patch("pathlib.Path.read_text", return_value="501 (shell with ) spaces) S 123 0 0"), \
             patch("os.readlink", return_value="/usr/bin/kitty") as readlink:
            self.assertEqual(D.target_pid(data), 123)
            readlink.assert_called_with("/proc/123/exe")
        with patch("pathlib.Path.read_text", side_effect=FileNotFoundError):
            self.assertEqual(D.target_pid(data), 0)
        with patch("pathlib.Path.read_text", return_value="501 (shell) S 123 0 0"), \
             patch("os.readlink", return_value="/usr/bin/not-kitty"):
            self.assertEqual(D.target_pid(data), 0)

    def test_vanished_child_does_not_hide_verified_live_owner(self):
        data = [{"tabs": [{"windows": [{"pid": 501}, {"pid": 502}]}]}]
        self.assertEqual(D.target_owner(data, {501: 123}, {123}), 123)
        self.assertEqual(D.target_owner(data, {}, {123}), 0)

    def test_ambiguous_or_nonkitty_parents_fail_closed(self):
        data = [{"tabs": [{"windows": [{"pid": 501}, {"pid": 502}]}]}]
        self.assertEqual(D.target_owner(data, {501: 123, 502: 456}, {123, 456}), 0)
        self.assertEqual(D.target_owner(data, {501: 123, 502: 123}, set()), 0)
        self.assertEqual(D.target_owner([], {}, {123}), 0)


class GroupTests(unittest.TestCase):
    def test_current_first_then_alpha_then_nosession(self):
        rows = mk(1, "zeta") + mk(1, "") + mk(2, "alpha") + mk(1, "beta")
        names = [n for n, _ in D.group_rows(rows, "beta")]
        self.assertEqual(names, ["beta", "alpha", "zeta", ""])

    def test_indices_are_per_session(self):
        rows = mk(2, "a") + mk(2, "b")
        groups = D.group_rows(rows, "a")
        self.assertEqual([r.index for r in groups[0][1]], [1, 2])
        self.assertEqual([r.index for r in groups[1][1]], [1, 2])

    def test_flatten_headers_and_rows(self):
        groups = D.group_rows(mk(2, "a") + mk(1, "b"), "a")
        items, flat = D.flatten(groups, "a")
        self.assertEqual([i.kind for i in items], ["header", "row", "row", "header", "row"])
        self.assertEqual(len(flat), 3)
        self.assertTrue(items[0].current)
        self.assertFalse(items[3].current)
        self.assertEqual(items[3].label, "b")

    def test_a_lone_unnamed_group_has_no_header_and_an_unnamed_group_beside_a_named_one_is_called_other_tabs(self):
        items, flat = D.flatten(D.group_rows(mk(2, ""), ""), "")
        self.assertEqual([i.kind for i in items], ["row", "row"])               # "N tabs" says it already
        self.assertEqual(len(flat), 2)
        items, _ = D.flatten(D.group_rows(mk(1, "work") + mk(1, ""), "work"), "work")
        self.assertEqual([i.label for i in items if i.kind == "header"], ["work", D.NO_SESSION])
        self.assertEqual(D.NO_SESSION, "other tabs")
        items, _ = D.flatten(D.group_rows(mk(1, "work"), "work"), "work")
        self.assertEqual(items[0].kind, "header")                                # a named session still says which one you are in

    def test_a_header_counts_the_rows_that_ask_for_you(self):
        rows = mk(4, "work")
        rows[0].status, rows[1].status, rows[2].status = "waiting", "limited", "working"
        items, _ = D.flatten(D.group_rows(rows, "work"), "work")
        self.assertEqual((items[0].count, items[0].attn), (4, 2))


class TidyPreviewTests(unittest.TestCase):
    SCREEN = ["", "\u250c" + "\u2500" * 30 + "\u2510", "\u2502 Audit codebase security and de \u2502", "\u2502 login RAM, verify the mount     \u2502", "\u2514" + "\u2500" * 30 + "\u2518",
              "\u26a0 5h 41% left", "\u203a Ask Codex to do anything", "? for shortcuts", "gpt-6.1 high \u00b7 Context 55% used", "esc to interrupt", "---------"]

    def test_real_lines_stay_and_chrome_goes(self):
        got = D.tidy_preview(self.SCREEN, 10)
        self.assertEqual(got, ["Audit codebase security and de", "login RAM, verify the mount", "\u26a0 5h 41% left", "\u203a Ask Codex to do anything"])

    def test_it_keeps_the_last_n_and_never_more(self):
        lines = [f"line {i}" for i in range(20)]
        self.assertEqual(D.tidy_preview(lines, 3), ["line 17", "line 18", "line 19"])
        self.assertEqual(D.tidy_preview(lines, 0), [])
        self.assertEqual(D.tidy_preview(lines, -2), [])
        self.assertEqual(len(D.tidy_preview(lines, 99)), 20)

    def test_repeats_blank_and_hostile_lines(self):
        self.assertEqual(D.tidy_preview(["a", "a", "", "   ", "a", "b", "a"], 5), ["a", "b", "a"])     # blanks go first, then back-to-back repeats collapse; a later repeat stays
        out = D.tidy_preview(["ok\x1b[31m red\x1b]0;x\x07", "tab\there"], 5)
        self.assertTrue(all("\x1b" not in l and "\x07" not in l for l in out))
        self.assertEqual(D.tidy_preview(None, 3), [])
        self.assertEqual(D.tidy_preview([5, None, b"x"], 3), ["5", "None", "b'x'"])

    def test_an_all_chrome_screen_is_empty_not_invented(self):
        self.assertEqual(D.tidy_preview(["\u2500" * 20, "? for shortcuts", "", "esc to interrupt"], 5), [])

    def test_a_long_real_line_that_merely_mentions_a_hint_is_kept(self):
        line = "The docs say press ctrl+c to stop the server, and then we need to rerun the migration with the new flags so the schema matches"
        self.assertEqual(D.tidy_preview([line], 3), [line])


class HitTests(unittest.TestCase):
    def setUp(self):
        groups = D.group_rows(mk(2, "a") + mk(2, "b"), "a")
        self.items, self.flat = D.flatten(groups, "a")
        # y: 0 header a, 1-2 row0, 3-4 row1, 5 header b, 6-7 row2, 8-9 row3

    def test_row_at(self):
        f = lambda y: D.row_at(self.items, 0, 20, y)
        self.assertEqual(f(0), -1)
        self.assertEqual((f(1), f(2)), (0, 0))
        self.assertEqual((f(3), f(4)), (1, 1))
        self.assertEqual(f(5), -1)
        self.assertEqual((f(6), f(7), f(8), f(9)), (2, 2, 3, 3))
        self.assertEqual(f(10), -1)

    def test_row_at_respects_scroll(self):
        # item 5 is row 3; scrolled so it is the first visible item
        self.assertEqual(D.row_at(self.items, 5, 20, 0), 3)

    def test_partial_items_are_not_visible(self):
        vis = D.visible(self.items, 0, 4)   # header(1) + row(2) fit, next row(2) does not
        self.assertEqual([it.kind for _, it in vis], ["header", "row"])

    def test_ensure_visible_scrolls_down_and_shows_header(self):
        scroll = D.ensure_visible(self.items, 0, 3, 5)   # avail 5 lines, select row 3 (last)
        vis_rows = [it.row for _, it in D.visible(self.items, scroll, 5) if it.kind == "row"]
        self.assertIn(3, vis_rows)

    def test_ensure_visible_scrolls_up(self):
        self.assertEqual(D.ensure_visible(self.items, 6, 0, 20), 0)


class StepTests(unittest.TestCase):
    def test_step_row_clamps(self):
        self.assertEqual(D.step_row(0, -1, 3), 0)
        self.assertEqual(D.step_row(2, 1, 3), 2)
        self.assertEqual(D.step_row(0, 0, 0), 0)

    def test_step_group(self):
        flat = mk(2, "a") + mk(2, "b") + mk(1, "c")
        self.assertEqual(D.step_group(flat, 1, 1), 2)    # a → first of b
        self.assertEqual(D.step_group(flat, 3, -1), 0)   # b → first of a
        self.assertEqual(D.step_group(flat, 4, 1), 4)    # last group stays


class TextTests(unittest.TestCase):
    def test_hint_never_exceeds_width(self):
        for w in range(0, 90):
            self.assertLessEqual(len(D.hint(w)), w)

    def test_hint_full_when_wide(self):
        self.assertIn("/ find", D.hint(36))
        self.assertIn("a absorb", D.hint(80))

    def test_fit_and_pad(self):
        self.assertEqual(D.fit("abcdef", 4), "abc…")
        self.assertEqual(D.fit("abc", 4), "abc")
        self.assertEqual(D.pad("ab", 5), "ab   ")
        self.assertEqual(len(D.pad("abcdefgh", 5)), 5)
        self.assertEqual(D.fit("x", 0), "")

    def test_fit_with_wide_cells(self):
        wide = lambda s: sum(2 if ord(c) > 0x2e80 else 1 for c in s)
        self.assertLessEqual(wide(D.fit("日本語日本語", 7, wide)), 7)


SS = """LISTEN 0 511 127.0.0.1:3000 0.0.0.0:* users:(("node",pid=4242,fd=19))
LISTEN 0 4096 [::]:5432 [::]:* users:(("postgres",pid=900,fd=5))
LISTEN 0 128 0.0.0.0:8080 0.0.0.0:* users:(("python3",pid=4300,fd=3),("python3",pid=4301,fd=3))
LISTEN 0 128 0.0.0.0:22 0.0.0.0:*
"""


class PortTests(unittest.TestCase):
    def test_parse_ss(self):
        got = D.parse_ss(SS)
        self.assertIn((3000, 4242), got)
        self.assertIn((5432, 900), got)
        self.assertIn((8080, 4301), got)
        self.assertFalse(any(port == 22 for port, _ in got))   # no pid → skipped

    def test_descendants_and_ports(self):
        # pane shell 4000 → npm 4100 → node 4242 ; python 4300/4301 under 4200 ; postgres unrelated
        children = D.children_map({4100: 4000, 4242: 4100, 4200: 4000, 4300: 4200, 4301: 4200, 900: 1})
        self.assertEqual(D.descendants(4000, children), {4000, 4100, 4242, 4200, 4300, 4301})
        self.assertEqual(D.ports_for(4000, children, D.parse_ss(SS)), (3000, 8080))

    def test_no_processes_no_ports(self):
        self.assertEqual(D.ports_for(1234, {}, D.parse_ss(SS)), ())

    def test_cycle_safe(self):
        children = {1: [2], 2: [1]}
        self.assertEqual(D.descendants(1, children), {1, 2})


class PanelDragTests(unittest.TestCase):
    def test_grab_zone_is_the_inner_edge(self):
        self.assertTrue(D.in_grab_zone(31, 32))
        self.assertTrue(D.in_grab_zone(30, 32))
        self.assertFalse(D.in_grab_zone(29, 32))
        self.assertFalse(D.in_grab_zone(0, 0))

    def test_drag_columns_clamped(self):
        self.assertEqual(D.drag_columns(43), 44)
        self.assertEqual(D.drag_columns(2), D.PANEL_MIN_COLS)
        self.assertEqual(D.drag_columns(500), D.PANEL_MAX_COLS)

    def test_throttle_rate_and_dedupe(self):
        t = D.DragThrottle(interval=0.1)
        self.assertTrue(t.should_send(0.0, 40))
        self.assertFalse(t.should_send(0.02, 41))           # too soon
        self.assertFalse(t.should_send(0.2, 40))            # same target as last sent
        self.assertTrue(t.should_send(0.2, 42))
        self.assertTrue(t.should_send(0.21, 42, final=True))  # release always lands


class PaneRowsTests(unittest.TestCase):
    def split_rows(self):
        rows = [D.RowData(tab_id=1, win_id=1, session="a", title="one"),
                D.RowData(tab_id=2, win_id=2, session="a", title="two",
                          pane_rows=tuple(D.PaneData(win_id=10 + i) for i in range(3))),
                D.RowData(tab_id=3, win_id=3, session="a", title="three")]
        return D.flatten(D.group_rows(rows, "a"), "a")

    def test_a_split_tab_gets_one_child_line_per_pane(self):
        items, flat = self.split_rows()
        kinds = [(it.kind, it.row, it.pane) for it in items]
        self.assertEqual(kinds, [("header", -1, -1), ("row", 0, -1), ("row", 1, -1), ("pane", 1, 0),
                                 ("pane", 1, 1), ("pane", 1, 2), ("row", 2, -1)])

    def test_a_single_pane_tab_has_no_children(self):
        rows = [D.RowData(tab_id=1, win_id=1, session="a", pane_rows=(D.PaneData(win_id=1),))]
        items, _ = D.flatten(D.group_rows(rows, "a"), "a")
        self.assertEqual([it.kind for it in items], ["header", "row"])

    def test_children_are_capped(self):
        rows = [D.RowData(tab_id=1, win_id=1, session="a", pane_rows=tuple(D.PaneData(win_id=i) for i in range(20)))]
        items, _ = D.flatten(D.group_rows(rows, "a"), "a")
        self.assertEqual(sum(1 for it in items if it.kind == "pane"), D.MAX_PANE_ROWS)

    def test_pane_at_and_row_at_do_not_mix(self):
        items, _ = self.split_rows()
        # y: header 0, row0 1-2, row1 3-4, panes 5,6,7, row2 8-9
        self.assertEqual(D.pane_at(items, 0, 30, 6), (1, 1))
        self.assertEqual(D.pane_at(items, 0, 30, 3), (-1, -1))
        self.assertEqual(D.row_at(items, 0, 30, 6), -1)
        self.assertEqual(D.row_at(items, 0, 30, 8), 2)

    def test_selecting_a_split_row_keeps_its_children_in_view(self):
        items, _ = self.split_rows()
        scroll = D.ensure_visible(items, 0, 1, 6)           # row1 (2) + its 3 panes = 5 lines fit in 6
        shown = [it for _o, it in D.visible(items, scroll, 6)]
        self.assertEqual(sum(1 for it in shown if it.kind == "pane"), 3)
        self.assertTrue(any(it.kind == "row" and it.row == 1 for it in shown))


class AbsorbTests(unittest.TestCase):
    def rows(self):
        return [D.RowData(tab_id=1, win_id=10, win_ids=(10,), current=True),
                D.RowData(tab_id=2, win_id=20, win_ids=(20, 21)),
                D.RowData(tab_id=3, win_id=30)]            # no window list: nothing to move

    def test_selected_tabs_windows_go_to_the_current_tab(self):
        self.assertEqual(D.absorb_plan(self.rows(), 1), ([20, 21], 1))

    def test_nothing_to_do_for_the_current_tab_an_empty_row_or_no_current_tab(self):
        self.assertEqual(D.absorb_plan(self.rows(), 0), ([], 0))
        self.assertEqual(D.absorb_plan(self.rows(), 2), ([], 0))
        self.assertEqual(D.absorb_plan(self.rows(), 9), ([], 0))
        rows = self.rows()
        rows[0].current = False
        self.assertEqual(D.absorb_plan(rows, 1), ([], 0))


class PromoteTests(unittest.TestCase):
    def split(self):
        return [D.RowData(tab_id=1, win_id=10, win_ids=(10,)),
                D.RowData(tab_id=2, win_id=20, win_ids=(20, 21, 22),
                          pane_rows=(D.PaneData(win_id=20), D.PaneData(win_id=21, active=True), D.PaneData(win_id=22)))]

    def test_the_hovered_pane_is_promoted(self):
        self.assertEqual(D.promote_target(self.split(), 1, (1, 2)), 22)

    def test_without_a_hover_the_focused_pane_is_promoted(self):
        self.assertEqual(D.promote_target(self.split(), 1), 21)
        self.assertEqual(D.promote_target(self.split(), 1, (0, 1)), 21)           # a hover on ANOTHER tab's pane is ignored

    def test_a_single_pane_tab_has_nothing_to_promote(self):
        self.assertEqual(D.promote_target(self.split(), 0), 0)
        self.assertEqual(D.promote_target(self.split(), 7), 0)


class SearchTests(unittest.TestCase):
    def groups(self):
        rows = [D.RowData(tab_id=1, win_id=1, session="work", title="api server", branch="feat/login", agent="claude"),
                D.RowData(tab_id=2, win_id=2, session="work", title="docs", branch="main", cwd="/home/u/docs", status="waiting",
                          msg="Approve: rm -rf node_modules?"),
                D.RowData(tab_id=3, win_id=3, session="play", title="sweep", branch="fix/resolve-gate", agent="codex")]
        return D.group_rows(rows, "work")

    def names(self, q):
        return [r.title for _n, members in D.filter_groups(self.groups(), q) for r in members]

    def test_every_word_must_match_somewhere(self):
        self.assertEqual(self.names("claude login"), ["api server"])
        self.assertEqual(self.names("fix gate"), ["sweep"])
        self.assertEqual(self.names("waiting"), ["docs"])                # state
        self.assertEqual(self.names("node_modules"), ["docs"])           # the agent's message
        self.assertEqual(self.names("PLAY"), ["sweep"])                  # session, case-insensitive

    def test_empty_query_keeps_everything_and_unknown_drops_everything(self):
        self.assertEqual(len(self.names("")), 3)
        self.assertEqual(self.names("zzz"), [])

    def test_empty_sessions_disappear_and_indexes_stay_those_of_the_full_list(self):
        groups = D.filter_groups(self.groups(), "docs")
        self.assertEqual([n for n, _m in groups], ["work"])
        self.assertEqual(groups[0][1][0].index, 2)                       # still tab 2 in its session, as the bar numbers it


class MiniMapTests(unittest.TestCase):
    def draw(self, rects, cols, rows):
        return ["".join(c[0] for c in line) for line in D.layout_minimap(rects, cols, rows)]

    def test_a_single_pane_is_one_solid_block(self):
        self.assertEqual(self.draw([(1, 0, 0, 100, 40)], 4, 1), ["████"])

    def test_two_panes_side_by_side_split_at_the_right_place(self):
        cells = D.layout_minimap([(1, 0, 0, 50, 40), (2, 50, 0, 100, 40)], 4, 1)
        self.assertEqual(["".join(c[0] for c in cells[0])], ["████"])                   # the split falls on a cell boundary
        self.assertEqual([c[1] for c in cells[0]], [1, 1, 2, 2])

    def test_a_split_inside_a_cell_uses_a_half_block(self):
        cells = D.layout_minimap([(1, 0, 0, 50, 40), (2, 50, 0, 100, 40)], 3, 1)       # 100/3: the boundary is mid-cell
        self.assertEqual(cells[0][1][0], "▌")
        self.assertEqual((cells[0][1][1], cells[0][1][2]), (1, 2))

    def test_stacked_panes_use_the_horizontal_half_blocks(self):
        cells = D.layout_minimap([(1, 0, 0, 100, 20), (2, 0, 20, 100, 40)], 2, 1)
        self.assertEqual(["".join(c[0] for c in cells[0])], ["▀▀"])
        self.assertEqual({(c[1], c[2]) for c in cells[0]}, {(1, 2)})

    def test_one_tall_left_and_two_stacked_right(self):
        cells = D.layout_minimap([(1, 0, 0, 50, 40), (2, 50, 0, 100, 20), (3, 50, 20, 100, 40)], 4, 2)
        ids = [[c[1] for c in line] for line in cells]
        self.assertEqual(ids, [[1, 1, 2, 2], [1, 1, 3, 3]])

    def test_gaps_between_panes_belong_to_the_nearest_one_and_empty_input_is_empty(self):
        self.assertEqual(len(D.layout_minimap([(1, 0, 0, 48, 40), (2, 52, 0, 100, 40)], 4, 1)[0]), 4)
        self.assertEqual(D.layout_minimap([], 4, 1), [])
        self.assertEqual(D.layout_minimap([(1, 0, 0, 10, 10)], 0, 1), [])


if __name__ == "__main__":
    unittest.main()
