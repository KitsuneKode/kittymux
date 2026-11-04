"""Renderer contracts; GUI dependencies are optional for the normal unit job."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
try:
    import kittymux_deckpx as dp
except ImportError:
    dp = None
import kittymux_theme as th


@unittest.skipIf(dp is None, "cairo/Pango/rsvg not installed")
class RendererTests(unittest.TestCase):
    def test_native_spinner_slots_leave_the_base_stable(self):
        pal = th.from_colors({})
        model = dp.Model("calm-otter", "demo", agents=[dp.Agent("Review", "codex", pal.accent, "core", state="working")])
        slots = []
        cache = dp.Resources()
        first = dp.render(model, pal, 196, 600, 4/3, dp.Frame(phase=0), spinners=slots, resources=cache)
        second = dp.render(model, pal, 196, 600, 4/3, dp.Frame(phase=.5), spinners=[], resources=cache)
        self.assertEqual(len(slots), 1)
        self.assertEqual(bytes(first.get_data()), bytes(second.get_data()))
        self.assertGreater(len(cache.layouts), 0)
        self.assertLessEqual(len(cache.layouts), cache.limit)

    def test_invalid_geometry_is_rejected(self):
        for w, h, scale in ((0, 100, 1), (100, 100, 0), (10001, 100, 1), (100, 100, float("nan"))):
            with self.assertRaises(ValueError):
                dp.render(dp.Model("calm-otter", "demo"), th.from_colors({}), w, h, scale)

    def test_resources_are_bounded(self):
        cache = dp.Resources(limit=4)
        surface = dp.cairo.ImageSurface(dp.cairo.FORMAT_ARGB32, 100, 100)
        pt = dp.Painter(dp.cairo.Context(surface), 1, th.from_colors({}), resources=cache)
        for n in range(20):
            pt.layout(str(n), 12)
        self.assertLessEqual(len(cache.layouts), 4)

    def test_states_selection_and_scroll_leave_the_visible_hits(self):
        pal = th.from_colors({})
        plain = dp.Agent("Review", "codex", pal.accent, "core")
        marked = dp.Agent("Review", "codex", pal.accent, "core", selected=True, current=True)
        a = dp.render(dp.Model("calm-otter", "demo", agents=[plain]), pal, 320, 400)
        b = dp.render(dp.Model("calm-otter", "demo", agents=[marked]), pal, 320, 400)
        self.assertNotEqual(bytes(a.get_data()), bytes(b.get_data()))
        for state in ("error", "limited", "waiting", "done", "idle"):
            dp.render(dp.Model("calm-otter", "demo", agents=[dp.Agent("Review", "codex", pal.accent, "core", state=state)]), pal, 320, 400)
        agents = [dp.Agent(f"task {i}", "shell", 0, "core", row=i) for i in range(24)]
        model = dp.Model("calm-otter", "demo", agents=agents)
        hits = []
        dp.render(model, pal, 280, 180, frame=dp.Frame(scroll=0), hits=hits)
        shown = {h[1] for h in hits if h[0] == "agent"}
        self.assertIn(0, shown)
        self.assertNotIn(23, shown)
        items = dp.body_items(model)
        scroll = dp.scroll_to_item(items, 0, 180 - dp.HEADER_END, "agent", 23)
        hits = []
        dp.render(model, pal, 280, 180, frame=dp.Frame(scroll=scroll), hits=hits)
        self.assertIn(23, {h[1] for h in hits if h[0] == "agent"})
        opened = dp.Agent("web", "shell", 0, "core", can_open=True, opened=False)
        hits = []
        dp.render(dp.Model("calm-otter", "demo", agents=[opened]), pal, 320, 400, hits=hits)
        agent = next(h for h in hits if h[0] == "agent")
        self.assertEqual(dp.hit_at(hits, agent[2] + 2, agent[3] + 4), ("toggle", 0))
        self.assertEqual(dp.hit_at(hits, agent[2] + 40, agent[3] + 4), ("agent", 0))

    def test_the_first_space_stays_where_the_spike_drew_it(self):
        pal = th.from_colors({})
        hits = []
        dp.render(dp.Model("calm-otter", "demo", spaces=[dp.Space("core", "main")],
                           agents=[dp.Agent("Review", "codex", pal.accent, "core")]), pal, 400, 700, hits=hits)
        self.assertEqual(next(h[3] for h in hits if h[0] == "space"), 76)


if __name__ == "__main__":
    unittest.main()
