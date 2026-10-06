import os
import sys
import unicodedata
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_theme as T  # noqa: E402
import kittymux_ui as U  # noqa: E402
import kittymux_usageview as V  # noqa: E402

TOKYO = {"background": 0x1a1b26, "foreground": 0xc0caf5, "active_border_color": 0xbb9af7,
         "color9": 0xf7768e, "color10": 0x9ece6a, "color11": 0xe0af68, "color12": 0x7aa2f7}
LATTE = {"background": 0xeff1f5, "foreground": 0x4c4f69, "active_border_color": 0x1e66f5,
         "color9": 0xd20f39, "color10": 0x40a02b, "color11": 0xdf8e1d, "color12": 0x1e66f5}
TODAY = datetime(2026, 10, 7, 12, 0, 0)       # a Wednesday
NOW = 1_800_000_000.0


def wide(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def kit(colors=TOKYO, **kw):
    return U.Kit(T.from_colors(colors), **kw)


def data(ts=NOW - 13, extra=(), live=None):
    providers = [
        {"name": "codex", "note": "plus", "rows": [
            {"label": "5h", "pct": 99.0, "reset": "resets in 3h 50m", "rem_s": 13800, "window_s": 18000},
            {"label": "wk", "pct": 63.0, "reset": "resets in 4d 19h", "rem_s": 4 * 86400 + 19 * 3600, "window_s": 7 * 86400}]},
        {"name": "claude", "rows": [
            {"label": "5h", "text": "window closed · next msg opens new", "state": "closed"},
            {"label": "week", "text": "109.0M tok (+6.0G cached) · 12 sess", "tok": 109e6, "cached": 6e9, "sess": 12},
            {"label": "cap", "text": "limit hit 7d ago", "ago_s": 7 * 86400}]},
        {"name": "cursor", "rows": [{"label": "plan", "text": "pro · active", "plan": "pro", "status": "active"}]},
        {"name": "devin", "note": "session totals · modified today", "rows": [
            {"label": "today", "text": "5 sess · 37.6M tok", "tok": 37.6e6, "sess": 5}, {"label": "model", "text": "SWE-2 Max"}]},
    ] + list(extra)
    return {"ts": ts, "providers": providers, "live": live or {}}


HISTORY = {"2026-10-01": {"claude_fresh": 5, "devin_tok": 1, "_daily_version": 2}, "2026-10-05": {"claude_fresh": 9, "devin_tok": 4, "_daily_version": 2},
           "2026-10-07": {"claude_fresh": 3, "devin_tok": 8, "_daily_version": 2}}


def text(view):
    return "\n".join(U.plain(line) for line in [view.header] + view.lines)


class LayoutTests(unittest.TestCase):
    def test_every_line_is_exactly_the_panel_width_at_every_width(self):
        for colors in (TOKYO, LATTE):
            for kw in ({}, {"cells": wide, "rounded": False}):
                k = kit(colors, **kw)
                for cols in (8, 14, 20, 26, 30, 38, 52, 80):
                    for sel in range(4):
                        v = V.view(data(), HISTORY, cols, sel, k, NOW, TODAY)
                        for i, line in enumerate([v.header] + v.lines):
                            self.assertEqual(U.line_cells(line, k.cells), cols, (cols, sel, i, U.plain(line)))

    def test_the_focus_card_follows_the_pick(self):
        k = kit()
        names = ["Codex", "Claude", "Cursor", "Devin"]
        for sel, name in enumerate(names):
            body = text(V.view(data(), HISTORY, 38, sel, k, NOW, TODAY))
            self.assertIn(name, body)
        self.assertIn("99%", text(V.view(data(), None, 38, 0, k, NOW, TODAY)))
        self.assertNotIn("99%", text(V.view(data(), None, 38, 3, k, NOW, TODAY)).split("Devin")[1])

    def test_a_selection_outside_the_list_is_clamped(self):
        k = kit()
        for sel in (-5, 99, None, "x", float("nan")):
            self.assertIn(V.view(data(), None, 38, sel, k, NOW, TODAY).sel, range(4))
        self.assertEqual(V.view(data(), None, 38, 99, k, NOW, TODAY).sel, 3)

    def test_summary_names_the_provider_closest_to_a_wall(self):
        body = text(V.view(data(), None, 38, 0, kit(), NOW, TODAY))
        self.assertIn("4 providers", body)
        self.assertIn("▲ Codex 99%", body)

    def test_a_calm_summary_does_not_shout(self):
        d = data()
        d["providers"][0]["rows"] = [{"label": "5h", "pct": 12.0}]
        body = text(V.view(d, None, 38, 0, kit(), NOW, TODAY))
        self.assertNotIn("▲", body)
        self.assertIn("● Codex 12%", body)


class TileTests(unittest.TestCase):
    def test_one_region_per_provider_inside_the_panel(self):
        k = kit()
        for cols in (20, 30, 38, 60):
            v = V.view(data(), None, cols, 0, k, NOW, TODAY)
            self.assertEqual(sorted(r[4] for r in v.tiles), [0, 1, 2, 3])
            for x0, x1, y0, y1, _ in v.tiles:
                self.assertTrue(0 <= x0 < x1 <= cols)
                self.assertTrue(0 <= y0 < y1 <= len(v.lines))

    def test_regions_do_not_overlap_and_sit_on_their_own_tile_text(self):
        k = kit()
        v = V.view(data(), None, 38, 0, k, NOW, TODAY)
        spans = sorted((r[0], r[1]) for r in v.tiles if r[2] == v.tiles[0][2])
        for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0)
        x0, x1, y0, y1, _ = v.tiles[0]
        import kittymux_agents
        self.assertIn(kittymux_agents.AGENTS["codex"].glyph, U.plain(v.lines[y0 + 1])[x0:x1])      # the logo line of the first tile

    def test_many_providers_wrap_to_a_second_row(self):
        k = kit()
        extra = [{"name": f"extra{i}", "rows": [{"label": "5h", "pct": 10.0 + i}]} for i in range(3)]
        v = V.view(data(extra=extra), None, 38, 0, k, NOW, TODAY)
        self.assertEqual(sorted(r[4] for r in v.tiles), list(range(7)))
        self.assertEqual(len({r[2] for r in v.tiles}), 2)

    def test_too_many_to_show_keeps_the_pick_visible(self):
        k = kit()
        extra = [{"name": f"p{i}", "rows": [{"label": "5h", "pct": 10.0}]} for i in range(20)]
        for sel in (0, 5, 12, 23):
            v = V.view(data(extra=extra), None, 38, sel, k, NOW, TODAY)
            self.assertIn(sel, [r[4] for r in v.tiles])
            self.assertLessEqual(len(v.tiles), 8)

    def test_selected_tile_is_marked_with_the_accent_edge(self):
        k = kit()
        v = V.view(data(), None, 38, 1, k, NOW, TODAY)

        def colours_at(line, x0, x1):
            out, x = set(), 0
            for s in line:
                w = len(s.text)
                if x < x1 and x + w > x0:
                    out.add(s.fg)
                x += w
            return out

        marked = [r[4] for r in v.tiles if k.p.accent in colours_at(v.lines[r[2]], r[0], r[1])]
        self.assertEqual(marked, [1])


class MeterDrawingTests(unittest.TestCase):
    def test_quota_shows_label_countdown_percent_gauge_and_pace(self):
        body = text(V.view(data(), None, 38, 0, kit(), NOW, TODAY))
        for want in ("5h", "↻ 3h 50m", "99%", "wk", "↻ 4d 19h", "63%", "plus"):
            self.assertIn(want, body)
        self.assertEqual(body.count("▏"), 2)                          # a pace tick on each quota that knows its window

    def test_the_share_survives_any_panel_width_and_the_countdown_gives_way_first(self):
        k = kit()
        for cols in (12, 16, 20, 22, 26, 30, 38):
            body = text(V.view(data(), None, cols, 0, k, NOW, TODAY))
            self.assertIn("99%", body, cols)
            self.assertIn("63%", body, cols)
        wide, narrow = text(V.view(data(), None, 38, 0, k, NOW, TODAY)), text(V.view(data(), None, 22, 0, k, NOW, TODAY))
        self.assertIn("↻ 3h 49m"[:2], wide)
        self.assertNotIn("↻", narrow)

    def test_pace_is_where_an_even_spend_would_be(self):
        q = {"pct": 99.0, "rem_s": 13800, "window_s": 18000}
        self.assertAlmostEqual(V._pace(q), 23.33, places=1)
        self.assertIsNone(V._pace({"pct": 5, "rem_s": 10}))
        self.assertIsNone(V._pace({"pct": 5, "window_s": 100}))
        self.assertIsNone(V._pace({"pct": 5, "rem_s": 10, "window_s": 100, "clock": True}))
        self.assertEqual(V._pace({"rem_s": 999999, "window_s": 10}), 0.0)

    def test_counter_shows_a_big_number_chips_bars_and_weekday_initials(self):
        k = kit()
        body = text(V.view(data(), HISTORY, 38, 1, k, NOW, TODAY))
        self.assertIn("109.0M tok", body)
        self.assertIn("12 sess", body)
        self.assertIn("+6.0G cache", body)
        self.assertIn("closed", body)
        self.assertIn("hit 7d ago", body)
        self.assertIn("▁", body)
        self.assertIn(V.week_letters(TODAY), body.replace(" ", ""))

    def test_state_only_provider_is_chips_with_no_gauge_noise(self):
        body = text(V.view(data(), None, 38, 2, kit(), NOW, TODAY))
        self.assertIn("pro", body)
        self.assertIn("active", body)
        self.assertNotIn("99%", body.split("Cursor")[1])

    def test_week_heat_card_appears_only_with_history(self):
        k = kit()
        with_hist = text(V.view(data(), HISTORY, 38, 0, k, NOW, TODAY))
        without = text(V.view(data(), None, 38, 0, k, NOW, TODAY))
        self.assertIn("tokens per day", with_hist)
        self.assertNotIn("tokens per day", without)

    def test_all_seven_days_fit_at_every_panel_width(self):
        k = kit()
        letters = V.week_letters(TODAY)
        for cols in (18, 20, 24, 26, 30, 38, 60):                         # below 18 columns a logo and seven days cannot share a row
            v = V.view(data(), HISTORY, cols, 0, k, NOW, TODAY)
            card = [U.plain(line) for line in v.lines]
            row = next(i for i, line in enumerate(card) if " 7d " in line)
            letters_line = card[row + 1]
            self.assertEqual("".join(letters_line.split()), letters, (cols, letters_line))
            heat = [s for s in v.lines[row + 2] if s.text.strip() == "" and s.bg is not None and len(s.text) in (1, 2)]
            self.assertEqual(len(heat), 7, (cols, U.plain(v.lines[row + 2])))

    def test_week_letters_end_on_today(self):
        self.assertEqual(len(V.week_letters(TODAY)), 7)
        self.assertEqual(V.week_letters(TODAY)[-1], "W")              # 2026-10-07 is a Wednesday
        self.assertEqual(V.week_letters(TODAY)[0], "T")


class MarkTests(unittest.TestCase):
    def test_known_providers_get_their_logo_and_unknown_ones_their_initial(self):
        import kittymux_agents
        k = kit()
        self.assertIn(kittymux_agents.AGENTS["claude"].glyph, U.plain(V.mark("claude", k, k.p.card)))
        self.assertIn("N", U.plain(V.mark("newcomer", k, k.p.card)))
        self.assertEqual(U.line_cells(V.mark("devin", k, k.p.card)), 3)

    def test_three_providers_starting_with_c_are_not_three_identical_marks(self):
        k = kit()
        marks = {U.plain(V.mark(n, k, k.p.card)) for n in ("claude", "codex", "cursor")}
        self.assertEqual(len(marks), 3)


class StateTests(unittest.TestCase):
    def test_loading_error_missing_and_empty_have_their_own_look(self):
        k = kit()
        d = data(extra=[{"name": "a", "pending": True, "rows": []}, {"name": "b", "err": "usage unavailable", "rows": []},
                        {"name": "c", "note": "not installed", "rows": []}, {"name": "d", "rows": []}])
        wants = {4: "collecting", 5: "usage unavailable", 6: "not installed", 7: "no usage data yet"}
        for idx, want in wants.items():
            self.assertIn(want, text(V.view(d, None, 38, idx, k, NOW, TODAY)))

    def test_nothing_collected_yet_says_so(self):
        for d in ({}, {"providers": []}, None, {"providers": None}, {"providers": ["x", 3]}):
            v = V.view(d, None, 38, 0, kit(), NOW, TODAY)
            self.assertIn("Collecting local usage", text(v))
            self.assertEqual(v.tiles, [])

    def test_a_stale_snapshot_is_flagged_and_a_fresh_one_is_quiet(self):
        k = kit()
        self.assertIn("stale 5m", text(V.view(data(ts=NOW - 300), None, 38, 0, k, NOW, TODAY)))
        self.assertNotIn("stale", text(V.view(data(ts=NOW - 13), None, 38, 0, k, NOW, TODAY)))
        self.assertIn("↻ 1m", text(V.view(data(ts=NOW - 70), None, 38, 0, k, NOW, TODAY)))

    def test_the_opt_in_note_goes_away_once_live_data_exists(self):
        k = kit()
        self.assertIn("live quotas are opt-in", text(V.view(data(), None, 38, 0, k, NOW, TODAY)))
        self.assertNotIn("opt-in", text(V.view(data(live={"claude": {"rows": []}}), None, 38, 0, k, NOW, TODAY)))


class RobustnessTests(unittest.TestCase):
    def test_hostile_provider_text_never_reaches_the_screen(self):
        k = kit()
        d = data(extra=[{"name": "ev\x1b]0;pwn\x07il", "note": "pl\x1bus", "rows": [
            {"label": "5h\x1b", "pct": 50, "reset": "x\x1b"}, {"label": "no\x00te", "text": "\x1b[31mred\x07" * 20}]}])
        for sel in range(5):
            v = V.view(d, None, 38, sel, k, NOW, TODAY)
            for line in [v.header] + v.lines:
                for ch in ("\x1b", "\x00", "\x07"):
                    self.assertNotIn(ch, U.plain(line))

    def test_junk_data_never_raises(self):
        k = kit()
        junk = [{"ts": "x", "providers": [{"name": 5, "rows": "x"}]}, {"ts": float("nan"), "providers": [{}]}, {"providers": [{"rows": [{"pct": float("nan")}]}]},
                {"providers": [{"name": "x", "rows": [{"label": "5h", "pct": 1e400}]}]}, {"ts": -5, "providers": [{"name": "x"}]}]
        for d in junk:
            for cols in (1, 8, 38):
                V.view(d, {"x": 1}, cols, 0, k, NOW, TODAY)

    def test_wide_characters_in_names_keep_every_line_the_right_width(self):
        k = kit(cells=wide)
        d = data(extra=[{"name": "日本語のプロバイダー", "rows": [{"label": "週", "pct": 40.0, "reset": "あと3時間"}]}])
        for cols in (20, 38):
            v = V.view(d, None, cols, 4, k, NOW, TODAY)
            for line in [v.header] + v.lines:
                self.assertEqual(U.line_cells(line, k.cells), cols)


class FormatTests(unittest.TestCase):
    def test_spans(self):
        cases = {13800: "3h 50m", 4 * 86400 + 19 * 3600: "4d 19h", 540: "9m", 59: "now", 0: "now", 7200: "2h", 172800: "2d", None: "", float("nan"): ""}
        for v, want in cases.items():
            self.assertEqual(V.fmt_span(v), want, v)

    def test_amounts(self):
        self.assertEqual(V.fmt_amount(109e6, "tok"), "109.0M")
        self.assertEqual(V.fmt_amount(412, "lines"), "412")
        self.assertEqual(V.fmt_amount(12_000, "tok"), "12k")
        self.assertEqual(V.fmt_amount(None), "?")
        self.assertEqual(V.fmt_amount(950, "tok"), "950")


if __name__ == "__main__":
    unittest.main()
