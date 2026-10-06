import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_meters as M  # noqa: E402

TODAY = datetime(2026, 10, 7, 12, 0, 0)


def kinds(ms):
    return [m["kind"] for m in ms]


class ParseTests(unittest.TestCase):
    def test_waits_in_every_format_the_collectors_print(self):
        cases = {"resets in 3h 50m": 13800, "in 4d 19h": 4 * 86400 + 19 * 3600, "in 9m": 540, "in 2d": 172800, "in 5h": 18000,
                 "resets in 42 minutes": 2520, "hit · resets in 1h 5m": 3900, "resets now": 0, "now": 0}
        for text, want in cases.items():
            self.assertEqual(M.parse_wait(text), want, text)

    def test_things_that_are_not_waits(self):
        for text in ("", None, 5, "closed", "7d ago", "in the middle", "resets in soon", "in", "in  "):
            self.assertIsNone(M.parse_wait(text), repr(text))

    def test_ago(self):
        self.assertEqual(M.parse_ago("limit hit 7d ago"), 7 * 86400)
        self.assertEqual(M.parse_ago("3h ago"), 3 * 3600)
        self.assertIsNone(M.parse_ago("recently"))
        self.assertIsNone(M.parse_ago(None))


class CodexTests(unittest.TestCase):
    ROWS = [{"label": "5h", "pct": 99.0, "reset": "resets in 3h 50m"}, {"label": "wk", "pct": 63.0, "reset": "resets in 4d 19h"}]

    def test_two_quotas_with_their_windows_and_waits(self):
        ms = M.meters({"name": "codex", "rows": self.ROWS, "note": "plus"})
        self.assertEqual(kinds(ms), ["quota", "quota"])
        five, week = ms
        self.assertEqual((five["label"], five["pct"], five["rem_s"], five["window_s"]), ("5h", 99.0, 13800.0, 18000))
        self.assertEqual((week["label"], week["window_s"]), ("wk", 7 * 86400))
        self.assertEqual(week["rem_s"], 4 * 86400 + 19 * 3600)

    def test_numeric_sidecars_beat_the_text(self):
        rows = [{"label": "5h", "pct": 10, "reset": "resets in 9m", "rem_s": 1200, "window_s": 3600}]
        q = M.meters({"name": "codex", "rows": rows})[0]
        self.assertEqual((q["rem_s"], q["window_s"]), (1200, 3600))

    def test_plan_comes_from_a_short_note_and_a_sentence_is_not_a_plan(self):
        self.assertEqual(M.plan_of({"note": "plus"}), "plus")
        for note in ("not installed", "no usage data", "session totals · modified today", "", None, "two words"):
            self.assertEqual(M.plan_of({"note": note}), "", note)


class ClaudeTests(unittest.TestCase):
    def test_a_live_window_a_week_and_a_cap(self):
        rows = [{"label": "5h", "pct": 23.0, "clock": True, "reset": "resets in 3h 50m"},
                {"label": "win", "text": "1.2M tok (+3.0M cached) · 8 turns"},
                {"label": "week", "text": "109.0M tok (+6.0G cached) · 12 sess"},
                {"label": "cap", "text": "limit hit 7d ago"}]
        ms = M.meters({"name": "claude", "rows": rows})
        self.assertEqual(kinds(ms), ["quota", "counter", "counter", "state"])
        clock, win, week, cap = ms
        self.assertTrue(clock["clock"])
        self.assertEqual((week["value"], week["unit"]), (109e6, "tok"))
        self.assertIn("12 sess", week["chips"])
        self.assertIn("+6.0G cache", week["chips"])
        self.assertIn("8 turns", win["chips"])
        self.assertEqual((cap["tone"], cap["text"]), ("warm", "hit 7d ago"))

    def test_closed_and_idle_windows_are_muted_states(self):
        closed = M.meters({"name": "claude", "rows": [{"label": "5h", "text": "window closed · next msg opens new"}]})[0]
        idle = M.meters({"name": "claude", "rows": [{"label": "5h", "text": "idle"}]})[0]
        self.assertEqual((closed["kind"], closed["text"], closed["tone"]), ("state", "closed", "muted"))
        self.assertEqual(idle["text"], "idle")

    def test_an_active_cap_is_a_hot_state_plus_a_countdown(self):
        ms = M.meters({"name": "claude", "rows": [{"label": "cap", "pct": 100.0, "reset": "hit · resets in 1h 5m"}]})
        self.assertEqual(kinds(ms), ["quota", "state"])
        self.assertEqual(ms[1]["tone"], "hot")
        self.assertEqual(ms[0]["rem_s"], 3900)

    def test_the_week_series_rides_on_the_first_token_counter(self):
        hist = {"2026-10-01": {"claude_fresh": 5}, "2026-10-07": {"claude_fresh": 9}, "2026-10-04": {"claude_fresh": 2}}
        rows = [{"label": "week", "text": "5M tok · 3 sess"}]
        ms = M.meters({"name": "claude", "rows": rows}, hist, TODAY)
        self.assertEqual(ms[0]["series"], [5, None, None, 2, None, None, 9])


class OtherProviderTests(unittest.TestCase):
    def test_cursor_plan_lines_and_spend(self):
        rows = [{"label": "plan", "text": "pro · active"}, {"label": "today", "text": "412 lines · 38% AI"},
                {"label": "mo", "pct": 41.0, "reset": "resets in 12d 4h", "rem_s": 1e6},
                {"label": "spend", "text": "$18 (incl $4 bonus)", "stack": [2000, 400]}]
        ms = M.meters({"name": "cursor", "rows": rows})
        self.assertEqual(kinds(ms), ["quota", "counter", "state", "state", "spend"])
        quota, counter, plan, status, spend = ms
        self.assertEqual(quota["window_s"], 30 * 86400)
        self.assertEqual((counter["value"], counter["unit"], counter["chips"]), (412.0, "lines", ["38% AI"]))
        self.assertEqual((plan["text"], status["text"], status["tone"]), ("pro", "active", "calm"))
        self.assertEqual(spend["parts"], [2000, 400])

    def test_devin_totals_and_model(self):
        rows = [{"label": "today", "text": "5 sess · 37.6M tok"}, {"label": "model", "text": "SWE-2 Max"}]
        ms = M.meters({"name": "devin", "rows": rows, "note": "session totals · modified today"})
        self.assertEqual(kinds(ms), ["counter", "state"])
        self.assertEqual(ms[0]["value"], 37.6e6)
        self.assertEqual(ms[0]["chips"], ["5 sess"])
        self.assertEqual(ms[1]["text"], "SWE-2 Max")

    def test_an_unknown_provider_shape_still_draws_as_states(self):
        ms = M.meters({"name": "newcomer", "rows": [{"label": "balance", "text": "7 credits"}, {"label": "tier", "text": "free"}]})
        self.assertEqual([(m["kind"], m["label"], m["text"]) for m in ms], [("state", "balance", "7 credits"), ("state", "tier", "free")])


class RobustnessTests(unittest.TestCase):
    def test_junk_never_raises_and_never_leaks_a_non_finite_number(self):
        junk = [None, 5, "x", [], {}, {"rows": None}, {"rows": "x"}, {"rows": [None, 1, "a", [], {"pct": float("nan")}, {"pct": float("inf")},
                {"pct": True}, {"pct": "50"}, {"pct": -40}, {"pct": 4000}, {"label": "x" * 500, "text": "y" * 500}, {"label": None, "text": None}]},
                {"name": None, "rows": [{"label": "5h", "pct": 50, "rem_s": float("nan"), "window_s": "x"}]}]
        for p in junk:
            ms = M.meters(p)
            json.dumps(ms, allow_nan=False)
            for m in ms:
                if m["kind"] == "quota":
                    self.assertTrue(0.0 <= m["pct"] <= 100.0)
            M.summary(p)

    def test_text_from_a_provider_is_cleaned_and_bounded(self):
        ms = M.meters({"name": "x", "rows": [{"label": "pl\x1bn", "text": "pro\x1b[31m · act\x07ive" + "z" * 400}]})
        for m in ms:
            for v in (m.get("label"), m.get("text")):
                self.assertNotIn("\x1b", v or "")
                self.assertNotIn("\x07", v or "")
                self.assertLessEqual(len(v or ""), 60)

    def test_pct_is_clamped(self):
        q = M.meters({"rows": [{"label": "5h", "pct": 140}, {"label": "wk", "pct": -3}]})
        self.assertEqual([m["pct"] for m in q], [100.0, 0.0])

    def test_week_series_tolerates_a_bad_history_file(self):
        for hist in (None, [], "x", {"2026-10-07": "x"}, {"2026-10-07": {"claude_fresh": "9"}}, {}):
            self.assertIsNone(M.week_series(hist, "claude_fresh", TODAY))
        self.assertIsNone(M.week_series({"2026-10-07": {"claude_fresh": 1}}, "", TODAY))
        self.assertIsNone(M.week_series({"2026-10-07": {"claude_fresh": 0}}, "claude_fresh", TODAY))

    def test_history_file_is_read_and_a_missing_or_broken_one_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(M.load_history(d), {})
            with open(os.path.join(d, "agent-usage-history.json"), "w") as f:
                f.write("{not json")
            self.assertEqual(M.load_history(d), {})
            with open(os.path.join(d, "agent-usage-history.json"), "w") as f:
                json.dump({"2026-10-07": {"claude_fresh": 3}}, f)
            self.assertEqual(M.load_history(d), {"2026-10-07": {"claude_fresh": 3}})
            with open(os.path.join(d, "agent-usage-history.json"), "w") as f:
                f.write("[1, 2]")
            self.assertEqual(M.load_history(d), {})


class SummaryTests(unittest.TestCase):
    def test_status_and_tone(self):
        ok = M.summary({"name": "codex", "rows": [{"label": "5h", "pct": 99.0}, {"label": "wk", "pct": 63.0}]})
        self.assertEqual((ok["status"], ok["worst"], ok["tone"]), ("ok", 99.0, "warm"))
        maxed = M.summary({"name": "codex", "rows": [{"label": "5h", "pct": 100.0}]})
        self.assertEqual(maxed["tone"], "hot")
        calm = M.summary({"name": "codex", "rows": [{"label": "5h", "pct": 12.0}]})
        self.assertEqual(calm["tone"], "calm")
        states = M.summary({"name": "devin", "rows": [{"label": "model", "text": "x"}]})
        self.assertEqual((states["status"], states["worst"], states["tone"]), ("ok", None, "calm"))

    def test_clock_rows_are_not_a_used_share(self):
        s = M.summary({"name": "claude", "rows": [{"label": "5h", "pct": 95.0, "clock": True}]})
        self.assertIsNone(s["worst"])

    def test_pending_error_missing_and_empty(self):
        self.assertEqual(M.summary({"name": "a", "pending": True, "rows": []})["status"], "pending")
        self.assertEqual(M.summary({"name": "a", "err": "usage unavailable", "rows": []})["status"], "error")
        self.assertEqual(M.summary({"name": "a", "note": "collector error", "rows": []})["status"], "error")
        self.assertEqual(M.summary({"name": "a", "note": "not installed", "rows": []})["status"], "missing")
        self.assertEqual(M.summary({"name": "a", "rows": []})["status"], "empty")

    def test_a_hot_state_makes_a_provider_hot_even_without_a_share(self):
        s = M.summary({"name": "claude", "rows": [{"label": "cap", "pct": 100.0, "reset": "hit · resets in 1h"}]})
        self.assertEqual(s["tone"], "hot")

    def test_the_worst_provider_is_the_one_closest_to_a_wall(self):
        providers = [{"name": "codex", "rows": [{"label": "5h", "pct": 99.0}]}, {"name": "cursor", "rows": [{"label": "mo", "pct": 41.0}]},
                     {"name": "devin", "rows": [{"label": "model", "text": "x"}]}]
        self.assertEqual(M.worst_provider(providers)["name"], "codex")
        self.assertIsNone(M.worst_provider([providers[2]]))
        self.assertIsNone(M.worst_provider(None))


if __name__ == "__main__":
    unittest.main()
