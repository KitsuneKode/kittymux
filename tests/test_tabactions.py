import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
import kittymux_quiet as Q  # noqa: E402
import kittymux_tabactions as A  # noqa: E402


class Win:
    def __init__(self, wid, focused_at=0.0):
        self.id = wid
        self.last_focused_at = focused_at


class Tab(list):
    def __init__(self, tid, wins):
        super().__init__(Win(w) for w in wins)
        self.id = tid
        self.os_window_id = 1
        self.active_window = self[0]


class Boss:
    def __init__(self, tabs, gone=()):
        self.tabs = {t.id: t for t in tabs}
        self.calls = []
        self.os_window_map = {}
        # kitty pops a closing window from window_id_map before the kitten's handle_result runs: the card's own window
        self.window_id_map = {w.id: w for t in tabs for w in t if w.id not in gone}

    def tab_for_id(self, tid):
        return self.tabs.get(tid)

    def set_active_tab(self, tab):
        self.calls.append(("activate", tab.id))

    def combine(self, action, window_for_dispatch=None):
        self.calls.append(("combine", action, window_for_dispatch.id))


class TabActionsTest(unittest.TestCase):
    """The right-click card's actions (2026-11-20: on the rail a right-click only peeked; mouse users had no rename, split,
    mute or close)."""

    def test_keys_and_answers(self):
        self.assertEqual([A.key_action(k) for k in "rsmxq"], ["rename", "split", "mute", "close", ""])
        self.assertEqual(A.parse(A.answer("split", 7)), ("split", 7))
        for bad in ("", "split", "split:", "split:0", "split:-2", "explode:3", "rename:3x", None):
            self.assertIsNone(A.parse(bad), bad)
        self.assertEqual(A.answer("explode", 3), "")

    def test_rename_and_split_act_on_that_tab_not_the_focused_one(self):
        boss = Boss([Tab(1, [10]), Tab(2, [20, 21])])
        self.assertTrue(A.run(boss, "rename:2"))
        self.assertTrue(A.run(boss, "split:2"))
        self.assertEqual(boss.calls, [("activate", 2), ("combine", "set_tab_title", 20),
                                      ("activate", 2), ("combine", "launch --location=vsplit --cwd=current", 20)])

    def test_a_gone_tab_or_no_action_does_nothing(self):
        boss = Boss([Tab(1, [10])])
        self.assertFalse(A.run(boss, "split:9"))
        self.assertFalse(A.run(boss, ""))
        self.assertEqual(boss.calls, [])

    def test_close_uses_the_close_cross_rule(self):
        boss = Boss([Tab(4, [40])])
        with patch("kittymux_pxbar.close_tab") as close:
            self.assertTrue(A.run(boss, "close:4"))
        close.assert_called_once_with(boss, 4, again="press x")

    def test_mute_mutes_the_whole_tab_then_unmutes_it(self):
        boss = Boss([Tab(3, [30, 31])])
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(A.run(boss, "mute:3", state_dir=d, kitty_pid=4242))
            self.assertEqual(Q.load_mutes(d, 4242), {"30", "31"})
            Q.set_muted(d, 4242, 31, False)                      # one muted, one not: the action mutes both
            A.run(boss, "mute:3", state_dir=d, kitty_pid=4242)
            self.assertEqual(Q.load_mutes(d, 4242), {"30", "31"})
            A.run(boss, "mute:3", state_dir=d, kitty_pid=4242)
            self.assertEqual(Q.load_mutes(d, 4242), set())
        self.assertEqual(boss.calls, [])                          # muting never moves focus


class CardOverItsOwnTabTest(unittest.TestCase):
    """Fable on #59: the card opens over the ACTIVE tab's active window, and kitty runs handle_result before it removes the card's
    window from the tab. On the tab you are on, the card's own (dying) window was counted and acted on."""

    def tab_with_card(self):
        tab = Tab(5, [50, 51, 99])
        tab[0].last_focused_at, tab[1].last_focused_at = 10.0, 20.0     # 51 was the pane you were in before the card
        tab.active_window = tab[2]                                       # 99: the card itself, closing
        return Boss([tab], gone={99}), tab

    def test_mute_counts_only_the_tabs_real_windows(self):
        boss, _ = self.tab_with_card()
        with tempfile.TemporaryDirectory() as d:
            A.run(boss, "mute:5", state_dir=d, kitty_pid=4242)
            self.assertEqual(Q.load_mutes(d, 4242), {"50", "51"})
            A.run(boss, "mute:5", state_dir=d, kitty_pid=4242)          # all muted: the second press unmutes
            self.assertEqual(Q.load_mutes(d, 4242), set())

    def test_split_and_rename_go_to_the_pane_you_were_in_not_the_card(self):
        boss, _ = self.tab_with_card()
        A.run(boss, "split:5")
        A.run(boss, "rename:5")
        self.assertEqual([c for c in boss.calls if c[0] == "combine"],
                         [("combine", "launch --location=vsplit --cwd=current", 51), ("combine", "set_tab_title", 51)])


if __name__ == "__main__":
    unittest.main()
