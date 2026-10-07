import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_ledger as L  # noqa: E402

NOW = datetime(2026, 10, 7, 15, 0, 0).timestamp()
DAY = 86400.0


def ev(kind="permission", t0=NOW - 600, ack=NOW - 300, status="read", **kw):
    e = {"id": f"e{id(object())}", "kind": kind, "t0": t0, "t": t0, "status": status, "agent": "claude", "tab": "api"}
    if ack is not None:
        e["ack_t"] = ack
    e.update(kw)
    return e


class WaitsTests(unittest.TestCase):
    def test_a_wait_runs_from_first_seen_to_first_looked_at(self):
        w = L.waits([ev(t0=NOW - 600, ack=NOW - 480)], NOW)
        self.assertEqual(len(w), 1)
        self.assertEqual((w[0]["seconds"], w[0]["ongoing"]), (120.0, False))

    def test_an_unread_event_is_waiting_now(self):
        w = L.waits([ev(status="unread", ack=None, t0=NOW - 90)], NOW)
        self.assertEqual((w[0]["seconds"], w[0]["ongoing"]), (90.0, True))

    def test_only_events_that_ask_for_you_count(self):
        events = [ev("permission"), ev("question"), ev("done"), ev("limit"), ev("error"), ev("info")]
        self.assertEqual(len(L.waits(events, NOW)), 2)

    def test_an_event_read_before_the_log_kept_when_is_skipped_not_guessed(self):
        self.assertEqual(L.waits([ev(status="read", ack=None)], NOW), [])

    def test_a_merged_event_is_measured_from_its_first_report(self):
        e = ev(t0=NOW - 600, ack=NOW - 300)
        e["t"] = NOW - 320                                   # the newest report; the wait still began at t0
        self.assertEqual(L.waits([e], NOW)[0]["seconds"], 300.0)

    def test_old_events_without_t0_fall_back_to_t(self):
        e = ev(ack=NOW - 100)
        del e["t0"]
        e["t"] = NOW - 400
        self.assertEqual(L.waits([e], NOW)[0]["seconds"], 300.0)

    def test_an_event_from_the_future_or_with_a_backwards_ack_is_harmless(self):
        self.assertEqual(L.waits([ev(t0=NOW + 500, ack=NOW + 600)], NOW), [])
        self.assertEqual(L.waits([ev(t0=NOW - 100, ack=NOW - 500)], NOW)[0]["seconds"], 0.0)

    def test_junk_never_raises(self):
        junk = [None, 5, "x", [None, 1, {}, {"kind": "permission"}, {"kind": "permission", "t0": "x", "status": "unread"},
                {"kind": "permission", "t0": float("nan"), "status": "unread"}, {"kind": "permission", "t": float("inf"), "status": "unread"},
                {"kind": "permission", "t0": True, "status": "unread"}, {"kind": "permission", "t0": 1.0, "status": "read", "ack_t": "x"}]]
        for events in junk:
            L.waits(events, NOW)
            L.summary(events, NOW)


class SummaryTests(unittest.TestCase):
    def test_nothing_measurable_is_none(self):
        self.assertIsNone(L.summary([], NOW))
        self.assertIsNone(L.summary(None, NOW))
        self.assertIsNone(L.summary([ev("done")], NOW))
        self.assertIsNone(L.summary([ev(t0=NOW - 30 * DAY, ack=NOW - 30 * DAY + 60)], NOW))        # older than the week

    def test_today_and_the_week_are_totalled_per_local_day(self):
        events = [ev(t0=NOW - 600, ack=NOW - 480), ev(t0=NOW - 300, ack=NOW - 180),                        # 120 s + 120 s today
                  ev(t0=NOW - DAY - 600, ack=NOW - DAY - 300),                                              # 300 s yesterday
                  ev(t0=NOW - 3 * DAY - 600, ack=NOW - 3 * DAY - 540)]                                       # 60 s three days ago
        s = L.summary(events, NOW)
        self.assertEqual((s["today_s"], s["count_today"]), (240.0, 2))
        self.assertEqual((s["week_s"], s["count_week"]), (240.0 + 300.0 + 60.0, 4))
        self.assertEqual(len(s["series"]), 7)
        self.assertEqual((s["series"][-1], s["series"][-2], s["series"][-4]), (240.0, 300.0, 60.0))

    def test_one_wait_counts_at_most_an_hour_but_the_longest_is_honest(self):
        s = L.summary([ev(t0=NOW - 3 * 3600, ack=NOW - 600, status="read")], NOW - 0)
        self.assertEqual(s["today_s"], L.CAP_S)
        self.assertEqual(s["longest_s"], 3 * 3600 - 600)

    def test_an_unread_wait_shows_as_ongoing(self):
        s = L.summary([ev(status="unread", ack=None, t0=NOW - 200)], NOW)
        self.assertEqual((s["ongoing"], s["today_s"]), (1, 200.0))

    def test_median_and_longest(self):
        events = [ev(t0=NOW - 1000, ack=NOW - 1000 + s) for s in (30, 60, 600)]
        s = L.summary(events, NOW)
        self.assertEqual((s["median_s"], s["longest_s"]), (60.0, 600.0))
        events.append(ev(t0=NOW - 900, ack=NOW - 900 + 120))
        self.assertEqual(L.summary(events, NOW)["median_s"], 90.0)


class FormatTests(unittest.TestCase):
    def test_durations(self):
        cases = {0: "0s", 42: "42s", 59.9: "59s", 60: "1m", 125: "2m", 3600: "1h", 3900: "1h 5m", 7322: "2h 2m", None: "", float("nan"): "", True: ""}
        for v, want in cases.items():
            self.assertEqual(L.fmt_dur(v), want, v)

    def test_the_sentence(self):
        s = L.summary([ev(t0=NOW - 600, ack=NOW - 480), ev(status="unread", ack=None, t0=NOW - 200)], NOW)
        text = L.format_text(s)
        self.assertIn("waited on you 5m today over 2 waits", text)
        self.assertIn("1 waiting now", text)
        self.assertIn("median", text)

    def test_nothing(self):
        self.assertIn("nothing has waited on you", L.format_text(None))

    def test_one_wait_is_singular(self):
        self.assertIn("over 1 wait ", L.format_text(L.summary([ev(t0=NOW - 600, ack=NOW - 480)], NOW)) + " ")


if __name__ == "__main__":
    unittest.main()
