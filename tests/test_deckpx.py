"""Renderer contracts; GUI dependencies are optional for the normal unit job."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
try:
    import kittymux_deckpx as dp
except (ImportError, ValueError):   # gi raises ValueError when a typelib (Pango) is missing
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
        opened = dp.Agent("web", "shell", 0, "core", can_open=True, opened=False, panes=2)
        hits = []
        dp.render(dp.Model("calm-otter", "demo", agents=[opened]), pal, 320, 400, hits=hits)
        agent = next(h for h in hits if h[0] == "agent")
        # the chevron is at the right end of the pill; the ring at the left cap belongs to the row
        self.assertEqual(dp.hit_at(hits, agent[2] + agent[4] - 6, agent[3] + 10), ("toggle", 0))
        self.assertEqual(dp.hit_at(hits, agent[2] + 6, agent[3] + 10), ("agent", 0))
        self.assertEqual(dp.hit_at(hits, agent[2] + 60, agent[3] + 10), ("agent", 0))

    def test_a_space_heads_its_own_tabs(self):
        """Machine -> Space -> Agents: one list, each space directly above its tabs, no second Spaces section."""
        pal = th.from_colors({})
        model = dp.Model("calm-otter", "demo", spaces=[dp.Space("core", "main"), dp.Space("web", "dev")],
                         agents=[dp.Agent("a", "codex", 0, "web"), dp.Agent("b", "codex", 0, "core"),
                                 dp.Agent("c", "codex", 0, "web"), dp.Agent("loose", "shell", 0, "")])
        kinds = [(k, i) for k, i, _y, _h, _p in dp.body_items(model)]
        self.assertEqual(kinds, [("space", 0), ("agent", 1), ("space", 1), ("agent", 0), ("agent", 2), ("agent", 3)])
        ys = [y for _k, _i, y, _h, _p in dp.body_items(model)]
        self.assertEqual(ys, sorted(ys))
        hits = []
        dp.render(model, pal, 400, 700, hits=hits)
        self.assertEqual(next(h[3] for h in hits if h[0] == "space"), dp.HEADER_END + 6)

    def test_the_working_ring_steps_and_never_sits_between_steps(self):
        self.assertEqual([dp.step_phase(x) for x in (0, .1, .26, .5, .74, .99, 1.0, -0.1, float("nan"))],
                         [0, 0, .25, .5, .5, .75, 0, .75, 0])
        pal = th.from_colors({"color12": 0x2F6FEB})
        size, frames = dp.ring_frames(pal, 1)
        self.assertEqual(len(frames), dp.STEP_FRAMES)
        self.assertEqual(len({bytes(f.get_data()) for f in frames}), dp.STEP_FRAMES)
        self.assertGreaterEqual(size, 2 * dp.RING_R)
        self.assertGreaterEqual(dp.STEP_MS, 1000)          # calm: a step every few seconds, never a spin
        model = dp.Model("calm-otter", "demo", agents=[dp.Agent("Review", "codex", 0, "core", state="working")])
        a = dp.render(model, pal, 280, 200, frame=dp.Frame(phase=.01))
        b = dp.render(model, pal, 280, 200, frame=dp.Frame(phase=.2))
        self.assertEqual(bytes(a.get_data()), bytes(b.get_data()))

    def test_counts_and_rollup(self):
        counts = dp.state_counts(["working", "idle", "working", "done", "waiting", "x"])
        self.assertEqual(counts, {"working": 2, "done": 1, "waiting": 1})
        self.assertEqual(dp.rollup(counts), ("waiting", 1))
        self.assertEqual(dp.rollup({"done": 3, "working": 1}), ("working", 1))
        self.assertEqual(dp.rollup({}), ("", 0))
        parent = dp.Agent("web", "shell", 0, "core", state="idle")
        parent.children = [dp.Agent("t", "claude", 0, "core", state="waiting")]
        model = dp.Model("s", "h", agents=[parent, dp.Agent("x", "codex", 0, "core", state="limited")])
        self.assertEqual(dp.needs_you(model), 2)

    def test_the_needs_you_chip_is_a_target_only_when_something_asks(self):
        pal = th.from_colors({})
        calm = dp.Model("s", "h", agents=[dp.Agent("x", "codex", 0, "core", state="working")])
        hits = []
        dp.render(calm, pal, 300, 300, hits=hits)
        self.assertNotIn("needs", {h[0] for h in hits})
        asks = dp.Model("s", "h", agents=[dp.Agent("x", "codex", 0, "core", state="waiting")])
        hits = []
        dp.render(asks, pal, 300, 300, hits=hits)
        chip = next(h for h in hits if h[0] == "needs")
        self.assertLess(chip[3] + chip[5], dp.HEADER_END)

    def test_colour_is_only_for_state(self):
        """The accent appears only around the tab you are in, and a mark is never drawn in its brand colour."""
        accent, brand = 0xE0115F, 0x22B573
        pal = th.from_colors({"background": 0x101014, "foreground": 0xE6E6EA, "active_border_color": accent})

        def has(surface, colour, tol=24):
            from PIL import Image
            im = Image.frombuffer("RGBA", (surface.get_width(), surface.get_height()), bytes(surface.get_data()),
                                  "raw", "BGRa", surface.get_stride(), 1)
            r0, g0, b0 = colour >> 16 & 255, colour >> 8 & 255, colour & 255
            return any(abs(r - r0) < tol and abs(g - g0) < tol and abs(b - b0) < tol and a > 200
                       for r, g, b, a in zip(*[iter(im.tobytes())] * 4))

        quiet = dp.Model("s", "h", spaces=[dp.Space("core", "main")],
                         agents=[dp.Agent("x", "claude", brand, "core", state="idle", selected=True)])
        here = dp.Model("s", "h", spaces=[dp.Space("core", "main")],
                        agents=[dp.Agent("x", "claude", brand, "core", state="idle", current=True)])
        a = dp.render(quiet, pal, 300, 200, frame=dp.Frame(hover=0))
        b = dp.render(here, pal, 300, 200)
        self.assertFalse(has(a, accent), "the selection or a hover used the accent")
        self.assertTrue(has(b, accent), "the current tab has no accent hairline")
        self.assertFalse(has(a, brand) or has(b, brand), "a mark was drawn in its brand colour")

    def test_crossfade_interpolates_and_never_mixes_sizes(self):
        a = dp.cairo.ImageSurface(dp.cairo.FORMAT_ARGB32, 4, 4)
        b = dp.cairo.ImageSurface(dp.cairo.FORMAT_ARGB32, 4, 4)
        for surf, value in ((a, 0), (b, 1)):
            cr = dp.cairo.Context(surf)
            cr.set_source_rgba(value, value, value, 1)
            cr.paint()
        mid = dp.crossfade(a, b, .5)
        self.assertTrue(100 < bytes(mid.get_data())[0] < 156)
        self.assertEqual(bytes(dp.crossfade(a, b, 1).get_data()), bytes(b.get_data()))
        self.assertEqual(bytes(dp.crossfade(a, b, 0).get_data()), bytes(a.get_data()))
        other = dp.cairo.ImageSurface(dp.cairo.FORMAT_ARGB32, 8, 8)
        self.assertEqual(bytes(dp.crossfade(other, b, .5).get_data()), bytes(b.get_data()))
        self.assertLessEqual(dp.FADE_MS, 200)


if __name__ == "__main__":
    unittest.main()
