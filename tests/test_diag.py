import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_diag as D  # noqa: E402


class MessageTests(unittest.TestCase):
    def test_the_message_names_the_command_the_places_and_the_fix(self):
        m = D.no_socket_message("spawn", ["/run/user/1000", "/tmp"])
        self.assertIn("kittymux spawn", m)
        self.assertIn("/run/user/1000", m)
        self.assertIn("allow_remote_control socket-only", m)
        self.assertNotIn("\n", m)

    def test_a_hostile_directory_name_cannot_inject_lines_or_escapes(self):
        m = D.no_socket_message("x", ["/tmp/a\nb\x1b[2J"])
        self.assertNotIn("\n", m)
        self.assertNotIn("\x1b", m)

    def test_no_directories_says_so(self):
        self.assertIn("nowhere", D.no_socket_message("x", []))


class DescribeTests(unittest.TestCase):
    def test_each_kind_of_failure_has_its_own_words(self):
        self.assertEqual(D.describe_failure(1, "", subprocess.TimeoutExpired("kitty", 3)), "timed out")
        self.assertEqual(D.describe_failure(1, "", FileNotFoundError()), "kitty is not on PATH")
        self.assertIn("exited 1: boom", D.describe_failure(1, "boom\nsecond line", None))
        self.assertEqual(D.describe_failure(3, "", None), "kitty @ exited 3")

    def test_stderr_is_one_clean_bounded_line(self):
        text = D.describe_failure(1, "x" * 500 + "\x1b[31m", None)
        self.assertLessEqual(len(text), 200)
        self.assertNotIn("\x1b", text)


class LogTests(unittest.TestCase):
    def test_a_failure_is_logged_private_and_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(3000):
                D.log_failure(d, "nav", f"timed out {i}", 1_700_000_000.0 + i)
            path = os.path.join(d, "cli-errors.log")
            self.assertLess(os.path.getsize(path), 40 * 1024)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertTrue(D.recent_failures(d, 2)[-1].endswith("nav: timed out 2999"))

    def test_logging_never_raises(self):
        D.log_failure("/proc/not/a/dir", "nav", "x", 0.0)

    def test_recent_failures_of_a_missing_log_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(D.recent_failures(d), [])


if __name__ == "__main__":
    unittest.main()
