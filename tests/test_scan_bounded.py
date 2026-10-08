import gc
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_scan as KS  # noqa: E402
from test_scan import FakeWindow, ScanBase  # noqa: E402


class BoundedStateTests(ScanBase):
    """The scanner lives as long as kitty. Windows come and go all day; nothing it keeps may grow with the number of windows it has EVER seen."""

    def sizes(self):
        rt = vars(KS._RT)
        out = {}
        for name, value in rt.items():
            if isinstance(value, (dict, set, list)):
                out[name] = len(value)
        return out

    def churn(self, n, prompt=True):
        """n windows open, are scanned a few times in various states, and close."""
        for i in range(1, n + 1):
            screens = ("• Working (3s • esc to interrupt)\n", "Do you want to proceed?\n❯ 1. Yes\n", "You've hit your usage limit. Try again at 9:21 PM.\n", "› Ask Codex\n")
            w = FakeWindow(i, "codex", screens[i % 4])
            self.add(w)
            for _ in range(3):
                KS.scan_all()
            if prompt:
                plain = FakeWindow(100000 + i, None, "[sudo] password for x: ")
                self.add(plain)
                with mock.patch.object(KS, "fg_job", return_value=(["sudo"], True)):
                    KS.scan_prompt(plain, float(i))
            self.k.boss.all_windows[:] = []
            self.k.boss.window_id_map.clear()
            KS.scan_all()                                         # the closed windows are noticed and forgotten

    def test_nothing_grows_with_the_number_of_windows_ever_seen(self):
        with mock.patch.object(KS, "_notify", return_value="sent"):
            self.churn(40)
            gc.collect()
            small = self.sizes()
            self.churn(400)
            gc.collect()
            big = self.sizes()
        grown = {k: (small.get(k, 0), big[k]) for k in big if big[k] > small.get(k, 0) + 2 and k not in ("decisions", "notify_log")}
        self.assertEqual(grown, {}, "these containers grew with window churn: " + repr(grown))

    def test_the_decision_log_and_the_notification_log_are_capped(self):
        with mock.patch.object(KS, "_notify", return_value="sent"):
            self.churn(150)
        self.assertLessEqual(len(vars(KS._RT).get("decisions", [])), 300)
        self.assertLessEqual(len(vars(KS._RT).get("notify_log", [])), 64)

    def test_the_unread_set_forgets_windows_that_closed(self):
        """A window that reported something (a question: one event per window) and closed unseen must not stay in `unread` for ever.
        The old version of this test never announced anything, so the set was always empty and it proved nothing."""
        with mock.patch.object(KS, "_notify", return_value="sent"):
            for i in range(1, 9):
                w = FakeWindow(i, "codex", "› Ask Codex\n")
                self.add(w)
                KS.scan_all()
                KS._announce(w, "question", "codex", "screen", f"q{i}")
            self.assertEqual(len(vars(KS._RT).get("unread", ())), 8, "the test must really populate the set, or it asserts about nothing")
            self.k.boss.all_windows[:] = []
            self.k.boss.window_id_map.clear()
            KS.scan_all()
        self.assertEqual(vars(KS._RT).get("unread", set()), set())

    def test_journal_records_in_memory_stop_at_the_files_limits(self):
        J, _ = KS._journal_mod()
        rt = KS._journal_rt()
        now = 10_000_000.0
        for i in range(J.RECORD_MAX + 50):                                   # more sessions than the file keeps
            rt["recs"][f"claude:{i}"] = {"agent": "claude", "last": now - (J.RECORD_MAX + 50 - i), "open": False}
        rt["recs"]["claude:old"] = {"agent": "claude", "last": now - J.MAX_AGE_S - 1, "open": False}
        rt["recs"]["claude:pinned-old"] = {"agent": "claude", "last": now - J.MAX_AGE_S - 1, "open": False, "pinned": True}
        KS._journal_prune_memory(now)
        self.assertLessEqual(len([r for r in rt["recs"].values() if not r.get("pinned")]), J.RECORD_MAX)
        self.assertNotIn("claude:old", rt["recs"])
        self.assertIn("claude:pinned-old", rt["recs"])                       # pinned means keep, in memory too
        self.assertIn(f"claude:{J.RECORD_MAX + 49}", rt["recs"])             # the newest survive


if __name__ == "__main__":
    unittest.main()
