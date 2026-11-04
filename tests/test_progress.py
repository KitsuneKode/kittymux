import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
import kittymux_progress as P  # noqa: E402


def _win(state, percent=0):
    return types.SimpleNamespace(progress=types.SimpleNamespace(state=types.SimpleNamespace(name=state), percent=percent))


def _tab(n=1, total=0, wid=7):
    return types.SimpleNamespace(num_of_windows_with_progress=n, total_progress=total, last_focused_window_with_progress_id=wid)


class ProgressTests(unittest.TestCase):
    def test_no_progress_reported(self):
        self.assertIsNone(P.of_tab(_tab(n=0, wid=0), {}))
        self.assertIsNone(P.of_tab(types.SimpleNamespace(), {}))          # an older kitty: the fields are missing

    def test_one_window_uses_its_own_percent(self):
        self.assertEqual(P.of_tab(_tab(), {7: _win("set", 42)}), ("set", 42))

    def test_several_windows_average(self):
        self.assertEqual(P.of_tab(_tab(n=2, total=130), {7: _win("paused", 90)}), ("paused", 65))

    def test_cleared_or_gone_window_is_none(self):
        self.assertIsNone(P.of_tab(_tab(), {7: _win("unset")}))
        self.assertIsNone(P.of_tab(_tab(), {}))

    def test_fill_cells(self):
        self.assertEqual(P.fill_cells(20, "set", 0), 0)
        self.assertEqual(P.fill_cells(20, "set", 1), 1)                 # started: visible at once
        self.assertEqual(P.fill_cells(20, "set", 50), 10)
        self.assertEqual(P.fill_cells(20, "set", 100), 20)
        self.assertEqual(P.fill_cells(20, "indeterminate", 0), 20)
        self.assertEqual(P.fill_cells(20, "error", 0), 20)
        self.assertEqual(P.fill_cells(0, "set", 50), 0)

    def test_label(self):
        self.assertEqual(P.label("set", 42), "42%")
        self.assertEqual(P.label("error", 0), "failed")
        self.assertEqual(P.label("indeterminate", 0), "…")


if __name__ == "__main__":
    unittest.main()
