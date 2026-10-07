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

    def test_how_long_it_has_waited_rides_with_the_word_and_a_finished_run_says_how_long_ago(self):
        k = next(kits())
        self.assertIn("needs you 4m", text(V.context_row(k, row(status="waiting", age="4m"), False, False, 40)))
        self.assertIn("limit hit 1h", text(V.context_row(k, row(status="limited", age="1h"), False, False, 40)))
        self.assertIn("done 3m", text(V.context_row(k, row(status="done", age="3m"), False, False, 40)))
        self.assertNotIn("done", text(V.context_row(k, row(status="done", age=""), False, False, 40)))          # under a minute is not news
        self.assertNotIn("4m", text(V.context_row(k, row(status="working", age="4m"), False, False, 40)))

    def test_the_state_words_give_way_before_the_place_does(self):
        k = next(kits())
        r = row(status="waiting", age="4m", branch="main")
        wide_text = text(V.context_row(k, r, False, False, 40))
        self.assertIn("needs you 4m", wide_text)
        for w in (20, 22, 24, 26, 30):
            t = text(V.context_row(k, r, False, False, w))
            self.assertIn("main", t, (w, t))                                  # the branch is never cut for the sake of the word
            self.assertTrue(t.rstrip().endswith("3"), (w, t))
        tight = text(V.context_row(k, r, False, False, 22))
        self.assertIn("4m", tight)                                            # the age survives longest: it is the news
        self.assertNotIn("needs you", tight)
        limited = text(V.context_row(k, row(status="limited", age="1h", cwd="/home/u/.config/hypr", branch=""), False, False, 26, "/home/u"))
        self.assertIn("~/.con", limited)

    def test_pr_and_ports_never_wear_a_state_colour(self):
        for k in kits():
            p = k.p
            state_colours = {p.working, p.waiting, p.alert, p.done}
            for s in V.context_row(k, row(), True, False, 40, ""):
                if ":3000" in s.text or "#42" in s.text:
                    self.assertFalse({s.fg} & state_colours, (s, "a PR or port looks like a state"))

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


class EmptyTests(unittest.TestCase):
    def test_an_empty_list_says_why_and_what_to_do_in_the_exact_width(self):
        for k in kits():
            for w in (10, 20, 26, 38):
                for query in ("", "zzz", "x" * 100, "\x1b[31mred"):
                    lines = V.empty_rows(k, w, query)
                    self.assertTrue(all(U.line_cells(l, k.cells) == w for l in lines), (w, query))
                    self.assertTrue(all("\x1b" not in text(l) for l in lines))
        k = next(kits())
        quiet = " ".join(text(l) for l in V.empty_rows(k, 40))
        self.assertIn("No tabs yet", quiet)
        searched = " ".join(text(l) for l in V.empty_rows(k, 60, "migrate"))
        self.assertIn("No tab matches", searched)
        self.assertIn("migrate", searched)
        self.assertIn("esc clears", searched)


class DisclosureTests(unittest.TestCase):
    def test_a_split_tab_shows_a_marker_that_says_open_or_closed_in_column_two(self):
        for k in kits():
            for state, glyph in ((False, "\u25b8"), (True, "\u25be")):
                line = V.context_row(k, row(panes=3), False, False, 36, "", state)
                t = text(line)
                self.assertEqual(t[2], glyph, t)
                self.assertEqual(U.line_cells(line, k.cells), 36)
            plain = text(V.context_row(k, row(panes=1), False, False, 36, "", None))
            self.assertNotIn("\u25b8", plain)
            self.assertNotIn("\u25be", plain)
            self.assertEqual(plain[2], " ")

    def test_the_marker_never_changes_the_width_or_pushes_the_number_off(self):
        k = next(kits())
        for w in (12, 16, 20, 26, 38):
            for state in (None, False, True):
                t = text(V.context_row(k, row(panes=3), False, False, w, "", state))
                self.assertEqual(len(t), w)
                self.assertTrue(t.rstrip().endswith("3"), (w, state, t))


class HeaderTests(unittest.TestCase):
    def test_the_header_is_exactly_the_width_and_shows_the_badge_only_when_something_asks(self):
        for k in kits():
            for w in (10, 14, 20, 26, 38):
                for attn in (0, 3):
                    line = V.header_row(k, "a very long session name indeed", 12, True, w, attn)
                    self.assertEqual(U.line_cells(line, k.cells), w, (w, attn))
            quiet = text(V.header_row(k, "work", 7, False, 30, 0))
            loud = text(V.header_row(k, "work", 7, False, 30, 2))
            self.assertNotIn("!", quiet)
            self.assertIn("! 2", loud)
            self.assertTrue(loud.rstrip().endswith("7"))
            self.assertTrue(quiet.strip().startswith("WORK"))

    def test_when_there_is_no_room_the_count_outlives_the_badge(self):
        k = next(kits())
        got = text(V.header_row(k, "work", 12, False, 9, 3))
        self.assertNotIn("!", got)
        self.assertIn("12", got)

    def test_a_hostile_session_name_is_cleaned(self):
        k = next(kits())
        self.assertNotIn("\x1b", text(V.header_row(k, "\x1b[31mred\x07", 1, False, 30)))


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
