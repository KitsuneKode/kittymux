import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_agents as A  # noqa: E402


class AgentTests(unittest.TestCase):
    def test_finds_agent_by_basename(self):
        self.assertEqual(A.agent_in(["/usr/bin/node", "/home/u/.local/bin/claude"]), "claude")

    def test_none_for_shell(self):
        self.assertIsNone(A.agent_in(["zsh"]))

    def test_case_insensitive(self):
        self.assertEqual(A.agent_in(["/opt/Codex"]), "codex")

    def test_brands_are_rgb_ints(self):
        for name, agent in A.AGENTS.items():
            self.assertTrue(0 <= agent.brand <= 0xFFFFFF, name)
            self.assertTrue(agent.glyph, name)


class ResolveStatusTests(unittest.TestCase):
    NOW = 1000.0

    def test_no_agent_is_blank_even_with_status(self):
        self.assertEqual(A.resolve_status({"status": "working"}, False, self.NOW), "")

    def test_explicit_beats_fresh_title(self):
        self.assertEqual(A.resolve_status({"status": "waiting", "ts_title": self.NOW - 1}, True, self.NOW), "waiting")

    def test_explicit_done_and_idle(self):
        self.assertEqual(A.resolve_status({"status": "done"}, True, self.NOW), "done")
        self.assertEqual(A.resolve_status({"status": "idle"}, True, self.NOW), "idle")

    def test_unknown_explicit_falls_back(self):
        self.assertEqual(A.resolve_status({"status": "bogus", "ts_title": self.NOW - 1}, True, self.NOW), "working")

    def test_missing_entry_is_idle_not_working(self):
        self.assertEqual(A.resolve_status(None, True, self.NOW), "idle")      # no evidence, no claim

    def test_quiet_title_is_never_waiting(self):
        self.assertEqual(A.resolve_status({"ts_title": self.NOW - 16}, True, self.NOW), "idle")
        self.assertEqual(A.resolve_status({"ts_title": self.NOW - 600}, True, self.NOW), "idle")

    def test_fresh_title_is_working(self):
        self.assertEqual(A.resolve_status({"ts_title": self.NOW - 3}, True, self.NOW), "working")

    def test_zero_title_ts_is_idle(self):
        self.assertEqual(A.resolve_status({"ts_title": 0}, True, self.NOW), "idle")

    def test_fresh_scanner_verdict_beats_hooks_and_titles(self):
        e = {"state": "working", "ts_scan": self.NOW - 1, "status": "waiting", "ts_title": self.NOW - 99}
        self.assertEqual(A.resolve_status(e, True, self.NOW), "working")

    def test_stale_scanner_verdict_is_ignored(self):
        e = {"state": "working", "ts_scan": self.NOW - 60, "status": "waiting"}
        self.assertEqual(A.resolve_status(e, True, self.NOW), "waiting")      # degrade to the hook

    def test_limited_is_a_state_and_needs_you(self):
        e = {"state": "limited", "ts_scan": self.NOW}
        self.assertEqual(A.resolve_status(e, True, self.NOW), "limited")
        self.assertIn("limited", A.NEEDS_YOU)
        self.assertIn("waiting", A.NEEDS_YOU)
        self.assertNotIn("working", A.NEEDS_YOU)

    def test_scanner_verdict_without_agent_is_blank(self):
        self.assertEqual(A.resolve_status({"state": "working", "ts_scan": self.NOW}, False, self.NOW), "")


class MergeScanTests(unittest.TestCase):
    def test_merges_verdicts_into_hook_entries(self):
        panes = {"7": {"status": "waiting", "msg": "x"}}
        scan = {"7": {"state": "working", "reason": "", "ts_scan": 5.0, "ts_state": 4.0},
                "9": {"state": "idle", "ts_scan": 5.0}}
        out = A.merge_scan(panes, scan)
        self.assertEqual(out["7"]["status"], "waiting")
        self.assertEqual(out["7"]["state"], "working")
        self.assertEqual(out["9"]["state"], "idle")
        self.assertNotIn("state", panes["7"])                                  # inputs untouched

    def test_garbage_is_ignored(self):
        self.assertEqual(A.merge_scan(None, None), {})
        self.assertEqual(A.merge_scan({"1": "junk"}, {"2": 5}), {})

    def test_load_panes_reads_sibling_scan_file(self):
        import json, tempfile
        d = tempfile.mkdtemp()
        json.dump({"3": {"status": "done"}}, open(os.path.join(d, "panes-42.json"), "w"))
        json.dump({"3": {"state": "idle", "ts_scan": 1.0}}, open(os.path.join(d, "scan-42.json"), "w"))
        out = A.load_panes(os.path.join(d, "panes-42.json"))
        self.assertEqual((out["3"]["status"], out["3"]["state"]), ("done", "idle"))
        self.assertEqual(A.load_panes(os.path.join(d, "panes-nope.json")), {})


class AgentTableTests(unittest.TestCase):
    def test_antigravity_is_recognised_by_both_names(self):
        self.assertEqual(A.agent_in(["/home/u/.local/bin/agy"]), "agy")
        self.assertEqual(A.agent_in(["node", "/opt/antigravity/bin/antigravity"]), "antigravity")
        self.assertEqual(A.AGENTS["agy"], A.AGENTS["antigravity"])

    def test_every_agent_with_a_pua_glyph_is_in_the_icon_font(self):
        import re
        src = open(os.path.join(os.path.dirname(__file__), "..", "tools", "build-icons.py"), encoding="utf-8").read()
        count = len(re.findall(r"\(0x10EA[0-9A-F]{2}, ", src))
        bmp = {ord(a.glyph) for a in A.AGENTS.values() if len(a.glyph) == 1 and 0xE0D8 <= ord(a.glyph) <= 0xE1FF}
        self.assertTrue(bmp)
        self.assertLessEqual(max(bmp) - 0xE0D8, count - 1)                    # every glyph has an icon behind it


class MsgTests(unittest.TestCase):
    def test_msg_only_for_waiting_limited_and_done(self):
        e = {"msg": "needs approval"}
        self.assertEqual(A.resolve_msg(e, "waiting"), "needs approval")
        self.assertEqual(A.resolve_msg(e, "done"), "needs approval")
        self.assertEqual(A.resolve_msg(e, "limited"), "needs approval")
        self.assertEqual(A.resolve_msg(e, "working"), "")
        self.assertEqual(A.resolve_msg(e, ""), "")

    def test_missing(self):
        self.assertEqual(A.resolve_msg(None, "waiting"), "")

    def test_screen_reason_fills_in_when_no_hook_message(self):
        e = {"reason": "Do you want to proceed?"}
        self.assertEqual(A.resolve_msg(e, "waiting"), "Do you want to proceed?")
        self.assertEqual(A.resolve_msg(e, "done"), "")                         # a finished agent has no open question
        self.assertEqual(A.resolve_msg({"msg": "hook says", "reason": "screen says"}, "waiting"), "hook says")

    def test_state_glyphs_distinct(self):
        self.assertEqual(len(set(A.STATE_GLYPH.values())), len(A.STATE_GLYPH))


class SpinnerTests(unittest.TestCase):
    def test_working_animates_through_all_frames(self):
        frames = {A.state_glyph("working", t / A.SPINNER_FPS) for t in range(len(A.SPINNER))}
        self.assertEqual(frames, set(A.SPINNER))

    def test_frame_is_a_pure_function_of_time(self):
        self.assertEqual(A.state_glyph("working", 3.14), A.state_glyph("working", 3.14))

    def test_static_states(self):
        self.assertEqual(A.state_glyph("waiting"), "!")
        self.assertEqual(A.state_glyph("done"), "✓")
        self.assertEqual(A.state_glyph("unread"), "•")
        self.assertEqual(A.state_glyph(""), "")
        self.assertEqual(A.state_glyph("idle"), "")

    def test_spinner_uses_braille_block(self):
        self.assertTrue(all(0x2800 <= ord(c) <= 0x28FF for c in A.SPINNER))


class ToolTests(unittest.TestCase):
    def test_plain_shell_has_no_glyph(self):
        self.assertIsNone(A.tool_in([["zsh"], ["-zsh"]]))

    def test_editor_wins_over_node_child(self):
        self.assertEqual(A.tool_in([["node", "x.js"], ["nvim", "a.py"]]), "nvim")

    def test_only_program_counts_not_arguments(self):
        self.assertEqual(A.tool_in([["git", "commit", "-m", "vim"]]), "git")
        self.assertIsNone(A.tool_in([["zsh", "-c", "echo nvim"]]))

    def test_wrapper_separator(self):
        self.assertEqual(A.tool_in([["zsh", "/x/trmw", "--profile", "font", "--", "nvim", "f"]]), "nvim")

    def test_env_sudo_wrappers(self):
        self.assertEqual(A.tool_in([["sudo", "-E", "htop"]]) or A.tool_in([["sudo", "htop"]]), "htop")
        self.assertEqual(A.tool_in([["env", "docker", "ps"]]), "docker")

    def test_full_paths_and_case(self):
        self.assertEqual(A.tool_in([["/usr/bin/SSH", "host"]]), "ssh")

    def test_all_glyphs_are_single_codepoints_in_nerd_ranges(self):
        for name, glyph in A.TOOLS.items():
            self.assertEqual(len(glyph), 1, name)
            cp = ord(glyph)
            self.assertTrue(0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD, f"{name} U+{cp:X}")

    def test_agents_and_tools_dont_collide(self):
        self.assertFalse(set(A.TOOLS) & set(A.AGENTS))


class SanitizeTests(unittest.TestCase):
    def test_control_and_escape_sequences_neutralised(self):
        evil = "ok\x1b[2J\x1b]0;pwned\x07\x9b31m\r\nnext\x00"
        out = A.sanitize_text(evil)
        self.assertFalse(any(ord(c) < 32 or ord(c) == 127 or 0x80 <= ord(c) < 0xA0 for c in out))
        self.assertIn("ok", out)

    def test_bounded_and_single_line(self):
        self.assertEqual(len(A.sanitize_text("x" * 500)), 120)
        self.assertNotIn("\n", A.sanitize_text("a\nb\tc"))

    def test_resolve_msg_applies_it(self):
        self.assertEqual(A.resolve_msg({"msg": "hi\x1b[31m"}, "waiting"), "hi [31m")

    def test_printable_unicode_survives(self):
        self.assertEqual(A.sanitize_text("Approve: rm -rf node_modules? ✓ 日本"), "Approve: rm -rf node_modules? ✓ 日本")


class TabVerdictTests(unittest.TestCase):
    NOW = 1000.0

    def panes(self, **states):
        return {wid: {"state": st, "ts_scan": self.NOW - 1.0} for wid, st in states.items()}

    def test_a_question_in_a_background_split_lights_the_tab(self):
        panes = self.panes(**{"1": "idle", "2": "waiting"})
        self.assertEqual(A.tab_verdict(panes, [1, 2], 1, True, self.NOW), ("waiting", "2"))

    def test_most_important_state_wins(self):
        panes = self.panes(**{"1": "working", "2": "done", "3": "limited"})
        self.assertEqual(A.tab_verdict(panes, [1, 2, 3], 1, True, self.NOW), ("limited", "3"))

    def test_active_pane_wins_ties(self):
        panes = self.panes(**{"1": "waiting", "2": "waiting"})
        self.assertEqual(A.tab_verdict(panes, [2, 1], 1, True, self.NOW), ("waiting", "1"))

    def test_stale_background_verdicts_are_ignored(self):
        panes = {"1": {"state": "idle", "ts_scan": self.NOW - 1}, "2": {"state": "waiting", "ts_scan": self.NOW - 60}}
        self.assertEqual(A.tab_verdict(panes, [1, 2], 1, True, self.NOW)[0], "idle")

    def test_active_shell_with_agent_elsewhere_shows_the_agent(self):
        panes = self.panes(**{"2": "working"})
        self.assertEqual(A.tab_verdict(panes, [1, 2], 1, False, self.NOW), ("working", "2"))

    def test_no_agents_means_no_state(self):
        self.assertEqual(A.tab_verdict({}, [1, 2], 1, False, self.NOW), ("", ""))


class TitlePrefixTests(unittest.TestCase):
    def test_status_icons_in_front_of_a_title_are_dropped(self):
        for raw, want in (("⛬ New Session", "New Session"), ("⠋ Thinking", "Thinking"), ("✳ Claude Code", "Claude Code"),
                          ("plain title", "plain title"), ("", "")):
            self.assertEqual(A.strip_title_prefix(raw), want)


class StrictNamesTests(unittest.TestCase):
    def test_short_common_names_only_match_where_a_command_goes(self):
        self.assertEqual(A.agent_in(["kilo"]), "kilo")
        self.assertEqual(A.agent_in(["/home/u/.local/bin/droid", "--resume"]), "droid")
        self.assertEqual(A.agent_in(["node", "/usr/lib/node_modules/@factory/cli/bin/droid"]), "droid")
        self.assertEqual(A.agent_in(["bash", "/opt/vibe"]), "vibe")
        for argv in (["nvim", "vibe"], ["cat", "goose"], ["ls", "kimi"], ["node", "server.js", "kilo"], ["man", "droid"]):
            self.assertIsNone(A.agent_in(argv), argv)

    def test_every_known_agent_has_a_distinct_glyph_or_a_plain_symbol(self):
        glyphs = [a.glyph for n, a in A.AGENTS.items() if n not in ("agy", "antigravity", "cursor", "cursor-agent")]
        self.assertEqual(len(glyphs), len(set(glyphs)))


if __name__ == "__main__":
    unittest.main()
