import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "python"))

import export_facts as E  # noqa: E402
import kittymux_features  # noqa: E402
import kittymux_state  # noqa: E402


class FactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = E.build_facts(ROOT)

    def test_it_is_plain_json_with_the_documented_shape(self):
        json.dumps(self.f)
        for key in ("version", "keys", "chords", "agents", "states", "features"):
            self.assertIn(key, self.f)

    def test_keys_come_from_the_real_template_and_are_counted(self):
        flat = {r["key"] for s in self.f["keys"] for r in s["rows"]}
        self.assertIn("ctrl+alt+e", flat)
        self.assertTrue(any(k.startswith("alt+1") for k in flat))
        self.assertEqual(self.f["chords"], sum(len(s["rows"]) for s in self.f["keys"]))
        self.assertGreater(self.f["chords"], 50)

    def test_states_are_exactly_the_states_the_resolver_knows(self):
        ids = {s["id"] for s in self.f["states"]}
        self.assertEqual(ids, (set(kittymux_state.PRIORITY) - {""}) | {"unread"})

    def test_the_important_state_comes_first(self):
        self.assertEqual([s["id"] for s in self.f["states"]][:2], ["limited", "waiting"])

    def test_agents_are_the_recognised_set_one_row_per_mark_and_say_whether_they_resume(self):
        ids = [a["id"] for a in self.f["agents"]]
        self.assertGreaterEqual(len(ids), 8)
        self.assertTrue({"claude", "codex", "devin"} <= set(ids))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse({"cursor", "antigravity"} & set(ids), "aliases must not be listed twice")
        self.assertTrue(all(isinstance(a["resumable"], bool) and a["name"] for a in self.f["agents"]))
        by = {a["id"]: a for a in self.f["agents"]}
        self.assertTrue(by["claude"]["resumable"])

    def test_every_feature_the_switchboard_has_is_described_and_planned_ones_say_so(self):
        by = {f["id"]: f for f in self.f["features"]}
        self.assertEqual(set(by), set(kittymux_features.FEATURES))
        self.assertTrue(by["titles"]["live"] and by["motion"]["live"] and by["sudo"]["live"])
        self.assertFalse(by["sheet"]["live"])
        for f in self.f["features"]:
            self.assertTrue(f["summary"], f"{f['id']} has no summary")

    def test_nothing_machine_specific_leaks_in(self):
        text = json.dumps(self.f)
        self.assertNotIn(os.path.expanduser("~"), text)
        self.assertNotIn("/home/", text)

    def test_a_template_with_no_chords_fails_loudly(self):
        with self.assertRaises(ValueError):
            E.keys_from_sections([])
        with self.assertRaises(ValueError):
            E.keys_from_sections([("TABS", [])])


if __name__ == "__main__":
    unittest.main()
