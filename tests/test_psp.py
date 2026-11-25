import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
import kittymux_psp as P  # noqa: E402


def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode().rstrip("=")


def osc(payload: str, st: str = "\x1b\\") -> bytes:
    return f"\x1b]7501;{payload}{st}".encode()


class ParseTests(unittest.TestCase):
    def test_spec_example(self):
        self.assertEqual(P.parse("state=working:app=brew:msg=" + b64("Installing updates")),
                         {"state": "working", "app": "brew", "msg": "Installing updates"})

    def test_state_is_required(self):
        self.assertIsNone(P.parse("app=x"))
        self.assertIsNone(P.parse("state=sleeping"))

    def test_malformed_pairs_are_skipped_last_key_wins(self):
        self.assertEqual(P.parse("state=idle:BAD=1:noequals:state=done"), {"state": "done"})

    def test_kind_only_with_blocked_progress_only_while_running(self):
        self.assertEqual(P.parse("state=blocked:kind=permission:progress=40"), {"state": "blocked", "kind": "permission", "progress": 40})
        self.assertEqual(P.parse("state=done:kind=permission:progress=40"), {"state": "done"})
        self.assertEqual(P.parse("state=blocked:kind=nope"), {"state": "blocked"})

    def test_bad_id_or_base64_or_control_char_discards(self):
        self.assertIsNone(P.parse("state=working:id=a//b"))
        self.assertIsNone(P.parse("state=working:msg=A"))              # in the charset, but not base64
        self.assertEqual(P.parse("state=working:msg=!!!"), {"state": "working"})   # outside it: a malformed pair, skipped
        self.assertIsNone(P.parse("state=working:msg=" + b64("bell\x07")))
        self.assertEqual(P.parse("state=working:id=build/test")["id"], "build/test")


class ScannerTests(unittest.TestCase):
    def test_probe_and_report_in_one_chunk(self):
        s = P.Scanner()
        ev = s.feed(b"hello " + osc("?") + b"\x1b[c" + osc("state=done", "\x07") + b" bye")
        self.assertEqual(ev, [("query",), ("report", {"state": "done"})])

    def test_split_anywhere(self):
        data = b"x" + osc("state=blocked:kind=question:msg=" + b64("Proceed?")) + b"y"
        for cut in range(1, len(data)):
            s = P.Scanner()
            ev = s.feed(data[:cut]) + s.feed(data[cut:])
            self.assertEqual(ev, [("report", {"state": "blocked", "kind": "question", "msg": "Proceed?"})], cut)

    def test_other_oscs_are_not_ours(self):
        s = P.Scanner()
        self.assertEqual(s.feed(b"\x1b]0;title\x07\x1b]750;x\x07\x1b]133;A\x07"), [])

    def test_unterminated_does_not_grow_forever(self):
        s = P.Scanner()
        s.feed(b"\x1b]7501;state=working" + b"a" * 5000)
        self.assertEqual(s.feed(osc("state=idle")), [("report", {"state": "idle"})])


class RecordTests(unittest.TestCase):
    def test_summary_prefers_urgent_then_new(self):
        r = P.Records()
        r.apply({"state": "working"}, 1)
        r.apply({"state": "blocked", "id": "tool"}, 2)
        self.assertEqual(r.summary()["state"], "blocked")
        r.apply({"state": "clear", "id": "tool"}, 3)
        self.assertEqual(r.summary()["state"], "working")

    def test_clear_subtree_and_all(self):
        r = P.Records()
        for i in ("a", "a/b", "ab"):
            r.apply({"state": "working", "id": i}, 1)
        r.apply({"state": "clear", "id": "a"}, 2)
        self.assertEqual(sorted(r.by_id), ["ab"])
        r.apply({"state": "clear"}, 3)
        self.assertIsNone(r.summary())

    def test_prompt_drops_live_keeps_done(self):
        r = P.Records()
        r.apply({"state": "working"}, 1)
        r.apply({"state": "done", "id": "x"}, 2)
        r.drop_live()
        self.assertEqual(list(r.by_id), ["x"])

    def test_user_var_round_trip(self):
        raw = P.user_var({"state": "blocked", "msg": "Allow rm?", "t": 5.0})
        self.assertTrue(raw.startswith(b"\x1b]1337;SetUserVar=kittymux_psp="))
        enc = raw.split(b"=", 2)[2][:-1]
        self.assertEqual(P.read_var({"kittymux_psp": base64.b64decode(enc).decode()})["msg"], "Allow rm?")
        self.assertIsNone(P.read_var({"kittymux_psp": ""}))


class ViewTests(unittest.TestCase):
    def test_blocked_is_waiting_with_the_message(self):
        view = {}
        self.assertEqual(P.apply_to_view({"state": "blocked", "msg": "Run tests?", "t": 3}, view, "", ""), ("waiting", "Run tests?"))

    def test_a_usage_limit_on_screen_outranks_blocked(self):
        view = {}
        self.assertEqual(P.apply_to_view({"state": "blocked", "msg": "Run tests?", "t": 3}, view, "limited", "usage limit reached"),
                         ("limited", "usage limit reached"))
        self.assertNotIn("why", view)

    def test_working_clears_a_stale_prompt(self):
        view = {}
        # the prompt is gone, and the report itself stands as the busy marker (a held record must not expire after the hook grace)
        self.assertEqual(P.apply_to_view({"state": "working", "t": 3}, view, "waiting", "old"), ("working", "old"))
        self.assertEqual(view["status"], "working")

    def test_done_feeds_the_agent_done_path(self):
        view = {"agent_done_ts": 1}
        P.apply_to_view({"state": "done", "t": 9}, view, "", "")
        self.assertEqual((view["agent_done_ts"], view["done_source"]), (9, "agent"))

    def test_nothing_reported_changes_nothing(self):
        view = {}
        self.assertEqual(P.apply_to_view(None, view, "working", "l"), ("working", "l"))
        self.assertEqual(view, {})

    def test_error_is_its_own_state_and_keeps_the_message(self):
        view = {"agent_done_ts": 1, "done_source": "agent"}
        marker, line = P.apply_to_view({"state": "error", "msg": "build failed", "t": 9}, view, "", "")
        self.assertEqual((marker, line), ("error", "build failed"))
        self.assertEqual(view.get("status"), "error")
        self.assertNotIn("agent_done_ts", view)
        self.assertNotIn("done_source", view)
        self.assertEqual(P.apply_to_view({"state": "error", "title": "boom", "t": 2}, {}, "working", "esc to interrupt"), ("error", "boom"))

    def test_a_prompt_or_a_limit_still_outranks_an_error(self):
        view = {}
        self.assertEqual(P.apply_to_view({"state": "error", "msg": "build failed", "t": 4}, view, "waiting", "Do you want to proceed?"),
                         ("waiting", "Do you want to proceed?"))
        self.assertEqual(P.apply_to_view({"state": "error", "msg": "build failed", "t": 4}, {}, "limited", "usage limit reached")[0], "limited")


class BoundaryTests(unittest.TestCase):
    def test_clean_and_unclean_ends(self):
        for data, ok in ((b"plain", True), (b"\x1b[3", False), (b"\x1b[31m", True), (b"\x1b", False),
                         (b"\x1b]0;tit", False), (b"\x1b]0;title\x07", True), (b"\x1b_Gf=100;AAAA", False),
                         (b"\x1b_Gf=100;AAAA\x1b\\", True), ("é".encode()[:1], False), ("é".encode(), True),
                         ("✓".encode()[:2], False), (b"\x1b(B", True), (b"\x1b(", False)):
            self.assertEqual(P.Boundary().feed(data), ok, data)

    def test_state_carries_across_reads(self):
        b = P.Boundary()
        self.assertFalse(b.feed(b"\x1b_Gm=1;" + b"A" * 100))
        self.assertFalse(b.feed(b"B" * 100))                 # still inside the image chunk: no ESC here at all
        self.assertTrue(b.feed(b"C\x1b\\text"))
        self.assertFalse(b.feed(b"\x1b]8;;http://x"))
        self.assertTrue(b.feed(b"\x1b\\link\x1b]8;;\x1b\\"))

    def test_a_character_split_across_three_reads_is_not_a_clean_point(self):
        euro = "€".encode()                                          # e2 82 ac, one character, three bytes
        self.assertEqual(len(euro), 3)
        b = P.Boundary()
        self.assertFalse(b.feed(euro[:1]))
        self.assertFalse(b.feed(euro[1:2]))                          # a continuation byte alone used to look complete
        self.assertTrue(b.feed(euro[2:]))
        self.assertTrue(b.feed(b"ok"))



class _Status:
    def __init__(self, records):
        self.records = records

    def as_list(self):
        return list(self.records)


class _Window:
    def __init__(self, wid, records):
        self.id = wid
        self.program_status = _Status(records)


class NativeTests(unittest.TestCase):
    """kitty 0.50 keeps the records itself (window.program_status.as_list()); read_native summarises them."""

    def setUp(self):
        P._SEEN.clear()

    def test_most_urgent_record_speaks(self):
        w = _Window(7, [
            {"id": "", "state": "working", "kind": None, "progress": 40, "app": "claude", "title": "", "msg": ""},
            {"id": "sub", "state": "blocked", "kind": "permission", "progress": None, "app": "claude",
             "title": "", "msg": "Allow rm?"},
        ])
        rec = P.read_native(w, 100.0)
        self.assertEqual((rec["state"], rec["kind"], rec["msg"]), ("blocked", "permission", "Allow rm?"))

    def test_time_is_when_the_state_was_first_seen(self):
        w = _Window(7, [{"id": "", "state": "working", "kind": None, "progress": None, "app": "", "title": "", "msg": ""}])
        self.assertEqual(P.read_native(w, 100.0)["t"], 100.0)
        self.assertEqual(P.read_native(w, 160.0)["t"], 100.0)              # still working: unchanged
        w.program_status.records[0]["state"] = "done"
        self.assertEqual(P.read_native(w, 200.0)["t"], 200.0)              # a new state: its own time

    def test_nothing_reported_or_old_kitty(self):
        self.assertIsNone(P.read_native(_Window(7, []), 1.0))
        self.assertIsNone(P.read_native(object(), 1.0))                    # kitty 0.49: no program_status

    def test_feeds_the_scanner_like_the_relay(self):
        w = _Window(3, [{"id": "", "state": "blocked", "kind": "question", "progress": None, "app": "pi",
                         "title": "", "msg": ""}])
        view = {}
        marker, line = P.apply_to_view(P.read_native(w, 5.0), view, "", "")
        self.assertEqual((marker, line), ("waiting", "Has a question"))


def _rec(rid, state, msg=""):
    return {"id": rid, "state": state, "kind": "permission" if state == "blocked" else None, "progress": None, "app": "claude",
            "title": "", "msg": msg}


class NativeReviewTests(unittest.TestCase):
    """CodeRabbit on #47: what kitty's records say must hold for as long as kitty holds them, survive a reload, forget a record
    that went away, and keep kitty's own order when two records were first seen together."""

    def setUp(self):
        P._SEEN.clear()

    def test_a_working_record_keeps_a_quiet_screen_working_past_the_hook_grace(self):
        import kittymux_state as S
        w = _Window(4, [_rec("", "working")])
        view = {}
        P.apply_to_view(P.read_native(w, 100.0), view, "", "")
        view = {}
        marker, _line = P.apply_to_view(P.read_native(w, 105.0), view, "", "")      # first seen at 100: 5 s later, still held
        self.assertEqual(S.resolve(view, "claude", marker, 105.0, False), "working")
        self.assertIn("OSC 7501", view.get("why", ""))

    def test_blocked_reaches_the_resolver_for_an_agent_whose_screen_is_not_read(self):
        import kittymux_state as S
        self.assertNotIn("pi", S.SCREEN_AGENTS)
        w = _Window(5, [_rec("", "blocked", "Allow rm?")])
        view = {}
        marker, _line = P.apply_to_view(P.read_native(w, 50.0), view, "", "")
        self.assertEqual(S.resolve(view, "pi", marker, 50.0, False), "waiting")
        self.assertEqual(view.get("msg"), "Allow rm?")

    def test_first_seen_times_survive_a_config_reload(self):
        import importlib
        w = _Window(6, [_rec("", "done")])
        self.assertEqual(P.read_native(w, 100.0)["t"], 100.0)
        importlib.reload(P)                                   # kitty re-runs the module on every config reload
        self.assertEqual(P.read_native(w, 300.0)["t"], 100.0, "an unchanged done must not get a new completion time")

    def test_a_record_that_went_away_starts_over_when_it_comes_back(self):
        w = _Window(8, [_rec("a", "blocked", "first")])
        P.read_native(w, 100.0)
        w.program_status.records = [_rec("a", "blocked", "first"), _rec("b", "blocked", "second")]
        P.read_native(w, 110.0)
        w.program_status.records = [_rec("b", "blocked", "second")]                 # a answered; b still asks
        P.read_native(w, 120.0)
        w.program_status.records = [_rec("b", "blocked", "second"), _rec("a", "blocked", "third")]
        rec = P.read_native(w, 130.0)
        self.assertEqual((rec["id"], rec["t"]), ("a", 130.0), "the new request is the newest, not a ghost from 100")

    def test_records_first_seen_together_keep_kittys_order(self):
        # kitty lists records from least to most recently changed: the last one is the newest
        w = _Window(9, [_rec("old", "blocked", "older question"), _rec("new", "blocked", "newer question")])
        self.assertEqual(P.read_native(w, 100.0)["id"], "new")


if __name__ == "__main__":
    unittest.main()
