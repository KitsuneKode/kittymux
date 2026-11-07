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

    def test_error_and_indeterminate_show_although_kitty_does_not_count_them(self):
        # kitty 0.49.2 Tab.update_progress counts only set/paused in num_of_windows_with_progress, but still makes an
        # error or indeterminate window the last focused one with progress (kitty/tabs.py update_progress)
        self.assertEqual(P.of_tab(_tab(n=0, wid=7), {7: _win("error", 0)}), ("error", 0))
        self.assertEqual(P.of_tab(_tab(n=0, wid=7), {7: _win("indeterminate", 0)}), ("indeterminate", 0))
        # one error window beside one counted window: the state is the focused one's, the amount the counted mean
        self.assertEqual(P.of_tab(_tab(n=1, total=40, wid=7), {7: _win("error", 0)}), ("error", 40))

    def test_cleared_or_gone_window_is_none(self):
        self.assertIsNone(P.of_tab(_tab(), {7: _win("unset")}))
        self.assertIsNone(P.of_tab(_tab(), {}))

    def test_of_window_reads_one_pane(self):
        self.assertEqual(P.of_window(_win("set", 55)), ("set", 55))
        self.assertIsNone(P.of_window(types.SimpleNamespace(progress=types.SimpleNamespace(state=types.SimpleNamespace(name="unset")))))

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

    def test_from_ls_uses_the_window_report_and_derives_the_count(self):
        tab = {"id": 3, "last_focused_window_with_progress_id": 9}
        wins = [{"id": 9, "progress": {"state": "set", "percent": 42}},
                {"id": 10, "progress": {"state": "paused", "percent": 10}}]
        self.assertEqual(P.from_ls(tab, wins), ("set", 26))          # mean of the two counted windows
        self.assertIsNone(P.from_ls({"id": 3}, wins))
        err = {"id": 4, "last_focused_window_with_progress_id": 9,
               "num_of_windows_with_progress": 0, "total_progress": 0}
        self.assertEqual(P.from_ls(err, [{"id": 9, "progress": {"state": "error", "percent": 0}}]), ("error", 0))
        self.assertEqual(P.from_ls(
            {"id": 5, "last_focused_window_with_progress_id": 9, "num_of_windows_with_progress": 0},
            [{"id": 9, "progress": {"state": "indeterminate", "percent": 0}}]), ("indeterminate", 0))

    def test_reports_roundtrip_and_a_bad_file_is_empty(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "progress-1.json"
            P.save_reports(path, {3: ("set", 42), "nope": ("gone", 1), 4: ("error", 0)})
            self.assertEqual(P.load_reports(path), {3: ("set", 42), 4: ("error", 0)})
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
            path.write_text("not json")
            self.assertEqual(P.load_reports(path), {})
            self.assertEqual(P.load_reports(Path(d) / "missing.json"), {})


if __name__ == "__main__":
    unittest.main()
