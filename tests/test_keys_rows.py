import importlib.util
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
spec = importlib.util.spec_from_file_location("mux_keys", os.path.join(ROOT, "bin", "mux-keys.py"))
K = importlib.util.module_from_spec(spec)
spec.loader.exec_module(K)

SECTIONS = K.parse_conf(os.path.join(ROOT, "kittymux-keys.conf.tpl"))
ROWS = {key: desc for _, rows in SECTIONS for key, desc in rows}
ALL = [(key, desc) for _, rows in SECTIONS for key, desc in rows]


class RowQualityTests(unittest.TestCase):
    """The rows are what the `ctrl+alt+/` overlay, the docs site's Keys page and the README table are built from: each must read like help."""

    def test_no_row_is_a_kitty_flag_or_a_mode_map(self):
        self.assertEqual([k for k, _ in ALL if k.startswith("-")], [])

    def test_a_row_never_shows_a_raw_kitty_action_name(self):
        raw = [(k, d) for k, d in ALL if re.fullmatch(r"[a-z]+(?:_[a-z]+)+", d)]
        self.assertEqual(raw, [])

    def test_a_resize_row_says_which_way(self):
        for chord, way in (("alt+shift+h", "narrower"), ("alt+shift+l", "wider"), ("alt+shift+j", "taller"), ("alt+shift+k", "shorter")):
            self.assertIn(way, ROWS[chord])

    def test_the_comment_on_a_backtick_chord_is_found(self):
        self.assertIn("previously active tab", ROWS["ctrl+alt+`"])

    def test_the_scroll_keys_say_what_they_scroll(self):
        self.assertIn("scroll", ROWS["ctrl+alt+PgUp"].lower())
        self.assertIn("up", ROWS["ctrl+alt+PgUp"].lower())
        self.assertIn("top", ROWS["ctrl+alt+Home"].lower())
        self.assertIn("bottom", ROWS["ctrl+alt+End"].lower())

    def test_the_prompt_jumps_say_so_and_the_home_tab_is_not_a_second_new_tab(self):
        self.assertIn("previous shell prompt", ROWS["ctrl+alt+["])
        self.assertIn("next shell prompt", ROWS["ctrl+alt+]"])
        self.assertIn("home", ROWS["ctrl+shift+t"])
        self.assertNotIn("home", ROWS["ctrl+alt+shift+t"])

    def test_no_row_talks_about_what_a_key_used_to_do(self):
        self.assertEqual([k for k, d in ALL if "used to" in d], [])

    def test_the_spawn_mode_chord_is_listed_with_its_comment(self):
        self.assertIn("spawn mode", ROWS["ctrl+alt+shift+o"])

    def test_no_chord_is_listed_twice_for_one_action_with_the_same_words(self):
        seen = {}
        for k, d in ALL:
            seen.setdefault(k, []).append(d)
        self.assertEqual({k: v for k, v in seen.items() if len(v) > 1}, {})


if __name__ == "__main__":
    unittest.main()
