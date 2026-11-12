"""The pixel tab bar's glue: clicks land on the tab drawn under the pointer, never on the blank cells beneath it."""
import os
import sys
import types
import unittest
from collections import namedtuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_agents as A  # noqa: E402
import kittymux_barsize as BS  # noqa: E402
import kittymux_pxbar as PX  # noqa: E402

Hit = namedtuple("Hit", "kind y0 y1 tab_id project")
Geom = namedtuple("Geom", "left top right bottom")


def bar(osw=7):
    return types.SimpleNamespace(is_vertical=True, os_window_id=osw, window_geometry=Geom(0, 0, 300, 900))


class ClickMappingTest(unittest.TestCase):
    def setUp(self):
        self._saved = dict(PX._S.windows)
        PX._S.windows.clear()
        PX._S.windows[7] = {"sig": None, "right": 300, "hits": (
            Hit("header", 0, 40, 0, ""), Hit("group", 40, 64, 0, "rice"),
            Hit("tab", 64, 110, 11, ""), Hit("tab", 110, 142, 12, ""))}

    def tearDown(self):
        PX._S.windows.clear()
        PX._S.windows.update(self._saved)

    def test_a_row_maps_to_its_tab_whatever_cell_is_under_it(self):
        self.assertEqual(BS.pxbar_tab_at(bar(), 100, 80), 11)
        self.assertEqual(BS.pxbar_tab_at(bar(), 100, 141), 12)

    def test_header_label_and_empty_space_activate_nothing(self):
        for y in (10, 50, 500):
            self.assertEqual(BS.pxbar_tab_at(bar(), 100, y), 0)

    def test_without_a_picture_kitty_answers(self):
        self.assertIsNone(BS.pxbar_tab_at(bar(osw=8), 100, 80))

    def test_a_horizontal_bar_is_left_to_kitty(self):
        b = bar()
        b.is_vertical = False
        self.assertIsNone(BS.pxbar_tab_at(b, 100, 80))

    def test_the_wrapper_uses_the_picture_first(self):
        calls = []
        wrapped = BS.make_tab_id_at(lambda self, x, y: calls.append((x, y)) or 99)
        self.assertEqual(wrapped(bar(), 100, 80), 11)
        self.assertEqual(calls, [])


class CloseCrossTest(unittest.TestCase):
    def setUp(self):
        self._saved = dict(PX._S.windows)
        PX._S.windows.clear()
        sig = ((), None, 300, 900, 1.0, "")
        PX._S.windows[7] = {"sig": sig, "right": 300, "hits": (Hit("tab", 64, 110, 11, ""), Hit("group", 110, 134, 0, "dots"))}

    def tearDown(self):
        PX._S.windows.clear()
        PX._S.windows.update(self._saved)

    def test_the_cross_is_the_row_end_in_its_first_line(self):
        self.assertEqual(PX.close_hit(7, 290, 70), 11)
        self.assertEqual(PX.close_hit(7, 270, 95), 11)

    def test_the_title_and_the_second_line_are_not_the_cross(self):
        self.assertEqual(PX.close_hit(7, 120, 70), 0)
        self.assertEqual(PX.close_hit(7, 290, 100), 0)

    def test_a_label_has_no_cross(self):
        self.assertEqual(PX.close_hit(7, 290, 120), 0)

    def test_a_group_label_click_opens_and_closes_it(self):
        saved = set(PX._S.expanded)
        try:
            PX._S.expanded.clear()
            PX.toggle_group("dots")
            self.assertEqual(PX.expanded(), frozenset({"dots"}))
            PX.toggle_group("dots")
            self.assertEqual(PX.expanded(), frozenset())
        finally:
            PX._S.expanded.clear()
            PX._S.expanded.update(saved)


class ToolMarksTest(unittest.TestCase):
    def test_every_tool_mark_is_a_real_icon(self):
        icons = os.path.join(os.path.dirname(__file__), "..", "assets", "icons")
        for tool, mark in A.TOOL_MARKS.items():
            self.assertTrue(os.path.exists(os.path.join(icons, f"{mark}.svg")), (tool, mark))

    def test_every_tool_with_a_mark_is_a_tool_the_bar_recognises(self):
        self.assertLessEqual(set(A.TOOL_MARKS), set(A.TOOLS))


if __name__ == "__main__":
    unittest.main()
