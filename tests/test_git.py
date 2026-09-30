import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_git as G  # noqa: E402

def _w(path, text):
    with open(path, "w") as f:
        f.write(text)


HAVE_GIT = shutil.which("git") is not None
ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def git(cwd, *args):
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always", *args],
                          cwd=cwd, env=ENV, capture_output=True, text=True, check=True).stdout.strip()


@unittest.skipUnless(HAVE_GIT, "git not installed")
class RealRepoTests(unittest.TestCase):
    def setUp(self):
        G._cache.clear()
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.repo = os.path.join(self.root, "proj")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "init")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_matches_git_for_branch(self):
        gi = G.info(self.repo)
        self.assertEqual(gi.branch, git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"))
        self.assertEqual((gi.project, gi.worktree, gi.top), ("proj", "", self.repo))

    def test_subdirectory_resolves_to_top(self):
        sub = os.path.join(self.repo, "a", "b")
        os.makedirs(sub)
        self.assertEqual(G.info(sub).top, self.repo)
        self.assertEqual(G.label(sub)[0], "proj/a/b")

    def test_switch_is_seen_immediately(self):
        self.assertEqual(G.info(self.repo).branch, "main")
        time.sleep(0.02)
        git(self.repo, "switch", "-q", "-c", "feat/x")
        self.assertEqual(G.info(self.repo).branch, "feat/x")

    def test_detached_head(self):
        git(self.repo, "checkout", "-q", "--detach")
        self.assertEqual(G.info(self.repo).branch, "detached")

    def test_linked_worktree_reports_project_and_worktree(self):
        wt = os.path.join(self.root, "proj-wt")
        git(self.repo, "worktree", "add", "-q", "-b", "wt-branch", wt)
        gi = G.info(wt)
        self.assertEqual((gi.branch, gi.project, gi.worktree), ("wt-branch", "proj", "proj-wt"))
        self.assertEqual(G.label(wt)[0], "proj:proj-wt")
        # and the main checkout is unaffected
        self.assertEqual(G.info(self.repo).worktree, "")

    def test_submodule_uses_its_own_name(self):
        sub_src = os.path.join(self.root, "libsrc")
        os.makedirs(sub_src)
        git(sub_src, "init", "-q", "-b", "main")
        git(sub_src, "commit", "-q", "--allow-empty", "-m", "s")
        git(self.repo, "submodule", "add", "-q", sub_src, "vendor/lib")
        gi = G.info(os.path.join(self.repo, "vendor", "lib"))
        self.assertIsNotNone(gi)
        self.assertEqual(gi.branch, "main")
        self.assertEqual(gi.project, "lib")

    def test_not_a_repo(self):
        plain = os.path.join(self.root, "plain")
        os.makedirs(plain)
        self.assertIsNone(G.info(plain))
        self.assertEqual(G.label(plain, home=self.root)[1], "")

    def test_never_spawns_a_process(self):
        import subprocess as sp
        real = sp.run
        sp.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("git reader must not spawn"))
        try:
            G._cache.clear()
            self.assertEqual(G.info(self.repo).branch, "main")
        finally:
            sp.run = real


class PureTests(unittest.TestCase):
    def test_empty_and_missing(self):
        self.assertIsNone(G.info(""))
        self.assertIsNone(G.info("/definitely/not/here"))

    def test_cache_is_bounded(self):
        G._cache.clear()
        base = tempfile.mkdtemp()
        for i in range(G._CACHE_MAX + 20):
            d = os.path.join(base, f"r{i}", ".git")
            os.makedirs(d)
            _w(os.path.join(d, "HEAD"), "ref: refs/heads/main\n")
            G.info(os.path.dirname(d))
        self.assertLessEqual(len(G._cache), G._CACHE_MAX)
        shutil.rmtree(base, ignore_errors=True)

    def test_short_path(self):
        home = "/home/u"
        self.assertEqual(G.short_path(home, home), "~")
        self.assertEqual(G.short_path(home + "/a/b", home), "~/a/b")
        long = home + "/" + "/".join(["dir"] * 20)
        self.assertLessEqual(len(G.short_path(long, home, 34)), 34)
        self.assertTrue(G.short_path(long, home, 34).startswith("~/…/"))

    def test_gitdir_file_relative_target(self):
        base = tempfile.mkdtemp()
        top = os.path.join(base, "wt")
        gd = os.path.join(base, "main", ".git", "worktrees", "wt")
        os.makedirs(top); os.makedirs(gd)
        _w(os.path.join(top, ".git"), "gitdir: ../main/.git/worktrees/wt\n")
        _w(os.path.join(gd, "HEAD"), "ref: refs/heads/topic\n")
        _w(os.path.join(gd, "commondir"), "../..\n")
        G._cache.clear()
        gi = G.info(top)
        self.assertEqual((gi.branch, gi.project, gi.worktree), ("topic", "main", "wt"))
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
