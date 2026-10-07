import json
import multiprocessing
import os
import stat
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_inbox as I  # noqa: E402


def jload(path):
    with open(path) as f:
        return json.load(f)



def ev(kind="permission", agent="claude", w=7, t=1000.0, src="screen", **kw):
    return I.make_event(kind, agent, w, src, t, pid=kw.pop("pid", 42), **kw)


class ClassifyTests(unittest.TestCase):
    def test_what_agents_say(self):
        c = lambda title, body="": I.classify_text(title, body)[0]    # noqa: E731
        self.assertEqual(c("Claude Code", "Claude needs your permission to use Bash"), "permission")
        self.assertEqual(c("Codex", "Approval requested: run `rm -rf build`?"), "permission")
        self.assertEqual(c("Claude Code", "You've hit your usage limit. Resets at 5pm"), "limit")
        self.assertEqual(c("Devin", "Weekly limit reached"), "limit")
        self.assertEqual(c("Agent", "Do you want to proceed?"), "permission")
        self.assertEqual(c("Agent", "Run the following command? (y/n)"), "permission")
        self.assertEqual(c("Agent", "Which file should I edit?"), "question")
        self.assertEqual(c("Agent", "Waiting for your answer"), "question")
        self.assertEqual(c("Codex", "Agent turn complete"), "done")
        self.assertEqual(c("Droid", "Task finished"), "done")
        self.assertEqual(c("Agent", "Build failed: 3 errors"), "error")

    def test_the_idle_notice_is_not_a_completion(self):
        # Claude fires "waiting for your input" ~60 s after it finished: idleness, never a new "finished"
        self.assertEqual(I.classify_text("Claude Code", "Claude is waiting for your input"), ("info", "idle-notice"))

    def test_unrecognised_text_is_info_never_guessed_into_a_completion(self):
        for text in ("Hello", "Started a new session", "Context 41% used", ""):
            self.assertEqual(I.classify_text("Agent", text)[0], "info", text)

    def test_limit_beats_everything_and_permission_beats_question(self):
        self.assertEqual(I.classify_text("x", "permission needed but you hit your usage limit")[0], "limit")
        self.assertEqual(I.classify_text("x", "Do you approve this?")[0], "permission")


class ResetTests(unittest.TestCase):
    def test_relative(self):
        self.assertEqual(I.parse_reset("limit reached · resets in 10h 50m", 1000.0), 1000.0 + 10 * 3600 + 50 * 60)
        self.assertEqual(I.parse_reset("Resets in 2d 3h", 0.0), 2 * 86400 + 3 * 3600)

    def test_clock_time_rolls_to_the_next_occurrence(self):
        noon = 12 * 3600.0                                        # 1970-01-01 12:00 UTC
        self.assertEqual(I.parse_reset("resets at 5pm", noon), 17 * 3600.0)
        self.assertEqual(I.parse_reset("resets at 9:30am", noon), 86400 + 9 * 3600 + 30 * 60)   # already past today: tomorrow
        self.assertEqual(I.parse_reset("resets at 5pm", noon, tz_offset_s=3600), 16 * 3600.0)   # local time is utc+1: 5pm local = 16:00 utc

    def test_no_hint_is_none(self):
        for text in ("", "limit reached", "resets soon", "at 25pm"):
            self.assertIsNone(I.parse_reset(text, 1000.0), text)


class EventTests(unittest.TestCase):
    def test_sanitised_bounded_and_private(self):
        e = I.make_event("permission", "claude\x1b[31m", 3, "agent", 5.0, pid=1, title="T\n" * 100, body="rm -rf ~\x07" * 100)
        self.assertNotIn("\x1b", e["agent"])
        self.assertLessEqual(len(e["title"]), I.TITLE_MAX)
        self.assertLessEqual(len(e["body"]), I.BODY_MAX)
        self.assertNotIn("\n", e["title"])
        p = I.make_event("permission", "claude", 3, "agent", 5.0, pid=1, body="rm -rf ~", private=True)
        self.assertEqual(p["body"], "")

    def test_unknown_kind_becomes_info_and_severity_follows_kind(self):
        self.assertEqual(I.make_event("bogus", "a", 1, "screen", 1.0)["kind"], "info")
        self.assertEqual(ev("permission")["severity"], "needs-you")
        self.assertEqual(ev("limit")["severity"], "warn")
        self.assertEqual(ev("done")["severity"], "info")


class FoldTests(unittest.TestCase):
    def test_the_same_thing_reported_by_two_sources_is_one_event(self):
        a = ev("permission", src="agent", t=1000.0)
        b = ev("permission", src="screen", t=1003.0, confidence="low", body="Allow rm?")
        out = I.fold([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["count"], out[0]["sources"]), (2, ["agent", "screen"]))
        self.assertEqual(out[0]["body"], "Allow rm?")

    def test_after_the_window_or_for_another_window_it_is_a_new_event(self):
        a = ev("permission", t=1000.0)
        self.assertEqual(len(I.fold([a, ev("permission", t=1000.0 + I.MERGE_WINDOW_S + 1)])), 2)
        self.assertEqual(len(I.fold([a, ev("permission", w=8, t=1001.0)])), 2)

    def test_a_high_confidence_source_upgrades_a_low_one(self):
        out = I.fold([ev("done", src="screen", confidence="low", t=1.0), ev("done", src="hook", confidence="high", t=2.0)])
        self.assertEqual(out[0]["confidence"], "high")

    def test_a_limit_is_one_event_per_agent_per_reset_across_windows(self):
        reset = 1_000_000.0
        out = I.fold([ev("limit", w=1, t=10.0, reset_at=reset), ev("limit", w=2, t=12.0, reset_at=reset + 60)])
        self.assertEqual(len(out), 1)
        self.assertEqual(len(I.fold([ev("limit", w=1, t=10.0, reset_at=reset), ev("limit", w=2, t=12.0, reset_at=reset + 7200)])), 2)

    def test_ack_by_id_and_by_window_and_clear(self):
        a, b = ev("permission", w=1, t=1.0), ev("done", w=2, t=2.0)
        out = I.fold([a, b, {"op": "ack", "ids": [a["id"]]}])
        self.assertEqual([e["status"] for e in out], ["read", "unread"])
        out = I.fold([a, b, {"op": "ack", "w": "2", "pid": 42}])
        self.assertEqual([e["status"] for e in out], ["unread", "read"])
        out = I.fold([a, b, {"op": "ack", "w": "2", "pid": 99}])                  # another kitty's window 2
        self.assertEqual([e["status"] for e in out], ["unread", "unread"])
        out = I.fold([a, b, {"op": "clear"}])
        self.assertEqual([e["status"] for e in out], ["dismissed", "dismissed"])

    def test_restore_undoes_a_dismissal_and_forgets_that_it_was_looked_at(self):
        a, b = ev("permission", w=1, t=1000.0), ev("done", w=2, t=1000.0)
        dismissed = [a, b, {"op": "ack", "t": 1060.0, "ids": [a["id"], b["id"]], "status": "dismissed"}]
        out = I.fold(dismissed + [{"op": "restore", "ids": [a["id"]]}])
        self.assertEqual([e["status"] for e in out], ["unread", "dismissed"])
        self.assertNotIn("ack_t", out[0])                                      # the wait is open again, not counted as answered
        self.assertEqual(out[1]["ack_t"], 1060.0)

    def test_restore_only_touches_dismissed_events_and_ignores_junk(self):
        a = ev("permission", w=1, t=1000.0)
        read = I.fold([a, {"op": "ack", "t": 1010.0, "ids": [a["id"]]}, {"op": "restore", "ids": [a["id"]]}])
        self.assertEqual((read[0]["status"], read[0]["ack_t"]), ("read", 1010.0))        # read is not dismissed: left alone
        out = I.fold([a, {"op": "restore", "ids": ["nope", 5, None]}, {"op": "restore"}, {"op": "restore", "ids": "x"}, {"op": "restore", "ids": 5}])
        self.assertEqual([e["status"] for e in out], ["unread"])

    def test_damaged_input_is_ignored(self):
        out = I.fold([None, 5, {"op": "add"}, {"op": "add", "id": "x", "kind": "nope"}, {"op": "?"}, ev("done", t=1.0)])
        self.assertEqual(len(out), 1)

    def test_snapshot_schema(self):
        events = [ev("permission", w=1, t=1.0), ev("done", w=2, t=2.0)]
        s = I.snapshot(events, 3.0)
        self.assertEqual((s["version"], s["unread"], s["needs_you"]), (1, 2, 1))
        self.assertEqual([e["kind"] for e in s["events"]], ["done", "permission"])   # newest first


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_add_ack_clear_roundtrip_with_a_snapshot_file_and_private_modes(self):
        new, e = I.add(self.d, ev("permission", t=10.0))
        self.assertTrue(new)
        snap = jload(I.snapshot_path(self.d))
        self.assertEqual((snap["unread"], snap["needs_you"]), (1, 1))
        I.ack(self.d, 11.0, window=7, pid=42)
        self.assertEqual(jload(I.snapshot_path(self.d))["unread"], 0)
        for path in (I.store_path(self.d), I.snapshot_path(self.d)):
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        I.add(self.d, ev("done", w=9, t=20.0))
        I.clear(self.d, 21.0)
        self.assertEqual([x["status"] for x in I.load(self.d)], ["read", "dismissed"])

    def test_add_reports_duplicates_so_the_caller_does_not_announce_twice(self):
        self.assertTrue(I.add(self.d, ev("permission", src="agent", t=100.0))[0])
        self.assertFalse(I.add(self.d, ev("permission", src="screen", t=102.0))[0])
        I.ack(self.d, 103.0, window=7, pid=42)                                     # you looked: a new occurrence is new again
        self.assertTrue(I.add(self.d, ev("permission", src="screen", t=104.0))[0])

    def test_the_store_is_bounded_by_compaction(self):
        for i in range(1200):
            I.add(self.d, ev("info", w=i, t=1000.0 + i * 100, body="x" * 150))
        self.assertLessEqual(os.path.getsize(I.store_path(self.d)), I.STORE_MAX_BYTES + 2000)
        self.assertLess(len(I.load(self.d)), 1000)                                   # bounded by bytes, not growing with the 1200 adds
        self.assertEqual(len(jload(I.snapshot_path(self.d))["events"]), I.SNAPSHOT_EVENTS)

    def test_nothing_raises_on_a_hostile_state_dir(self):
        self.assertTrue(I.add("/proc/definitely/not/writable", ev("done", t=1.0))[0])
        I.ack("/proc/definitely/not/writable", 1.0, window=1)
        I.clear("/proc/definitely/not/writable", 1.0)
        self.assertEqual(I.load("/nonexistent"), [])

    def test_a_torn_line_does_not_poison_the_log(self):
        I.add(self.d, ev("done", t=1.0))
        with open(I.store_path(self.d), "a") as f:
            f.write('{"op":"add","id":"half')
        self.assertEqual(len(I.load(self.d)), 1)


class WaitTimeTests(unittest.TestCase):
    """The two times the wait ledger needs: when an event first appeared, and when you first looked at it."""

    def test_first_seen_stays_put_while_a_merged_report_moves_the_newest_time(self):
        a, b = ev("permission", t=1000.0), ev("permission", t=1020.0)
        e = I.fold([a, b])[0]
        self.assertEqual((e["t0"], e["t"], e["count"]), (1000.0, 1020.0, 2))

    def test_acknowledging_records_when_and_only_the_first_time(self):
        a = ev("permission", t=1000.0)
        ops = [a, {"op": "ack", "t": 1090.0, "ids": [a["id"]]}, {"op": "ack", "t": 5000.0, "ids": [a["id"]]}]
        e = I.fold(ops)[0]
        self.assertEqual((e["status"], e["ack_t"]), ("read", 1090.0))

    def test_a_window_ack_and_a_dismissal_and_a_clear_all_count_as_looking(self):
        a, b, c = ev("permission", w=1, t=1000.0), ev("question", w=2, t=1000.0), ev("done", w=3, t=1000.0)
        ops = [a, b, c, {"op": "ack", "t": 1050.0, "w": "1", "pid": 42}, {"op": "ack", "t": 1060.0, "ids": [b["id"]], "status": "dismissed"}, {"op": "clear", "t": 1070.0}]
        got = {e["w"]: e for e in I.fold(ops)}
        self.assertEqual((got["1"]["ack_t"], got["2"]["ack_t"], got["3"]["ack_t"]), (1050.0, 1060.0, 1070.0))
        self.assertEqual((got["2"]["status"], got["3"]["status"]), ("dismissed", "dismissed"))

    def test_an_event_nobody_looked_at_has_no_ack_time(self):
        self.assertNotIn("ack_t", I.fold([ev("permission", t=1000.0)])[0])

    def test_an_older_report_appended_later_is_not_merged_into_a_newer_event_hours_away(self):
        new, old = ev("permission", t=100000.0), ev("permission", t=100000.0 - 5 * 3600)
        folded = I.fold([new, old])
        self.assertEqual(len(folded), 2)
        self.assertEqual({e["t"] for e in folded}, {100000.0, 100000.0 - 5 * 3600})
        self.assertEqual([e["count"] for e in folded], [1, 1])

    def test_a_slightly_out_of_order_report_still_merges_and_time_never_moves_backwards(self):
        a, b = ev("permission", t=1000.0), ev("permission", t=980.0)
        e = I.fold([a, b])[0]
        self.assertEqual((e["count"], e["t"], e["t0"]), (2, 1000.0, 980.0))

    def test_is_duplicate_is_symmetric_too(self):
        existing = I.fold([ev("permission", t=100000.0)])
        self.assertTrue(I.is_duplicate(existing, ev("permission", t=99990.0)))
        self.assertFalse(I.is_duplicate(existing, ev("permission", t=100000.0 - 5 * 3600)))

    def test_compaction_keeps_both_times(self):
        a = ev("permission", t=1000.0)
        events = I.fold([a, ev("permission", t=1010.0), {"op": "ack", "t": 1100.0, "ids": [a["id"]]}])
        again = I.fold(I.compact(events))[0]
        self.assertEqual((again["t0"], again["ack_t"], again["status"]), (1000.0, 1100.0, "read"))

    def test_events_from_an_old_log_without_the_fields_still_fold(self):
        old = dict(ev("permission", t=1000.0))
        old.pop("op")
        e = I.fold([dict(old, op="add")])[0]
        self.assertEqual(e["t0"], 1000.0)


def _writer(args):
    d, n, base = args
    for i in range(n):
        I.add(d, I.make_event("info", "agent", base + i, "screen", 1000.0 + base + i * 100, pid=base))


class RestoreStoreTests(unittest.TestCase):
    def test_dismiss_then_restore_through_the_store(self):
        with tempfile.TemporaryDirectory() as d:
            a = ev("permission", w=1, t=1000.0)
            I.add(d, a)
            I.ack(d, 1010.0, ids=[a["id"]], status="dismissed")
            self.assertEqual(I.load(d)[0]["status"], "dismissed")
            I.restore(d, 1011.0, [a["id"]])
            got = I.load(d)[0]
            self.assertEqual(got["status"], "unread")
            self.assertNotIn("ack_t", got)


class ConcurrencyTests(unittest.TestCase):
    def test_several_processes_append_without_losing_events(self):
        d = tempfile.mkdtemp()
        with multiprocessing.get_context("fork").Pool(4) as pool:
            pool.map(_writer, [(d, 25, k * 1000) for k in range(4)])
        self.assertEqual(len(I.load(d)), 100)
        jload(I.snapshot_path(d))                                       # the snapshot is always whole JSON


if __name__ == "__main__":
    unittest.main()
