import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load_keys_module():
    spec = importlib.util.spec_from_file_location("mux_keys", os.path.join(ROOT, "bin", "mux-keys.py"))
    mod = importlib.util.module_from_spec(spec)
    os.environ.pop("KITTY_LISTEN_ON", None)   # never talk to a real kitty from tests
    spec.loader.exec_module(mod)
    return mod


def render_tpl(leader="ctrl+space"):
    text = open(os.path.join(ROOT, "kittymux-leader.conf.tpl"), encoding="utf-8").read()
    text = text.replace("@KITTYMUX_HOME@", "/opt/kittymux").replace("@KITTYMUX_LEADER@", leader)
    f = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False)
    f.write(text)
    f.close()
    return f.name


class LeaderParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_keys_module()
        cls.conf = render_tpl("ctrl+a")

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.conf)

    def test_leader_key_detected(self):
        leader, groups = self.mod.parse_leader(self.conf)
        self.assertEqual(leader, "ctrl+a")
        self.assertGreaterEqual(len(groups), 4)

    def test_every_mapping_has_a_description(self):
        _, groups = self.mod.parse_leader(self.conf)
        for group in groups:
            for key, desc in group:
                self.assertNotEqual(desc, "?", f"leader key {key!r} has no description comment")

    def test_key_names_are_humanized(self):
        _, groups = self.mod.parse_leader(self.conf)
        keys = {k for g in groups for k, _ in g}
        for want in ("h", "\\", "-", "=", "X", "P", ";", "?"):
            self.assertIn(want, keys)
        self.assertNotIn("backslash", keys)

    def test_digit_run_collapsed(self):
        _, groups = self.mod.parse_leader(self.conf)
        rows = [r for g in groups for r in g]
        self.assertIn(("1…9", "jump to tab N"), rows)
        self.assertFalse([r for r in rows if r[1] == "jump to tab 5"])

    def test_missing_file_is_empty_not_crash(self):
        leader, groups = self.mod.parse_leader("/nonexistent/leader.conf")
        self.assertEqual(groups, [])

    def test_card_renders_all_widths(self):
        for cols in (60, 90, 140):
            lines = self.mod.leader_card(self.conf, cols)
            self.assertGreater(len(lines), 5)


class TemplateTests(unittest.TestCase):
    def test_no_unrendered_placeholders_besides_known(self):
        text = open(os.path.join(ROOT, "kittymux-leader.conf.tpl"), encoding="utf-8").read()
        import re
        self.assertEqual(set(re.findall(r"@[A-Z_]+@", text)), {"@KITTYMUX_HOME@", "@KITTYMUX_LEADER@"})

    def test_uses_documented_kitty_syntax(self):
        text = open(os.path.join(ROOT, "kittymux-leader.conf.tpl"), encoding="utf-8").read()
        self.assertIn("map --new-mode leader --on-action end --on-unknown end", text)
        self.assertTrue(all(l.startswith(("map --mode leader ", "map --new-mode leader ", "#")) or not l.strip()
                            for l in text.splitlines()))


if __name__ == "__main__":
    unittest.main()
