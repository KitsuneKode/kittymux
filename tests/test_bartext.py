"""The bar's title and second-line decisions (kittymux_bartext)."""
import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_bartext as B  # noqa: E402


class BarTextTests(unittest.TestCase):
    def test_show_program_matches_the_bar(self):
        """The draw path's old condition, as a truth table, so the two cannot drift."""
        def drawn(has_agent, has_place, home_only, place_is_folder):
            return (not has_agent) and ((not has_place) or (home_only and place_is_folder))

        for bits in itertools.product((False, True), repeat=4):
            self.assertEqual(B.show_program(*bits), drawn(*bits), bits)

    def test_home_is_named(self):
        self.assertEqual(B.display_title("~"), "Home")
        self.assertEqual(B.display_title("  ~  "), "Home")
        self.assertEqual(B.display_title("Port the configs"), "Port the configs")
        self.assertEqual(B.display_title(""), "")


if __name__ == "__main__":
    unittest.main()
