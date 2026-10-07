import os
import sys
import unicodedata
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_palette as P  # noqa: E402
import kittymux_theme as T  # noqa: E402
import kittymux_ui as U  # noqa: E402

TOKYO = {"background": 0x1a1b26, "foreground": 0xc0caf5, "active_border_color": 0xbb9af7,
         "color9": 0xf7768e, "color10": 0x9ece6a, "color11": 0xe0af68, "color12": 0x7aa2f7}
LATTE = {"background": 0xeff1f5, "foreground": 0x4c4f69, "active_border_color": 0x1e66f5,
         "color9": 0xd20f39, "color10": 0x40a02b, "color11": 0xdf8e1d, "color12": 0x1e66f5}


def wide(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def kit(colors=TOKYO, **kw):
    return U.Kit(T.from_colors(colors), **kw)


TABS = [{"os": 1, "id": 11, "title": "api", "cwd": "/home/u/code/api", "panes": 1, "state": "waiting"},
        {"os": 1, "id": 12, "title": "web", "cwd": "/home/u/code/web", "panes": 3, "state": "working"},
        {"os": 1, "id": 13, "title": "notes", "cwd": "/home/u/plain/notes", "panes": 1, "state": ""}]
ROWS = [{"kind": "event", "agent": "claude", "tone": "urgent", "text": "◆  claude  api — Do you want to proceed?   3m",
         "action": {"op": "jump", "pid": 100, "w": 7, "ack": "1a2b-3"}},
        {"kind": "event", "agent": "claude", "tone": "", "text": "✓  claude  docs — finished   9m", "action": {"op": "jump", "pid": 100, "w": 8}},
        {"kind": "running", "agent": "claude", "tone": "active", "text": "⠙  claude  web   ~/code/web   working", "action": {"op": "jump", "pid": 100, "w": 9}},
        {"kind": "closed", "agent": "codex", "tone": "", "text": "↺  codex  old   ~/code/old   closed 2h ago · 3 runs", "action": {"op": "reopen", "key": "codex:abc"}},
        {"kind": "new", "agent": "claude", "tone": "", "text": "+  new claude   tab · ~/code/api   ◔ 5h 99% used", "action": {"op": "spawn", "agent": "claude", "where": "tab"}},
        {"kind": "more", "agent": "", "tone": "", "text": "⋯  2 settled", "action": {"op": "all"}},
        {"kind": "utility", "agent": "", "tone": "", "text": "≋  Usage   provider quotas", "action": {"op": "usage"}}]


class BuildTests(unittest.TestCase):
    def test_groups_come_in_order_and_each_keeps_its_own_order(self):
        items = P.build(TABS, ROWS)
        groups = [it["group"] for it in items]
        self.assertEqual(groups, sorted(groups, key=P.GROUPS.index))
        self.assertEqual([it["group"] for it in items][:3], ["Needs you", "Inbox", "Tabs"])
        self.assertEqual([it["title"] for it in items if it["group"] == "Tabs"], ["api", "web", "notes"])

    def test_running_agents_and_the_show_more_row_are_not_listed_twice(self):
        titles = " | ".join(it["title"] for it in P.build(TABS, ROWS))
        self.assertNotIn("working", titles)
        self.assertNotIn("settled", titles)

    def test_the_rows_own_glyph_is_replaced_by_our_mark(self):
        needs = next(it for it in P.build(TABS, ROWS) if it["group"] == "Needs you")
        self.assertTrue(needs["title"].startswith("claude api"))
        self.assertEqual(needs["mark"], ("!", "warm"))
        self.assertEqual(needs["action"]["op"], "jump")

    def test_tabs_carry_their_state_and_pane_count(self):
        tabs = {it["title"]: it for it in P.from_tabs(TABS)}
        self.assertEqual(tabs["api"]["mark"][1], "warm")
        self.assertEqual(tabs["web"]["right"], "3 panes")
        self.assertEqual(tabs["notes"]["right"], "")
        self.assertEqual(tabs["notes"]["detail"], "notes")
        self.assertEqual(tabs["api"]["action"], {"op": "focus-tab", "tab": 11})

    def test_a_new_agent_row_keeps_its_headroom_hint(self):
        new = next(it for it in P.build([], ROWS) if it["action"].get("op") == "spawn")
        self.assertIn("◔ 5h 99% used", new["title"])

    def test_every_fixed_action_is_listed_and_points_at_a_known_id(self):
        acts = [it for it in P.actions()]
        self.assertEqual({a["action"]["id"] for a in acts}, set(P.ACTIONS))
        for it in acts:
            self.assertEqual(it["group"], "Actions")

    def test_junk_input_never_raises(self):
        for tabs in (None, 5, [None, 1, "x", {}, {"id": True}, {"id": "7"}, {"id": 5, "title": None, "cwd": None, "panes": "x", "state": 3}]):
            P.from_tabs(tabs)
        for rows in (None, 5, [None, {}, {"kind": "event"}, {"kind": "event", "action": 5}, {"kind": "new", "action": {}, "text": None, "agent": 7}]):
            P.from_rows(rows)
        P.build(None, None)

    def test_hostile_text_is_cleaned(self):
        tabs = [{"id": 1, "title": "a\x1b]0;x\x07b", "cwd": "/x/\x1bdir", "panes": 1, "state": ""}]
        rows = [{"kind": "closed", "agent": "co\x1bdex", "text": "↺  co\x1bdex  ti\x00tle", "action": {"op": "reopen", "key": "k"}}]
        for it in P.build(tabs, rows):
            for field in ("title", "detail", "agent", "right"):
                for ch in ("\x1b", "\x07", "\x00"):
                    self.assertNotIn(ch, it[field])


class LsTests(unittest.TestCase):
    def ls(self):
        return [{"id": 1, "tabs": [
            {"id": 11, "title": "api", "is_focused": False, "active_window_history": [101], "windows": [
                {"id": 101, "cwd": "/home/u/code/api", "title": "t", "cmdline": ["zsh"], "foreground_processes": []}]},
            {"id": 12, "title": "", "windows": [
                {"id": 102, "cwd": "/w", "title": "fallback title", "cmdline": ["zsh"]}, {"id": 103, "cwd": "/w", "title": "b", "cmdline": ["kitten", "x/palette-kit.py"]}]},
            {"id": 13, "title": "ghost", "windows": [{"id": 104, "cwd": "/", "title": "x", "cmdline": ["kitty", "+runpy", "from kittens.runner import main"]}]}]},
            {"id": 2, "tabs": [{"id": 21, "title": "other window", "windows": [{"id": 201, "cwd": "/o", "title": "o", "cmdline": ["sh"]}]}]}]

    def test_every_tab_with_a_real_pane_is_listed_across_os_windows(self):
        tabs = P.tabs_from_ls(self.ls(), {}, 103, 0.0)
        self.assertEqual([(t["os"], t["id"]) for t in tabs], [(1, 11), (1, 12), (2, 21)])

    def test_the_overlay_is_not_a_pane_and_marks_its_own_tab_current(self):
        tabs = {t["id"]: t for t in P.tabs_from_ls(self.ls(), {}, 103, 0.0)}
        self.assertEqual(tabs[12]["panes"], 1)
        self.assertTrue(tabs[12]["current"])
        self.assertFalse(tabs[11]["current"])
        self.assertNotIn(13, tabs)                       # a tab that is only an overlay is not a destination

    def test_title_falls_back_to_the_active_pane_and_is_cleaned(self):
        tabs = {t["id"]: t for t in P.tabs_from_ls(self.ls(), {}, 0, 0.0)}
        self.assertEqual(tabs[12]["title"], "fallback title")
        self.assertEqual(tabs[11]["cwd"], "/home/u/code/api")

    def test_junk_never_raises(self):
        for data in (None, 5, [None, 1, {}, {"tabs": None}, {"id": 1, "tabs": [None, {}, {"id": "x", "windows": [{}]}, {"id": 3, "windows": [None, {"id": 1}]}]}]):
            P.tabs_from_ls(data, None, 0, 0.0)


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.items = P.build(TABS, ROWS)

    def titles(self, q):
        return [it["title"] for it in P.filter_items(self.items, q)]

    def test_no_query_is_the_grouped_list_without_its_long_tail(self):
        shown = [it for it in self.items if not it.get("extra")]
        self.assertEqual(P.filter_items(self.items, ""), shown)
        self.assertEqual(P.filter_items(self.items, "   "), shown)

    def test_only_the_first_few_new_agents_show_by_default_and_a_query_finds_the_rest(self):
        names = ["claude", "codex", "devin", "cursor-agent", "opencode", "agy", "grok"]
        rows = []
        for n in names:
            for where in ("tab", "vsplit"):
                rows.append({"kind": "new", "agent": n, "tone": "", "text": f"+  new {n}   {where}", "action": {"op": "spawn", "agent": n, "where": where}})
        items = P.build([], rows)
        default = [it["agent"] for it in P.filter_items(items, "") if it["action"].get("op") == "spawn"]
        self.assertEqual(default, names[:P.NEW_VISIBLE])
        self.assertTrue(all(it["action"]["where"] == "tab" for it in P.filter_items(items, "") if it["action"].get("op") == "spawn"))
        found = [it["action"] for it in P.filter_items(items, "grok")]
        self.assertEqual({a["where"] for a in found}, {"tab", "vsplit"})
        self.assertEqual(len(P.filter_items(items, "split")), len(names))

    def test_every_word_must_match_somewhere(self):
        self.assertEqual(self.titles("api"), [t for t in self.titles("api")])
        self.assertTrue(all("api" in (it["title"] + it["detail"] + it["group"]).lower() for it in P.filter_items(self.items, "api")))
        self.assertEqual(self.titles("zzz nothing"), [])
        self.assertEqual(self.titles("api zzz"), [])

    def test_a_title_that_starts_with_the_word_beats_one_that_only_contains_it(self):
        items = [P._item("Tabs", "my web app"), P._item("Tabs", "web"), P._item("Tabs", "cobweb")]
        self.assertEqual([it["title"] for it in P.filter_items(items, "web")], ["web", "my web app", "cobweb"])

    def test_the_title_beats_the_detail(self):
        items = [P._item("Tabs", "other", detail="api folder"), P._item("Tabs", "api")]
        self.assertEqual([it["title"] for it in P.filter_items(items, "api")], ["api", "other"])

    def test_matching_ignores_case_and_looks_at_the_group_and_agent_too(self):
        self.assertIn("Join this tab into another", self.titles("JOIN"))
        self.assertTrue(any(it["agent"] == "codex" for it in P.filter_items(self.items, "codex")))
        self.assertTrue(any(it["group"] == "Actions" for it in P.filter_items(self.items, "actions")))

    def test_ties_keep_the_grouped_order(self):
        items = [P._item("Tabs", "same"), P._item("Agents", "same"), P._item("Actions", "same")]
        self.assertEqual([it["group"] for it in P.filter_items(items, "same")], ["Tabs", "Agents", "Actions"])


class CursorTests(unittest.TestCase):
    def test_typing_and_editing_reset_the_pick(self):
        c = P.Cursor()
        c.count = 5
        c.move(3)
        self.assertEqual(c.index, 3)
        c.type("ap")
        self.assertEqual((c.query, c.index), ("ap", 0))
        c.move(2)
        c.backspace()
        self.assertEqual((c.query, c.index), ("a", 0))
        c.type("x")
        c.clear()
        self.assertEqual((c.query, c.index), ("", 0))

    def test_moving_clamps_and_an_empty_list_stays_at_zero(self):
        c = P.Cursor()
        c.count = 3
        c.move(99)
        self.assertEqual(c.index, 2)
        c.move(-99)
        self.assertEqual(c.index, 0)
        c.count = 0
        c.move(5)
        self.assertEqual(c.index, 0)

    def test_non_printable_input_and_huge_pastes_are_bounded(self):
        c = P.Cursor()
        c.type("a\x1b[Ab\x00c")
        self.assertNotIn("\x1b", c.query)
        self.assertNotIn("\x00", c.query)
        c.type("z" * 5000)
        self.assertLessEqual(len(c.query), 200)


class ValidateTests(unittest.TestCase):
    def test_every_action_the_palette_builds_is_accepted_unchanged(self):
        for it in P.build(TABS, ROWS):
            ok = P.validate_action(it["action"], known_agents=("claude", "codex"))
            self.assertIsNotNone(ok, it["action"])
            for k, v in ok.items():
                self.assertEqual(str(it["action"].get(k)) if k == "w" else it["action"].get(k), v)

    def test_anything_else_is_refused(self):
        bad = [None, 5, "x", [], {}, {"op": "rm"}, {"op": "focus-tab"}, {"op": "focus-tab", "tab": -1}, {"op": "focus-tab", "tab": True},
               {"op": "focus-tab", "tab": "7"}, {"op": "focus-tab", "tab": 2 ** 41}, {"op": "jump", "pid": 1, "w": "x"}, {"op": "jump", "w": 5},
               {"op": "reopen", "key": "../../etc"}, {"op": "reopen", "key": "a b"}, {"op": "reopen", "key": "claude:a..b"}, {"op": "reopen", "key": "/etc/passwd"}, {"op": "reopen", "key": "nocolon"}, {"op": "reopen", "key": 5}, {"op": "reopen", "key": "x" * 500},
               {"op": "spawn", "agent": "Claude;rm", "where": "tab"}, {"op": "spawn", "agent": "claude", "where": "elsewhere"},
               {"op": "spawn", "agent": "--help", "where": "tab"}, {"op": "run", "id": "rm -rf"}, {"op": "run"}, {"op": "run", "id": ["join"]}]
        for obj in bad:
            self.assertIsNone(P.validate_action(obj), obj)

    def test_spawn_only_starts_agents_that_are_installed(self):
        a = {"op": "spawn", "agent": "gemini", "where": "tab"}
        self.assertIsNotNone(P.validate_action(a))
        self.assertIsNone(P.validate_action(a, known_agents=("claude", "codex")))
        self.assertIsNotNone(P.validate_action(a, known_agents=("gemini",)))

    def test_extra_keys_are_dropped_not_passed_through(self):
        out = P.validate_action({"op": "focus-tab", "tab": 3, "cmd": "rm -rf ~", "argv": ["x"]})
        self.assertEqual(out, {"op": "focus-tab", "tab": 3})
        out = P.validate_action({"op": "jump", "pid": 1, "w": 2, "ack": "ab-1", "evil": 1})
        self.assertEqual(out, {"op": "jump", "pid": 1, "w": "2", "ack": "ab-1"})
        self.assertNotIn("ack", P.validate_action({"op": "jump", "pid": 1, "w": 2, "ack": "no spaces; allowed"}))

    def test_every_fixed_action_has_a_kittymux_argv_that_is_a_known_verb(self):
        verbs = {"join", "peek", "panel", "notify", "sessions"}
        for key, (_title, _hint, argv) in P.ACTIONS.items():
            self.assertIn(argv[0], verbs, key)
            self.assertTrue(all(isinstance(a, str) and not a.startswith("-") or a == "--waiting" for a in argv), key)


class ViewTests(unittest.TestCase):
    def items(self, extra=0):
        return P.build(TABS + [{"os": 1, "id": 100 + i, "title": f"tab {i}", "cwd": f"/x/{i}", "panes": 1, "state": ""} for i in range(extra)], ROWS)

    def test_every_line_is_exactly_as_wide_as_the_panel(self):
        for colors in (TOKYO, LATTE):
            for kw in ({}, {"cells": wide, "rounded": False}):
                k = kit(colors, **kw)
                for cols in (8, 20, 40, 64, 100):
                    for query in ("", "api", "zzz", "join"):
                        for rows in (1, 3, 8, 30):
                            v = P.view(self.items(4), query, 0, 0, cols, rows, k)
                            self.assertEqual(len(v.lines), rows)
                            for line in v.lines + v.preview:
                                self.assertEqual(U.line_cells(line, k.cells), cols, (cols, query, rows))

    def test_the_grouped_list_has_headers_and_a_search_does_not(self):
        k = kit()
        grouped = "\n".join(U.plain(x) for x in P.view(self.items(), "", 0, 0, 60, 30, k).lines)
        for g in ("Needs you", "Inbox", "Tabs", "Agents", "Actions"):
            self.assertIn(g, grouped)
        flat = "\n".join(U.plain(x) for x in P.view(self.items(), "api", 0, 0, 60, 30, k).lines)
        self.assertNotIn("Needs you", flat.split("api")[0])

    def test_hits_map_rows_back_to_items_in_order_and_the_pick_is_marked(self):
        k = kit()
        v = P.view(self.items(), "", 3, 0, 60, 30, k)
        self.assertEqual([i for _y, i in v.hits], list(range(v.count)))
        y = next(y for y, i in v.hits if i == 3)
        self.assertTrue(U.plain(v.lines[y]).lstrip().startswith("▌") or "▌" in U.plain(v.lines[y])[:2])
        self.assertEqual(sum("▌" in U.plain(line)[:1] for line in v.lines), 1)

    def test_scrolling_keeps_the_pick_visible_with_its_group_header(self):
        k = kit()
        items = self.items(40)
        for index in (0, 5, 20, 45, len(items) - 1):
            v = P.view(items, "", index, 0, 60, 8, k)
            self.assertIn(index, [i for _y, i in v.hits])
            again = P.view(items, "", index, v.scroll, 60, 8, k)
            self.assertEqual(again.scroll, v.scroll)

    def test_the_picked_item_is_previewed_in_full_and_wraps(self):
        k = kit()
        long = P.build([{"id": 1, "title": "word " * 60, "cwd": "", "panes": 1, "state": ""}], [])
        v = P.view(long, "word", 0, 0, 40, 6, k)
        self.assertEqual(len(v.preview), P.PREVIEW_ROWS)
        self.assertIn("word", U.plain(v.preview[0]))

    def test_nothing_matching_says_so(self):
        v = P.view(self.items(), "zzzz", 0, 0, 60, 6, kit())
        self.assertEqual(v.count, 0)
        self.assertIn("nothing matches", U.plain(v.preview[0]))
        self.assertEqual(v.hits, [])

    def test_an_empty_world_is_just_the_fixed_actions(self):
        v = P.view(P.build([], []), "", 0, 0, 60, 10, kit())
        self.assertEqual(v.count, len(P.ACTIONS))

    def test_junk_arguments_never_raise(self):
        k = kit()
        for index in (-5, 999, None if False else 0):
            for scroll in (-9, 99):
                P.view(self.items(), "", index, scroll, 1, 1, k)
                P.view([], "x", index, scroll, 8, 0, k)


if __name__ == "__main__":
    unittest.main()
