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


if __name__ == "__main__":
    unittest.main()
