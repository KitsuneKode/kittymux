import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_keymap as K  # noqa: E402

USERPREFS = """\
action_alias kitty_scrollback_nvim kitten /somewhere/kitty_scrollback_nvim.py --nvim-args -n

# Browse scrollback buffer in nvim
map kitty_mod+h kitty_scrollback_nvim
# Browse output of the last shell command in nvim
map kitty_mod+g kitty_scrollback_nvim --config ksb_builtin_last_cmd_output
map kitty_mod+f kitty_scrollback_nvim --config search
# Show clicked command output in nvim
mouse_map ctrl+shift+right press ungrabbed combine : mouse_select_command_output : kitty_scrollback_nvim --config ksb_builtin_last_visited_cmd_output
map ctrl+alt+x launch --type=overlay htop
"""


class ChordTests(unittest.TestCase):
    def test_modifier_order_does_not_matter_and_case_is_ignored(self):
        self.assertEqual(K.chord_key("ctrl+shift+alt+R"), K.chord_key("ctrl+alt+shift+r"))
        self.assertNotEqual(K.chord_key("ctrl+alt+r"), K.chord_key("ctrl+alt+shift+r"))
        self.assertEqual(K.chord_key("alt+1"), "alt+1")
        self.assertEqual(K.chord_key("f5"), "f5")


class ParseUserMapsTests(unittest.TestCase):
    def rows(self, text=USERPREFS, **kw):
        return dict(K.parse_user_maps(text, **kw))

    def test_kitty_mod_is_expanded_and_the_comment_above_is_the_description(self):
        rows = self.rows()
        self.assertEqual(rows["ctrl+shift+h"], "Browse scrollback buffer in nvim")
        self.assertEqual(rows["ctrl+shift+g"], "Browse output of the last shell command in nvim")

    def test_a_map_without_a_comment_says_what_it_runs(self):
        rows = self.rows()
        self.assertIn("search", rows["ctrl+shift+f"])
        self.assertIn("htop", rows["ctrl+alt+x"])

    def test_a_comment_belongs_to_the_next_line_only(self):
        self.assertNotEqual(self.rows()["ctrl+shift+f"], "Browse output of the last shell command in nvim")

    def test_a_mouse_map_is_spelled_as_a_click(self):
        self.assertEqual(self.rows()["ctrl+shift+right-click"], "Show clicked command output in nvim")

    def test_a_custom_kitty_mod_is_honoured_and_so_is_one_the_file_sets(self):
        self.assertIn("ctrl+alt+h", self.rows("map kitty_mod+h launch htop\n", kitty_mod="ctrl+alt"))
        self.assertIn("ctrl+alt+h", self.rows("kitty_mod ctrl+alt\nmap kitty_mod+h launch htop\n"))

    def test_options_after_map_are_skipped_not_mistaken_for_the_key(self):
        self.assertIn("ctrl+alt+j", self.rows("map --mode default ctrl+alt+j launch htop\n"))

    def test_separator_lines_are_decoration_not_a_description(self):
        rows = self.rows("# ============================================\nmap ctrl+alt+q close_window_with_confirmation\n")
        self.assertEqual(rows["ctrl+alt+q"], "close_window_with_confirmation")

    def test_a_comment_that_names_a_key_describes_that_key_wherever_it_sits(self):
        """The `# key — description` convention: the comment may sit above a different map (a pair of related ones)."""
        text = ("# ctrl+alt+shift+d — move pane anywhere: kitty's tab/OS-window chooser\n"
                "map ctrl+alt+d detach_window new-tab-right\n"
                "map ctrl+alt+shift+d detach_window ask\n")
        rows = self.rows(text)
        self.assertEqual(rows["ctrl+alt+shift+d"], "move pane anywhere: kitty's tab/OS-window chooser")
        self.assertEqual(rows["ctrl+alt+d"], "detach_window new-tab-right")

    def test_a_comment_that_just_echoes_the_chord_and_dash_is_trimmed(self):
        rows = self.rows("# ctrl+alt+g — agent picker\nmap ctrl+alt+g launch picker\n")
        self.assertEqual(rows["ctrl+alt+g"], "agent picker")

    def test_nonsense_never_raises(self):
        self.assertEqual(K.parse_user_maps("map\nmap onlyone\n# map x y\n\x00junk\n"), [])


class UserFilesTests(unittest.TestCase):
    def make(self, d):
        def write(name, text):
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        write("kitty.conf", "include hyde.conf\ninclude userprefs.conf\ninclude %s/kittymux-keys.conf\n"
                            "include /opt/kittymux/kittymux.conf\ninclude include-tab-edge.conf\nmap ctrl+alt+q launch htop\n" % d)
        write("hyde.conf", "include theme.conf\n")
        write("theme.conf", "map ctrl+alt+t launch from-theme\n")
        write("userprefs.conf", USERPREFS + "include session-keybinds.conf\n")
        write("session-keybinds.conf", "map ctrl+alt+shift+h launch --type=background /x/scratch-tab.sh --cwd /home/u/.config/hypr -- nvim\n")
        write("kittymux-keys.conf", "map ctrl+alt+shift+f toggle_window_title_bars\n")
        write("include-tab-edge.conf", "map ctrl+alt+shift+e nonsense\n")

    def test_it_follows_your_includes_and_skips_what_kittymux_wrote(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d)
            keys = {k for k, _d in K.user_kitty_maps(d, os.path.join(d, "kitty.conf"))}
            self.assertTrue({"ctrl+shift+h", "ctrl+alt+q", "ctrl+alt+t", "ctrl+alt+shift+h"} <= keys)     # userprefs, kitty.conf, theme (2 deep), session-keybinds
            self.assertNotIn("ctrl+alt+shift+f", keys)                                                 # kittymux's own file
            self.assertNotIn("ctrl+alt+shift+e", keys)

    def test_each_map_knows_which_of_your_files_defines_it(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d)
            src = K.user_map_sources(d, os.path.join(d, "kitty.conf"))
            self.assertEqual(src["ctrl+alt+shift+h"][0], "session-keybinds.conf")
            self.assertIn("scratch-tab.sh", src["ctrl+alt+shift+h"][1])
            self.assertEqual(src["ctrl+alt+q"][0], "kitty.conf")

    def test_an_include_cycle_or_a_missing_file_is_harmless(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "kitty.conf"), "w") as f:
                f.write("include kitty.conf\ninclude missing.conf\nmap ctrl+alt+q launch htop\n")
            self.assertEqual({k for k, _d in K.user_kitty_maps(d, os.path.join(d, "kitty.conf"))}, {"ctrl+alt+q"})
        self.assertEqual(K.user_kitty_maps("/nonexistent", "/nonexistent/kitty.conf"), [])


class ConditionalMapTests(unittest.TestCase):
    """`map --when-focus-on title:keys ctrl+alt+slash close_window` only applies while that window has focus: it is not a second meaning of the chord."""
    TEXT = "map ctrl+alt+slash launch overlay keys\nmap --when-focus-on title:keys ctrl+alt+slash close_window\n"

    def test_the_plain_map_keeps_the_chord_in_listings(self):
        self.assertEqual(dict(K.parse_user_maps(self.TEXT))["ctrl+alt+slash"], "launch overlay keys")

    def test_it_never_creates_or_hides_a_clash(self):
        user = {"ctrl+alt+slash": ("kitty.conf", "launch overlay keys")}
        self.assertEqual(K.conflicts(self.TEXT, user), [])
        self.assertEqual(K.conflicts("map --when-focus-on title:keys ctrl+alt+slash close_window\n", user), [])


class ConflictTests(unittest.TestCase):
    def test_a_chord_defined_by_both_with_different_actions_is_a_clash(self):
        ours = "map ctrl+alt+shift+h toggle_window_title_bars\nmap ctrl+shift+alt+r load_config_file\nmap ctrl+alt+d detach_window new-tab-right\n"
        user = {"ctrl+alt+shift+h": ("session-keybinds.conf", "launch scratch-tab.sh --cwd hypr"),
                "ctrl+alt+shift+r": ("kitty.conf", "load_config_file"),                  # same action: not a clash
                "ctrl+alt+d": ("session-keybinds.conf", "detach_window new-tab-right")}    # same action
        clashes = K.conflicts(ours, user)
        self.assertEqual([c[0] for c in clashes], ["ctrl+alt+shift+h"])
        self.assertEqual(clashes[0][1], "session-keybinds.conf")

    def test_nothing_clashes_when_there_is_nothing_of_yours(self):
        self.assertEqual(K.conflicts("map ctrl+alt+x foo\n", {}), [])


class HyprBindsTests(unittest.TestCase):
    SUPER, CTRL, ALT, SHIFT = 64, 4, 8, 1
    BINDS = [
        {"modmask": SUPER | CTRL, "key": "T", "description": "[Launcher|Apps] dropdown terminal", "dispatcher": "exec", "arg": "kitty --class drop-term"},
        {"modmask": SUPER | ALT, "key": "T", "description": "floating terminal", "dispatcher": "exec", "arg": "kitty --class float-term"},
        {"modmask": SUPER, "key": "S", "description": "[Workspaces|Navigation|Special workspace] toggle scratchpad", "dispatcher": "togglespecialworkspace", "arg": ""},
        {"modmask": SUPER | SHIFT, "key": "S", "description": "move to scratchpad", "dispatcher": "movetoworkspace", "arg": "special"},
        {"modmask": SUPER, "key": "Q", "description": "close window", "dispatcher": "killactive", "arg": ""},
        {"modmask": SUPER, "key": "B", "description": "", "dispatcher": "exec", "arg": "firefox"},
        {"modmask": CTRL | ALT, "key": "W", "description": "restart waybar", "dispatcher": "exec", "arg": "killall waybar"},
    ]

    def test_only_terminal_and_scratchpad_binds_are_listed_with_readable_chords(self):
        rows = dict(K.hypr_rows(self.BINDS))
        self.assertEqual(rows["super+ctrl+t"], "dropdown terminal")           # HyDE's [category|path] prefix is dropped
        self.assertEqual(rows["super+alt+t"], "floating terminal")
        self.assertEqual(rows["super+s"], "toggle scratchpad")
        self.assertEqual(rows["super+shift+s"], "move to scratchpad")
        self.assertEqual(len(rows), 4)

    def test_a_bind_without_a_description_says_what_it_runs(self):
        rows = dict(K.hypr_rows([{"modmask": 64, "key": "Return", "description": "", "dispatcher": "exec", "arg": "kitty --class main-term"}]))
        self.assertIn("kitty --class main-term", rows["super+return"])

    def test_junk_never_raises(self):
        self.assertEqual(K.hypr_rows([{}, {"modmask": "x"}, None, 5]), [])
        self.assertEqual(K.hypr_rows(None), [])


class YoursSectionTests(unittest.TestCase):
    def test_the_sections_say_whose_they_are_and_empty_ones_are_left_out(self):
        groups = K.yours_groups([("ctrl+shift+h", "Browse scrollback buffer in nvim")], [("super+s", "toggle scratchpad")])
        self.assertEqual(len(groups), 2)
        self.assertTrue(groups[0][0].startswith("YOURS"))
        self.assertIn("kitty", groups[0][0].lower())
        self.assertIn("hyprland", groups[1][0].lower())
        self.assertEqual(K.yours_groups([], []), [])
        self.assertEqual(len(K.yours_groups([("a", "b")], [])), 1)

    def test_kittys_built_in_rows_you_have_overridden_are_dropped(self):
        extras = [("KITTY BUILT-INS", [("ctrl+shift+h", "scrollback in a pager (/ searches)"), ("ctrl+shift+c / v", "copy / paste")])]
        self.assertEqual(K.drop_overridden(extras, {"ctrl+shift+h"})[0][1], [("ctrl+shift+c / v", "copy / paste")])
        self.assertEqual(K.drop_overridden(extras, set())[0][1], extras[0][1])


if __name__ == "__main__":
    unittest.main()
