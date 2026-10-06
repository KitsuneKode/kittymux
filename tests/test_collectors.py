"""Real collector entry points with isolated files, clocks and fake transport."""
import importlib
import json
import os
import subprocess
import sqlite3
import stat
import threading
import shutil
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from contextlib import closing
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "collectors"))
common = importlib.import_module("_common")
claude, codex, cursor, devin = [importlib.import_module(n) for n in
                              ("claude", "codex", "cursor", "devin")]
RESPONSES = {
    claude: {"five_hour": {"utilization": 25}},
    cursor: {"planUsage": {"totalPercentUsed": 25}},
    devin: {"userStatus": {"planStatus": {"dailyQuotaRemainingPercent": 75}}},
}


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        for mod in (common, claude, codex, cursor, devin):
            p = patch.object(mod, "HOME", self.home)
            p.start()
            self.addCleanup(p.stop)
        p = patch("time.time", return_value=1800000000.0)
        self.clock = p.start()
        self.addCleanup(p.stop)

    def test_file_disappearing_during_sort_does_not_fail_the_provider(self):
        paths = ((claude, ".claude/projects/demo"), (devin, ".local/share/devin/cli/transcripts"))
        original = Path.stat
        for mod, folder in paths:
            with self.subTest(provider=mod.__name__):
                self.write(folder + "/vanished.jsonl" if mod is claude else folder + "/vanished.json", "{}")
                self.write(folder + "/kept.jsonl" if mod is claude else folder + "/kept.json", "{}")
                def raced(path, *a, **kw):
                    if path.name.startswith("vanished"):
                        raise FileNotFoundError("synthetic deleted file")
                    return original(path, *a, **kw)
                with patch.object(Path, "stat", raced):
                    data = mod.collect()
                self.assertEqual(data["name"], mod.__name__)
                self.assertNotIn("err", data)

    def write(self, name, payload):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
        return path

    def credentials(self, token):
        self.write(".claude/.credentials.json", json.dumps({"claudeAiOauth": {"accessToken": token}}))
        self.write(".config/cursor/auth.json", json.dumps({"accessToken": token}))
        self.write(".local/share/devin/credentials.toml", "windsurf_api_key = " + json.dumps(token))

    def timezone(self, zone):
        old = os.environ.get("TZ")
        os.environ["TZ"] = zone
        time.tzset()
        def restore():
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()
        self.addCleanup(restore)

    def event(self, timestamp, fresh):
        return json.dumps({"type": "assistant", "timestamp": timestamp,
                           "message": {"usage": {"input_tokens": fresh,
                                                  "cache_read_input_tokens": 999}}}) + "\n"

    def test_claude_daily_metric_uses_local_midnight_not_week_or_cached_tokens(self):
        self.timezone("America/New_York")
        self.clock.return_value = datetime.fromisoformat("2026-03-09T04:30:00+00:00").timestamp()
        path = self.write(".claude/projects/demo/session.jsonl",
                          self.event("2026-03-09T03:59:59Z", 9000) +
                          self.event("2026-03-09T04:00:00Z", 400) +
                          self.event("2026-03-09T04:10:00Z", 834) +
                          self.event("2026-03-09T05:00:00Z", 8888))
        os.utime(path, (self.clock.return_value, self.clock.return_value))
        result = claude.collect()
        self.assertEqual(result["daily"], {"day": "2026-03-09", "claude_fresh": 1234})
        self.assertIn("10k tok", next(r["text"] for r in result["rows"] if r["label"] == "week"))
        self.assertIn("clock", result["rows"][0])

    def test_claude_five_hour_boundary_opens_new_window_across_dst(self):
        self.timezone("America/New_York")
        self.clock.return_value = datetime.fromisoformat("2026-03-08T11:31:00+00:00").timestamp()
        path = self.write(".claude/projects/demo/session.jsonl",
                          self.event("2026-03-08T06:30:00Z", 10) +
                          self.event("2026-03-08T11:30:00Z", 20))
        os.utime(path, (self.clock.return_value, self.clock.return_value))
        result = claude.collect()
        self.assertAlmostEqual(result["rows"][0]["pct"], 1 / 3)
        self.assertIn("20 tok", result["rows"][1]["text"])
        self.assertEqual(result["daily"]["claude_fresh"], 30)

    def test_devin_mtime_activity_is_not_persisted_as_exact_daily_burn(self):
        self.timezone("America/New_York")
        self.clock.return_value = datetime.fromisoformat("2026-03-09T04:30:00+00:00").timestamp()
        for name, stamp, tokens in (("old", "2026-03-09T03:59:59+00:00", 9000),
                                    ("today", "2026-03-09T04:00:00+00:00", 1234),
                                    ("future", "2026-03-09T05:00:00+00:00", 8000)):
            path = self.write(f".local/share/devin/cli/transcripts/{name}.json", json.dumps({
                "final_metrics": {"total_prompt_tokens": tokens, "total_completion_tokens": 67}}))
            stamp = datetime.fromisoformat(stamp).timestamp()
            os.utime(path, (stamp, stamp))
        result = devin.collect()
        self.assertNotIn("daily", result)
        self.assertIn("1k tok", result["rows"][0]["text"])
        self.assertIn("modified today", result["note"])
        self.clock.return_value = datetime.fromisoformat("2026-03-10T04:30:00+00:00").timestamp()
        self.assertNotIn("daily", devin.collect())

    def test_resumed_devin_transcript_does_not_double_count_daily_history(self):
        self.timezone("UTC")
        path = self.write(".local/share/devin/cli/transcripts/resumed.json", json.dumps({
            "final_metrics": {"total_prompt_tokens": 1000}}))
        self.clock.return_value = datetime.fromisoformat("2026-03-09T12:00:00+00:00").timestamp()
        os.utime(path, (self.clock.return_value, self.clock.return_value))
        self.assertNotIn("daily", devin.collect())
        path.write_text(json.dumps({"final_metrics": {"total_prompt_tokens": 1100}}))
        self.clock.return_value += 86400
        os.utime(path, (self.clock.return_value, self.clock.return_value))
        self.assertNotIn("daily", devin.collect())

    def test_cursor_local_lines_observe_midnight_and_current_time(self):
        self.timezone("America/New_York")
        self.clock.return_value = datetime.fromisoformat("2026-03-09T04:30:00+00:00").timestamp()
        state = self.home / ".config/Cursor/User/globalStorage/state.vscdb"
        state.parent.mkdir(parents=True)
        with closing(sqlite3.connect(state)) as db, db:
            db.execute("create table ItemTable (key text, value text)")
            db.execute("insert into ItemTable values ('cursorAuth/stripeMembershipType', 'pro')")
        tracking = self.home / ".cursor/ai-tracking/ai-code-tracking.db"
        tracking.parent.mkdir(parents=True)
        with closing(sqlite3.connect(tracking)) as db, db:
            db.execute("create table scored_commits (composerLinesAdded int, tabLinesAdded int, humanLinesAdded int, linesAdded int, scoredAt int)")
            for stamp, lines in (("2026-03-09T03:59:59+00:00", 100),
                                  ("2026-03-09T04:00:00+00:00", 10),
                                  ("2026-03-09T05:00:00+00:00", 500)):
                db.execute("insert into scored_commits values (?, 0, 0, ?, ?)",
                           (lines, lines, datetime.fromisoformat(stamp).timestamp() * 1000))
        self.assertEqual(cursor.collect()["rows"][1]["text"], "10 lines · 100% AI")

    def test_codex_local_rollout_uses_real_snapshot(self):
        self.write(".codex/sessions/rollout-2026-01.jsonl", "broken\n" + json.dumps({
            "payload": {"rate_limits": {"primary": {"used_percent": 0.5},
                                         "secondary": {"used_percent": 99}, "plan_type": "plus"}}}))
        result = codex.collect()
        self.assertEqual([r["pct"] for r in result["rows"]], [0.5, 99])
        self.assertEqual(result["note"], "plus")

    def test_codex_rows_carry_numeric_window_and_reset_for_the_panel(self):
        self.clock.return_value = 1_700_000_000.0
        self.write(".codex/sessions/rollout-2026-01.jsonl", json.dumps({
            "payload": {"rate_limits": {"primary": {"used_percent": 99, "resets_at": 1_700_000_000 + 13800},
                                         "secondary": {"used_percent": 63}, "plan_type": "plus"}}}))
        five, week = codex.collect()["rows"]
        self.assertEqual((five["window_s"], week["window_s"]), (5 * 3600, 7 * 86400))
        self.assertIn("rem_s", five)
        self.assertNotIn("rem_s", week)                         # no reset time on record: nothing is invented

    def test_claude_rows_carry_numeric_sidecars_next_to_the_text(self):
        self.timezone("America/New_York")
        self.clock.return_value = datetime.fromisoformat("2026-03-09T04:30:00+00:00").timestamp()
        path = self.write(".claude/projects/demo/session.jsonl",
                          self.event("2026-03-09T04:00:00Z", 400) + self.event("2026-03-09T04:10:00Z", 834))
        os.utime(path, (self.clock.return_value, self.clock.return_value))
        rows = {r["label"]: r for r in claude.collect()["rows"]}
        self.assertEqual((rows["5h"]["window_s"], round(rows["5h"]["rem_s"])), (5 * 3600, 5 * 3600 - 30 * 60))
        self.assertEqual((rows["win"]["tok"], rows["win"]["turns"], rows["win"]["cached"]), (1234, 2, 1998))
        self.assertEqual((rows["week"]["tok"], rows["week"]["sess"]), (1234, 1))
        self.assertIn("1k tok", rows["week"]["text"])           # the text the overlay prints is unchanged

    def test_claude_closed_window_is_a_state(self):
        self.timezone("America/New_York")
        self.clock.return_value = datetime.fromisoformat("2026-03-09T12:30:00+00:00").timestamp()
        path = self.write(".claude/projects/demo/session.jsonl", self.event("2026-03-09T04:00:00Z", 400))
        os.utime(path, (self.clock.return_value, self.clock.return_value))
        self.assertEqual(claude.collect()["rows"][0].get("state"), "closed")

    def test_malformed_credential_documents_fail_safely_without_network(self):
        self.write(".claude/.credentials.json", '{"claudeAiOauth": ["fake"]}')
        self.write(".config/cursor/auth.json", '["fake"]')
        self.write(".local/share/devin/credentials.toml", 'windsurf_api_key = ["fake"]')
        for mod in RESPONSES:
            with self.subTest(provider=mod.__name__), patch("subprocess.run") as run:
                result = mod.live({})
                self.assertEqual(result["attempt_ts"], self.clock.return_value)
                self.assertIn("credential", result["error"])
                run.assert_not_called()

    def test_malformed_live_responses_are_cached_as_failures(self):
        self.credentials("fake-shape-token")
        for mod, data in ((claude, ["unexpected"]), (cursor, {"planUsage": ["unexpected"]}),
                          (devin, {"userStatus": ["unexpected"]})):
            with self.subTest(provider=mod.__name__), patch("subprocess.run", return_value=
                    subprocess.CompletedProcess([], 0, json.dumps(data), "")):
                result = mod.live({})
                self.assertEqual(result["attempt_ts"], self.clock.return_value)
                self.assertIn("error", result)
                self.assertEqual(result["rows"], [])

    def test_claude_utilization_is_percentage_even_at_or_below_one(self):
        self.credentials("fake-percent-token")
        for percent in (0, 0.5, 1, 1.5, 100):
            with self.subTest(percent=percent), patch("subprocess.run", return_value=
                    subprocess.CompletedProcess([], 0, json.dumps({"five_hour": {"utilization": percent}}), "")):
                self.assertEqual(claude.live({})["rows"][0]["pct"], percent)

    def test_devin_proto_zero_remaining_with_reset_is_exhausted_not_absent(self):
        self.credentials("fake-proto-token")
        response = {"userStatus": {"planStatus": {
            "dailyQuotaResetAtUnix": "1800003600",
            "weeklyQuotaResetAtUnix": "1800086400"}}}
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, json.dumps(response), "")):
            rows = devin.live({})["rows"]
        self.assertEqual([(r["label"], r["pct"]) for r in rows], [("day", 100), ("wk", 100)])

    def test_failed_fetch_keeps_last_success_and_cools_down_attempts(self):
        self.credentials("fake-cache-token")
        for mod in RESPONSES:
            for failure in (subprocess.CompletedProcess([], 22, "", "secret stderr"),
                            subprocess.CompletedProcess([], 0, "not-json", ""),
                            subprocess.CompletedProcess([], 0, "{}", ""),
                            subprocess.TimeoutExpired("curl", 3)):
                with self.subTest(provider=mod.__name__, failure=type(failure).__name__):
                    self.clock.return_value = 1800000000.0
                    old = {"ts": 1799999000.0, "rows": [{"label": "cached", "pct": 17}]}
                    kw = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
                    with patch("subprocess.run", **kw) as run:
                        failed = mod.live(old)
                        self.assertEqual(failed["ts"], old["ts"])
                        self.assertEqual(failed["rows"], old["rows"])
                        self.assertEqual(failed["attempt_ts"], 1800000000.0)
                        self.assertIn("error", failed)
                        self.assertNotIn("secret", failed["error"])
                        self.clock.return_value += 60
                        self.assertEqual(mod.live(failed), failed)
                        self.assertEqual(run.call_count, 1)
                        self.clock.return_value = failed["attempt_ts"] + common.LIVE_TTL
                        mod.live(failed)
                        self.assertEqual(run.call_count, 2)
                    self.assertNotIn("attempt_ts", old)

    def test_missing_credentials_cache_failure_without_network(self):
        for mod in RESPONSES:
            with self.subTest(provider=mod.__name__), patch("subprocess.run") as run:
                result = mod.live({})
                self.assertEqual(result["attempt_ts"], 1800000000.0)
                self.assertEqual(result["ts"], 0)
                self.assertEqual(result["rows"], [])
                self.assertIn("credential", result["error"])
                self.assertEqual(mod.live(result), result)
                run.assert_not_called()

    def test_live_success_clears_error_and_legacy_success_timestamp_is_respected(self):
        self.credentials("fake-success-token")
        for mod, response in RESPONSES.items():
            with self.subTest(provider=mod.__name__), patch("subprocess.run", return_value=
                    subprocess.CompletedProcess([], 0, json.dumps(response), "")) as run:
                legacy = {"ts": 1799999999.0, "rows": [{"label": "old", "pct": 17}]}
                self.assertEqual(mod.live(legacy), legacy)
                run.assert_not_called()
                success = mod.live(dict(legacy, ts=0, error="old failure"))
                self.assertEqual(success["ts"], 1800000000.0)
                self.assertEqual(success["attempt_ts"], success["ts"])
                self.assertNotIn("error", success)

    def test_live_tokens_and_bodies_use_escaped_stdin_not_argv(self):
        token = 'fake-"\\token\t--config evil'
        self.credentials(token)
        for mod, response in RESPONSES.items():
            with self.subTest(provider=mod.__name__):
                with patch("subprocess.run", return_value=subprocess.CompletedProcess(
                        [], 0, json.dumps(response), "")) as run:
                    result = mod.live({})
                self.assertEqual(result["rows"][0]["pct"], 25)
                args, kw = run.call_args
                self.assertNotIn(token, " ".join(args[0]))
                self.assertIn("--config", args[0])
                self.assertIn("-", args[0])
                config = dict((k.strip(), json.loads(v.strip())) for k, v in
                              (line.split("=", 1) for line in kw["input"].splitlines()))
                if mod is devin:
                    self.assertEqual(json.loads(config["data"])["metadata"]["apiKey"], token)
                else:
                    headers = [json.loads(line.split("=", 1)[1].strip()) for line in
                               kw["input"].splitlines() if line.startswith("header")]
                    self.assertIn("Authorization: Bearer " + token, headers)
                self.assertNotIn("-k", args[0])
                self.assertIn("--max-time", args[0])
                self.assertEqual(kw["timeout"], 5 if mod is claude else 6)

    def test_header_tokens_reject_crlf_without_spawning_curl(self):
        self.credentials("fake\r\nX-Injected: bad")
        for mod in (claude, cursor):
            with self.subTest(provider=mod.__name__), patch("subprocess.run") as run:
                result = mod.live({})
                run.assert_not_called()
                self.assertIn("error", result)

    def test_body_token_newlines_are_json_data_not_curl_options(self):
        token = 'fake\nurl = "https://evil.invalid"\r\\'
        self.credentials(token)
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(
                [], 0, json.dumps(RESPONSES[devin]), "")) as run:
            self.assertTrue(devin.live({})["rows"])
        config = run.call_args.kwargs["input"]
        self.assertEqual(len(config.splitlines()), 3)
        body = json.loads(next(line.split("=", 1)[1].strip() for line in
                               config.splitlines() if line.startswith("data")))
        self.assertEqual(json.loads(body)["metadata"]["apiKey"], token)


class CommonTests(unittest.TestCase):
    def test_private_cache_is_atomic_and_private_before_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "cache.json"
            dest.write_text("old complete cache")
            replace = os.replace
            observed = []

            def commit(src, dst):
                observed.append(src)
                self.assertEqual(dest.read_text(), "old complete cache")
                self.assertEqual(stat.S_IMODE(Path(src).stat().st_mode), 0o600)
                self.assertEqual(Path(src).read_text(), "new complete cache")
                replace(src, dst)

            with patch.object(common, "STATE_DIR", root), patch.object(common.os, "replace", side_effect=commit):
                common.write_private(dest, "new complete cache")
            self.assertEqual(len(observed), 1)
            self.assertEqual(dest.read_text(), "new complete cache")
            self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o600)
            self.assertEqual(list(root.iterdir()), [dest])

    def test_private_cache_failure_preserves_old_data_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "cache.json"
            dest.write_text("old")
            with patch.object(common, "STATE_DIR", root), patch.object(common.os, "replace", side_effect=OSError):
                common.write_private(dest, "new")
            self.assertEqual(dest.read_text(), "old")
            self.assertEqual(list(root.iterdir()), [dest])

    def test_private_cache_does_not_follow_an_existing_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "unrelated"
            other.write_text("keep")
            dest = root / "cache.json"
            dest.symlink_to(other)
            with patch.object(common, "STATE_DIR", root):
                common.write_private(dest, "cache")
            self.assertEqual(other.read_text(), "keep")
            self.assertFalse(dest.is_symlink())
            self.assertEqual(dest.read_text(), "cache")

    def test_bad_or_future_live_timestamps_are_not_fresh(self):
        with patch("time.time", return_value=1000):
            for timestamp in (None, "oops", [], float("nan"), float("inf"), 1001, True):
                with self.subTest(timestamp=timestamp):
                    self.assertFalse(common.live_fresh({"attempt_ts": timestamp}))
            self.assertTrue(common.live_fresh({"attempt_ts": 999}))
            self.assertFalse(common.live_fresh({"attempt_ts": 700}))

    @unittest.skipUnless(shutil.which("curl"), "curl not installed")
    def test_real_curl_parser_delivers_escaped_credentials_only_as_data(self):
        seen = []

        class Endpoint(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.headers.get("Authorization"), self.rfile.read(
                    int(self.headers.get("Content-Length", "0"))).decode()))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok": true}')

            def log_message(self, *args):
                pass

        with HTTPServer(("127.0.0.1", 0), Endpoint) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            token = 'fake-"\\token--config'
            body = json.dumps({"apiKey": 'fake\nurl = "https://invalid.example"\r\\'})
            try:
                # Keep proxy configuration out of this loopback-only test.
                with patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}):
                    result = common.curl_json("http://127.0.0.1:" + str(server.server_port),
                        headers=["Authorization: Bearer " + token, "Content-Type: application/json"], body=body)
                self.assertEqual(result, {"ok": True})
                self.assertEqual(seen, [("Bearer " + token, body)])
            finally:
                server.shutdown()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
