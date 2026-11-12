import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
import kittymux_groups as G  # noqa: E402


def row(tid, project, **kw):
    return G.Row(tab_id=tid, title=kw.pop("title", f"tab {tid}"), project=project, **kw)


class GroupingTest(unittest.TestCase):
    def test_groups_keep_first_appearance_order_and_join_split_runs(self):
        groups = G.group([row(1, "rice"), row(2, "kittymux"), row(3, "rice")])
        self.assertEqual([g.project for g in groups], ["rice", "kittymux"])
        self.assertEqual([r.tab_id for r in groups[0].rows], [1, 3])

    def test_rows_keep_kitty_order_whatever_their_state(self):
        groups = G.group([row(1, "rice", state="idle"), row(2, "rice", state="waiting"), row(3, "rice", state="working")])
        self.assertEqual([r.tab_id for r in groups[0].rows], [1, 2, 3])

    def test_branch_shows_only_when_shared_and_not_the_default(self):
        self.assertEqual(G.group([row(1, "a", branch="main"), row(2, "a", branch="main")])[0].branch, "")
        self.assertEqual(G.group([row(1, "a", branch="master")])[0].branch, "")
        self.assertEqual(G.group([row(1, "a", branch="feat/x"), row(2, "a", branch="feat/x")])[0].branch, "feat/x")
        self.assertEqual(G.group([row(1, "a", branch="feat/x"), row(2, "a", branch="main")])[0].branch, "")

    def test_a_large_settled_group_collapses_to_its_header(self):
        rows = [row(i, "dots", state="idle") for i in range(1, 9)]
        g = G.group(rows)[0]
        self.assertEqual((g.rows, g.hidden), ((), 8))

    def test_collapse_needs_more_than_the_limit(self):
        g = G.group([row(i, "dots") for i in range(1, 7)])[0]
        self.assertEqual((len(g.rows), g.hidden), (6, 0))

    def test_a_group_with_live_work_never_collapses(self):
        rows = [row(i, "dots") for i in range(1, 9)] + [row(9, "dots", state="working")]
        self.assertEqual(G.group(rows)[0].hidden, 0)

    def test_the_active_tab_keeps_its_group_open(self):
        rows = [row(i, "dots", active=(i == 4)) for i in range(1, 9)]
        self.assertEqual(G.group(rows)[0].hidden, 0)

    def test_a_group_you_opened_stays_open(self):
        rows = [row(i, "dots") for i in range(1, 9)]
        self.assertEqual(G.group(rows, expanded=frozenset({"dots"}))[0].hidden, 0)

    def test_a_group_with_a_tab_reporting_progress_stays_open(self):
        rows = [row(i, "dots") for i in range(1, 9)] + [row(9, "dots", progress=("set", 40))]
        self.assertEqual(G.group(rows)[0].hidden, 0)

    def test_needs_you_counts_waiting_rows_but_not_muted_ones(self):
        groups = G.group([row(1, "a", state="waiting"), row(2, "a", state="waiting", muted=True), row(3, "b", state="working")])
        self.assertEqual(G.needs_you(groups), 1)

    def test_settled_means_no_live_state(self):
        for st in ("", "idle"):
            self.assertTrue(G.settled(row(1, "a", state=st)))
        for st in ("working", "waiting", "done", "limited", "error"):
            self.assertFalse(G.settled(row(1, "a", state=st)))


class StepTest(unittest.TestCase):
    """ctrl+tab walks the rows in the order the bar DRAWS them, and only the ones you can see (2026-11-12: kitty's next_tab
    walked kitty's order, which interleaved projects drawn apart, and stepped into folded groups, which unfolded and shifted)."""

    def groups(self):
        # kitty's order: 1 (a), 2 (b), 3 (a), 4 (c, folded), 5 (b) — drawn: a: 1 3 | b: 2 5 | c: +1
        return [G.Group("a", "", (row(1, "a", active=True), row(3, "a"))), G.Group("b", "", (row(2, "b"), row(5, "b"))),
                G.Group("c", "", (), hidden=1)]

    def test_next_follows_the_drawn_order_across_groups(self):
        gs = self.groups()
        self.assertEqual(G.step(gs, 1, 1), 3)
        self.assertEqual(G.step(gs, 3, 1), 2)
        self.assertEqual(G.step(gs, 2, 1), 5)

    def test_it_wraps_and_skips_folded_groups(self):
        gs = self.groups()
        self.assertEqual(G.step(gs, 5, 1), 1)              # past the end: the first row, never the folded tab 4
        self.assertEqual(G.step(gs, 1, -1), 5)             # before the start: the last visible row

    def test_previous_walks_back(self):
        self.assertEqual(G.step(self.groups(), 2, -1), 3)

    def test_an_active_tab_not_drawn_steps_to_an_end(self):
        gs = self.groups()
        self.assertEqual(G.step(gs, 4, 1), 1)
        self.assertEqual(G.step(gs, 4, -1), 5)

    def test_nothing_to_step_to(self):
        self.assertIsNone(G.step([], 1, 1))
        self.assertIsNone(G.step([G.Group("a", "", (row(1, "a", active=True),))], 1, 1))


if __name__ == "__main__":
    unittest.main()
