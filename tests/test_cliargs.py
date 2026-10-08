import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_cliargs as A  # noqa: E402


class TakeTests(unittest.TestCase):
    def test_returns_the_next_value(self):
        self.assertEqual(A.take(iter(["/tmp/x"]), "--cwd"), "/tmp/x")

    def test_a_missing_value_is_a_usage_error(self):
        with self.assertRaisesRegex(A.UsageError, "--cwd needs a value"):
            A.take(iter([]), "--cwd")

    def test_another_option_is_not_a_value(self):
        with self.assertRaisesRegex(A.UsageError, "--name needs a value"):
            A.take(iter(["--base"]), "--name")

    def test_a_single_dash_value_is_fine(self):
        self.assertEqual(A.take(iter(["-"]), "--cwd"), "-")

    def test_allowed_values_are_enforced(self):
        self.assertEqual(A.take(iter(["auto"]), "--side", allow=("auto", "right")), "auto")
        with self.assertRaisesRegex(A.UsageError, "--side needs one of: auto, right"):
            A.take(iter(["left"]), "--side", allow=("auto", "right"))


if __name__ == "__main__":
    unittest.main()
