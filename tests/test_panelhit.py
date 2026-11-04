import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import kittymux_panelhit as H


class PanelHitTests(unittest.TestCase):
    def test_scrolled_off_summary_does_not_hit_the_header_row(self):
        """Line 0 scrolled away must not register on screen y=0 (the view header)."""
        x0, x1, line_y0, line_y1 = 0, 20, 0, 2
        scroll = 2
        self.assertEqual(H.line_to_screen_y(0, scroll), 0)
        self.assertFalse(H.hit_in_body(5, 0, scroll, x0, x1, line_y0, line_y1))
        self.assertFalse(H.hit_in_body(5, 1, scroll, x0, x1, line_y0, line_y1))

    def test_body_line_zero_maps_to_row_two_when_not_scrolled(self):
        scroll = 0
        self.assertTrue(H.hit_in_body(3, 2, scroll, 0, 10, 0, 1))
        self.assertFalse(H.hit_in_body(3, 1, scroll, 0, 10, 0, 1))

    def test_filter_chips_sit_on_body_line_zero(self):
        scroll = 3
        self.assertFalse(H.hit_body_row(4, 0, scroll, 1, 8, 0))
        self.assertFalse(H.hit_body_row(4, 1, scroll, 1, 8, 0))
        scroll = 0
        self.assertTrue(H.hit_body_row(4, 2, scroll, 1, 8, 0))

    def test_screen_span_clips_to_body(self):
        self.assertIsNone(H.screen_span_for_lines(0, 1, scroll=2))
        self.assertEqual(H.screen_span_for_lines(2, 5, scroll=2), (2, 5))


if __name__ == "__main__":
    unittest.main()
