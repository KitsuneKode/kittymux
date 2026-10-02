import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_fanout as F  # noqa: E402
import kittymux_launcher as L  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false"]


def sh(args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class PromptFormTests(unittest.TestCase):
    FORMS = L.load_prompt_forms(os.path.join(ROOT, "assets", "agent-prompt.json"))

    def test_each_verified_form(self):
        a = lambda agent: L.prompt_args(self.FORMS, agent, "fix the login bug")        # noqa: E731
        self.assertEqual(a("claude"), ["fix the login bug"])
        self.assertEqual(a("codex"), ["fix the login bug"])
        self.assertEqual(a("cursor-agent"), ["fix the login bug"])
        self.assertEqual(a("grok"), ["fix the login bug"])
        self.assertEqual(a("droid"), ["fix the login bug"])
        self.assertEqual(a("devin"), ["--", "fix the login bug"])
        self.assertEqual(a("opencode"), ["--prompt", "fix the login bug"])
        self.assertEqual(a("agy"), ["--prompt-interactive", "fix the login bug"])
        self.assertIsNone(a("nosuchagent"))                                          # never guessed

    def test_unusable_prompts_are_refused_and_shell_text_is_just_text(self):
        for bad in ("", "   ", None, 5, "-x --stdin", "- a bullet", "a" * (L.PROMPT_MAX + 1), "has\0nul"):
            self.assertIsNone(L.validate_prompt(bad), repr(bad)[:30])
            self.assertIsNone(L.prompt_args(self.FORMS, "claude", bad))
        evil = 'fix `rm -rf ~` $(id) "; echo pwned'
        self.assertEqual(L.prompt_args(self.FORMS, "claude", evil), [evil])             # ONE argv element: no shell ever sees it
        self.assertEqual(L.validate_prompt("  multi\nline  "), "multi\nline")

    def test_a_users_file_extends_and_a_bad_flag_name_is_refused(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "prompt.json")
        import json
        with open(p, "w") as f:
            json.dump({"mine": {"form": "flag", "flag": "--ask"}, "evil": {"form": "flag", "flag": "--x; rm -rf ~"}, "junk": {"form": "unknown"}}, f)
        forms = L.load_prompt_forms(os.path.join(ROOT, "assets", "agent-prompt.json"), p)
        self.assertEqual(L.prompt_args(forms, "mine", "hi"), ["--ask", "hi"])
        self.assertIsNone(L.prompt_args(forms, "evil", "hi"))
        self.assertNotIn("junk", forms)
        self.assertIn("claude", forms)

    def test_launch_args_carry_the_tab_title_cleaned(self):
        a = L.launch_args("claude", "/x/claude", "tab", cwd="/w", extra=["hi"], tab_title="claude · fix\nlogin\x1b")
        self.assertEqual(a[a.index("--tab-title") + 1], "claude · fix login")


class GitCase(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.repo, self.state = os.path.join(self.t, "r"), os.path.join(self.t, "state")
        os.makedirs(self.repo)
        sh(["git", "init", "-q", "-b", "main"], self.repo)
        with open(os.path.join(self.repo, "a.txt"), "w") as f:
            f.write("one\ntwo\n")
        sh(["git", "add", "."], self.repo)
        sh(GIT + ["commit", "-qm", "init"], self.repo)
        self.base = F.resolve_base(self.repo, None)

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)


class CreateTests(GitCase):
    def test_one_worktree_and_branch_per_agent_from_the_same_base_and_excluded_from_status(self):
        made, err = F.create(self.repo, "fix", self.base, ["claude", "codex"])
        self.assertIsNone(err)
        self.assertEqual([m["branch"] for m in made], ["fix-claude", "fix-codex"])
        for m in made:
            self.assertTrue(os.path.isdir(m["path"]))
            self.assertEqual(F.resolve_base(m["path"], "HEAD"), self.base)               # all start from the same commit
        status = subprocess.run(["git", "status", "--porcelain"], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertEqual(status.strip(), "")                                               # .worktrees/ is excluded locally, nothing tracked was touched
        self.assertIn(".worktrees/", open(os.path.join(self.repo, ".git", "info", "exclude")).read().split())

    def test_it_is_all_or_nothing_and_never_reuses_an_existing_path_or_branch(self):
        os.makedirs(os.path.join(self.repo, ".worktrees", "fix-codex"))
        made, err = F.create(self.repo, "fix", self.base, ["claude", "codex"])
        self.assertEqual(made, [])
        self.assertIn("already exists", err)
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".worktrees", "fix-claude")))      # checked BEFORE creating anything
        shutil.rmtree(os.path.join(self.repo, ".worktrees", "fix-codex"))
        sh(["git", "branch", "fix-codex"], self.repo)
        made, err = F.create(self.repo, "fix", self.base, ["claude", "codex"])
        self.assertIn("branch fix-codex already exists", err)
        self.assertEqual(made, [])

    def test_a_failure_part_way_rolls_back_what_was_made(self):
        real = F._git
        calls = {"n": 0}

        def flaky(args, cwd, timeout=60.0):
            if args[:2] == ["worktree", "add"]:
                calls["n"] += 1
                if calls["n"] == 2:
                    return 1, "", "fatal: boom"
            return real(args, cwd, timeout)
        F._git = flaky
        try:
            made, err = F.create(self.repo, "fix", self.base, ["claude", "codex"])
        finally:
            F._git = real
        self.assertEqual(made, [])
        self.assertIn("boom", err)
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".worktrees", "fix-claude")))      # the first one was removed again
        self.assertNotEqual(subprocess.run(["git", "rev-parse", "--verify", "-q", "refs/heads/fix-claude"], cwd=self.repo, capture_output=True).returncode, 0)

    def test_bases_and_names(self):
        self.assertEqual(F.resolve_base(self.repo, "main"), self.base)
        for bad in ("--all", "-x", "nosuchref", "ma\nin", "ma\0in", "HEAD~99"):
            self.assertIsNone(F.resolve_base(self.repo, bad), bad)
        self.assertEqual(F.resolve_base(self.repo, "main\n"), self.base)               # a trailing newline is just stripped
        for good in ("fix", "fix-login.v2", "A1"):
            self.assertTrue(F.NAME_RE.match(good))
        for bad in ("", "-x", ".hidden", "a b", "a/b", "x" * 60, "a;rm"):
            self.assertFalse(F.NAME_RE.match(bad), bad)

    def test_main_repo_is_found_from_a_linked_worktree(self):
        made, _ = F.create(self.repo, "fix", self.base, ["claude"])
        self.assertEqual(os.path.realpath(F.main_repo(made[0]["path"])), os.path.realpath(self.repo))
        self.assertEqual(os.path.realpath(F.main_repo(self.repo)), os.path.realpath(self.repo))
        self.assertIsNone(F.main_repo(self.t))
        self.assertIsNone(F.main_repo("/nonexistent"))


class CompareAndCleanTests(GitCase):
    def test_compare_reports_each_agents_work_committed_or_not_relative_to_the_base(self):
        made, _ = F.create(self.repo, "fix", self.base, ["claude", "codex", "devin"])
        F.save(self.state, "fix", self.repo, self.base, "do the thing", made)
        with open(os.path.join(made[0]["path"], "a.txt"), "a") as f:
            f.write("x\ny\n")                                                              # claude: uncommitted +2
        with open(os.path.join(made[1]["path"], "new.py"), "w") as f:
            f.write("z\n" * 7)
        sh(["git", "add", "."], made[1]["path"])
        sh(GIT + ["commit", "-qm", "codex work"], made[1]["path"])                         # codex: committed +7
        rows = {r["agent"]: r for r in F.compare(self.state, F.load(self.state)["fix"])}
        self.assertEqual((rows["claude"]["summary"]["files"], rows["claude"]["summary"]["add"]), (1, 2))
        self.assertEqual((rows["codex"]["summary"]["files"], rows["codex"]["summary"]["add"]), (1, 7))
        self.assertEqual((rows["devin"]["summary"]["files"], rows["devin"]["summary"]["add"]), (0, 0))      # did nothing

    def test_a_missing_worktree_is_reported_not_crashed_on(self):
        made, _ = F.create(self.repo, "fix", self.base, ["claude"])
        F.save(self.state, "fix", self.repo, self.base, "p", made)
        shutil.rmtree(made[0]["path"])
        row = F.compare(self.state, F.load(self.state)["fix"])[0]
        self.assertEqual((row["exists"], row["summary"]), (False, None))

    def test_clean_keeps_dirty_worktrees_unless_forced_and_removes_exactly_what_it_made(self):
        made, _ = F.create(self.repo, "fix", self.base, ["claude", "codex"])
        with open(os.path.join(made[0]["path"], "a.txt"), "a") as f:
            f.write("unsaved work\n")
        notes = F.remove(self.repo, made)
        self.assertTrue(os.path.isdir(made[0]["path"]))                                    # dirty: kept
        self.assertTrue(any("kept claude" in n for n in notes))
        self.assertFalse(os.path.exists(made[1]["path"]))                                  # clean: removed
        self.assertNotEqual(subprocess.run(["git", "rev-parse", "--verify", "-q", "refs/heads/fix-codex"], cwd=self.repo, capture_output=True).returncode, 0)
        F.remove(self.repo, made[:1], force=True)
        self.assertFalse(os.path.exists(made[0]["path"]))
        self.assertTrue(os.path.isdir(self.repo))

    def test_the_record_is_private_bounded_and_a_corrupt_file_is_empty(self):
        for i in range(60):
            F.save(self.state, f"n{i}", self.repo, self.base, "p", [], now=1000.0 + i)
        self.assertEqual(len(F.load(self.state)), F.KEEP)
        self.assertEqual(oct(os.stat(F._path(self.state)).st_mode & 0o777), "0o600")
        F.forget(self.state, "n59")
        self.assertNotIn("n59", F.load(self.state))
        with open(F._path(self.state), "w") as f:
            f.write("{broken")
        self.assertEqual(F.load(self.state), {})


if __name__ == "__main__":
    unittest.main()
