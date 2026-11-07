"""The panel snapshot becomes a pixel model: states, open panes, selection, scroll, the graphics probe."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_deck as deck
import kittymux_deckadapt as adapt
import kittymux_switches as switches

try:
    import kittymux_deckpx as dp
except ImportError:
    dp = None


def snap(rows, session="", query="", open_tabs=None):
    groups = deck.filter_groups(deck.group_rows(rows, session), query)
    items, flat = deck.flatten(groups, session, open_tabs)

    class Snap:
        pass

    out = Snap()
    out.items, out.rows, out.query, out.current_session = items, flat, query, session
    return out


def row(i, title, **kw):
    return deck.RowData(tab_id=i, win_id=i, title=title, session=kw.pop("session", "work"), **kw)


@unittest.skipIf(dp is None, "cairo/Pango/rsvg not installed")
class AdaptTests(unittest.TestCase):
    def test_states_progress_and_empty_wording(self):
        rows = [
            row(1, "api", status="working", progress=("set", 42), current=True, branch="feat"),
            row(2, "docs", status="waiting", age="4m"),
            row(3, "bad", status="error", progress=("error", 0)),
            row(4, "cap", status="limited"),
            row(5, "old", status="done"),
            row(6, "quiet", status=""),
            row(7, "odd", status="unread"),
        ]
        model = adapt.to_model(snap(rows, "work"), 1, (-1, -1), "demo", "work")
        by = {a.title: a for a in model.agents}
        self.assertEqual(by["api"].state, "working")
        self.assertEqual(by["api"].progress, 0.42)
        self.assertTrue(by["api"].current)
        self.assertEqual(by["docs"].state, "waiting")
        self.assertEqual(by["docs"].age, "4m")
        self.assertTrue(by["docs"].selected and by["docs"].active)
        self.assertFalse(by["api"].selected)
        self.assertEqual(by["bad"].progress, 1.0)
        self.assertEqual(by["bad"].progress_state, "error")
        self.assertEqual(by["cap"].state, "limited")
        self.assertEqual(by["old"].state, "done")
        self.assertEqual(by["quiet"].state, "idle")
        self.assertEqual(by["odd"].state, "idle")
        self.assertEqual(model.spaces[0].branch, "feat")          # the current tab's branch, not the first
        self.assertEqual(model.spaces[0].state, "limited")        # limited outranks waiting
        none = adapt.to_model(snap([], "work"), 0, None, "demo", "work")
        self.assertEqual(none.empty, "No tabs yet")
        missed = adapt.to_model(snap(rows, "work", query="zzzz"), 0, None, "demo", "work")
        self.assertIn("zzzz", missed.empty)
        self.assertIn("esc clears", missed.empty_hint)

    def test_panes_follow_open_tabs_and_not_the_pointer(self):
        panes = (deck.PaneData(11, title="left", agent="claude"), deck.PaneData(12, title="right", agent=""))
        rows = [row(1, "web", pane_rows=panes), row(2, "api")]
        closed = adapt.to_model(snap(rows, "work", open_tabs=frozenset()), 0, (0, 0), "demo", "work")
        self.assertEqual(closed.agents[0].children, [])
        self.assertTrue(closed.agents[0].can_open)
        self.assertFalse(closed.agents[0].opened)
        self.assertTrue(closed.agents[0].selected)               # a hover pane that is not listed does not steal the row
        opened = adapt.to_model(snap(rows, "work", open_tabs=frozenset({1})), 0, (0, 1), "demo", "work")
        self.assertEqual([c.title for c in opened.agents[0].children], ["left", "right"])
        self.assertTrue(opened.agents[0].opened)
        self.assertFalse(opened.agents[0].selected)
        self.assertTrue(opened.agents[0].children[1].selected)
        self.assertEqual(adapt.hit_target(opened, "toggle", 0), (0, -1))
        self.assertEqual(adapt.hit_target(opened, "pane", 1), (0, 1))
        self.assertEqual(adapt.selected_target(opened), ("pane", 1))

    def test_a_long_list_scrolls_the_selection_into_view(self):
        rows = [row(i, f"task {i}") for i in range(1, 31)]
        model = adapt.to_model(snap(rows, "work"), 29, (-1, -1), "demo", "work")
        items = dp.body_items(model)
        view = 120
        scrolled = dp.scroll_to_item(items, 0, view, "agent", 29)
        self.assertGreater(scrolled, 0)
        y = next(y for k, i, y, h, _p in items if k == "agent" and i == 29)
        self.assertLessEqual(y + 30, scrolled + view)
        hits = [("agent", 0, 0, 0, 100, 20), ("toggle", 0, 0, 0, 16, 20)]
        self.assertEqual(dp.hit_at(hits, 4, 4), ("toggle", 0))

    def test_the_probe_times_out_as_no(self):
        self.assertEqual(adapt.graphics_verdict("Gi=999;OK", False), "ok")
        self.assertEqual(adapt.graphics_verdict("i=999;ENOTSUP", False), "no")
        self.assertEqual(adapt.graphics_verdict("", True), "no")
        self.assertEqual(adapt.graphics_verdict("i=1;OK", False), "wait")


class SwitchTests(unittest.TestCase):
    def test_deckpx_defaults_off_and_the_on_file_is_the_only_one(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(switches.enabled("deckpx", d))
            switches.set_switch(d, "deckpx", True)
            self.assertEqual(os.listdir(d), ["deckpx-on"])
            self.assertTrue(switches.enabled("deckpx", d))


if __name__ == "__main__":
    unittest.main()
