import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_deck as D  # noqa: E402


def mk(n, session, **kw):
    return [D.RowData(tab_id=i, win_id=i, session=session, title=f"{session}{i}", **kw) for i in range(n)]


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

    def test_no_session_label(self):
        items, _ = D.flatten(D.group_rows(mk(1, ""), ""), "")
        self.assertEqual(items[0].label, D.NO_SESSION)


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
        self.assertIn("click", D.hint(36))

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


if __name__ == "__main__":
    unittest.main()
