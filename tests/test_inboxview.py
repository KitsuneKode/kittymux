import os
import sys
import unicodedata
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_inbox as I  # noqa: E402
import kittymux_inboxview as IV  # noqa: E402
import kittymux_theme as T  # noqa: E402
import kittymux_ui as U  # noqa: E402

TOKYO = {"background": 0x1a1b26, "foreground": 0xc0caf5, "active_border_color": 0xbb9af7,
         "color9": 0xf7768e, "color10": 0x9ece6a, "color11": 0xe0af68, "color12": 0x7aa2f7}
LATTE = {"background": 0xeff1f5, "foreground": 0x4c4f69, "active_border_color": 0x1e66f5,
         "color9": 0xd20f39, "color10": 0x40a02b, "color11": 0xdf8e1d, "color12": 0x1e66f5}
NOW = 1_800_000_000.0


def wide(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def kit(colors=TOKYO, **kw):
    return U.Kit(T.from_colors(colors), **kw)


def ev(kind, agent="claude", tab="web", age=180, status="unread", **kw):
    e = I.make_event(kind, agent, 7, "screen", NOW - age, pid=100, tab=tab, title=kw.pop("title", f"{kind} title"), body=kw.pop("body", ""), **kw)
    e.pop("op")
    e["status"] = status
    return e


def sample():
    return [ev("permission", age=180, title="Claude needs your permission to use Bash", body="rm -rf node_modules"),
            ev("question", tab="web", age=60, title="Which migration approach?"),
            ev("limit", agent="codex", tab="api", age=540, title="5h limit reached", reset_at=NOW + 13800),
            ev("done", tab="docs", age=250, title="Finished in 4m 12s"),
            ev("info", age=900, status="read", title="Session started")]


def text(v):
    return "\n".join(U.plain(x) for x in [v.header] + v.lines)


class OrderTests(unittest.TestCase):
    def test_needs_you_first_then_the_rest_unread_before_read(self):
        kinds = [e["kind"] for e in IV.visible(sample())]
        self.assertEqual(kinds[:2], ["question", "permission"])         # both need you; the newer one (the question) first
        self.assertEqual(kinds[-1], "info")                              # read ones sink
        self.assertEqual(set(kinds), {"permission", "question", "limit", "done", "info"})

    def test_filters(self):
        events = sample()
        self.assertEqual({e["kind"] for e in IV.visible(events, "needs")}, {"permission", "question"})
        self.assertEqual([e["kind"] for e in IV.visible(events, "done")], ["done"])
        self.assertEqual([e["kind"] for e in IV.visible(events, "limits")], ["limit"])
        self.assertEqual(len(IV.visible(events, "all")), 5)
        self.assertEqual(len(IV.visible(events, "nonsense")), 5)

    def test_dismissed_events_never_show_and_counts_follow_the_filters(self):
        events = sample()
        events[3]["status"] = "dismissed"
        self.assertNotIn("done", [e["kind"] for e in IV.visible(events)])
        self.assertEqual(IV.counts(events), {"all": 4, "needs": 2, "done": 0, "limits": 1})
        self.assertEqual((IV.unread(events), IV.needs_you(events)), (3, 2))

    def test_a_long_log_is_capped(self):
        many = [ev("info", age=i) for i in range(200)]
        self.assertEqual(len(IV.visible(many)), IV.SHOWN_MAX)

    def test_unknown_kinds_and_junk_are_skipped(self):
        junk = [None, 1, "x", {}, {"kind": "bogus"}, {"kind": "done", "status": "unread", "t": "x"}]
        self.assertEqual([e["kind"] for e in IV.visible(junk)], ["done"])
        self.assertEqual(IV.visible(None), [])
        self.assertEqual(IV.counts(None), {"all": 0, "needs": 0, "done": 0, "limits": 0})


class LayoutTests(unittest.TestCase):
    def test_every_line_is_exactly_the_panel_width(self):
        for colors in (TOKYO, LATTE):
            for kw in ({}, {"cells": wide, "rounded": False}):
                k = kit(colors, **kw)
                for cols in (8, 14, 20, 26, 38, 52, 80):
                    for filt in ("all", "needs", "done", "limits"):
                        for sel in (0, 1, 3, 99):
                            v = IV.view(sample(), filt, sel, cols, k, NOW)
                            for line in [v.header] + v.lines:
                                self.assertEqual(U.line_cells(line, k.cells), cols, (cols, filt, sel, U.plain(line)))

    def test_cards_cover_their_own_lines_without_overlap(self):
        v = IV.view(sample(), "all", 0, 38, kit(), NOW)
        self.assertEqual(len(v.cards), 5)
        for (a0, a1, _), (b0, b1, _) in zip(v.cards, v.cards[1:]):
            self.assertLessEqual(a1, b0)
        for y0, y1, _ in v.cards:
            self.assertTrue(0 <= y0 < y1 <= len(v.lines))

    def test_the_picked_card_alone_has_buttons_and_regions_that_sit_on_them(self):
        k = kit()
        for sel in range(5):
            v = IV.view(sample(), "all", sel, 38, k, NOW)
            self.assertEqual(sorted({b[3] for b in v.buttons}), [sel])
            self.assertEqual([b[4] for b in v.buttons], ["jump", "dismiss"])
            y = v.buttons[0][2]
            row = U.plain(v.lines[y])
            self.assertIn("Jump", row)
            self.assertIn("Dismiss", row)
            jump, dismiss = v.buttons
            self.assertIn("Jump", row[jump[0]:jump[1]])
            self.assertIn("Dismiss", row[dismiss[0]:dismiss[1]])
            self.assertLessEqual(jump[1], dismiss[0])
            self.assertEqual(text(v).count("Jump"), 1)

    def test_a_panel_too_narrow_for_both_buttons_draws_none_rather_than_a_broken_one(self):
        v = IV.view(sample(), "all", 0, 16, kit(), NOW)
        self.assertEqual(v.buttons, [])

    def test_all_four_filters_stay_reachable_at_every_realistic_panel_width(self):
        k = kit()
        for cols in (26, 30, 32, 36, 38, 44, 52, 80):
            for filt in ("all", "needs", "done", "limits"):
                v = IV.view(sample(), filt, 0, cols, k, NOW)
                self.assertEqual([c[2] for c in v.chips], ["all", "needs", "done", "limits"], (cols, filt))
                for x0, x1, _ in v.chips:
                    self.assertTrue(0 <= x0 < x1 <= cols)

    def test_wider_panels_get_the_wider_wording(self):
        k = kit()
        self.assertIn("Needs you", text(IV.view(sample(), "all", 0, 80, k, NOW)))
        narrow = text(IV.view(sample(), "all", 0, 32, k, NOW))
        self.assertNotIn("Needs you", narrow)
        self.assertIn("!", narrow)

    def test_filter_chips_are_regions_in_order_and_the_active_one_is_strong(self):
        k = kit()
        v = IV.view(sample(), "needs", 0, 52, k, NOW)
        self.assertEqual([c[2] for c in v.chips], ["all", "needs", "done", "limits"])
        for (a0, a1, _), (b0, b1, _) in zip(v.chips, v.chips[1:]):
            self.assertLessEqual(a1, b0)
        line = U.plain(v.lines[0])
        self.assertIn("Needs you 2", line[v.chips[1][0]:v.chips[1][1]])
        strong = [s for s in v.lines[0] if s.bold]
        self.assertEqual(len(strong), 1)
        self.assertIn("Needs you", strong[0].text)


class ContentTests(unittest.TestCase):
    def test_header_counts_unread_and_those_that_need_you(self):
        self.assertIn("4 unread", text(IV.view(sample(), "all", 0, 38, kit(), NOW)))
        self.assertIn("! 2 need you", text(IV.view(sample(), "all", 0, 38, kit(), NOW)))
        one = [ev("permission")]
        self.assertIn("! 1 needs you", text(IV.view(one, "all", 0, 38, kit(), NOW)))
        self.assertIn("all read", text(IV.view([ev("info", status="read")], "all", 0, 38, kit(), NOW)))

    def test_a_permission_shows_who_when_what_and_the_command(self):
        body = text(IV.view(sample(), "needs", 1, 52, kit(), NOW))
        for want in ("Claude", "web", "3m", "Claude needs your permission to use Bash", "rm -rf node_modules"):
            self.assertIn(want, body)

    def test_a_limit_shows_a_full_gauge_and_the_time_to_reset(self):
        body = text(IV.view(sample(), "limits", 0, 38, kit(), NOW))
        self.assertIn("Codex", body)
        self.assertIn("↻ 3h 50m", body)
        self.assertIn("▄" * 10, body)

    def test_a_merged_event_shows_how_many_times_it_happened(self):
        e = ev("permission")
        e["count"] = 3
        self.assertIn("×3", text(IV.view([e], "all", 0, 38, kit(), NOW)))

    def test_read_events_are_dimmer_than_unread_ones(self):
        k = kit()
        both_unread = IV.view([ev("done", title="beta"), ev("done", title="alpha")], "all", 0, 38, k, NOW)
        one_read = IV.view([ev("done", title="beta"), ev("done", title="alpha", status="read")], "all", 0, 38, k, NOW)
        fg = lambda v: next(s.fg for line in v.lines for s in line if s.text.strip().startswith("alpha"))
        self.assertNotEqual(fg(both_unread), fg(one_read))

    def test_empty_states(self):
        k = kit()
        self.assertIn("All clear", text(IV.view([], "all", 0, 38, k, NOW)))
        self.assertIn("nothing waits on you", text(IV.view([], "all", 0, 38, k, NOW)))
        self.assertIn("nothing in this filter", text(IV.view([ev("done")], "limits", 0, 38, k, NOW)))
        v = IV.view([], "all", 0, 38, k, NOW)
        self.assertEqual((v.cards, v.buttons, v.count), ([], [], 0))

    def test_long_text_wraps_to_two_lines_and_ends_with_an_ellipsis(self):
        long = "word " * 80
        body = text(IV.view([ev("done", title=long.strip())], "all", 0, 30, kit(), NOW))
        self.assertIn("…", body)
        self.assertLessEqual(body.count("word"), 12)


class RobustnessTests(unittest.TestCase):
    def test_hostile_event_text_never_reaches_the_screen(self):
        k = kit()
        e = ev("permission", agent="cl\x1b]0;x\x07aude", tab="t\x1bab", title="ti\x1b[31mtle\x07", body="b\x00ody")
        e["agent"], e["tab"], e["title"], e["body"] = "cl\x1b]0;x\x07aude", "t\x1bab", "ti\x1b[31mtle\x07", "b\x00ody"   # past make_event's own cleaning
        v = IV.view([e], "all", 0, 38, k, NOW)
        for line in [v.header] + v.lines:
            for ch in ("\x1b", "\x07", "\x00"):
                self.assertNotIn(ch, U.plain(line))

    def test_junk_never_raises(self):
        k = kit()
        junk = [None, [], [None], [{"kind": "done", "t": float("nan"), "count": "x", "status": None, "agent": 5, "tab": None, "title": ["a"]}],
                [{"kind": "limit", "reset_at": "soon", "t": 1e400}], "x", 5]
        for events in junk:
            for sel in (-3, 0, 9, None, "x"):
                for cols in (1, 8, 38):
                    IV.view(events, "all", sel, cols, k, NOW)

    def test_wide_characters_keep_the_width(self):
        k = kit(cells=wide)
        e = ev("done", agent="日本語", tab="タブ", title="完了しました " * 10)
        for cols in (20, 38):
            v = IV.view([e], "all", 0, cols, k, NOW)
            for line in [v.header] + v.lines:
                self.assertEqual(U.line_cells(line, k.cells), cols)


if __name__ == "__main__":
    unittest.main()
