"""agents.json: one file, every kitty, written only when a visible field changed, and never half-written."""
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_agents as A  # noqa: E402
import kittymux_agentsnap as S
import kittymux_palette as P

ROOT = os.path.join(os.path.dirname(__file__), "..")


def spec(state, **over):
    row = {"window_id": 19, "agent": "claude", "state": state, "title": "Port the configs",
           "tab_title": "calm-otter", "cwd": "", "session": "calm-otter", "reason": "",
           "progress": None, "limit_reset": None}
    row.update(over)
    return row


class BrandTests(unittest.TestCase):
    def test_one_table_names_a_real_mark_and_the_exceptions(self):
        icons = os.path.join(ROOT, "assets", "icons")
        for name in set(A.BRANDS.values()):
            self.assertTrue(os.path.isfile(os.path.join(icons, name + ".svg")), name)
        for name, agent in A.AGENTS.items():
            if agent.glyph and ord(agent.glyph[0]) >= 0xE000:
                self.assertIn(name, A.BRANDS, name)
        self.assertEqual(A.brand_of("codex"), "openai")
        self.assertEqual(A.brand_of("cursor-agent"), "cursor")
        self.assertEqual(A.brand_of("gemini"), "googlegemini")
        self.assertEqual(A.brand_of("droid"), "factorydroid")
        self.assertEqual(A.brand_of("vibe"), "mistralvibe")
        self.assertEqual(A.brand_of("agy"), "antigravity")
        self.assertEqual(A.brand_of("aider"), "")
        self.assertEqual(A.brand_of("crush"), "")


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.home = os.path.join(self.dir, "calm")
        self.cwd = os.path.join(self.home, "work", "calm-otter")
        os.makedirs(self.cwd)
        self.alive = lambda pid: True

    def pub(self, specs, pid=4035, now=1793780700.0):
        return S.publish(self.dir, pid, specs, now, alive=self.alive, home=self.home)

    def doc(self):
        with open(S.path_for(self.dir), encoding="utf-8") as handle:
            return json.load(handle)

    def test_each_state_is_a_write_and_a_repeat_is_not(self):
        seen = []
        for state, now in (("working", 1793780700.0), ("waiting", 1793780701.0), ("done", 1793780702.0), ("error", 1793780703.0)):
            reason = {"waiting": "Do you want to proceed?", "error": "build failed"}.get(state, "")
            self.assertTrue(self.pub([spec(state, reason=reason, progress=0.42 if state == "working" else None)], now=now))
            seen.append(self.doc()["agents"][0]["state"])
        self.assertEqual(seen, ["working", "waiting", "done", "error"])
        with mock.patch("kittymux_agentsnap.os.replace") as replace:
            self.assertFalse(self.pub([spec("error", reason="build failed")], now=1793780800.0))
        replace.assert_not_called()
        row = self.doc()["agents"][0]
        self.assertEqual(list(row), list(S._FIELDS))
        self.assertEqual(row["question"], None)
        self.assertEqual(row["error"], "build failed")
        self.assertIsNone(row["limit_reset"])
        self.assertEqual(row["source"], "agent")
        self.assertEqual(row["brand"], "claude")
        self.assertEqual(row["action"], P.validate_action({"op": "jump", "pid": 4035, "w": "19"}))
        self.assertEqual(stat.S_IMODE(os.stat(S.path_for(self.dir)).st_mode), 0o600)
        self.assertEqual(list(self.doc()["counts"]), list(S.COUNTS))
        self.assertEqual(self.doc()["counts"]["error"], 1)

    def test_a_muted_agent_is_listed_but_never_needs_you(self):
        """Mute (Rex adoption): still in the file, flagged, and left out of needs_you so a shell can honour it."""
        self.pub([spec("waiting", reason="Do you want to proceed?", muted=True),
                  spec("waiting", window_id=20, reason="Allow this command?"), spec("working", window_id=21)])
        doc = self.doc()
        by = {r["window_id"]: r for r in doc["agents"]}
        self.assertIs(by[19]["muted"], True)
        self.assertIs(by[20]["muted"], False)
        self.assertEqual(doc["counts"]["waiting"], 2)            # the states are the states: additive, version 1
        self.assertEqual(doc["needs_you"], 1)
        self.assertEqual(doc["version"], 1)
        self.assertTrue(self.pub([spec("waiting", reason="Do you want to proceed?", muted=False),
                                  spec("waiting", window_id=20, reason="Allow this command?"), spec("working", window_id=21)], now=1793780701.0))
        self.assertEqual(self.doc()["needs_you"], 2)              # unmuting is a write

    def test_waiting_keeps_the_question_and_limited_keeps_the_reset(self):
        self.pub([spec("waiting", reason="Do you want to proceed?")])
        self.assertEqual(self.doc()["agents"][0]["question"], "Do you want to proceed?")
        self.assertIsNone(self.doc()["agents"][0]["error"])
        self.pub([spec("limited", window_id=20, agent="codex", limit_reset=1793784393, title="Review the parser")], now=1793780705.0)
        row = self.doc()["agents"][0]
        self.assertEqual((row["state"], row["brand"], row["limit_reset"]), ("limited", "openai", 1793784393))
        self.assertIsNone(row["question"])
        self.assertEqual(self.doc()["counts"]["limited"], 1)

    def test_cwd_is_abbreviated_and_the_project_is_the_folder(self):
        with mock.patch("kittymux_agentsnap.kittymux_git.info", return_value=None):
            self.pub([spec("working", cwd=self.cwd, progress=0.42)])
        row = self.doc()["agents"][0]
        self.assertEqual(row["cwd"], "~/work/calm-otter")
        self.assertEqual(row["project"], "calm-otter")
        self.assertEqual(row["progress"], 0.42)
        self.assertEqual(row["title"], "Port the configs")

    def test_other_kitties_stay_and_a_dead_one_goes(self):
        self.pub([spec("working")], pid=4035)
        self.pub([spec("idle", window_id=8, agent="devin")], pid=4036, now=1793780710.0)
        keys = [r["key"] for r in self.doc()["agents"]]
        self.assertEqual(keys, ["w4035.19", "w4036.8"])
        self.alive = lambda pid: pid == 4036
        self.pub([spec("idle", window_id=8, agent="devin")], pid=4036, now=1793780720.0)
        self.assertEqual([r["key"] for r in self.doc()["agents"]], ["w4036.8"])

    def test_a_dead_pid_already_in_the_file_is_dropped_on_the_next_write(self):
        path = S.path_for(self.dir)
        os.makedirs(self.dir, mode=0o700, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "t": 1, "agents": [{"key": "w1073741824.1", "kitty_pid": 1073741824, "state": "working"}],
                       "counts": {}}, handle)
        self.assertTrue(S.publish(self.dir, os.getpid(), [spec("idle")], 1793780700.0, home=self.home))
        pids = {r["kitty_pid"] for r in self.doc()["agents"]}
        self.assertEqual(pids, {os.getpid()})

    def test_a_failed_replace_leaves_the_previous_file_and_the_temporary_is_whole(self):
        self.assertTrue(self.pub([spec("working")]))
        old = open(S.path_for(self.dir), encoding="utf-8").read()

        def boom(src, dst):
            text = open(src, encoding="utf-8").read()
            parsed = json.loads(text)
            self.assertEqual(parsed["version"], 1)
            self.assertEqual(parsed["agents"][0]["state"], "waiting")
            raise OSError("disk full")

        with mock.patch("kittymux_agentsnap.os.replace", side_effect=boom):
            self.assertFalse(self.pub([spec("waiting", reason="Do you want to proceed?")], now=1793780710.0))
        self.assertEqual(open(S.path_for(self.dir), encoding="utf-8").read(), old)
        self.assertFalse([n for n in os.listdir(self.dir) if n.endswith(".tmp")])
        self.assertEqual(json.loads(old)["agents"][0]["state"], "working")

    def test_a_bad_pid_does_not_create_the_file(self):
        self.assertFalse(S.publish(self.dir, True, [spec("working")], 1.0, alive=self.alive, home=self.home))
        self.assertFalse(os.path.exists(S.path_for(self.dir)))


if __name__ == "__main__":
    unittest.main()
