"""Usage HUD regressions, importing the real system-Python module."""
import importlib.util
import json
import os
import time
import threading
from datetime import datetime
from types import SimpleNamespace
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "collectors"))
spec = importlib.util.spec_from_file_location("mux_usage_test", ROOT / "bin" / "mux-usage.py")
usage = importlib.util.module_from_spec(spec)
with patch.dict(os.environ, KITTYMUX_HOME=str(ROOT)):
    spec.loader.exec_module(usage)


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.tmp.cleanup)
        state = Path(self.tmp.name)
        for key, value in (("STATE_DIR", state), ("CACHE", state / "cache.json"),
                           ("HIST", state / "history.json"), ("LIVE", False)):
            p = patch.object(usage.C, key, value)
            p.start()
            self.addCleanup(p.stop)

    def test_history_records_exact_dated_daily_counters_not_display_text(self):
        providers = [
            {"name": "claude", "rows": [{"label": "week", "text": "9.9M tok"}],
             "daily": {"day": "2026-03-09", "claude_fresh": 1234}},
            {"name": "devin", "rows": [{"label": "today", "text": "1 sess · 2k tok"}],
             "daily": {"day": "2026-03-09", "devin_tok": 2345}}]
        mods = [SimpleNamespace(__name__=p["name"], collect=lambda p=p: p) for p in providers]
        with patch.object(usage, "load_collectors", return_value=mods):
            usage.get_data(True)
        hist = json.loads(usage.C.HIST.read_text())
        self.assertEqual(hist["2026-03-09"]["burn"], 3579)
        self.assertEqual(hist["2026-03-09"]["claude_fresh"], 1234)
        self.assertEqual(hist["2026-03-09"]["devin_tok"], 2345)
        providers[0]["daily"]["claude_fresh"] = 0
        with patch.object(usage, "load_collectors", return_value=mods[:1]):
            usage.get_data(True)
        self.assertEqual(json.loads(usage.C.HIST.read_text())["2026-03-09"]["burn"], 2345)

    def test_legacy_weekly_history_is_not_rendered_as_daily_burn(self):
        usage.C.HIST.write_text(json.dumps({"2026-03-08": {
            "claude_fresh": 9900000, "devin_tok": 2000, "burn": 9902000, "other": "preserved"}}))
        self.assertEqual(usage._sparkline("burn"), "")
        self.assertEqual(usage._week_chart("claude_fresh", usage.C_NAME), [])
        mod = SimpleNamespace(__name__="claude", collect=lambda: {
            "name": "claude", "rows": [], "daily": {"day": "2026-03-09", "claude_fresh": 17}})
        with patch.object(usage, "load_collectors", return_value=[mod]):
            usage.get_data(True)
        hist = json.loads(usage.C.HIST.read_text())
        self.assertNotIn("burn", hist["2026-03-08"])
        self.assertEqual(hist["2026-03-08"]["other"], "preserved")
        self.assertEqual(hist["2026-03-08"]["_legacy_counters"], {
            "claude_fresh": 9900000, "devin_tok": 2000, "burn": 9902000})
        self.assertEqual(hist["2026-03-09"]["burn"], 17)

    def test_history_chart_uses_calendar_dates_across_dst(self):
        old = os.environ.get("TZ")
        with patch.dict(os.environ, TZ="America/New_York"):
            time.tzset()
            try:
                now = datetime.fromisoformat("2026-03-09T04:30:00+00:00").timestamp()
                usage.C.HIST.write_text(json.dumps({"2026-03-08": {
                    "_daily_version": 2, "claude_fresh": 17, "burn": 17}}))
                with patch("time.time", return_value=now):
                    chart = usage._week_chart("claude_fresh", usage.C_NAME)
                self.assertIn("T W T F S S M", chart[0][0])
            finally:
                if old is None:
                    os.environ.pop("TZ", None)
                else:
                    os.environ["TZ"] = old
                time.tzset()

    def test_stuck_live_loader_records_a_failed_attempt_for_cooldown(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        def stuck(cached):
            entered.set()
            release.wait(2)
            finished.set()
            return {}
        mod = SimpleNamespace(__name__="claude", collect=lambda: {
            "name": "claude", "rows": []}, live=stuck)
        with patch("time.time", return_value=1800000000.0) as clock:
            data, loader = usage._seed(True, [mod])
            try:
                self.assertTrue(entered.wait(1))
                local = loader.q.get(timeout=1)
                loader.q.put(local)
                clock.return_value += usage.STUCK_S + 3
                usage._drain(loader, data)
                live = json.loads(usage.C.CACHE.read_text())["live"]["claude"]
                self.assertEqual(live["attempt_ts"], clock.return_value)
                self.assertIn("timed out", live["error"])
                self.assertFalse(loader.alive())
            finally:
                release.set()
                self.assertTrue(finished.wait(1))

    def test_sync_cache_persists_empty_failed_live_attempts_and_safe_errors(self):
        mod = SimpleNamespace(__name__="claude", collect=lambda: {
            "name": "claude", "rows": [{"label": "week", "text": "local rows"}]})
        calls = []
        def live(cached):
            if usage.C.live_fresh(cached):
                return cached
            calls.append(1)
            raise RuntimeError("fake credential must not appear")
        mod.live = live
        with patch.object(usage, "load_collectors", return_value=[mod]), \
                patch.object(usage.C, "LIVE", True), patch("time.time", return_value=1800000000.0) as clock:
            first = usage.get_data(True)
            self.assertEqual(first["live"]["claude"]["attempt_ts"], clock.return_value)
            self.assertIn("live unavailable", " ".join(r[0] for r in usage.build_detail(first["providers"][0])))
            self.assertNotIn("credential", json.dumps(first))
            clock.return_value += 61
            second = usage.get_data(False)
            self.assertEqual(second["live"], first["live"])
            self.assertEqual(len(calls), 1)
            clock.return_value += usage.C.LIVE_TTL
            usage.get_data(True)
            self.assertEqual(len(calls), 2)

    def test_progressive_loader_persists_failure_and_keeps_cached_rows_visible(self):
        old = {"ts": 1, "rows": [{"label": "wk", "pct": 17}]}
        mod = SimpleNamespace(__name__="claude", collect=lambda: {
            "name": "claude", "rows": [{"label": "week", "text": "local rows"}]},
            live=lambda cached: usage.C.live_failure(cached, "request timed out"))
        for local_first in (False, True):
            with self.subTest(local_first=local_first):
                usage.C.CACHE.write_text(json.dumps({"ts": 1, "providers": [], "live": {"claude": old}}))
                with patch("time.time", return_value=1800000000.0):
                    data, loader = usage._seed(True, [mod])
                    events = [loader.q.get(timeout=2) for _ in range(2)]
                    # Local data must not erase live diagnostics in either order.
                    for event in sorted(events, key=lambda e: e[0], reverse=local_first):
                        loader.q.put(event)
                    usage._drain(loader, data)
                self.assertFalse(loader.alive())
                persisted = json.loads(usage.C.CACHE.read_text())
                self.assertEqual(persisted["live"]["claude"]["ts"], 1)
                self.assertEqual(persisted["live"]["claude"]["attempt_ts"], 1800000000.0)
                self.assertEqual(data["providers"][0]["rows"][0]["pct"], 17)
                for view in (usage.build_summary(data, 0), usage.build_detail(data["providers"][0]), usage.build_all(data)):
                    text = " ".join(r[0] for r in view)
                    self.assertIn("live unavailable", text)
                    self.assertIn("17%", text)

    def test_progressive_loader_persists_failure_without_cached_rows(self):
        mod = SimpleNamespace(__name__="cursor", collect=lambda: {
            "name": "cursor", "rows": []}, live=lambda cached: usage.C.live_failure(cached, "credentials unavailable"))
        data, loader = usage._seed(True, [mod])
        for event in [loader.q.get(timeout=2) for _ in range(2)]:
            loader.q.put(event)
        usage._drain(loader, data)
        self.assertIn("attempt_ts", json.loads(usage.C.CACHE.read_text())["live"]["cursor"])

    def test_elapsed_clock_never_reports_exhausted_quota(self):
        p = {"name": "claude", "rows": [{"label": "5h", "pct": 99, "clock": True}]}
        data = {"ts": 0, "providers": [p]}
        views = (usage.build_summary(data, 0), usage.build_detail(p), usage.build_all(data))
        for view in views:
            text = " ".join(row[0] for row in view)
            self.assertNotIn("exhausted", text)
            self.assertNotIn("maxed", text)
            self.assertIn("elapsed", text)
        p["rows"].append({"label": "cap", "pct": 100})
        self.assertIn("maxed", " ".join(r[0] for r in usage.build_summary(data, 0)))

    def test_refresh_recovers_error_pending_and_empty_providers(self):
        data = {"providers": [
            {"name": "claude", "rows": [], "err": "failed"},
            {"name": "cursor", "rows": [], "pending": True},
            {"name": "devin", "rows": []}]}
        usage._respawn(usage.Loader([]), data)
        self.assertEqual([p["name"] for p in data["providers"]],
                         ["claude", "cursor", "devin"])
        self.assertTrue(all(p["pending"] for p in data["providers"]))


if __name__ == "__main__":
    unittest.main()
