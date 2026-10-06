import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import kittymux_usageview as U


class UsageViewTests(unittest.TestCase):
    def test_narrow_view_preserves_reset_and_reports_elapsed_honestly(self):
        data = {"providers": [{"name": "codex", "rows": [{"label": "5h", "pct": 100, "reset": "resets in 42 minutes"},
                                                        {"label": "window", "pct": 50, "clock": True}]}]}
        rows = U.rows(data, 16)
        self.assertTrue(all(len(s) <= 15 for s, _ in rows))
        text = "".join(s.strip() for s, _ in rows)
        self.assertIn("100% used", text)
        self.assertIn("50% elapsed", text)
        self.assertIn("resets in 42 minutes", text)
        self.assertTrue(any(role == "alert" for _, role in rows))

    def test_controls_are_cleaned_and_missing_data_is_explicit(self):
        self.assertIn("Collecting", " ".join(s for s, _ in U.rows({}, 32)))
        rows = U.rows({"providers": [{"name": "bad\x1btitle", "rows": [{"text": "note\x00safe"}]}]}, 32)
        self.assertFalse(any("\x1b" in s or "\x00" in s for s, _ in rows))
