import json
import os
import shlex
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_resume as R  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
AGENTS = R.load_agents(os.path.join(ROOT, "assets", "resume-agents.json"))
SID = "4d4710c8-de7d-4c89-b7d2-c76a51f6fed7"


class DefinitionTests(unittest.TestCase):
    def test_shipped_definitions_are_loadable_and_complete(self):
        for name in ("claude", "codex", "devin", "droid", "opencode", "cursor-agent", "grok", "agy", "gemini", "amp"):
            self.assertIn(name, AGENTS)
        self.assertNotIn("_about", AGENTS)
        for name, d in AGENTS.items():
            self.assertTrue(d.get("exact") or d.get("latest"), name)
            self.assertIn(d.get("latest_scope"), ("directory", "unstated"), name)
            self.assertTrue(d.get("probe", {}).get("expect"), f"{name} has no probe: it could never be verified on a machine")
        for name in ("claude", "codex", "devin", "droid", "opencode", "cursor-agent", "grok", "agy"):
            self.assertTrue(AGENTS[name]["verified"], name)

    def test_user_file_overrides_and_bad_files_are_ignored(self):
        d = tempfile.mkdtemp()
        user = os.path.join(d, "resume.json")
        with open(user, "w") as f:
            json.dump({"grok": {"exact": ["--resume", "{id}"], "probe": {"args": ["--help"], "expect": ["--resume"]}}, "claude": {"latest": ["-c"]}}, f)
        merged = R.load_agents(os.path.join(ROOT, "assets", "resume-agents.json"), user)
        self.assertIn("grok", merged)
        self.assertEqual(merged["claude"], {"latest": ["-c"]})                    # a user entry REPLACES the shipped one
        with open(user, "w") as f:
            f.write("{not json")
        self.assertIn("claude", R.load_agents(os.path.join(ROOT, "assets", "resume-agents.json"), user))
        self.assertEqual(R.load_agents("/nonexistent", None), {})


class ResumeArgvTests(unittest.TestCase):
    def r(self, agent, argv, sid=SID, mode="exact", idx=0):
        return R.resume_argv(AGENTS[agent], argv, sid, mode, idx)

    def test_claude_keeps_the_flags_it_was_started_with(self):
        self.assertEqual(self.r("claude", ["claude", "--dangerously-skip-permissions", "--model", "opus"]),
                         ["claude", "--dangerously-skip-permissions", "--model", "opus", "--resume", SID])

    def test_existing_resume_and_continue_forms_are_not_doubled(self):
        for old in (["--resume", "abc"], ["-r", "abc"], ["--resume=abc"], ["--continue"], ["-c"], ["--session-id", "abc"], ["-r"]):
            self.assertEqual(self.r("claude", ["claude", *old, "--verbose"]), ["claude", "--verbose", "--resume", SID], old)

    def test_a_runtime_in_front_is_preserved(self):
        self.assertEqual(self.r("claude", ["node", "/usr/lib/node_modules/claude/cli.js", "--model", "x"], idx=1),
                         ["node", "/usr/lib/node_modules/claude/cli.js", "--model", "x", "--resume", SID])

    def test_latest_mode_needs_no_id(self):
        self.assertEqual(self.r("claude", ["claude"], sid=None, mode="latest"), ["claude", "--continue"])
        self.assertEqual(self.r("opencode", ["opencode"], sid=None, mode="latest"), ["opencode", "-c"])
        self.assertEqual(self.r("droid", ["droid"], sid=None, mode="latest"), ["droid", "-r", "--last"])

    def test_each_agents_exact_form_matches_its_own_help(self):
        self.assertEqual(self.r("devin", ["devin"]), ["devin", "-r", SID])
        self.assertEqual(self.r("droid", ["droid"]), ["droid", "-r", SID])
        self.assertEqual(self.r("opencode", ["opencode"]), ["opencode", "-s", SID])
        self.assertEqual(self.r("cursor-agent", ["cursor-agent"]), ["cursor-agent", "--resume", SID])
        self.assertEqual(self.r("grok", ["grok", "--worktree=feat"]), ["grok", "--worktree=feat", "--resume", SID])
        self.assertEqual(self.r("agy", ["agy", "--model", "x"]), ["agy", "--model", "x", "--conversation", SID])
        self.assertEqual(self.r("grok", ["grok", "-s", "newuuid", "--fork-session"]), ["grok", "--resume", SID])      # flags that start a NEW session are dropped
        self.assertEqual(self.r("grok", ["grok"], sid=None, mode="latest"), ["grok", "--continue"])
        self.assertEqual(self.r("agy", ["agy"], sid=None, mode="latest"), ["agy", "--continue"])

    def test_subcommand_agents_resume_after_their_flags_and_refuse_other_subcommands(self):
        self.assertEqual(self.r("codex", ["codex"]), ["codex", "resume", SID])
        self.assertEqual(self.r("codex", ["codex", "--search"]), ["codex", "--search", "resume", SID])
        self.assertIsNone(self.r("codex", ["codex", "exec", "fix the tests"]))
        self.assertIsNone(self.r("codex", ["codex", "do something"]))             # a prompt argument: never replay it
        self.assertEqual(self.r("codex", ["codex"], sid=None, mode="latest"), ["codex", "resume", "--last"])

    def test_a_hostile_session_id_is_refused_and_the_result_is_one_argv_token(self):
        for bad in ("x; rm -rf ~", "$(id)", "a b", "--help", "", None, "x" * 300):
            self.assertIsNone(self.r("claude", ["claude"], sid=bad), bad)
        out = self.r("claude", ["claude"], sid="abc-123_x.y:z")
        self.assertEqual(out[-1], "abc-123_x.y:z")

    def test_unknown_mode_or_empty_argv(self):
        self.assertIsNone(self.r("claude", ["claude"], mode="bogus"))
        self.assertIsNone(R.resume_argv(AGENTS["claude"], [], SID, "exact"))
        self.assertIsNone(self.r("gemini", ["gemini"], mode="exact"))              # no exact form defined: never invent one


class DetectionTests(unittest.TestCase):
    def test_names_runtimes_and_helpers(self):
        self.assertEqual(R.agent_of(AGENTS, ["/home/u/.local/bin/claude", "--x"]), ("claude", 0))
        self.assertEqual(R.agent_of(AGENTS, ["node", "/opt/x/codex", "--y"]), ("codex", 1))
        self.assertEqual(R.agent_of(AGENTS, ["cursor"]), ("cursor-agent", 0))      # alias
        self.assertEqual(R.agent_of(AGENTS, ["antigravity"]), ("agy", 0))
        self.assertIsNone(R.agent_of(AGENTS, ["grok", "doctor"]))                  # a grok subcommand is not the interactive agent
        self.assertIsNone(R.agent_of(AGENTS, ["/home/u/.local/share/devin/cli/bin/devin", "acp"]))   # its helper process
        self.assertIsNone(R.agent_of(AGENTS, ["codex", "app-server"]))
        self.assertIsNone(R.agent_of(AGENTS, ["zsh"]))
        self.assertIsNone(R.agent_of(AGENTS, ["python3", "/x/not_an_agent.py"]))
        self.assertIsNone(R.agent_of(AGENTS, []))


def fake_proc(root, pid, start="777", fds=()):
    os.makedirs(os.path.join(root, str(pid), "fd"), exist_ok=True)
    with open(os.path.join(root, str(pid), "stat"), "w") as f:
        f.write("%d (claude) S 1 1 1 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 %s 0 0\n" % (pid, start))
    for i, target in enumerate(fds):
        os.symlink(target, os.path.join(root, str(pid), "fd", str(i + 3)))


class SessionIdTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.home, self.proc = os.path.join(self.d, "claude"), os.path.join(self.d, "proc")
        os.makedirs(os.path.join(self.home, "sessions"))
        fake_proc(self.proc, 4242, start="777")

    def reg(self, pid=4242, **kw):
        d = {"pid": pid, "sessionId": SID, "cwd": "/w", "procStart": 777, "status": "busy", "name": "n"}
        d.update(kw)
        with open(os.path.join(self.home, "sessions", f"{pid}.json"), "w") as f:
            json.dump(d, f)

    def test_claude_registry_valid(self):
        self.reg()
        self.assertEqual(R.claude_session(self.home, 4242, self.proc), {"id": SID, "cwd": "/w", "status": "busy", "name": "n"})

    def test_a_reused_pid_a_wrong_pid_and_a_bad_id_are_refused(self):
        self.reg(procStart=999)
        self.assertIsNone(R.claude_session(self.home, 4242, self.proc))            # a different process with the same pid
        self.reg(pid=1)
        self.assertIsNone(R.claude_session(self.home, 4242, self.proc))            # the file claims another pid
        self.reg(sessionId="not-a-uuid; rm -rf")
        self.assertIsNone(R.claude_session(self.home, 4242, self.proc))
        self.assertIsNone(R.claude_session(self.home, 31337, self.proc))           # no file
        with open(os.path.join(self.home, "sessions", "4242.json"), "w") as f:
            f.write("{broken")
        self.assertIsNone(R.claude_session(self.home, 4242, self.proc))

    def test_a_missing_start_time_does_not_block_a_valid_file(self):
        self.reg()
        self.assertEqual(R.claude_session(self.home, 4242, os.path.join(self.d, "noproc"))["id"], SID)

    def test_open_files_name_the_session(self):
        fake_proc(self.proc, 5001, fds=["/home/u/.codex/sessions/2026/10/02/rollout-2026-10-02T11-52-03-01a0fb46-e943-7081-8553-993e0c7f1f38.jsonl", "/dev/null"])
        pat = AGENTS["codex"]["open_file_pattern"]
        self.assertEqual(R.open_session_ids([5001], pat, self.proc), ["01a0fb46-e943-7081-8553-993e0c7f1f38"])
        self.assertEqual(R.open_session_ids([4242, 9999], pat, self.proc), [])


def win(wid, cwd, *procs):
    return {"id": wid, "cwd": cwd, "fg": [{"pid": p, "cmdline": c} for p, c in procs]}


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.home, self.proc = os.path.join(self.d, "c"), os.path.join(self.d, "p")
        os.makedirs(os.path.join(self.home, "sessions"))
        fake_proc(self.proc, 100)

    def plan(self, windows, **kw):
        return {e["id"]: e for e in R.build_plan(windows, AGENTS, self.home, self.proc, **kw)}

    def test_exact_latest_and_ambiguous(self):
        with open(os.path.join(self.home, "sessions", "100.json"), "w") as f:
            json.dump({"pid": 100, "sessionId": SID, "cwd": "/a", "procStart": 777}, f)
        plan = self.plan([win(1, "/a", (100, ["claude", "--model", "x"])), win(2, "/b", (200, ["opencode"])),
                          win(3, "/c", (301, ["droid"])), win(4, "/c", (302, ["droid"])), win(5, "/d", (400, ["zsh"]))])
        self.assertEqual((plan[1]["mode"], plan[1]["resume"]), ("exact", ["claude", "--model", "x", "--resume", SID]))
        self.assertEqual((plan[2]["mode"], plan[2]["resume"]), ("latest", ["opencode", "-c"]))     # the only opencode window: allowed
        for wid in (3, 4):                                                          # two droids in one directory: never open one session twice
            self.assertEqual((plan[wid]["mode"], plan[wid]["resume"]), ("none", None))
            self.assertIn("several droid windows", plan[wid]["why"])
        self.assertNotIn(5, plan)                                                   # not an agent

    def test_latest_scope_decides_when_continue_latest_is_safe(self):
        # claude/codex/droid document directory scope: one per directory is enough. devin/opencode/cursor-agent do not: only when it is the single window.
        plan = self.plan([win(1, "/a", (1, ["opencode"])), win(2, "/b", (2, ["opencode"])), win(3, "/a", (3, ["devin"])), win(4, "/b", (4, ["claude"])),
                          win(5, "/c", (5, ["claude"]))])
        for wid in (1, 2):
            self.assertIsNone(plan[wid]["resume"])
            self.assertIn("not documented as per-directory", plan[wid]["why"])
        self.assertEqual(plan[3]["mode"], "latest")
        self.assertIn("does not say whether", plan[3]["why"])
        for wid in (4, 5):                                                           # two claudes in DIFFERENT directories: each is unambiguous
            self.assertEqual(plan[wid]["mode"], "latest")

    def test_a_disabled_agent_is_left_alone_with_the_reason(self):
        plan = self.plan([win(1, "/a", (1, ["devin"]))], enabled=lambda name: name != "devin")
        self.assertIsNone(plan[1]["resume"])
        self.assertIn("kittymux sessions check", plan[1]["why"])

    def test_the_helper_process_is_not_mistaken_for_the_agent(self):
        plan = self.plan([win(1, "/a", (10, ["/x/devin", "acp"]), (11, ["devin"]))])
        self.assertEqual(plan[1]["pid"], 11)


NATIVE = '''
new_tab alpha
layout splits
set_layout_state {"pairs": {"one": 1, "two": 2}}
cd proj

launch 'kitty-unserialize-data={"id": 1}' --var=kittymux_status=working --var=kittymux_msg='Allow rm?' --title=one /usr/bin/sh
focus
launch 'kitty-unserialize-data={"id": 2}' --cwd=/work/my\\ project --var=kittymux_status=waiting --title=two /usr/bin/claude --dangerously-skip-permissions

new_tab beta
launch 'kitty-unserialize-data={"id": 3}' --title=three /home/u/.bun/bin/codex
focus_tab 0
'''


class RewriteTests(unittest.TestCase):
    def plan(self):
        return [{"id": 2, "agent": "claude", "argv": ["/usr/bin/claude", "--dangerously-skip-permissions"],
                 "resume": ["/usr/bin/claude", "--dangerously-skip-permissions", "--resume", SID]},
                {"id": 3, "agent": "codex", "argv": ["/home/u/.bun/bin/codex"], "resume": ["/home/u/.bun/bin/codex", "resume", SID]}]

    def test_agent_lines_resume_and_everything_else_is_untouched(self):
        out, report = R.rewrite_with_plan(NATIVE, self.plan())
        lines = out.splitlines()
        claude = next(l for l in lines if '"id": 2' in l)
        toks = shlex.split(claude)
        self.assertEqual(toks[toks.index("/usr/bin/claude"):], ["/usr/bin/claude", "--dangerously-skip-permissions", "--resume", SID])
        self.assertIn("--cwd=/work/my project", toks)                                # options survive, quoting intact
        self.assertIn("--title=two", toks)
        self.assertEqual(shlex.split(next(l for l in lines if '"id": 3' in l))[-3:], ["/home/u/.bun/bin/codex", "resume", SID])
        self.assertEqual([l for l in NATIVE.splitlines() if not l.startswith("launch")], [l for l in lines if not l.startswith("launch")])
        self.assertEqual(len(report), 2)

    def test_restored_hook_state_is_stripped_from_every_line(self):
        out, _ = R.rewrite_with_plan(NATIVE, self.plan())
        self.assertNotIn("kittymux_status", out)
        self.assertNotIn("kittymux_msg", out)
        shell_line = next(l for l in out.splitlines() if '"id": 1' in l)
        self.assertEqual(shlex.split(shell_line)[-1], "/usr/bin/sh")               # a plain shell window is otherwise unchanged

    def test_a_stale_plan_cannot_rewrite_the_wrong_window(self):
        plan = [{"id": 1, "agent": "claude", "argv": ["/usr/bin/claude"], "resume": ["/usr/bin/claude", "--resume", SID]}]   # id 1 is a shell here
        out, report = R.rewrite_with_plan(NATIVE, plan)
        self.assertEqual(report, [])
        self.assertNotIn("--resume", out)

    def test_idempotent_and_newline_preserving(self):
        once, _ = R.rewrite_with_plan(NATIVE, self.plan())
        twice, _ = R.rewrite_with_plan(once, self.plan())
        self.assertEqual(once, twice)
        self.assertTrue(once.endswith("\n"))
        self.assertEqual(R.rewrite_with_plan("", [])[0], "")

    def test_unparseable_lines_pass_through(self):
        text = "launch 'unterminated\nnew_tab x\n"
        self.assertEqual(R.rewrite_with_plan(text, self.plan())[0], text)


SELF_DESCRIBING = '''
new_tab a
launch 'kitty-unserialize-data={"id": 7}' --var=kittymux_agent=claude --var=kittymux_sid=%s --var=kittymux_resume=exact --var=kittymux_status=working --title=one /home/u/.local/bin/claude --model opus
launch 'kitty-unserialize-data={"id": 8}' --var=kittymux_resume=latest --title=two /usr/bin/opencode
launch 'kitty-unserialize-data={"id": 9}' --var=kittymux_resume=latest --title=amb /usr/bin/droid
launch 'kitty-unserialize-data={"id": 10}' --var=kittymux_resume=none --title=none /usr/bin/devin
launch 'kitty-unserialize-data={"id": 11}' --var=kittymux_resume=exact --var=kittymux_sid='x; rm -rf ~' /home/u/.bun/bin/codex
launch 'kitty-unserialize-data={"id": 12}' --title=shell /usr/bin/zsh
''' % SID


class SelfDescribingRewriteTests(unittest.TestCase):
    def rewrite(self, **kw):
        return R.rewrite_session(SELF_DESCRIBING, AGENTS, **kw)

    def line(self, out, wid):
        return shlex.split(next(l for l in out.splitlines() if f'"id": {wid}' in l))

    def test_exact_latest_and_untouched(self):
        out, report = self.rewrite()
        self.assertEqual(self.line(out, 7)[-5:], ["/home/u/.local/bin/claude", "--model", "opus", "--resume", SID])
        self.assertEqual(self.line(out, 8)[-2:], ["/usr/bin/opencode", "-c"])
        self.assertEqual(self.line(out, 9)[-3:], ["/usr/bin/droid", "-r", "--last"])
        self.assertEqual(self.line(out, 10)[-1], "/usr/bin/devin")                  # mode none: restored as saved
        self.assertEqual(self.line(out, 12)[-1], "/usr/bin/zsh")
        self.assertEqual(len(report), 3)

    def test_a_hostile_id_in_the_file_is_never_turned_into_a_command(self):
        out, _ = self.rewrite()
        self.assertEqual(self.line(out, 11)[-1], "/home/u/.bun/bin/codex")           # refused: restored as saved
        self.assertNotIn("rm -rf", " ".join(self.line(out, 11)[self.line(out, 11).index("/home/u/.bun/bin/codex"):]))

    def test_stale_hook_state_is_stripped_and_our_vars_are_kept(self):
        out, _ = self.rewrite()
        self.assertNotIn("kittymux_status", out)
        self.assertIn("--var=kittymux_sid=" + SID, self.line(out, 7))

    def test_a_disabled_agent_is_not_rewritten(self):
        out, report = self.rewrite(enabled=lambda name: name != "claude")
        self.assertEqual(self.line(out, 7)[-3:], ["/home/u/.local/bin/claude", "--model", "opus"])
        self.assertEqual(len(report), 2)

    def test_idempotent(self):
        once, _ = self.rewrite()
        twice, _ = R.rewrite_session(once, AGENTS)
        self.assertEqual(once, twice)


class TemplateTests(unittest.TestCase):
    def test_placeholders_and_quoting(self):
        out = R.render_template("cd @Q:CWD@\nnew_tab @NAME@\nlaunch @Q:AGENT@ @UNKNOWN@\n", {"CWD": "/w/my project's", "NAME": "api", "AGENT": "claude"})
        self.assertEqual(shlex.split(out.splitlines()[0]), ["cd", "/w/my project's"])
        self.assertIn("new_tab api", out)
        self.assertIn("@UNKNOWN@", out)                                              # an unknown placeholder is left visible, never silently empty


if __name__ == "__main__":
    unittest.main()
