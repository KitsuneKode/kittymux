import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_bounded as B  # noqa: E402


class CapNewestTests(unittest.TestCase):
    def test_keeps_the_newest_inserted(self):
        t = {i: i for i in range(10)}
        self.assertEqual(B.cap_newest(t, 4), 6)
        self.assertEqual(list(t), [6, 7, 8, 9])

    def test_under_the_cap_changes_nothing(self):
        t = {1: 1}
        self.assertEqual(B.cap_newest(t, 4), 0)
        self.assertEqual(t, {1: 1})

    def test_a_zero_or_negative_cap_empties_the_table(self):
        t = {1: 1, 2: 2}
        B.cap_newest(t, 0)
        self.assertEqual(t, {})


class SeenWithinTests(unittest.TestCase):
    def test_a_repeat_inside_the_window_is_reported_once(self):
        t = {}
        self.assertFalse(B.seen_within(t, "boom", 100.0, 60.0))
        self.assertTrue(B.seen_within(t, "boom", 130.0, 60.0))
        self.assertFalse(B.seen_within(t, "boom", 161.0, 60.0))        # the window passed: log it again

    def test_distinct_keys_never_exceed_the_cap_and_the_newest_survive(self):
        t = {}
        for i in range(1000):
            B.seen_within(t, f"error {i}", float(i), 60.0, cap=64)
        self.assertLessEqual(len(t), 64)
        self.assertIn("error 999", t)
        self.assertNotIn("error 0", t)

    def test_a_zero_window_sees_every_repeat(self):              # tests set KITTYMUX_ERR_DEDUPE=0 to see every error
        t = {}
        self.assertFalse(B.seen_within(t, "x", 1.0, 0.0))
        self.assertFalse(B.seen_within(t, "x", 1.0, 0.0))


class AppendCappedTests(unittest.TestCase):
    def test_a_log_past_the_cap_keeps_its_tail_and_keeps_logging(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.log")
            for i in range(400):
                self.assertTrue(B.append_capped(path, f"line {i:04d} " + "x" * 90 + "\n", cap=8192))
            size = os.path.getsize(path)
            self.assertLessEqual(size, 8192 + 200)
            text = open(path, encoding="utf-8").read()
            self.assertIn("line 0399", text)
            self.assertNotIn("line 0000", text)
            self.assertTrue(text.startswith("line "), "the cut must land on a line start, not mid-line")

    def test_an_unwritable_path_returns_false_instead_of_raising(self):
        self.assertFalse(B.append_capped("/proc/definitely/not/here.log", "x"))

    def test_the_file_is_private(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.log")
            B.append_capped(path, "x\n")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
