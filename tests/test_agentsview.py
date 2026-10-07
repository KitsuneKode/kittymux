import os
import sys
import unicodedata
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_agentsview as V  # noqa: E402
import kittymux_deck as deck  # noqa: E402
import kittymux_theme as T  # noqa: E402
import kittymux_ui as U  # noqa: E402

TOKYO = {"background": 0x1a1b26, "foreground": 0xc0caf5, "active_border_color": 0xbb9af7,
         "color9": 0xf7768e, "color10": 0x9ece6a, "color11": 0xe0af68, "color12": 0x7aa2f7}
LATTE = {"background": 0xeff1f5, "foreground": 0x4c4f69, "active_border_color": 0x1e66f5,
         "color9": 0xd20f39, "color10": 0x40a02b, "color11": 0xdf8e1d, "color12": 0x1e66f5}
WIDTHS = (12, 16, 20, 26, 30, 36, 48)


def wide(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def kits():
    for colors in (TOKYO, LATTE):
        for kw in ({}, {"cells": wide, "rounded": False}):
            yield U.Kit(T.from_colors(colors), **kw)


def row(**kw):
    base = dict(tab_id=1, win_id=11, title="Audit codebase security and de", glyph="", agent="claude", branch="main", cwd="/home/u/proj",
                panes=1, status="", pr="#42", ports=(3000, 5173), index=3, current=False)
    base.update(kw)
    return deck.RowData(**base)


def text(line):
    return U.plain(line)


class WidthTests(unittest.TestCase):
    def test_every_line_is_exactly_as_wide_as_asked_in_every_state_theme_and_width(self):
        panes = (deck.PaneData(11, "", "claude", False, "waiting", "reviewing the long migration plan", True, "/x"),
                 deck.PaneData(12, "", "codex", False, "working", "tests", False, "/x"),
                 deck.PaneData(13, "", "", False, "", "", False, "/x"))
        for k in kits():
            for status in ("", "working", "waiting", "limited", "done", "unread"):
                for sel, cur in ((False, False), (True, False), (False, True)):
                    r = row(status=status, current=cur, panes=3, pane_rows=panes)
                    for w in WIDTHS:
                        for fn in (lambda: V.title_row(k, r, sel, False, w), lambda: V.context_row(k, r, sel, False, w, "/home/u")):
                            self.assertEqual(U.line_cells(fn(), k.cells), w, (status, sel, cur, w))
                        for j in range(3):
                            self.assertEqual(U.line_cells(V.pane_row(k, r, j, j == 1, w), k.cells), w)
            for w in WIDTHS:
                self.assertEqual(U.line_cells(V.header_row(k, "kitty session with a very long name", 12, True, w), k.cells), w)
                self.assertEqual(U.line_cells(V.summary_row(k, 12, 3, 4, w), k.cells), w)

    def test_an_empty_or_hostile_title_still_draws(self):
        k = next(kits())
        for title in ("", None, "\x1b[31mred\x1b]0;x\x07", "界" * 40, "a" * 5000):
            r = row(title=title or "")
            for w in WIDTHS:
                line = V.title_row(k, r, False, False, w)
                self.assertEqual(U.line_cells(line, k.cells), w)
                self.assertNotIn("\x1b", text(line))
                self.assertNotIn("\x07", text(line))


class GapTests(unittest.TestCase):
    def test_nothing_touches_the_mark_or_the_tab_number_at_any_width(self):
        panes = (deck.PaneData(11, "\ue0a0", "claude", False, "waiting", "x" * 80, True), deck.PaneData(12, "\ue0a0", "codex", False, "done", "y" * 80, False))
        for k in kits():
            for status in ("working", "waiting", "limited", "done"):
                r = row(status=status, title="t" * 90, branch="b" * 90, panes=2, pane_rows=panes)
                for w in (14, 20, 26, 38):
                    t = text(V.title_row(k, r, False, False, w))
                    self.assertEqual(t[-3], " ", (status, w, t))               # a gap before the mark ...
                    self.assertEqual(t[-1], " ", (status, w, t))               # ... and one after it
                    c = text(V.context_row(k, r, False, False, w))
                    self.assertEqual(c[-3], " ", (status, w, c))               # a gap before the tab number
                for j in range(2):
                    for w in (14, 20, 26, 38):
                        t = text(V.pane_row(k, r, j, False, w))
                        self.assertEqual(t[-3], " ", (j, w, t))


class QuietByDefaultTests(unittest.TestCase):
    def test_ports_and_pr_show_only_on_the_picked_row_but_the_branch_always_does(self):
        k = next(kits())
        quiet = text(V.context_row(k, row(), False, False, 36))
        picked = text(V.context_row(k, row(), True, False, 36))
        self.assertIn("main", quiet)
        self.assertNotIn(":3000", quiet)
        self.assertNotIn("#42", quiet)
        self.assertIn(":3000", picked)
        self.assertIn("#42", picked)

    def test_the_current_tab_counts_as_lit_too(self):
        k = next(kits())
        self.assertIn(":3000", text(V.context_row(k, row(current=True), False, False, 36)))

    def test_a_folder_stands_in_for_a_missing_branch_and_home_is_shortened(self):
        k = next(kits())
        got = text(V.context_row(k, row(branch="", cwd="/home/u/proj"), False, False, 36, "/home/u"))
        self.assertIn("~/proj", got)
        self.assertNotIn("/home/u", got)

    def test_the_pane_count_survives_narrow_widths_longest_and_the_number_is_always_last(self):
        k = next(kits())
        self.assertIn("3 panes", text(V.context_row(k, row(panes=3), False, False, 40)))
        for w in (16, 24, 40):
            self.assertTrue(text(V.context_row(k, row(panes=3), False, False, w)).rstrip().endswith("3"), w)    # the tab number sits at the right edge

    def test_a_row_that_needs_you_says_so_and_a_quiet_one_does_not(self):
        k = next(kits())
        self.assertIn("needs you", text(V.context_row(k, row(status="waiting"), False, False, 40)))
        self.assertIn("limit hit", text(V.context_row(k, row(status="limited"), False, False, 40)))
        for status in ("", "working", "done", "unread"):
            got = text(V.context_row(k, row(status=status), False, False, 40))
            self.assertNotIn("needs you", got)
            self.assertNotIn("limit hit", got)

    def test_needs_you_has_a_stripe_and_a_tint_and_nothing_else_does(self):
        for k in kits():
            p = k.p
            waiting = V.title_row(k, row(status="waiting"), False, False, 30)
            plain_row = V.title_row(k, row(status=""), False, False, 30)
            self.assertEqual(waiting[0].text, V.RAIL)
            self.assertEqual(waiting[0].fg, p.waiting)
            self.assertEqual(plain_row[0].text, " ")
            self.assertNotEqual(V.row_bg(p, row(status="waiting"), False, False), p.bar)
            self.assertEqual(V.row_bg(p, row(status=""), False, False), p.bar)
            self.assertEqual(V.row_bg(p, row(status="waiting"), True, False), p.surface_hi)     # picked wins: the tint never hides the pick

    def test_the_mark_is_the_state_glyph_and_a_still_frame_when_motion_is_off(self):
        k = next(kits())
        still = {text(V.title_row(k, row(status="working"), False, False, 30, animate=False))[-3:] for _ in range(5)}
        self.assertEqual(len(still), 1)
        self.assertIn("!", text(V.title_row(k, row(status="waiting"), False, False, 30)))
        self.assertIn("✓", text(V.title_row(k, row(status="done"), False, False, 30)))

    def test_the_title_is_the_bright_thing_on_a_quiet_row_only_when_lit(self):
        k = next(kits())
        p = k.p
        dim = next(s for s in V.title_row(k, row(), False, False, 36) if "Audit" in s.text)
        lit = next(s for s in V.title_row(k, row(), True, False, 36) if "Audit" in s.text)
        self.assertFalse(dim.bold)
        self.assertTrue(lit.bold)
        self.assertGreaterEqual(T.contrast(lit.fg, V.row_bg(p, row(), True, False)), 4.5)
        self.assertGreaterEqual(T.contrast(dim.fg, p.bar), 4.5)

    def test_text_keeps_contrast_on_every_background_in_both_themes(self):
        for k in kits():
            p = k.p
            for status in ("", "working", "waiting", "limited", "done"):
                for sel, hov in ((False, False), (True, False), (False, True)):
                    r = row(status=status)
                    bg = V.row_bg(p, r, sel, hov)
                    for s in V.title_row(k, r, sel, hov, 36) + V.context_row(k, r, sel, hov, 36, ""):
                        if s.text.strip() and s.fg is not None and s.bg == bg and s.text.strip() not in (V.RAIL, "", "", ""):
                            self.assertGreaterEqual(T.contrast(s.fg, s.bg), 2.9, (status, sel, hov, s))


class ActionBarTests(unittest.TestCase):
    PAIRS = [("⏎", "jump", "ENTER"), ("/", "find", "/"), ("a", "join", "A"), ("t", "detach", "T")]

    def test_the_bar_is_exactly_the_width_and_regions_lie_inside_what_was_drawn(self):
        for k in kits():
            for w in (0, 6, 12, 20, 28, 36, 60):
                line, regions = V.action_bar(k, self.PAIRS, w)
                self.assertEqual(U.line_cells(line, k.cells), w)
                for x0, x1, token, i in regions:
                    self.assertTrue(0 <= x0 < x1 <= w, (w, regions))
                    self.assertEqual(self.PAIRS[i][2], token)
                for (a0, a1, *_), (b0, b1, *_) in zip(regions, regions[1:]):
                    self.assertLessEqual(a1, b0)

    def test_a_button_is_dropped_whole_never_cut_and_the_order_is_kept(self):
        k = next(kits())
        seen = []
        for w in range(0, 60):
            _line, regions = V.action_bar(k, self.PAIRS, w)
            toks = [t for _a, _b, t, _i in regions]
            self.assertEqual(toks, [p[2] for p in self.PAIRS][:len(toks)])
            seen.append(len(toks))
        self.assertEqual(seen, sorted(seen))                                      # more room never shows fewer buttons
        self.assertEqual(seen[-1], len(self.PAIRS))

    def test_the_hot_button_lights_up_in_the_accent_and_a_hint_never_does(self):
        k = next(kits())
        cold, _ = V.action_bar(k, self.PAIRS, 60)
        hot, regions = V.action_bar(k, self.PAIRS, 60, hot=1)
        self.assertNotEqual([s.bg for s in cold], [s.bg for s in hot])
        x0, x1, _tok, _i = regions[1]
        self.assertIn(k.p.accent, [s.bg for s in hot])
        hint, hregions = V.action_bar(k, [("j k", "move", None), ("⏎", "jump", "ENTER")], 40, hot=0)
        self.assertEqual([r[2] for r in hregions], ["ENTER"])                       # only the button has a region
        self.assertNotIn(k.p.accent, [s.bg for s in hint])                          # a hint cannot be hot

    def test_hostile_labels_are_cleaned(self):
        k = next(kits())
        line, _ = V.action_bar(k, [("\x1b[31mx", "ev\x1b]0;t\x07il", "X")], 30)
        self.assertNotIn("\x1b", text(line))
        self.assertNotIn("\x07", text(line))


class SummaryTests(unittest.TestCase):
    def test_numbers_a_glance_wants_and_only_when_they_are_not_zero(self):
        k = next(kits())
        self.assertIn("8 tabs", text(V.summary_row(k, 8, 0, 0, 40)))
        self.assertNotIn("need you", text(V.summary_row(k, 8, 0, 0, 40)))
        self.assertIn("2 need you", text(V.summary_row(k, 8, 2, 0, 40)))
        self.assertIn("3 working", text(V.summary_row(k, 8, 0, 3, 40)))
        self.assertIn("1 tab", text(V.summary_row(k, 1, 0, 0, 40)))
        self.assertNotIn("1 tabs", text(V.summary_row(k, 1, 0, 0, 40)))


if __name__ == "__main__":
    unittest.main()
