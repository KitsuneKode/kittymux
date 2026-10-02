import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_launcher as L  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
RISK = L.load_risk(os.path.join(ROOT, "assets", "agent-risk.json"))
NOW = 100000.0


class RiskTests(unittest.TestCase):
    def test_every_documented_bypass_flag_is_recognised_in_every_form(self):
        r = lambda agent, *argv: L.risk_of(RISK, agent, list(argv))          # noqa: E731
        self.assertEqual(r("claude", "claude", "--dangerously-skip-permissions"), "no-approvals")
        self.assertEqual(r("claude", "claude", "--permission-mode", "bypassPermissions"), "no-approvals")
        self.assertEqual(r("claude", "claude", "--permission-mode=bypassPermissions"), "no-approvals")
        self.assertEqual(r("codex", "codex", "--dangerously-bypass-approvals-and-sandbox"), "no-approvals")
        self.assertEqual(r("cursor-agent", "cursor-agent", "--yolo"), "no-approvals")
        self.assertEqual(r("cursor-agent", "cursor-agent", "-f"), "no-approvals")
        self.assertEqual(r("opencode", "opencode", "--auto"), "no-approvals")
        self.assertEqual(r("devin", "devin", "--permission-mode", "dangerous"), "no-approvals")
        self.assertEqual(r("agy", "agy", "--dangerously-skip-permissions"), "no-approvals")
        self.assertEqual(r("grok", "grok", "--always-approve"), "no-approvals")

    def test_ordinary_and_merely_related_flags_are_not_flagged(self):
        r = lambda agent, *argv: L.risk_of(RISK, agent, list(argv))          # noqa: E731
        self.assertEqual(r("claude", "claude", "--model", "opus", "--resume", "x"), "")
        self.assertEqual(r("claude", "claude", "--allow-dangerously-skip-permissions"), "")     # only makes the option available
        self.assertEqual(r("claude", "claude", "--permission-mode", "plan"), "")
        self.assertEqual(r("devin", "devin", "--permission-mode", "auto"), "")                    # read-only auto-approval, not "dangerous"
        self.assertEqual(r("devin", "devin", "-r", "dangerous"), "")                              # a value of another flag
        self.assertEqual(r("codex", "codex", "resume", "--last"), "")
        self.assertEqual(r("nosuch", "x", "--auto"), "")
        self.assertEqual(L.risk_of(RISK, "claude", None), "")
        self.assertEqual(L.risk_of({}, "claude", ["--dangerously-skip-permissions"]), "")        # no table: nothing is claimed

    def test_a_users_table_extends_the_shipped_one_and_bad_files_are_ignored(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, "risk.json")
        with open(p, "w") as f:
            json.dump({"myagent": {"flags": ["--yes-to-all"]}, "_x": {}}, f)
        t = L.load_risk(os.path.join(ROOT, "assets", "agent-risk.json"), p)
        self.assertEqual(L.risk_of(t, "myagent", ["--yes-to-all"]), "no-approvals")
        self.assertIn("claude", t)
        self.assertEqual(L.load_risk("/nonexistent", "/also/not"), {})


class SpawnTests(unittest.TestCase):
    def test_names_and_aliases_resolve_and_nothing_else_does(self):
        self.assertEqual([L.resolve_agent(x) for x in ("claude", "Claude", "c", "x", "d", "u", "o", "a", "cursor", "antigravity")],
                         ["claude", "claude", "claude", "codex", "devin", "cursor-agent", "opencode", "agy", "cursor-agent", "agy"])
        for bad in ("", "rm", "../claude", "claude; rm -rf ~", "--help", "/usr/bin/claude", "nosuch", None, "claude code", "claude\0"):
            self.assertIsNone(L.resolve_agent(bad), bad)

    def test_a_tab_a_split_and_a_tab_that_keeps_the_scratch_tab_last(self):
        a = L.launch_args("claude", "/usr/bin/claude", "tab")
        self.assertEqual(a[:2], ["--type=tab", "--cwd=current"])
        self.assertEqual(a[-2:], ["--", "/usr/bin/claude"])
        self.assertIn("kittymux_agent=claude", " ".join(a))
        s = L.launch_args("codex", "/usr/bin/codex", "vsplit", source_window="7")
        self.assertEqual(s[:2], ["--type=window", "--location=vsplit"])
        self.assertIn("--source-window", s)
        self.assertEqual(s[s.index("--source-window") + 1], "id:7")
        b = L.launch_args("claude", "/usr/bin/claude", "tab", before_scratch=True)
        self.assertIn("--location=before", b)
        self.assertIn("title:^!scratch and state:focused_os_window", b)

    def test_an_explicit_directory_and_extra_flags_and_hostile_input(self):
        a = L.launch_args("devin", "/x/devin", "tab", cwd="/work/a b", extra=["-r", "calm-otter"])
        self.assertIn("--cwd=/work/a b", a)
        self.assertEqual(a[-3:], ["/x/devin", "-r", "calm-otter"])
        self.assertEqual(L.launch_args("devin", "/x/devin", "tab", source_window="7; rm")[:2], ["--type=tab", "--cwd=current"])      # a non-numeric source window is dropped
        self.assertNotIn("--source-window", L.launch_args("devin", "/x/devin", "tab", source_window="7; rm"))
        with self.assertRaises(ValueError):
            L.launch_args("devin", "/x/devin", "overlay")


def ev(i, sev="needs-you", t=NOW - 600, pid=1, w=3, agent="claude", body="Approve: run tests?", tab="api"):
    return {"id": i, "severity": sev, "t": t, "pid": pid, "w": w, "agent": agent, "body": body, "tab": tab}


def win(w, state="idle", agent="codex", pid=1, tab="t", argv=None, cwd="/home/u/code/api"):
    return {"pid": pid, "w": w, "agent": agent, "state": state, "tab": tab, "cwd": cwd, "argv": argv or [agent]}


class RowTests(unittest.TestCase):
    def rows(self, **kw):
        base = dict(events=[], windows=[], closed=[], installed=["claude", "codex"], now=NOW, home="/home/u", cwd="/home/u/code/api", risk=RISK)
        base.update(kw)
        return L.build_rows(**base)

    def kinds(self, rows):
        return [r["kind"] for r in rows]

    def test_order_needs_you_longest_waiting_first_then_running_then_closed_then_new(self):
        rows = self.rows(events=[ev("new", t=NOW - 60, w=3), ev("old", t=NOW - 3600, w=4), ev("fin", sev="info", t=NOW - 10, w=5)],
                         windows=[win(6, "working"), win(7, "idle"), win(8, "waiting")],
                         closed=[{"key": "codex:s1", "agent": "codex", "tab": "x", "cwd": "/home/u/p", "last": NOW - 7200, "turns": 3}])
        self.assertEqual([r.get("event") for r in rows[:3]], ["old", "new", "fin"])
        self.assertEqual(self.kinds(rows)[:3], ["event"] * 3)
        running = [r for r in rows if r["kind"] == "running"]
        self.assertEqual([r["action"]["w"] for r in running], [8, 6, 7])                         # waiting, working, idle
        self.assertEqual(self.kinds(rows).index("closed"), 3 + 3)
        self.assertEqual(self.kinds(rows)[-1], "new")

    def test_a_window_with_an_event_is_listed_once_and_events_jump_and_ack(self):
        rows = self.rows(events=[ev("e1", w=3)], windows=[win(3, "waiting", agent="claude")])
        self.assertEqual(self.kinds(rows).count("running"), 0)
        self.assertEqual(rows[0]["action"], {"op": "jump", "pid": 1, "w": 3, "ack": "e1"})

    def test_closed_rows_reopen_and_new_rows_spawn_a_tab_and_a_split(self):
        rows = self.rows(closed=[{"key": "claude:abc", "agent": "claude", "tab": "api", "cwd": "/home/u/code/api", "last": NOW - 90000}])
        self.assertEqual([r["action"] for r in rows if r["kind"] == "closed"], [{"op": "reopen", "key": "claude:abc"}])
        new = [r["action"] for r in rows if r["kind"] == "new"]
        self.assertEqual(new, [{"op": "spawn", "agent": "claude", "where": "tab"}, {"op": "spawn", "agent": "claude", "where": "vsplit"},
                               {"op": "spawn", "agent": "codex", "where": "tab"}, {"op": "spawn", "agent": "codex", "where": "vsplit"}])
        self.assertIn("25h", [r for r in rows if r["kind"] == "closed"][0]["text"])

    def test_agents_that_are_not_installed_are_not_offered_and_the_closed_list_is_capped(self):
        rows = self.rows(installed=["codex"], closed=[{"key": f"k{i}", "agent": "codex", "cwd": f"/p/{i}", "last": NOW - i} for i in range(20)])
        self.assertEqual({r["action"]["agent"] for r in rows if r["kind"] == "new"}, {"codex"})
        self.assertEqual(self.kinds(rows).count("closed"), 8)

    def test_near_duplicate_closed_conversations_are_one_row(self):
        dup = lambda i, tab="api": {"key": f"k{i}", "agent": "claude", "tab": tab, "cwd": "/home/u/code/api", "last": NOW - i}          # noqa: E731
        rows = self.rows(closed=[dup(1), dup(2), dup(3), dup(4, tab="other")])
        closed = [r for r in rows if r["kind"] == "closed"]
        self.assertEqual([r["action"]["key"] for r in closed], ["k1", "k4"])                                  # the newest of each distinct (agent, cwd, tab)

    def closed(self, key, life, last=NOW - 100, **kw):
        return dict({"key": key, "agent": "claude", "tab": key, "cwd": f"/p/{key}", "last": last, "lifecycle": life}, **kw)

    def test_pinned_conversations_come_first_and_always_show_whatever_their_age(self):
        rows = self.rows(closed=[self.closed("new", "recent"), self.closed("old-pin", "pinned", last=NOW - 90 * 86400, pinned=True), self.closed("mid", "recent", last=NOW - 500)])
        closed = [r for r in rows if r["kind"] == "closed"]
        self.assertEqual([r["jkey"] for r in closed], ["old-pin", "new", "mid"])
        self.assertTrue(closed[0]["text"].startswith("★") and closed[0]["pinned"])
        self.assertTrue(closed[1]["text"].startswith("↺"))

    def test_settled_ones_are_folded_behind_one_row_that_shows_them(self):
        closed = [self.closed("a", "recent"), self.closed("b", "settled"), self.closed("c", "settled")]
        rows = self.rows(closed=closed)
        self.assertEqual([r["jkey"] for r in rows if r["kind"] == "closed"], ["a"])
        more = [r for r in rows if r["kind"] == "more"]
        self.assertEqual(len(more), 1)
        self.assertEqual(more[0]["action"], {"op": "all"})
        self.assertIn("2 settled conversations", more[0]["text"])
        self.assertEqual(self.kinds(rows).index("more"), self.kinds(rows).index("closed") + 1)         # right after the list it folds
        everything = self.rows(closed=closed, include_settled=True)
        self.assertEqual(sorted(r["jkey"] for r in everything if r["kind"] == "closed"), ["a", "b", "c"])
        self.assertEqual([r["settled"] for r in everything if r["kind"] == "closed" and r["jkey"] in ("b", "c")], [True, True])
        self.assertNotIn("more", self.kinds(everything))

    def test_the_recent_cap_does_not_hide_a_pin(self):
        closed = [self.closed(f"r{i}", "recent", last=NOW - i) for i in range(12)] + [self.closed("pin", "pinned", last=NOW - 10 ** 6, pinned=True)]
        rows = [r for r in self.rows(closed=closed) if r["kind"] == "closed"]
        self.assertEqual(len(rows), 9)                                                                  # 8 recent + the pin
        self.assertEqual(rows[0]["jkey"], "pin")

    def test_a_pinned_running_agent_leads_the_running_group_and_rows_carry_their_journal_key(self):
        rows = self.rows(windows=[win(6, "working", tab="a"), dict(win(7, "idle", tab="z"), pinned=True, jkey="codex:s")])
        running = [r for r in rows if r["kind"] == "running"]
        self.assertEqual([r["action"]["w"] for r in running], [7, 6])
        self.assertTrue(running[0]["text"].startswith("★"))
        self.assertEqual((running[0]["jkey"], running[0]["pinned"]), ("codex:s", True))

    def test_the_cached_change_summary_shows_on_running_and_event_rows_only_when_there_is_one(self):
        rows = self.rows(events=[ev("e", w=3)], windows=[dict(win(3, "waiting", agent="claude"), changes="7 files +142 −30"), dict(win(6, "idle"), changes="no changes"), win(7, "idle")])
        by = {(r["kind"], r["action"]["w"]): r["text"] for r in rows if r["kind"] in ("event", "running")}
        self.assertIn("Δ 7 files +142 −30", by[("event", 3)])
        self.assertNotIn("Δ", by[("running", 6)])                       # "no changes" is not worth a column
        self.assertNotIn("Δ", by[("running", 7)])

    def test_a_no_approvals_agent_is_marked_in_every_kind_of_row(self):
        risky = ["claude", "--dangerously-skip-permissions"]
        rows = self.rows(events=[ev("e", w=3)], windows=[win(3, "waiting", agent="claude", argv=risky), win(4, "idle", agent="claude", argv=risky), win(5, "idle", agent="codex")],
                         closed=[{"key": "k", "agent": "claude", "last": NOW - 5, "argv": risky}])
        marked = [r["kind"] for r in rows if "no approvals" in r["text"]]
        self.assertEqual(sorted(marked), ["closed", "event", "running"])
        self.assertNotIn("no approvals", [r for r in rows if r["kind"] == "running"][-1]["text"])

    def test_texts_are_unique_single_line_and_survive_hostile_event_text(self):
        evil = "Approve?\n\x1b]0;pwned\x07 <b>x</b>\t" + "A" * 500
        rows = self.rows(events=[ev("a", body=evil), ev("b", body=evil)], windows=[win(9), win(9)])
        texts = [r["text"] for r in rows]
        self.assertEqual(len(texts), len(set(texts)))
        for t in texts:
            self.assertNotIn("\n", t)
        self.assertLess(max(len(t) for t in texts), 400)

    def test_a_hostile_window_title_cannot_forge_rows_shift_indexes_or_spoof_text(self):
        evil = "api\nFAKE ROW  ↺ claude  closed 1m ago\x00icon\x1finfo\x1b[2J\u202e gnp.exe\u200b\u2028x\ue000"
        rows = self.rows(events=[ev("a", body=evil)], windows=[win(9, tab=evil, cwd="/x\ny\x00z", agent="co\nde\x00x")],
                         closed=[{"key": "k", "agent": "claude", "tab": evil, "cwd": evil, "last": NOW - 5}])
        for r in rows:
            for bad in ("\n", "\r", "\x00", "\x1b", "\x1f", "\u202e", "\u200b", "\u2028", "\ue000"):
                self.assertNotIn(bad, r["text"], repr(r["text"]))
        for menu in ("rofi", "fuzzel", "fzf"):
            _argv, stdin = L.menu_command(menu, rows)
            self.assertEqual(stdin.count("\n"), len(rows), menu)        # one line per row: an answer's index is the row's index

    def test_the_menu_boundary_refuses_a_row_that_slipped_through(self):
        for bad in ("a\nb", "a\x00b", "a\u202eb"):
            with self.assertRaises(ValueError):
                L.menu_command("rofi", [{"kind": "x", "text": bad, "action": {}}])

    def test_clean_text(self):
        self.assertEqual(L.clean_text("  a\tb\n c  "), "a b c")
        self.assertEqual(L.clean_text(None), "")
        self.assertEqual(L.clean_text("x" * 500, 10), "x" * 10)
        self.assertEqual(L.clean_text("日本語 ✓ ◆ ⎇"), "日本語 ✓ ◆ ⎇")             # ordinary unicode, symbols and CJK survive

    def test_nothing_at_all_still_offers_new_agents_and_an_empty_machine_does_not_crash(self):
        self.assertEqual(self.kinds(self.rows()), ["new"] * 4)
        self.assertEqual(self.rows(installed=[]), [])


class WaybarTests(unittest.TestCase):
    def test_nothing_unread_is_hidden_needs_you_is_a_diamond_and_finished_a_tick(self):
        self.assertEqual(L.waybar_status([], NOW), {"text": "", "tooltip": "", "class": "idle"})
        self.assertEqual(L.waybar_status([dict(ev("a"), status="read")], NOW)["class"], "idle")
        w = L.waybar_status([ev("a", t=NOW - 600), ev("b", t=NOW - 60), ev("c", sev="info", t=NOW - 5)], NOW)
        self.assertEqual((w["text"], w["class"]), ("◆ 2", "needs-you"))
        self.assertTrue(w["tooltip"].splitlines()[0].startswith("◆ claude"))                       # longest-waiting first
        self.assertIn("(10m)", w["tooltip"].splitlines()[0])
        f = L.waybar_status([ev("c", sev="info")], NOW)
        self.assertEqual((f["text"], f["class"]), ("✓ 1", "unread"))

    def test_terminal_text_cannot_break_the_json_line_or_forge_tooltip_lines(self):
        import json as _json
        w = L.waybar_status([ev("a", body="x\ny\x1b[2J\u202e", tab="t\nFAKE")], NOW)
        self.assertEqual(len(w["tooltip"].splitlines()), 1)
        self.assertEqual(_json.loads(_json.dumps(w, ensure_ascii=False)), w)


class ModeHintTests(unittest.TestCase):
    def test_the_longest_variant_that_fits_and_nothing_when_none_does(self):
        self.assertEqual(L.mode_hint("spawn"), "c x d u o a g  ⇧ split")
        self.assertEqual(L.mode_hint("spawn", 22), "c x d u o a g  ⇧ split")
        self.assertEqual(L.mode_hint("spawn", 21), "c x d u o a g ⇧")
        self.assertEqual(L.mode_hint("spawn", 10), "cxduoag")
        self.assertEqual(L.mode_hint("spawn", 3), "")
        self.assertEqual(L.mode_hint("LEADER", 40), "hjkl cnp saw g ?")
        self.assertEqual([L.mode_hint(m, 40) for m in ("", None, "mystery")], ["", "", ""])           # a mode we have no card for: just its name in the badge


class MenuTests(unittest.TestCase):
    ROWS = [{"kind": "event", "text": "one", "action": {}}, {"kind": "new", "text": "two", "action": {}}, {"kind": "new", "text": "three", "action": {}}]

    def test_commands_are_plain_argv_lists_with_the_rows_on_stdin(self):
        for menu in ("rofi", "fuzzel", "fzf"):
            argv, stdin = L.menu_command(menu, self.ROWS)
            self.assertIsInstance(argv, list)
            self.assertEqual(argv[0], menu)
            self.assertIn("two", stdin)
        self.assertIn("-format", L.menu_command("rofi", self.ROWS)[0])
        with self.assertRaises(ValueError):
            L.menu_command("rm", self.ROWS)

    def test_rofi_index_open_ack_and_cancel(self):
        p = lambda rc, out: L.parse_choice("rofi", self.ROWS, rc, out)           # noqa: E731
        self.assertEqual(p(0, "1\n")[0]["text"], "two")
        self.assertEqual(p(0, "1\n")[1], "open")
        self.assertEqual(p(10, "0\n")[1], "ack")                                   # alt+a
        for bad in ((1, ""), (0, ""), (0, "x"), (0, "7"), (0, "-1"), (130, "0"), (0, "1; rm")):
            self.assertIsNone(p(*bad), bad)

    def test_fuzzel_answers_with_the_text(self):
        p = lambda rc, out: L.parse_choice("fuzzel", self.ROWS, rc, out)         # noqa: E731
        self.assertEqual(p(0, "three\n")[0]["text"], "three")
        self.assertIsNone(p(1, "three"))
        self.assertIsNone(p(0, "not a row"))
        self.assertIsNone(p(0, ""))

    def test_the_pin_and_settle_keys(self):
        r = L.parse_choice("rofi", self.ROWS, 11, "1\n")
        self.assertEqual((r[0]["text"], r[1]), ("two", "pin"))
        self.assertEqual(L.parse_choice("rofi", self.ROWS, 12, "2\n")[1], "settle")
        self.assertIsNone(L.parse_choice("rofi", self.ROWS, 13, "2\n"))                                 # a custom key we did not bind
        self.assertEqual(L.parse_choice("fzf", self.ROWS, 0, "alt-p\n1\ttwo\n")[1], "pin")
        self.assertEqual(L.parse_choice("fzf", self.ROWS, 0, "alt-s\n2\tthree\n")[1], "settle")
        argv = L.menu_command("rofi", self.ROWS)[0]
        self.assertEqual((argv[argv.index("-kb-custom-2") + 1], argv[argv.index("-kb-custom-3") + 1]), ("alt+p", "alt+s"))
        self.assertIn("alt-a,alt-p,alt-s", L.menu_command("fzf", self.ROWS)[0])

    def test_fzf_index_prefix_enter_alt_a_and_cancel(self):
        p = lambda rc, out: L.parse_choice("fzf", self.ROWS, rc, out)            # noqa: E731
        self.assertEqual(p(0, "\n2\tthree\n")[1], "open")                         # --expect: an empty first line is Enter
        self.assertEqual(p(0, "alt-a\n1\ttwo\n")[1], "ack")
        self.assertEqual(p(0, "alt-a\n1\ttwo\n")[0]["text"], "two")
        for bad in ((130, ""), (0, ""), (0, "\n"), (0, "\nx\ty\n"), (0, "\n9\tz\n")):
            self.assertIsNone(p(*bad), bad)


COLORS = {k: "#%06x" % (0x102030 + i * 0x0a0a0a) for i, k in enumerate(("bg", "bar", "surface", "surface_hi", "text", "muted", "faint", "accent", "waiting", "working", "alert"))}


class LookTests(unittest.TestCase):
    MASCOT = os.path.join(ROOT, "assets", "notify", "kittymux.png")

    def test_the_theme_is_built_only_from_the_live_colours_it_is_given(self):
        t = L.rofi_theme(COLORS, self.MASCOT)
        self.assertEqual(t.count("{"), t.count("}"))
        self.assertIn(f'filename: "{self.MASCOT}"', t)
        for v in COLORS.values():
            self.assertIn(v, t)
        for old in ("str:", "imagebox"):                       # rofi 2.0 spells these `content:` and the Icon widget
            self.assertNotIn(old, t)

    def test_no_colour_literal_of_our_own_is_in_the_theme_source(self):
        import inspect
        src = inspect.getsource(L.rofi_theme)
        body = src[src.index('return f"""'):]
        self.assertEqual(__import__("re").findall(r"#[0-9a-fA-F]{6}", body), [])        # every colour is a parameter: nothing hardcoded (the palette follows the kitty theme)

    def test_a_missing_or_malformed_colour_or_path_means_no_theme_so_the_users_own_stays(self):
        self.assertEqual(L.rofi_theme({k: v for k, v in COLORS.items() if k != "accent"}, self.MASCOT), "")
        self.assertEqual(L.rofi_theme(dict(COLORS, bg="red"), self.MASCOT), "")
        self.assertEqual(L.rofi_theme(dict(COLORS, bg="#fff; } window { background: url(x)"), self.MASCOT), "")
        for bad in ('/x"; } * { ', "/x\\y", "/x\ny", ""):
            self.assertEqual(L.rofi_theme(COLORS, bad), "", bad)

    def test_rofis_own_parser_accepts_the_theme(self):
        import shutil
        import subprocess
        import tempfile
        if not shutil.which("rofi"):
            self.skipTest("rofi not installed")
        with tempfile.NamedTemporaryFile("w", suffix=".rasi", delete=False) as f:
            f.write(L.rofi_theme(COLORS, self.MASCOT))
        r = subprocess.run(["rofi", "-theme", f.name, "-dump-theme"], capture_output=True, text=True, timeout=20)
        os.unlink(f.name)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("error", r.stderr.lower())

    def test_icons_come_from_our_directory_by_validated_name_only(self):
        d = os.path.join(ROOT, "assets", "notify")
        self.assertEqual(L.icon_for("claude", d, "FB"), os.path.join(d, "claude.png"))
        self.assertEqual(L.icon_for("cursor", d, "FB"), os.path.join(d, "cursor-agent.png"))          # an alias
        for bad in ("../../etc/passwd", "claude/../../x", "nosuchagent", "", None, "claude\0"):
            self.assertEqual(L.icon_for(bad, d, "FB"), "FB", bad)

    def test_rofi_rows_carry_icon_and_tone_after_the_text_and_other_menus_do_not(self):
        rows = [{"kind": "event", "text": "needs", "agent": "claude", "tone": "urgent", "action": {}},
                {"kind": "new", "text": "plain", "agent": "../x", "tone": "", "action": {}}]
        d = os.path.join(ROOT, "assets", "notify")
        argv, stdin = L.menu_command("rofi", rows, "2 need you", "/t/theme.rasi", d, "/m.png")
        self.assertIn("-show-icons", argv)
        self.assertEqual(argv[argv.index("-theme") + 1], "/t/theme.rasi")
        lines = stdin.split("\n")[:-1]
        self.assertEqual(lines[0], f"needs\0icon\x1f{d}/claude.png\x1furgent\x1ftrue")
        self.assertEqual(lines[1], "plain\0icon\x1f/m.png")                                          # a hostile name falls back to the mascot
        self.assertEqual(len(lines), len(rows))
        for menu in ("fuzzel", "fzf"):
            self.assertNotIn("\0", L.menu_command(menu, rows, "", "/t", d, "/m.png")[1])


if __name__ == "__main__":
    unittest.main()
