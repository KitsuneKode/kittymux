"""`limited` (an agent waiting for its usage limit to reset) has ONE colour in every renderer: the waiting colour, never the
alert one. It comes back by itself and nothing is broken, and the alert colour is kept for errors. The cell bar drew it in alert
while the pixel bar and deck drew it in waiting (CodeRabbit on #49); docs/agents/status-contract.md records the choice."""
import os
import re
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))


class LimitedColourTest(unittest.TestCase):
    def test_no_renderer_maps_limited_to_the_alert_colour(self):
        bad = []
        pattern = re.compile(r"""["']limit(?:ed)?["']\s*:\s*(?:["'](?:alert|hot)["']|\w+\.alert\b)"""   # a mapping (hot = alert)
                             r"""|["']limit["']\s*:\s*\([^)]*["']hot["']\)"""                        # an inbox kind's (glyph, tone)
                             r"""|\.alert\s+if\s+\w+\s*==\s*["']limited["']"""                     # an inline if (the rail's stripe)
                             r"""|\.alert\s+if\s+\w+\s+in\s+\([^)]*["']limit["']""")              # an inline if over event kinds
        for name in sorted(os.listdir(os.path.join(ROOT, "python"))):
            if name.endswith(".py"):
                with open(os.path.join(ROOT, "python", name), encoding="utf-8") as f:
                    for n, line in enumerate(f, 1):
                        if pattern.search(line):
                            bad.append(f"python/{name}:{n}")
        self.assertEqual(bad, [], "limited must use the waiting colour, as the pixel bar and deck do")

    def test_the_cell_views_draw_limited_as_waiting(self):
        import kittymux_agentsview as AV
        import kittymux_panetitle as PT
        p = types.SimpleNamespace(waiting=0xFFCC00, working=0x00AAFF, alert=0xFF0000, done=0x00FF00, bg=0x101010, faint=0x777777)
        self.assertEqual(AV._state_color(p, "limited"), AV._state_color(p, "waiting"))
        self.assertEqual(PT._state_rgb("limited", p, p.bg, 0xFFFFFF), PT._state_rgb("waiting", p, p.bg, 0xFFFFFF))

    def test_the_inbox_and_the_palette_agree(self):
        import kittymux_inboxview as IV
        self.assertEqual(IV.KIND["limit"][1], IV.KIND["permission"][1], "a usage-limit event wears the waiting tone")

    def test_no_user_doc_calls_limited_red(self):
        for path in ("README.md", os.path.join("docs", "users", "agent-status.mdx")):
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                self.assertNotIn("red limited", f.read(), path)

    def test_the_contract_records_one_colour(self):
        with open(os.path.join(ROOT, "docs", "agents", "status-contract.md"), encoding="utf-8") as f:
            row = next(line for line in f if line.startswith("| `limited`"))
        self.assertIn("the waiting colour in every view", row)
        self.assertNotIn("in cell views", row)                  # the old split: dim waiting in pixel panels, alert in cell views


if __name__ == "__main__":
    unittest.main()
