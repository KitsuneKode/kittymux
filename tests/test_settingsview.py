import os
import sys
import tempfile
import unicodedata
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_settingsview as SV  # noqa: E402
import kittymux_switches as SW  # noqa: E402
import kittymux_theme as T  # noqa: E402
import kittymux_ui as U  # noqa: E402

TOKYO = {"background": 0x1a1b26, "foreground": 0xc0caf5, "active_border_color": 0xbb9af7,
         "color9": 0xf7768e, "color10": 0x9ece6a, "color11": 0xe0af68, "color12": 0x7aa2f7}
LATTE = {"background": 0xeff1f5, "foreground": 0x4c4f69, "active_border_color": 0x1e66f5,
         "color9": 0xd20f39, "color10": 0x40a02b, "color11": 0xdf8e1d, "color12": 0x1e66f5}


def wide(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def kit(colors=TOKYO):
    return U.Kit(T.from_colors(colors), cells=wide)


def text(line):
    return "".join(sp.text for sp in line)


def rows_for(env=None, flags=()):
    d = tempfile.mkdtemp()
    for f in flags:
        open(os.path.join(d, f), "w").close()
    return SV.rows(d, env or {}), d


class RowsTests(unittest.TestCase):
    def test_every_catalog_switch_has_a_row_in_group_order(self):
        rs, _ = rows_for()
        self.assertEqual([r.sw.id for r in rs], SV.ids_in_order())
        self.assertEqual(set(SV.ids_in_order()), set(SW.IDS))

    def test_state_and_source_come_from_the_resolver(self):
        rs, _ = rows_for({"KITTYMUX_BELL": "0"}, ["hue-off", "attention-on"])
        by = {r.sw.id: r for r in rs}
        self.assertEqual((by["bell"].on, by["bell"].where, by["bell"].what), (False, "env", "KITTYMUX_BELL"))
        self.assertEqual((by["hue"].on, by["hue"].where), (False, "flag"))
        self.assertEqual((by["attention"].on, by["attention"].where), (True, "flag"))
        self.assertEqual((by["folder"].on, by["folder"].where), (True, "default"))

    def test_changed_counts_non_defaults_and_env_holds(self):
        rs, _ = rows_for()
        self.assertEqual(SV.changed(rs), 0)
        rs, _ = rows_for({"KITTYMUX_BELL": "0"}, ["hue-off"])
        self.assertEqual(SV.changed(rs), 2)

    def test_the_current_preset_is_found_only_when_the_twelve_match(self):
        d = tempfile.mkdtemp()
        self.assertEqual(SV.current_preset(SV.rows(d, {})), "default")
        import kittymux_features as F
        F.apply_preset(d, "minimal")
        self.assertEqual(SV.current_preset(SV.rows(d, {})), "minimal")
        F.apply_preset(d, "full")
        self.assertEqual(SV.current_preset(SV.rows(d, {})), "full")
        SW.set_switch(d, "hue", False)
        self.assertIsNone(SV.current_preset(SV.rows(d, {})))

    def test_a_notification_switch_does_not_change_which_preset_matches(self):
        d = tempfile.mkdtemp()
        SW.set_switch(d, "bell", False)
        self.assertEqual(SV.current_preset(SV.rows(d, {})), "default")

    def test_only_a_risky_switch_that_is_off_and_not_held_asks(self):
        rs, _ = rows_for()
        by = {r.sw.id: r for r in rs}
        self.assertTrue(SV.needs_confirm(by["usage-live"]))
        self.assertTrue(SV.needs_confirm(by["attention"]))
        self.assertTrue(SV.needs_confirm(by["resume-auto"]))
        self.assertFalse(SV.needs_confirm(by["hue"]))
        rs, _ = rows_for({}, ["usage-live-on"])
        self.assertFalse(SV.needs_confirm({r.sw.id: r for r in rs}["usage-live"]))       # already on: turning OFF never asks
        rs, _ = rows_for({"KITTYMUX_ATTENTION": "1"})
        self.assertFalse(SV.needs_confirm({r.sw.id: r for r in rs}["attention"]))        # held by the environment: nothing to confirm


class DrawingTests(unittest.TestCase):
    def draw(self, cols, sel=0, colors=TOKYO, env=None, flags=(), asking=None, notice=None):
        rs, _ = rows_for(env, flags)
        return SV.view(rs, sel, cols, kit(colors), asking=asking, notice=notice)

    def test_every_line_is_exactly_as_wide_as_asked_at_every_width_and_in_both_themes(self):
        for colors in (TOKYO, LATTE):
            for cols in (8, 12, 18, 26, 32, 40, 48, 80):
                for sel in (0, 3, 8, 14, 21):
                    for asking in (None, "usage-live", "attention"):
                        v = self.draw(cols, sel, colors, env={"KITTYMUX_BELL": "0"}, flags=["hue-off"], asking=asking)
                        for line in [v.header] + v.lines:
                            self.assertEqual(sum(wide(sp.text) for sp in line), cols, f"cols={cols} sel={sel}: {text(line)!r}")

    def test_every_region_is_inside_the_body(self):
        for cols in (18, 26, 40, 80):
            for asking in (None, "usage-live"):
                v = self.draw(cols, SV.ids_in_order().index("usage-live"), asking=asking)
                n = len(v.lines)
                for y0, y1, _ in v.rows:
                    self.assertTrue(0 <= y0 < y1 <= n)
                for x0, x1, y, _ in v.toggles:
                    self.assertTrue(0 <= x0 < x1 <= cols and 0 <= y < n, (cols, x0, x1, y))
                for x0, x1, y, _ in v.presets:
                    self.assertTrue(0 <= x0 < x1 <= cols and y == 0)
                for x0, x1, y, _ in v.buttons:
                    self.assertTrue(0 <= x0 < x1 <= cols and 0 <= y < n)

    def test_each_row_says_its_state_in_a_word_and_a_glyph(self):
        v = self.draw(40, 0, flags=["hue-off"])
        body = [text(l) for l in v.lines]
        self.assertTrue(any("● on" in l for l in body))
        self.assertTrue(any("○ off" in l for l in body))

    def test_source_markers_show_only_off_the_default(self):
        quiet = " ".join(text(l) for l in self.draw(60).lines)
        self.assertNotIn(" env", quiet)
        self.assertNotIn(" file", quiet)
        loud = " ".join(text(l) for l in self.draw(60, env={"KITTYMUX_BELL": "0"}, flags=["hue-off"]).lines)
        self.assertIn("env", loud)
        self.assertIn("file", loud)

    def test_the_header_counts_changes_and_holds(self):
        self.assertIn("all defaults", text(self.draw(40).header))
        h = text(self.draw(60, env={"KITTYMUX_BELL": "0"}, flags=["hue-off"]).header)
        self.assertIn("2 changed", h)
        self.assertIn("1 held by env", h)

    def test_a_held_row_names_its_variable_when_picked(self):
        i = SV.ids_in_order().index("bell")
        v = self.draw(60, i, env={"KITTYMUX_BELL": "0"})
        self.assertIn("held by KITTYMUX_BELL", " ".join(text(l) for l in v.lines))

    def test_the_help_of_the_picked_row_only(self):
        i = SV.ids_in_order().index("folder")
        body = " ".join(text(l) for l in self.draw(80, i).lines)
        self.assertIn(SW.get("folder").help[:30], body)
        self.assertNotIn(SW.get("hue").help[:30], body)

    def test_a_risky_switch_that_is_asking_shows_its_consequence_and_two_buttons(self):
        i = SV.ids_in_order().index("usage-live")
        v = self.draw(60, i, asking="usage-live")
        body = " ".join(text(l) for l in v.lines)
        self.assertIn("contact each provider", body)
        self.assertEqual({a for _, _, _, a in v.buttons}, {"confirm", "cancel"})
        quiet = self.draw(60, i)
        self.assertEqual(quiet.buttons, [])
        self.assertNotIn("contact each provider", " ".join(text(l) for l in quiet.lines))

    def test_the_confirm_buttons_survive_a_narrow_panel(self):
        i = SV.ids_in_order().index("usage-live")
        for cols in (26, 32):
            v = self.draw(cols, i, asking="usage-live")
            self.assertEqual({a for _, _, _, a in v.buttons}, {"confirm", "cancel"}, cols)

    def test_every_row_has_a_toggle_region_in_catalog_order(self):
        v = self.draw(48)
        self.assertEqual([t[3] for t in v.toggles], SV.ids_in_order())
        ys = [t[2] for t in v.toggles]
        self.assertEqual(ys, sorted(ys))

    def test_presets_are_clickable_at_every_width_and_the_current_one_is_marked(self):
        for cols in (18, 26, 32, 48):
            v = self.draw(cols)
            self.assertEqual([p[3] for p in v.presets], list(SV.PRESET_NAMES), cols)

    def test_hostile_text_in_a_variable_name_cannot_reach_the_screen(self):
        rs, _ = rows_for()
        evil = SV.Row(SW.get("bell"), False, "env", "KITTYMUX_BELL\x1b[2J\nboom")
        rs = [evil if r.sw.id == "bell" else r for r in rs]
        v = SV.view(rs, SV.ids_in_order().index("bell"), 60, kit())
        for line in v.lines:
            self.assertNotIn("\x1b", text(line))
            self.assertNotIn("\n", text(line))

    def test_a_notice_shows_under_its_row_only(self):
        i = SV.ids_in_order().index("hue")
        v = self.draw(60, i, notice=("hue", "cannot save: read-only", "error"))
        self.assertIn("cannot save", " ".join(text(l) for l in v.lines))
        v2 = self.draw(60, 0, notice=("hue", "cannot save: read-only", "error"))
        self.assertNotIn("cannot save", " ".join(text(l) for l in v2.lines))

    def test_a_planned_switch_says_so(self):
        i = SV.ids_in_order().index("sheet")
        body = " ".join(text(l) for l in self.draw(60, i).lines)
        self.assertIn("not built yet", body)
        self.assertIn("(planned)", body)

    def test_it_never_raises_on_nonsense(self):
        rs, _ = rows_for()
        for sel in (-5, 999, None, "x", 2.7):
            SV.view(rs, sel, 3, kit())
            SV.view(rs, sel, 500, kit())
        SV.view([], 0, 40, kit())


if __name__ == "__main__":
    unittest.main()
