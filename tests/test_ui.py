import os
import sys
import unicodedata
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_theme as T  # noqa: E402
import kittymux_ui as U  # noqa: E402

TOKYO = {"background": 0x1a1b26, "foreground": 0xc0caf5, "active_border_color": 0xbb9af7,
         "color9": 0xf7768e, "color10": 0x9ece6a, "color11": 0xe0af68, "color12": 0x7aa2f7}
LATTE = {"background": 0xeff1f5, "foreground": 0x4c4f69, "active_border_color": 0x1e66f5,
         "color9": 0xd20f39, "color10": 0x40a02b, "color11": 0xdf8e1d, "color12": 0x1e66f5}


def wide_cells(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def kits():
    for colors in (TOKYO, LATTE):
        yield U.Kit(T.from_colors(colors))
        yield U.Kit(T.from_colors(colors), cells=wide_cells, rounded=False)


class WidthTests(unittest.TestCase):
    """The one promise every component makes: the line is exactly as wide as it was asked to be."""

    def check(self, kit, line, width, what):
        self.assertEqual(U.line_cells(line, kit.cells), width, f"{what}: {U.plain(line)!r}")

    def test_every_single_line_component_fills_its_width_exactly(self):
        for kit in kits():
            for width in (1, 2, 3, 5, 8, 17, 30, 38, 60):
                for what, line in (
                        ("tabs", kit.tabs([("A", "Agents", False, 0), ("U", "Usage", True, 0), ("I", "Inbox", False, 2)], width)),
                        ("keycaps", kit.keycaps([("↑↓", "scroll"), ("r", "refresh"), ("a", "agents")], width)),
                        ("kv", kit.kv("week", "109.0M tok · 12 sess", width)),
                        ("kv-wide", kit.kv("週", "日本語のとても長い値", width)),
                        ("fit", kit.fit_line([U.S("hello world " * 5)], width, kit.p.bar)),
                        ("rule", kit.rule(width, kit.p.bar)),
                        ("blank", kit.blank(width, kit.p.bar))):
                    self.check(kit, line, width, f"{what} @{width}")

    def test_zero_and_negative_widths_give_nothing_and_never_raise(self):
        for kit in kits():
            for width in (0, -1, -40):
                self.assertEqual(kit.tabs([("A", "Agents", True, 0)], width), [])
                self.assertEqual(kit.gauge(50, width), [])
                self.assertEqual(kit.kv("a", "b", width), [])
                self.assertEqual(kit.keycaps([("a", "b")], width), [])
                self.assertEqual(kit.card([[U.S("x")]], width), [[] for _ in range(1)])

    def test_gauge_is_exactly_as_wide_as_asked_at_any_value(self):
        for kit in kits():
            for pct in (0, 1, 49.5, 80, 99, 100, 250, -5, None, float("nan"), True, "7"):
                for width in (1, 2, 10, 25):
                    self.check(kit, kit.gauge(pct, width), width, f"gauge {pct!r}")

    def test_card_lines_are_all_the_same_width(self):
        for kit in kits():
            for width in (8, 20, 38):
                inner = kit.inner_width(width)
                rows = [kit.fit_line([U.S("row")], inner, kit.p.card), kit.kv("a", "b", inner)]
                card = kit.card(rows, width)
                self.assertEqual(len(card), len(rows) + 2)
                for line in card:
                    self.check(kit, line, width, f"card @{width}")

    def test_a_card_too_narrow_to_hold_anything_is_blank_not_broken(self):
        kit = next(iter(kits()))
        for line in kit.card([[U.S("x")], [U.S("y")]], 4):
            self.assertEqual(U.line_cells(line), 4)

    def test_bars_and_labels_fill_the_width(self):
        for kit in kits():
            lines = kit.bars([1, 4, 2, 9, 3, 0, 5], 30, rows=3, labels="MTWTFSS")
            self.assertEqual(len(lines), 4)
            for line in lines:
                self.check(kit, line, 30, "bars")


class CleaningTests(unittest.TestCase):
    def test_hostile_text_never_reaches_a_span(self):
        for kit in kits():
            for line in (kit.chip("a\x1b[31mred\x07"), kit.button("go\x1b]0;x\x07", key="\x1b"), kit.kv("la\x1bbel", "va\x00lue", 30),
                         kit.keycaps([("\x1b", "esc\x1b")], 30), kit.tabs([("\x1b", "Use\x1br", True, 0)], 30), [kit.text("t\x1bt")],
                         kit.monogram("\x1b", 0xd97757)):
                self.assertNotIn("\x1b", U.plain(line))
                self.assertNotIn("\x00", U.plain(line))
                self.assertNotIn("\x07", U.plain(line))


class ChipTests(unittest.TestCase):
    def test_round_caps_and_the_square_fallback(self):
        pal = T.from_colors(TOKYO)
        round_, square = U.Kit(pal), U.Kit(pal, rounded=False)
        self.assertEqual((U.plain(round_.chip("plus"))[0], U.plain(round_.chip("plus"))[-1]), (U.CAP_L, U.CAP_R))
        self.assertEqual((U.plain(square.chip("plus"))[0], U.plain(square.chip("plus"))[-1]), (U.HALF_CAP_L, U.HALF_CAP_R))
        self.assertEqual(U.line_cells(round_.chip("plus")), round_.chip_width("plus"))

    def test_toned_chip_text_reads_on_its_own_tint(self):
        for colors in (TOKYO, LATTE):
            kit = U.Kit(T.from_colors(colors))
            for tone in ("calm", "warm", "hot", "accent", "muted"):
                chip = kit.chip("ok", tone)
                body = chip[1]
                self.assertGreaterEqual(T.contrast(body.fg, body.bg), 4.5, (tone, colors["background"]))

    def test_primary_button_is_the_accent_with_readable_text(self):
        for colors in (TOKYO, LATTE):
            pal = T.from_colors(colors)
            body = U.Kit(pal).button("Review", key="⏎", primary=True)[1]
            self.assertEqual(body.bg, pal.accent)
            self.assertGreaterEqual(T.contrast(body.fg, body.bg), 4.5)


class GaugeTests(unittest.TestCase):
    def fills(self, kit, pct, width=20):
        line = kit.gauge(pct, width)
        return sum(U.line_cells([s]) for s in line if s.fg not in (kit.p.track, kit.p.text) and s.text.startswith(U.LOWER))

    def test_fill_grows_with_the_value(self):
        kit = U.Kit(T.from_colors(TOKYO))
        counts = [self.fills(kit, v) for v in (0, 10, 25, 50, 75, 99, 100)]
        self.assertEqual(counts, sorted(counts))
        self.assertEqual((counts[0], counts[-1]), (0, 20))

    def test_ramp_is_calm_then_warm_then_hot(self):
        kit = U.Kit(T.from_colors(TOKYO))
        self.assertEqual([kit.ramp(v) for v in (0, 79.9, 80, 99.9, 100, 140)], ["calm", "calm", "warm", "warm", "hot", "hot"])
        self.assertEqual(kit.ramp(None), "muted")
        self.assertEqual(kit.ramp(float("nan")), "muted")

    def test_pace_tick_lands_where_asked_and_costs_one_cell(self):
        kit = U.Kit(T.from_colors(TOKYO))
        line = kit.gauge(99, 25, pace=24)
        text = U.plain(line)
        self.assertEqual(text.index("▏"), 6)
        self.assertEqual(text.count("▏"), 1)
        self.assertNotIn("▏", U.plain(kit.gauge(99, 25)))

    def test_no_value_is_a_dotted_groove_not_an_empty_bar(self):
        kit = U.Kit(T.from_colors(TOKYO))
        self.assertEqual(U.plain(kit.gauge(None, 6)), "╌" * 6)

    def test_adjacent_cells_merge_into_runs(self):
        kit = U.Kit(T.from_colors(TOKYO))
        self.assertLessEqual(len(kit.gauge(63, 25)), 2)


class CardTests(unittest.TestCase):
    def test_corners_are_the_quadrant_glyphs(self):
        kit = U.Kit(T.from_colors(TOKYO))
        card = kit.card([kit.blank(kit.inner_width(20), kit.p.card)], 20)
        top, bottom = U.plain(card[0]).strip(), U.plain(card[-1]).strip()
        self.assertEqual((top[0], top[-1]), (U.TOP_L, U.TOP_R))
        self.assertEqual((bottom[0], bottom[-1]), (U.BOT_L, U.BOT_R))

    def test_selected_card_sits_on_the_hover_layer_and_accent_marks_the_top_edge(self):
        kit = U.Kit(T.from_colors(TOKYO))
        card = kit.card([[U.S("x", None, kit.p.card_hi)]], 20, selected=True, accent=True)
        self.assertEqual(card[0][1].fg, kit.p.accent)
        self.assertEqual(card[1][1].bg, kit.p.card_hi)
        plainer = kit.card([[U.S("x")]], 20)
        self.assertEqual(plainer[0][1].fg, kit.p.card)


class TabsTests(unittest.TestCase):
    def test_only_the_active_tab_carries_its_label(self):
        kit = U.Kit(T.from_colors(TOKYO))
        text = U.plain(kit.tabs([("A", "Agents", False, 0), ("U", "Usage", True, 0), ("I", "Inbox", False, 3)], 38))
        self.assertIn("Usage", text)
        self.assertNotIn("Agents", text)
        self.assertNotIn("Inbox", text)
        self.assertIn("3", text)

    def test_active_label_gets_the_accent_with_readable_text(self):
        for colors in (TOKYO, LATTE):
            kit = U.Kit(T.from_colors(colors))
            line = kit.tabs([("A", "Agents", True, 0)], 30)
            active = next(s for s in line if s.bold)
            self.assertEqual(active.bg, kit.p.accent)
            self.assertGreaterEqual(T.contrast(active.fg, active.bg), 4.5)

    def test_a_huge_badge_is_capped(self):
        kit = U.Kit(T.from_colors(TOKYO))
        self.assertIn("99", U.plain(kit.tabs([("I", "Inbox", False, 4000)], 30)))
        self.assertNotIn("4000", U.plain(kit.tabs([("I", "Inbox", False, 4000)], 30)))


class TabRegionTests(unittest.TestCase):
    ITEMS = [("A", "Agents", False, 0), ("U", "Usage", True, 0), ("I", "Inbox", False, 3)]

    def test_regions_tile_the_strip_in_order_and_each_covers_its_own_text(self):
        for kit in kits():
            regions = kit.tab_regions(self.ITEMS)
            self.assertEqual(len(regions), 3)
            for (a0, a1), (b0, b1) in zip(regions, regions[1:]):
                self.assertLessEqual(a1, b0)
            line = U.plain(kit.tabs(self.ITEMS, 40))
            self.assertIn("U", line[regions[1][0]:regions[1][1] + 1] if kit.cells is len else line)
            self.assertIn("3", line[regions[2][0]:regions[2][1] + 1] if kit.cells is len else line)

    def test_a_strip_too_narrow_for_a_named_pill_draws_icons_and_every_region_is_on_screen(self):
        for k in kits():
            for picked in range(3):
                items = [("▦", "Agents", picked == 0, 0), ("◔", "Usage", picked == 1, 0), ("✉", "Inbox", picked == 2, 4)]
                for width in (14, 16, 18, 20, 26):
                    regions = k.tab_regions(items, width)
                    drawn = U.plain(k.tabs(items, width))
                    self.assertEqual(U.line_cells(k.tabs(items, width), k.cells), width)
                    self.assertNotIn("…", drawn, (picked, width))                # nothing is cut off mid-word
                    for x0, x1 in regions:
                        self.assertLessEqual(x1, width, (picked, width, regions))
                    self.assertEqual(len(regions), 3)
                # roomy enough: the picked pill still carries its name
                self.assertIn(items[picked][1], U.plain(k.tabs(items, 40)))

    def test_a_click_inside_a_region_maps_back_to_its_tab(self):
        kit = U.Kit(T.from_colors(TOKYO))
        regions = kit.tab_regions(self.ITEMS)
        x = lambda i: (regions[i][0] + regions[i][1]) // 2
        self.assertEqual([next(i for i, (a, b) in enumerate(regions) if a <= x(j) < b) for j in range(3)], [0, 1, 2])


class ChartTests(unittest.TestCase):
    def test_a_day_with_any_use_never_rounds_to_an_empty_column(self):
        self.assertEqual(U.spark_level(0.0001, 1000), 1)
        self.assertEqual(U.spark_level(0, 1000), 0)
        self.assertEqual(U.spark_level(5, 0), 0)
        self.assertEqual(U.spark_level(float("nan"), 5), 0)
        self.assertEqual(U.spark_level(True, 5), 0)
        self.assertEqual(U.spark_level(1000, 1000), 8)

    def test_spark_is_one_cell_per_value_and_flat_when_there_is_no_data(self):
        kit = U.Kit(T.from_colors(TOKYO))
        self.assertEqual(len(U.plain(kit.spark([1, 2, 3, 4, 5, 6, 7]))), 7)
        self.assertEqual(U.plain(kit.spark([0, 0, 0])), "▁▁▁")
        self.assertEqual(kit.spark([]), [])

    def test_bars_taller_value_means_taller_bar(self):
        kit = U.Kit(T.from_colors(TOKYO))
        lines = kit.bars([1, 8], 7, rows=2, labels="AB")
        top, bottom = U.plain(lines[0]), U.plain(lines[1])
        self.assertNotEqual(bottom[0], " ")                    # the small bar still shows at the foot
        self.assertEqual(top[0], " ")                           # and only the tall bar reaches the top row
        self.assertNotEqual(top[-1], " ")

    def test_bars_with_nothing_to_draw_are_blank_lines_of_the_right_width(self):
        kit = U.Kit(T.from_colors(TOKYO))
        lines = kit.bars([], 20, rows=2, labels="MTW")
        self.assertEqual([U.line_cells(x) for x in lines], [20, 20, 20])

    def test_heat_is_brighter_for_more_and_neutral_for_no_data(self):
        kit = U.Kit(T.from_colors(TOKYO))
        line = kit.heat([1, 10, None, 0])
        cells = [s for s in line if s.text.strip() == "" and s.bg is not None and s.text == "  "]
        lum = [T.luminance(s.bg) for s in cells]
        self.assertGreater(lum[1], lum[0])
        self.assertEqual(cells[2].bg, kit.p.track)
        self.assertEqual(cells[3].bg, kit.p.track)


class AnsiTests(unittest.TestCase):
    def test_to_ansi_round_trips_the_text_and_resets(self):
        line = [U.S("ab", 0xff0000, 0x00ff00, bold=True), U.S("cd")]
        out = U.to_ansi(line)
        self.assertIn("38;2;255;0;0", out)
        self.assertIn("48;2;0;255;0", out)
        self.assertTrue(out.endswith("cd"))
        self.assertEqual(U.plain(line), "abcd")


class KvTests(unittest.TestCase):
    def test_label_is_kept_and_value_is_cut_with_an_ellipsis(self):
        kit = U.Kit(T.from_colors(TOKYO))
        line = kit.kv("week", "109.0M tok · 12 sess", 14)
        text = U.plain(line)
        self.assertTrue(text.startswith("week"))
        self.assertTrue(text.endswith("…"))
        self.assertEqual(len(text), 14)

    def test_value_sits_at_the_right_edge_when_there_is_room(self):
        kit = U.Kit(T.from_colors(TOKYO))
        text = U.plain(kit.kv("plan", "pro", 20))
        self.assertTrue(text.endswith("pro"))
        self.assertTrue(text.startswith("plan"))


if __name__ == "__main__":
    unittest.main()
