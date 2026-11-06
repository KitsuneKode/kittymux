"""Group by priority (Rex adoption): `g` lists every tab, across sessions, under Needs you → Working → Finished → Idle."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_deck as D  # noqa: E402


def row(tab, status, session="", title=None):
    return D.RowData(tab, tab * 10, session=session, title=title or f"t{tab}", status=status)


class ByStateTests(unittest.TestCase):
    def rows(self):
        return [row(1, "working", "a"), row(2, "", "a"), row(3, "waiting", "b"), row(4, "done", "b"),
                row(5, "limited", "a"), row(6, "error", "b"), row(7, "unread", "a"), row(8, "working", "b")]

    def test_states_in_priority_order_across_sessions(self):
        groups = D.group_by_state(D.group_rows(self.rows(), "a"))
        self.assertEqual([name for name, _m in groups], ["Needs you", "Working", "Finished", "Idle"])
        by = {name: [r.tab_id for r in m] for name, m in groups}
        self.assertEqual(by["Needs you"], [5, 3, 6])          # waiting, limited and error ask for you; session order kept inside
        self.assertEqual(by["Working"], [1, 8])
        self.assertEqual(by["Finished"], [4])
        self.assertEqual(by["Idle"], [2, 7])

    def test_empty_groups_are_left_out_and_tab_numbers_stay_the_bars(self):
        rows = [row(1, "working", "a"), row(2, "working", "a"), row(3, "", "b")]
        groups = D.group_by_state(D.group_rows(rows, "a"))
        self.assertEqual([name for name, _m in groups], ["Working", "Idle"])
        self.assertEqual([r.index for r in groups[0][1]], [1, 2])          # the index is the tab's number in its session (the bar's)
        self.assertEqual(groups[1][1][0].index, 1)

    def test_flatten_gives_each_state_a_header_even_alone(self):
        items, flat = D.flatten(D.group_by_state(D.group_rows([row(1, "working")], "")), "", None, headed=True)
        self.assertEqual(items[0].kind, "header")
        self.assertEqual(items[0].label, "Working")

    def test_a_muted_tab_never_counts_as_asking(self):
        r = row(1, "waiting")
        r.muted = True
        items, _flat = D.flatten(D.group_by_state(D.group_rows([r, row(2, "waiting")], "")), "", None, headed=True)
        self.assertEqual(items[0].attn, 1)


if __name__ == "__main__":
    unittest.main()
