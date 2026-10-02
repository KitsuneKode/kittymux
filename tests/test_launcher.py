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
        rows = self.rows(installed=["codex"], closed=[{"key": f"k{i}", "agent": "codex", "last": NOW - i} for i in range(20)])
        self.assertEqual({r["action"]["agent"] for r in rows if r["kind"] == "new"}, {"codex"})
        self.assertEqual(self.kinds(rows).count("closed"), 8)

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

    def test_nothing_at_all_still_offers_new_agents_and_an_empty_machine_does_not_crash(self):
        self.assertEqual(self.kinds(self.rows()), ["new"] * 4)
        self.assertEqual(self.rows(installed=[]), [])


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

    def test_fzf_index_prefix_enter_alt_a_and_cancel(self):
        p = lambda rc, out: L.parse_choice("fzf", self.ROWS, rc, out)            # noqa: E731
        self.assertEqual(p(0, "\n2\tthree\n")[1], "open")                         # --expect: an empty first line is Enter
        self.assertEqual(p(0, "alt-a\n1\ttwo\n")[1], "ack")
        self.assertEqual(p(0, "alt-a\n1\ttwo\n")[0]["text"], "two")
        for bad in ((130, ""), (0, ""), (0, "\n"), (0, "\nx\ty\n"), (0, "\n9\tz\n")):
            self.assertIsNone(p(*bad), bad)


if __name__ == "__main__":
    unittest.main()
