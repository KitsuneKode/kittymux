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


class AgentIdentityTests(unittest.TestCase):
    """What each agent exposes about a running window — verified against the real CLIs/data on a live machine (docs/sessions.md): Devin's session lock names
    its session, an id on the command line is the conversation it was started on, and agy / Cursor / opencode only expose "latest in this directory"."""
    TICKS = 100                                   # the fake process started 1 s after boot

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.proc, self.home = os.path.join(self.d, "proc"), os.path.join(self.d, "home")
        os.makedirs(self.home)
        os.makedirs(self.proc, exist_ok=True)
        with open(os.path.join(self.proc, "stat"), "w") as f:
            f.write("cpu 1 2 3\nbtime 1000000\n")
        self.started = 1000000 + self.TICKS / os.sysconf("SC_CLK_TCK")

    def touch(self, path, when):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("x")
        os.utime(path, (when, when))

    # ids on the command line
    def test_an_id_on_the_command_line_is_the_conversation_the_window_was_started_on(self):
        f = R.argv_session_id
        self.assertEqual(f(AGENTS["opencode"], ["opencode", "-s", "ses_fc7aa6d21ffeml3zCp99jR7fyd"]), "ses_fc7aa6d21ffeml3zCp99jR7fyd")
        self.assertEqual(f(AGENTS["agy"], ["agy", "--conversation=c6941cdb-3241-484a-b39f-4fd92ebd1382"]), "c6941cdb-3241-484a-b39f-4fd92ebd1382")
        self.assertEqual(f(AGENTS["cursor-agent"], ["cursor-agent", "--model", "x", "--resume", "375db6e9-2e3a-47c3-925c-8566208428a7"]), "375db6e9-2e3a-47c3-925c-8566208428a7")
        self.assertIsNone(f(AGENTS["devin"], ["devin", "-r"]))                           # the picker, not an id
        self.assertIsNone(f(AGENTS["devin"], ["devin", "-r", "--model", "x"]))
        self.assertIsNone(f(AGENTS["opencode"], ["opencode", "-s", "-c"]))
        self.assertIsNone(f(AGENTS["opencode"], ["opencode", "-s", "x; rm -rf ~"]))        # not a plain token

    # Devin: the session lock a running window holds names the session
    def test_devins_session_lock_names_its_session_and_the_pattern_ignores_other_files(self):
        pat = AGENTS["devin"]["open_file_pattern"]
        fake_proc(self.proc, 2555541, fds=["/home/u/.local/share/devin/cli/session_locks/tall-yogurt.lock", "/home/u/.local/share/devin/cli/sessions.db"])
        self.assertEqual(R.open_session_ids([2555541], pat, self.proc), ["tall-yogurt"])
        fake_proc(self.proc, 2, fds=["/home/u/.local/share/devin/cli/session_locks/-evil.lock", "/x/session_locks/a/b.lock"])
        self.assertEqual(R.open_session_ids([2], pat, self.proc), [])

    def test_a_devin_window_resolves_through_its_acp_childs_lock_and_resumes_by_name(self):
        fake_proc(self.proc, 100, start="100")
        fake_proc(self.proc, 101, fds=["/h/.local/share/devin/cli/session_locks/tall-yogurt.lock"])
        plan = R.build_plan([win(3, "/w", (100, ["devin", "-r"]), (101, ["/h/.local/share/devin/cli/_versions/3000.11.3/bin/devin", "acp"]))], AGENTS, self.home, self.proc)
        self.assertEqual((plan[0]["mode"], plan[0]["session_id"], plan[0]["resume"]), ("exact", "tall-yogurt", ["devin", "-r", "tall-yogurt"]))
        ident = R.identify(AGENTS, [{"pid": 100, "cmdline": ["devin", "-r"]}, {"pid": 101, "cmdline": ["devin", "acp"]}], self.home, self.proc)
        self.assertEqual(ident["sid"], "tall-yogurt")

    def test_two_devin_windows_each_get_their_own_session(self):
        for pid, name in ((100, "tall-yogurt"), (200, "admitted-cattle")):
            fake_proc(self.proc, pid, start="100")
            fake_proc(self.proc, pid + 1, fds=[f"/h/devin/cli/session_locks/{name}.lock"])
        plan = R.build_plan([win(3, "/w", (100, ["devin", "-r"]), (101, ["devin", "acp"])), win(4, "/w", (200, ["devin", "-r"]), (201, ["devin", "acp"]))], AGENTS, self.home, self.proc)
        self.assertEqual([e["session_id"] for e in plan], ["tall-yogurt", "admitted-cattle"])      # same directory: still exact, never opened twice

    # touched-since-start
    def test_proc_start_epoch(self):
        fake_proc(self.proc, 7, start=str(self.TICKS))
        self.assertAlmostEqual(R.proc_start_epoch(7, self.proc), self.started)
        self.assertIsNone(R.proc_start_epoch(99, self.proc))

    def test_agy_resumes_the_directorys_last_conversation_only_if_this_run_touched_it(self):
        base = os.path.join(self.home, ".gemini", "antigravity-cli")
        cid = "c6941cdb-3241-484a-b39f-4fd92ebd1382"
        os.makedirs(os.path.join(base, "cache"))
        with open(os.path.join(base, "cache", "last_conversations.json"), "w") as f:
            json.dump({"/w": cid, "/other": "not-a-uuid"}, f)
        self.touch(os.path.join(base, "conversations", cid + ".db"), self.started - 3600)           # an old conversation
        self.assertEqual(R.dir_latest("agy-last", "/w", self.started, self.home), (None, "none"))
        self.touch(os.path.join(base, "conversations", cid + ".db-wal"), self.started + 60)          # written to since: it is this window's
        self.assertEqual(R.dir_latest("agy-last", "/w", self.started, self.home), (cid, "found"))
        self.assertEqual(R.dir_latest("agy-last", "/other", self.started, self.home), (None, "none"))  # a corrupt id is never used
        self.assertEqual(R.dir_latest("agy-last", "/nowhere", self.started, self.home), (None, "none"))
        self.assertEqual(R.dir_latest("agy-last", "/w", None, self.home), (None, "unknown"))          # unknown start time: do not guess

    def test_cursor_chats_are_found_by_the_md5_of_the_directory(self):
        import hashlib
        root = os.path.join(self.home, ".config", "cursor", "chats", hashlib.md5(b"/w").hexdigest())
        a, b = "375db6e9-2e3a-47c3-925c-8566208428a7", "48fe3a73-0fbc-4fab-ba7d-1ab365f6e897"
        self.touch(os.path.join(root, a, "store.db"), self.started - 500)
        self.touch(os.path.join(root, b, "store.db"), self.started + 30)
        os.makedirs(os.path.join(root, "../../not-a-uuid"), exist_ok=True)
        self.assertEqual(R.dir_latest("cursor-chats", "/w", self.started, self.home), (b, "found"))   # the newest, touched since start
        os.utime(os.path.join(root, b, "store.db"), (self.started - 10, self.started - 10))
        self.assertEqual(R.dir_latest("cursor-chats", "/w", self.started, self.home), (None, "none"))
        self.assertEqual(R.dir_latest("cursor-chats", "/elsewhere", self.started, self.home), (None, "none"))

    def test_opencode_asks_its_own_cli_and_checks_directory_and_time(self):
        rows = [{"id": "ses_new", "updated": (self.started + 5) * 1000, "directory": "/w"}, {"id": "ses_old", "updated": (self.started - 99) * 1000, "directory": "/w"}]
        seen = []
        run = lambda argv, cwd: (seen.append((argv, cwd)), json.dumps(rows))[1]                   # noqa: E731
        self.assertEqual(R.dir_latest("opencode-list", "/w", self.started, self.home, run), ("ses_new", "found"))
        self.assertEqual(seen[0][1], "/w")
        self.assertEqual(seen[0][0][:3], ["opencode", "session", "list"])
        self.assertEqual(R.dir_latest("opencode-list", "/w", self.started, self.home, lambda a, c: json.dumps(rows[1:])), (None, "none"))
        self.assertEqual(R.dir_latest("opencode-list", "/w", self.started, self.home, lambda a, c: json.dumps([dict(rows[0], id="-s")])), (None, "none"))
        self.assertEqual(R.dir_latest("opencode-list", "/w", self.started, self.home, lambda a, c: None), (None, "unknown"))      # CLI missing/failing
        self.assertEqual(R.dir_latest("opencode-list", "/w", self.started, self.home, lambda a, c: "not json"), (None, "unknown"))
        self.assertEqual(R.dir_latest("opencode-list", "/w", self.started, self.home, None), (None, "unknown"))

    def plan(self, agent, argv, cwd="/w", windows=1, run=None):
        fake_proc(self.proc, 100, start=str(self.TICKS))
        wins = [win(i + 1, cwd, (100 + i, argv)) for i in range(windows)]
        for i in range(1, windows):
            fake_proc(self.proc, 100 + i, start=str(self.TICKS))
        return R.build_plan(wins, AGENTS, self.home, self.proc, home=self.home, run=run)

    def test_the_plan_uses_the_directory_conversation_when_it_is_the_only_window(self):
        rows = json.dumps([{"id": "ses_new", "updated": (self.started + 5) * 1000, "directory": "/w"}])
        e = self.plan("opencode", ["opencode"], run=lambda a, c: rows)[0]
        self.assertEqual((e["mode"], e["session_id"], e["resume"]), ("exact", "ses_new", ["opencode", "-s", "ses_new"]))
        self.assertIn("touched since", e["why"])

    def test_a_window_that_never_had_a_conversation_is_not_pointed_at_an_old_one(self):
        rows = json.dumps([{"id": "ses_old", "updated": (self.started - 999) * 1000, "directory": "/w"}])
        e = self.plan("opencode", ["opencode"], run=lambda a, c: rows)[0]
        self.assertEqual((e["mode"], e["resume"]), ("none", None))             # previously `opencode -c`: somebody else's conversation
        self.assertIn("nothing to resume", e["why"])

    def test_when_it_cannot_look_the_agents_own_latest_is_still_the_fallback(self):
        e = self.plan("opencode", ["opencode"], run=lambda a, c: None)[0]
        self.assertEqual((e["mode"], e["resume"]), ("latest", ["opencode", "-c"]))

    def test_several_windows_in_one_directory_are_never_paired_by_guesswork(self):
        rows = json.dumps([{"id": "ses_new", "updated": (self.started + 5) * 1000, "directory": "/w"}])
        plan = self.plan("opencode", ["opencode"], windows=2, run=lambda a, c: rows)
        self.assertEqual([(e["mode"], e["resume"]) for e in plan], [("none", None)] * 2)

    def test_an_id_on_the_command_line_beats_any_lookup(self):
        e = self.plan("opencode", ["opencode", "-s", "ses_given"], run=lambda a, c: self.fail("must not ask"))[0]
        self.assertEqual((e["mode"], e["session_id"], e["resume"]), ("exact", "ses_given", ["opencode", "-s", "ses_given"]))
        self.assertIn("command line", e["why"])


class PromptTests(unittest.TestCase):
    SID = "4d4710c8-de7d-4c89-b7d2-c76a51f6fed7"

    def line(self):
        return ("launch --cwd=/w --title=claude 'kitty-unserialize-data={\"id\": 3}' --var=kittymux_resume=exact --var=kittymux_sid=%s "
                "--var=kittymux_status=working /usr/bin/claude --model x\n" % self.SID)

    def test_a_wrapper_makes_the_window_ask_first_and_carries_both_commands(self):
        agents = AGENTS
        new, report = R.rewrite_session(self.line(), agents, wrapper=["/k/bin/kittymux", "resume-prompt"])
        tokens = shlex.split(new)
        self.assertEqual(tokens[tokens.index("/k/bin/kittymux"):][:3], ["/k/bin/kittymux", "resume-prompt", "--info"])
        info = R.parse_info(tokens[-1])
        self.assertEqual((info["agent"], info["mode"], info["sid"]), ("claude", "exact", self.SID))
        self.assertEqual(info["orig"], ["/usr/bin/claude", "--model", "x"])
        self.assertEqual(info["resume"], ["/usr/bin/claude", "--model", "x", "--resume", self.SID])
        self.assertNotIn("kittymux_status", new)
        self.assertIn("asks", report[0])
        again, report2 = R.rewrite_session(new, agents, wrapper=["/k/bin/kittymux", "resume-prompt"])        # a rewritten file is left alone
        self.assertEqual((again, report2), (new, []))

    def test_without_a_wrapper_it_resumes_directly(self):
        new, _ = R.rewrite_session(self.line(), AGENTS)
        self.assertIn("--resume " + self.SID, new)
        self.assertNotIn("resume-prompt", new)

    def test_info_is_validated_because_a_session_file_is_editable(self):
        good = dict(agent="claude", mode="exact", sid=self.SID, orig=["claude"], resume=["claude", "--resume", self.SID])
        self.assertIsNotNone(R.parse_info(json.dumps(good)))
        for bad in (dict(good, sid="--dangerously-skip-permissions"), dict(good, resume=["rm", "-rf", "~"]), dict(good, orig=[]), dict(good, mode="auto"),
                    dict(good, agent="a b; c"), dict(good, orig=["claude", 5]), dict(good, resume=["claude\0"]), dict(good, orig="claude"),
                    dict(good, resume=["claude"] * 500)):
            self.assertIsNone(R.parse_info(json.dumps(bad)), bad)
        for junk in ("", "{", "[]", "null", "5"):
            self.assertIsNone(R.parse_info(junk))

    def test_keys(self):
        c = R.prompt_choice
        self.assertEqual([c(k) for k in (b"\r", b"\n", b"r", b"R", b"y")], ["resume"] * 5)
        self.assertEqual([c(k) for k in (b"n", b"s", b"a", b"i", b"\x1b", b"\x03")], ["new", "shell", "all", "info", "shell", "shell"])
        self.assertIsNone(c(b"\x1b[A"))               # an arrow key is not Escape
        self.assertIsNone(c(b"x"))
        self.assertEqual(c(b"xyn"), "resume")           # the first recognised key of what arrived

    def test_identify_uses_the_agents_own_session_id_only(self):
        agents = AGENTS
        home = tempfile.mkdtemp()
        os.makedirs(os.path.join(home, "sessions"))
        with open(os.path.join(home, "sessions", "77.json"), "w") as f:
            json.dump({"pid": 77, "sessionId": self.SID}, f)
        got = R.identify(agents, [{"pid": 77, "cmdline": ["/usr/bin/claude", "-p", "x"]}], home, proc=tempfile.mkdtemp())
        self.assertEqual((got["agent"], got["sid"], got["argv"][0]), ("claude", self.SID, "/usr/bin/claude"))
        self.assertIsNone(R.identify(agents, [{"pid": 1, "cmdline": ["zsh"]}], home))
        self.assertIsNone(R.identify(agents, [{"pid": 78, "cmdline": ["claude"]}], home, proc=tempfile.mkdtemp())["sid"])    # no registry file: unknown, not guessed


class TemplateTests(unittest.TestCase):
    def test_placeholders_and_quoting(self):
        out = R.render_template("cd @Q:CWD@\nnew_tab @NAME@\nlaunch @Q:AGENT@ @UNKNOWN@\n", {"CWD": "/w/my project's", "NAME": "api", "AGENT": "claude"})
        self.assertEqual(shlex.split(out.splitlines()[0]), ["cd", "/w/my project's"])
        self.assertIn("new_tab api", out)
        self.assertIn("@UNKNOWN@", out)                                              # an unknown placeholder is left visible, never silently empty


if __name__ == "__main__":
    unittest.main()
