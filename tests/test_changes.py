import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_changes as C  # noqa: E402

GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false"]


def sh(args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def objects_snapshot(repo):
    return sorted(os.path.join(d, f) for d, _s, fs in os.walk(os.path.join(repo, ".git", "objects")) for f in fs)


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.repo, self.state = os.path.join(self.t, "r"), os.path.join(self.t, "state")
        os.makedirs(self.repo)
        os.makedirs(self.state)
        sh(["git", "init", "-q"], self.repo)
        self.write("a.txt", "one\ntwo\n")
        self.write(".gitignore", "build/\n")
        sh(["git", "add", "."], self.repo)
        sh(GIT + ["commit", "-qm", "init"], self.repo)

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def write(self, rel, text, mode="w"):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode) as f:
            f.write(text)


class SnapshotTests(RepoCase):
    def test_edits_new_files_and_deletions_since_the_start_are_counted_and_ignored_files_are_not(self):
        self.assertTrue(C.start(self.state, 1, 7, self.repo))
        self.write("a.txt", "one\ntwo\nthree\nfour\n")                        # +2
        self.write("src/new.py", "x\n" * 5)                                    # +5, untracked
        self.write("build/out.bin", "junk\n" * 100)                            # ignored: must not count
        s = C.finish(self.state, 1, 7, self.repo)
        self.assertEqual((s["files"], s["add"], s["del"]), (2, 7, 0))
        self.assertEqual(C.format_summary(s), "2 files +7")
        self.assertEqual({t["path"] for t in s["top"]}, {"a.txt", "src/new.py"})
        os.unlink(os.path.join(self.repo, "a.txt"))
        s = C.finish(self.state, 1, 7, self.repo)
        self.assertEqual((s["files"], s["del"]), (2, 2))                       # the deletion shows too, still relative to the run start

    def test_changes_made_before_the_run_started_are_not_attributed_to_it(self):
        self.write("earlier.txt", "x\n" * 9)                                   # dirty BEFORE the run
        C.start(self.state, 1, 7, self.repo)
        self.write("a.txt", "one\ntwo\nthree\n")
        s = C.finish(self.state, 1, 7, self.repo)
        self.assertEqual((s["files"], s["add"]), (1, 1))

    def test_without_a_baseline_it_falls_back_to_head_and_says_so(self):
        self.write("a.txt", "one\n")
        s = C.finish(self.state, 1, 9, self.repo)
        self.assertEqual((s["files"], s["add"], s["del"]), (1, 0, 1))
        self.assertEqual(C.load(self.state, 1)["9"]["vs"], "HEAD")
        C.start(self.state, 1, 9, self.repo)
        C.finish(self.state, 1, 9, self.repo)
        self.assertEqual(C.load(self.state, 1)["9"]["vs"], "run")

    def test_the_repository_itself_is_never_written(self):
        before = objects_snapshot(self.repo)
        with open(os.path.join(self.repo, ".git", "index"), "rb") as f:
            index_before = f.read()
        C.start(self.state, 1, 7, self.repo)
        self.write("a.txt", "changed\n")
        self.write("new.txt", "n\n")
        C.finish(self.state, 1, 7, self.repo)
        self.assertEqual(objects_snapshot(self.repo), before)                  # no new objects in the repo
        with open(os.path.join(self.repo, ".git", "index"), "rb") as f:
            self.assertEqual(f.read(), index_before)
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".git", "index.lock")))
        self.assertTrue(os.path.isdir(C.odb_dir(self.state, os.path.realpath(self.repo))))      # they went to our private directory

    def test_not_a_repository_a_missing_directory_and_an_empty_repository(self):
        plain = os.path.join(self.t, "plain")
        os.makedirs(plain)
        self.assertIsNone(C.snapshot(plain, self.state))
        self.assertIsNone(C.snapshot("/nonexistent/dir", self.state))
        self.assertIsNone(C.snapshot("", self.state))
        self.assertFalse(C.start(self.state, 1, 7, plain))
        empty = os.path.join(self.t, "empty")
        os.makedirs(empty)
        sh(["git", "init", "-q"], empty)
        with open(os.path.join(empty, "f.txt"), "w") as f:
            f.write("a\nb\n")
        self.assertEqual(C.snapshot(empty, self.state)["head"], None)          # no commits yet: still works
        self.assertEqual(C.summarize(C.numstat(C.EMPTY_TREE, C.snapshot(empty, self.state)["tree"], empty, self.state))["add"], 2)

    def test_binary_files_and_odd_names_do_not_break_the_numbers(self):
        C.start(self.state, 1, 7, self.repo)
        self.write("img.bin", b"\x00\x01\x02\xff" * 50, mode="wb")
        self.write("sp ace/ünï.txt", "x\n")
        s = C.finish(self.state, 1, 7, self.repo)
        self.assertEqual(s["files"], 2)
        paths = {t["path"] for t in s["top"]}
        self.assertEqual(paths, {"img.bin", "sp ace/ünï.txt"})
        self.assertEqual(s["add"], 1)                                          # the binary file adds no line count

    def test_a_path_with_a_newline_is_one_row(self):
        C.start(self.state, 1, 7, self.repo)
        self.write("we\nird.txt", "x\n")
        s = C.finish(self.state, 1, 7, self.repo)
        self.assertEqual(s["files"], 1)


class SummaryTests(unittest.TestCase):
    def test_format(self):
        f = C.format_summary
        self.assertEqual(f({"files": 7, "add": 142, "del": 30}), "7 files +142 −30")
        self.assertEqual(f({"files": 1, "add": 3, "del": 0}), "1 file +3")
        self.assertEqual(f({"files": 0, "add": 0, "del": 0}), "no changes")
        for bad in (None, {}, {"files": "x"}, {"files": 1}, "7 files"):
            self.assertEqual(f(bad), "", bad)

    def test_summarize_picks_the_biggest_files_and_tolerates_failure(self):
        s = C.summarize([(1, 0, "small"), (50, 5, "big"), (None, None, "bin")], top_n=2)
        self.assertEqual([t["path"] for t in s["top"]], ["big", "small"])
        self.assertIsNone(C.summarize(None))


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_private_merge_and_bounds(self):
        C.update(self.d, 5, 7, {"a": 1}, 1000.0)
        C.update(self.d, 5, 7, {"b": 2}, 1001.0)
        self.assertEqual({k: v for k, v in C.load(self.d, 5)["7"].items() if k in "ab"}, {"a": 1, "b": 2})
        self.assertEqual(oct(os.stat(C.path_for(self.d, 5)).st_mode & 0o777), "0o600")
        for w in range(250):
            C.update(self.d, 5, w + 100, {"x": 1}, 2000.0 + w)
        self.assertEqual(len(C.load(self.d, 5)), 200)                          # bounded
        C.update(self.d, 5, 1, {"y": 1}, 2000.0 + C.KEEP_S + 500)
        self.assertEqual(list(C.load(self.d, 5)), ["1"])                       # week-old entries are dropped

    def test_a_corrupt_cache_is_empty_and_prune_keeps_the_stores_bounded(self):
        with open(C.path_for(self.d, 5), "w") as f:
            f.write("{broken")
        self.assertEqual(C.load(self.d, 5), {})
        root = os.path.join(self.d, "changes-objects")
        for name, age in (("old", 9 * 86400), ("big1", 100), ("big2", 50)):
            p = os.path.join(root, name)
            os.makedirs(p)
            with open(os.path.join(p, "blob"), "wb") as f:
                f.write(b"x" * 600)
            os.utime(p, (1000.0 - age, 1000.0 - age))
        C.prune_stores(self.d, now=1000.0, max_bytes=1000)
        self.assertEqual(sorted(os.listdir(root)), ["big2"])                   # the week-old one, then the oldest over the limit


if __name__ == "__main__":
    unittest.main()
