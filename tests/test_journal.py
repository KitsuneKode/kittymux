import json
import time
import multiprocessing
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_journal as J  # noqa: E402

SID = "0a1b2c3d-0000-4000-8000-000000000001"


def obs(**kw):
    d = {"agent": "claude", "sid": SID, "cwd": "/w/a", "tab": "my tab", "argv": ["claude", "--model", "x"], "state": "idle", "kitty_pid": 10, "wid": 7, "mode": "exact"}
    d.update(kw)
    return d


class ObserveTests(unittest.TestCase):
    def test_a_session_accumulates_runs_and_working_time(self):
        r = {}
        self.assertTrue(J.observe(r, obs(state="idle"), 1000.0))
        J.observe(r, obs(state="working"), 1010.0)
        J.observe(r, obs(state="working"), 1100.0)                     # still working: only `last` moves
        self.assertFalse(J.observe(r, obs(state="working"), 1110.0))
        J.observe(r, obs(state="done"), 1130.0)                        # 120 s of work, one finished run
        J.observe(r, obs(state="working"), 1200.0)
        J.observe(r, obs(state="idle"), 1230.0)                        # 30 s more, not a completion
        rec = r[f"claude:{SID}"]
        self.assertEqual((rec["turns"], rec["work_s"], rec["state"], rec["last"]), (1, 150, "idle", 1230))
        self.assertEqual((rec["first"], rec["cwd"], rec["argv"]), (1000, "/w/a", ["claude", "--model", "x"]))

    def test_a_window_bound_record_becomes_the_sessions_record_when_its_id_appears(self):
        r = {}
        J.observe(r, obs(sid=None, state="working"), 1000.0)
        self.assertEqual(list(r), ["claude:w10.7"])
        J.observe(r, obs(sid=SID, state="working"), 1030.0)
        self.assertEqual(list(r), [f"claude:{SID}"])
        self.assertEqual(r[f"claude:{SID}"]["first"], 1000)              # its history came with it
        self.assertEqual(r[f"claude:{SID}"]["sid"], SID)

    def test_fields_update_when_they_change_and_empty_values_do_not_erase(self):
        r = {}
        J.observe(r, obs(), 1.0)
        self.assertTrue(J.observe(r, obs(cwd="/w/b", tab="renamed"), 2.0))
        J.observe(r, obs(cwd="", tab=None, argv=None), 3.0)
        rec = r[f"claude:{SID}"]
        self.assertEqual((rec["cwd"], rec["tab"], rec["argv"]), ("/w/b", "renamed", ["claude", "--model", "x"]))

    def test_closing_finalises_work_and_marks_closed(self):
        r = {}
        J.observe(r, obs(state="working"), 1000.0)
        self.assertFalse(J.close_missing(r, 99, set(), 1100.0))          # another kitty's windows are not ours to close
        self.assertTrue(J.close_missing(r, 10, set(), 1100.0))
        rec = r[f"claude:{SID}"]
        self.assertEqual((rec["open"], rec["work_s"], rec["state"]), (False, 100, ""))
        self.assertFalse(J.close_missing(r, 10, set(), 1200.0))

    def test_prune_by_age_and_count(self):
        r = {f"a:{i}": {"agent": "a", "last": 1000.0 + i} for i in range(J.RECORD_MAX + 20)}
        r["old"] = {"agent": "a", "last": 0}
        J.prune(r, 1000.0 + J.MAX_AGE_S - 5)
        self.assertNotIn("old", r)
        self.assertEqual(len(r), J.RECORD_MAX)
        self.assertIn(f"a:{J.RECORD_MAX + 19}", r)                        # the newest survive


class FileTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_roundtrip_private_atomic_and_newest_wins_on_merge(self):
        a, b = {}, {}
        J.observe(a, obs(), 1000.0)
        self.assertTrue(J.flush(self.d, a, 1000.0))
        self.assertEqual(stat.S_IMODE(os.stat(J.path_for(self.d)).st_mode), 0o600)
        J.observe(b, obs(state="working", kitty_pid=11), 2000.0)         # another kitty saw the same session later
        J.flush(self.d, b, 2000.0)
        J.flush(self.d, a, 2001.0)                                        # a stale copy must not overwrite the newer record
        rec = J.load(self.d)[f"claude:{SID}"]
        self.assertEqual((rec["kitty_pid"], rec["state"], rec["last"]), (11, "working", 2000))
        self.assertEqual([f for f in os.listdir(self.d) if f.endswith(".tmp")], [])

    def test_bad_or_missing_file_is_empty_and_flush_never_raises(self):
        self.assertEqual(J.load(self.d), {})
        with open(J.path_for(self.d), "w") as f:
            f.write("{not json")
        self.assertEqual(J.load(self.d), {})
        self.assertFalse(J.flush("/proc/not/writable", {"k": {"agent": "a"}}, 1.0))

    def test_the_file_stays_bounded(self):
        mine = {f"a:{i}": {"agent": "a", "last": 1000.0 + i, "cwd": "/x", "argv": ["a"]} for i in range(J.RECORD_MAX * 3)}
        J.flush(self.d, mine, 5000.0)
        self.assertEqual(len(J.load(self.d)), J.RECORD_MAX)


def _w(args):
    d, base = args
    for i in range(20):
        r = {}
        J.observe(r, obs(sid=f"{base:08x}-0000-4000-8000-{i:012x}", kitty_pid=base, wid=i), 1000.0 + i)
        for _ in range(200):                                 # flush gives up after 0.25 s on a busy lock and says False; the scanner keeps its record dirty and retries on the next tick
            if J.flush(d, r, 1000.0 + i):
                break
            time.sleep(0.01)


class ConcurrencyTests(unittest.TestCase):
    def test_several_processes_share_one_journal_without_losing_records(self):
        d = tempfile.mkdtemp()
        with multiprocessing.get_context("fork").Pool(4) as pool:
            pool.map(_w, [(d, k) for k in range(1, 5)])
        self.assertEqual(len(J.load(d)), 80)
        with open(J.path_for(d)) as f:
            json.load(f)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.key = f"claude:{SID}"

    def seed(self, **kw):
        recs = {}
        J.observe(recs, obs(**kw), 1000.0)
        J.flush(self.d, recs, 1000.0)
        return recs

    def test_a_pin_made_by_the_cli_survives_the_scanners_stale_copy_and_newer_activity(self):
        stale = self.seed()                                              # the scanner's in-memory copy: it has never heard of a pin
        self.assertTrue(J.set_flag(self.d, self.key, "pinned", True, 2000.0))
        J.observe(stale, obs(state="working"), 3000.0)                   # the scanner keeps observing: a newer `last`, no flag
        J.flush(self.d, stale, 3000.0)
        rec = J.load(self.d)[self.key]
        self.assertTrue(rec["pinned"])                                    # the newer activity won, the pin was not erased
        self.assertEqual((rec["state"], rec["last"]), ("working", 3000))
        self.assertTrue(J.set_flag(self.d, self.key, "pinned", False, 4000.0))
        J.flush(self.d, stale, 4100.0)                                    # …and an unpin is not undone by the same stale copy either
        self.assertFalse(J.load(self.d)[self.key]["pinned"])

    def test_pinning_unsettles_and_unknown_keys_or_fields_are_refused(self):
        self.seed()
        self.assertTrue(J.set_flag(self.d, self.key, "settled", True, 2000.0))
        self.assertTrue(J.load(self.d)[self.key]["settled"])
        self.assertTrue(J.set_flag(self.d, self.key, "pinned", True, 2001.0))
        self.assertFalse(J.load(self.d)[self.key]["settled"])
        self.assertFalse(J.set_flag(self.d, "claude:nope", "pinned", True))
        with self.assertRaises(ValueError):
            J.set_flag(self.d, self.key, "last", True)                   # only the two user flags can be set

    def test_pinned_records_are_exempt_from_the_age_and_size_limits(self):
        recs = {f"a:{i}": {"agent": "a", "last": 1000.0 + i} for i in range(J.RECORD_MAX + 20)}
        recs["old-pinned"] = {"agent": "a", "last": 0, "pinned": True}
        recs["old"] = {"agent": "a", "last": 0}
        J.prune(recs, 1000.0 + J.MAX_AGE_S + 5)
        self.assertIn("old-pinned", recs)
        self.assertNotIn("old", recs)
        self.assertEqual(len([k for k, r in recs.items() if not r.get("pinned")]), J.RECORD_MAX)

    def test_lifecycle_states(self):
        now = 10 * 86400.0
        lc = lambda **kw: J.lifecycle(dict(kw), now)                      # noqa: E731
        self.assertEqual(lc(pinned=True, running=True), "pinned")
        self.assertEqual(lc(pinned=True, running=False, last=0), "pinned")  # pinned beats age
        self.assertEqual(lc(running=True, last=now), "running")
        self.assertEqual(lc(running=False, last=now - 3600), "recent")
        self.assertEqual(lc(running=False, last=now - 3600, settled=True), "settled")     # settled by hand
        self.assertEqual(lc(running=False, last=now - 4 * 86400), "settled")              # untouched for > 3 days
        self.assertEqual(J.lifecycle({"running": False, "last": now - 5 * 86400}, now, settle_after=10 * 86400), "recent")

    def test_the_record_of_a_running_window_is_found_by_kitty_and_window(self):
        recs = {}
        J.observe(recs, obs(kitty_pid=10, wid=7), 1000.0)
        J.observe(recs, obs(sid=None, agent="codex", argv=["codex"], kitty_pid=10, wid=8), 1000.0)
        self.assertEqual(J.key_for_window(recs, 10, 7), f"claude:{SID}")
        self.assertEqual(J.key_for_window(recs, 10, "8"), "codex:w10.8")
        self.assertIsNone(J.key_for_window(recs, 11, 7))
        J.close_missing(recs, 10, set(), 2000.0)
        self.assertIsNone(J.key_for_window(recs, 10, 7))                  # a closed window has no running record


class RedactionTests(unittest.TestCase):
    def test_secret_flags_and_credential_shaped_values_are_hidden_but_ordinary_flags_are_kept(self):
        r = J.redact_argv
        self.assertEqual(r(["claude", "--model", "opus", "--resume", SID]), ["claude", "--model", "opus", "--resume", SID])
        self.assertEqual(r(["x", "--api-key", "abc123", "--model", "m"]), ["x", "--api-key", "<redacted>", "--model", "m"])
        self.assertEqual(r(["x", "--token=abc123"]), ["x", "--token=<redacted>"])
        # credential-SHAPED values are built at run time from filler: no real (or key-looking) literal belongs in the repository
        shaped_a, shaped_b = "sbp_" + "x" * 24, "sk-" + "y" * 30
        self.assertEqual(r(["mcp", "--access-token", shaped_a]), ["mcp", "--access-token", "<redacted>"])
        self.assertEqual(r(["x", shaped_b]), ["x", "<redacted>"])
        self.assertEqual(r(["x", "--password"]), ["x", "--password"])                 # a flag at the end has no value to hide
        self.assertEqual(r([5, None]), ["5", "None"])                                  # never raises on odd input

    def test_the_stored_journal_keeps_the_real_command_so_recovery_works(self):
        d = tempfile.mkdtemp()
        recs = {}
        J.observe(recs, obs(argv=["x", "--api-key", "abc123"]), 1.0)
        J.flush(d, recs, 1.0)
        self.assertEqual(J.load(d)[f"claude:{SID}"]["argv"], ["x", "--api-key", "abc123"])


class ReadBackTests(unittest.TestCase):
    def test_entries_insights_and_recoverable(self):
        proc = tempfile.mkdtemp()
        os.makedirs(os.path.join(proc, "10"))                             # kitty 10 is alive; 11 is not
        r = {}
        J.observe(r, obs(), 5000.0)
        J.observe(r, obs(sid=None, agent="codex", argv=["codex"], kitty_pid=11, wid=3, state="working"), 5000.0)
        J.observe(r, obs(sid="aaaaaaaa-0000-4000-8000-000000000001", agent="droid", argv=["droid"], kitty_pid=11, wid=4), 100.0)
        es = J.entries(r, 5100.0, 3600, proc)
        self.assertEqual([e["agent"] for e in es], ["claude", "codex"])      # the droid is older than the window
        self.assertEqual([e["running"] for e in es], [True, False])
        ins = J.insights(es)
        self.assertEqual((ins["sessions"], ins["running"]), (2, 1))
        self.assertEqual([e["agent"] for e in J.recoverable(es)], ["codex"])  # claude is running; codex's kitty is gone

    def test_missing_proc_is_unknown_and_keeps_positive_pid_running(self):
        with tempfile.TemporaryDirectory() as d:
            missing = os.path.join(d, "no-proc")
            self.assertTrue(J._alive(424242, missing))
            self.assertFalse(J._alive(0, missing))
            self.assertFalse(J._alive(-1, missing))

    def test_spans(self):
        self.assertEqual(J.parse_span("90m", 0), 5400)
        self.assertEqual(J.parse_span("2d", 0), 172800)
        self.assertEqual(J.parse_span("junk", 7), 7)
        self.assertEqual([J.human_span(s) for s in (5, 600, 5400, 8000, 300000)], ["5s", "10m", "1h30m", "2h13m", "3d"])


if __name__ == "__main__":
    unittest.main()
