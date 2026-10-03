import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
with open(os.path.join(ROOT, "kittymux-keys.conf.tpl"), encoding="utf-8") as _f:
    TPL = _f.read()


def mapping(chord: str) -> str:
    m = re.search(rf"^map\s+{re.escape(chord)}\s+(.*)$", TPL, re.M)
    return m.group(1) if m else ""


class YourShortcutsAreLeftAloneTests(unittest.TestCase):
    """The author's own kitty config (session-keybinds.conf, included BEFORE kittymux-keys.conf) maps ctrl+alt+shift+h/k/v/z (scratch nvim in the Hyprland / kitty /
    nvim / zsh config), +f (font toggle) and +x (screenshot). kitty's last definition wins and ours loads last, so merely mapping one of these chords
    silently disabled the user's own shortcut. kittymux works around them, never over them: `kittymux doctor` reports any chord defined by both."""

    def test_kittymux_does_not_map_the_chords_that_are_the_users(self):
        for key in "hkvzfx":
            self.assertEqual(mapping(f"ctrl+alt+shift+{key}"), "", f"ctrl+alt+shift+{key} belongs to the user's own config")

    def test_kittymux_moved_its_own_features_to_chords_nobody_uses(self):
        self.assertEqual(mapping("ctrl+alt+shift+c").strip(), "toggle_window_title_bars")      # was +h
        self.assertEqual(mapping("ctrl+alt+shift+y").strip(), "swap_with_window")              # was +x

    def test_the_template_says_why_those_chords_are_missing(self):
        self.assertIn("ctrl+alt+shift+h / k / v / z / f / x are NOT ours", TPL)

    def test_new_tab_chords_of_the_original_set_are_untouched(self):
        self.assertIn("mux-newtab.sh", mapping("ctrl+alt+shift+t"))


if __name__ == "__main__":
    unittest.main()
