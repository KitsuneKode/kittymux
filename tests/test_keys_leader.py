import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load_keys_module():
    spec = importlib.util.spec_from_file_location("mux_keys", os.path.join(ROOT, "bin", "mux-keys.py"))
    mod = importlib.util.module_from_spec(spec)
    os.environ.pop("KITTY_LISTEN_ON", None)   # never talk to a real kitty from tests
    spec.loader.exec_module(mod)
    return mod


def render_tpl(leader="ctrl+space"):
    text = open(os.path.join(ROOT, "kittymux-leader.conf.tpl"), encoding="utf-8").read()
    text = text.replace("@KITTYMUX_HOME@", "/opt/kittymux").replace("@KITTYMUX_LEADER@", leader)
    f = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False)
    f.write(text)
    f.close()
    return f.name


class LeaderParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_keys_module()
        cls.conf = render_tpl("ctrl+a")

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.conf)

    def test_leader_key_detected(self):
        leader, groups = self.mod.parse_leader(self.conf)
        self.assertEqual(leader, "ctrl+a")
        self.assertGreaterEqual(len(groups), 4)

    def test_every_mapping_has_a_description(self):
        _, groups = self.mod.parse_leader(self.conf)
        for group in groups:
            for key, desc in group:
                self.assertNotEqual(desc, "?", f"leader key {key!r} has no description comment")

    def test_key_names_are_humanized(self):
        _, groups = self.mod.parse_leader(self.conf)
        keys = {k for g in groups for k, _ in g}
        for want in ("h", "\\", "-", "=", "X", "P", ";", "?"):
            self.assertIn(want, keys)
        self.assertNotIn("backslash", keys)

    def test_digit_run_collapsed(self):
        _, groups = self.mod.parse_leader(self.conf)
        rows = [r for g in groups for r in g]
        self.assertIn(("1…9", "jump to tab N"), rows)
        self.assertFalse([r for r in rows if r[1] == "jump to tab 5"])

    def test_missing_file_is_empty_not_crash(self):
        leader, groups = self.mod.parse_leader("/nonexistent/leader.conf")
        self.assertEqual(groups, [])

    def test_card_renders_all_widths(self):
        for cols in (60, 90, 140):
            lines = self.mod.frame(self.mod.State(), self.mod.sections_for(self.conf, True), 40, cols)
            self.assertEqual(len(lines), 40)
            self.assertGreater(len([l for l in lines if l.strip()]), 5)


def render_keys_conf():
    text = open(os.path.join(ROOT, "kittymux-keys.conf.tpl"), encoding="utf-8").read().replace("@KITTYMUX_HOME@", "/opt/kittymux")
    f = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False)
    f.write(text)
    f.close()
    return f.name


class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_keys_module()
        cls.conf = render_keys_conf()
        cls.sections = cls.mod.sections_for(cls.conf, False)

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.conf)

    def visible(self, lines):
        import re
        return [re.sub(r"\033\[[0-9;]*m", "", l) for l in lines]

    def test_pane_and_tab_number_chords_are_described_by_what_they_do(self):
        rows = {}
        for n, rs in self.sections:
            for k, d in rs:
                rows[k] = (n, d)
        self.assertEqual(rows["ctrl+alt+1…9"], ("PANES", "focus pane"))
        self.assertNotIn("ctrl+alt+shift+1…9", rows)
        self.assertEqual(rows["alt+1…9"][0], "TABS")
        self.assertEqual(rows["alt+0"], ("TABS", "jump to the LAST tab of the session (not the !scratch tab; ctrl+alt+` is the tab you were on before)"))
        self.assertEqual(rows["ctrl+alt+0"][0], "PANES")
        self.assertIn("LAST pane", rows["ctrl+alt+0"][1])
        self.assertEqual(self.mod._humanize("nth_window 3"), "focus pane 4")
        self.assertEqual(self.mod._humanize("nth_window -1"), "last pane")

    def test_everything_kittymux_does_is_listed(self):
        text = " ".join(f"{n} {k} {d}" for n, rows in self.sections for k, d in rows)
        for want in ("DECK", "TAB BAR", "COMMANDS", "NOTIFICATIONS", "FILE REFERENCES", "dim on|off", "screenshot",
                     "promote the pane", "right-click a tab", "ctrl+alt+1", "ctrl+alt+e"):
            self.assertIn(want, text)

    def test_search_filters_by_every_word_across_section_key_and_description(self):
        hit = self.mod.filter_sections(self.sections, "deck promote")
        self.assertEqual([n for n, _ in hit], ["DECK  (ctrl+alt+b)"])
        self.assertEqual(len(hit[0][1]), 1)
        self.assertEqual(self.mod.filter_sections(self.sections, "zzzqq"), [])
        self.assertIs(self.mod.filter_sections(self.sections, "  "), self.sections)

    def test_columns_follow_the_width(self):
        self.assertEqual([self.mod.column_count(w) for w in (60, 100, 160, 250)], [1, 2, 3, 3])
        narrow = self.mod.build_body(self.sections, 60)
        wide = self.mod.build_body(self.sections, 200)
        self.assertLess(len(wide), len(narrow))                      # more columns, fewer lines
        for width in (40, 60, 100, 200):
            for line in self.mod.build_body(self.sections, width):
                self.assertLessEqual(self.mod._vlen(line), width - 1, (width, line))

    def test_frame_has_exact_size_and_scrolls(self):
        st = self.mod.State()
        lines = self.mod.frame(st, self.sections, 20, 80)
        self.assertEqual(len(lines), 20)
        first = self.visible(lines)[3]
        st.top = 6
        self.assertNotEqual(self.visible(self.mod.frame(st, self.sections, 20, 80))[3], first)
        st.top = 10 ** 6
        self.mod.frame(st, self.sections, 20, 80)
        self.assertGreater(st.top, 0)                                  # clamped to the last page, not past it
        self.assertIn("end", self.visible(self.mod.frame(st, self.sections, 20, 80))[-1])

    def test_no_match_message(self):
        st = self.mod.State()
        st.query = "zzzqq"
        self.assertIn("no bindings match", "".join(self.visible(self.mod.frame(st, self.sections, 20, 80))))

    def test_input_parsing(self):
        P = self.mod.parse_input
        self.assertEqual(P("\x1b"), ["esc"])
        self.assertEqual(P("\x1b[A\x1b[B\x1b[6~"), ["up", "down", "pgdn"])
        self.assertEqual(P("\x1b[<64;10;5M\x1b[<65;10;5M\x1b[<0;10;5M"), ["wheel_up", "wheel_down"])
        self.assertEqual(P("ab\r\x7f"), ["a", "b", "enter", "backspace"])
        self.assertEqual(P("\x1b[1;5C"), [])                         # unknown sequence swallowed, not typed into the search

    def test_escape_closes_in_one_press(self):
        st = self.mod.State()
        self.assertEqual(self.mod.step(st, "esc", 100, 20), "quit")   # the old overlay needed several presses
        self.assertEqual(self.mod.step(self.mod.State(), "q", 100, 20), "quit")
        self.assertEqual(self.mod.step(self.mod.State(), "ctrl-c", 100, 20), "quit")

    def test_search_flow(self):
        st, step = self.mod.State(), self.mod.step
        for tok in "/pane":
            step(st, tok, 100, 20)
        self.assertEqual((st.query, st.searching), ("pane", True))
        step(st, "enter", 100, 20)
        self.assertEqual((st.query, st.searching), ("pane", False))
        self.assertIsNone(step(st, "esc", 100, 20))                    # first esc clears the search
        self.assertEqual((st.query, st.searching), ("", False))
        self.assertEqual(step(st, "esc", 100, 20), "quit")             # the second closes
        st = self.mod.State()
        step(st, "x", 100, 20)                                         # any other character starts a search
        self.assertEqual((st.query, st.searching), ("x", True))
        step(st, "backspace", 100, 20)
        self.assertEqual((st.query, st.searching), ("", False))

    def test_scroll_keys_clamp(self):
        st, step = self.mod.State(), self.mod.step
        step(st, "k", 50, 10)
        self.assertEqual(st.top, 0)
        step(st, "G", 50, 10)
        self.assertEqual(st.top, 40)
        step(st, "pgdn", 50, 10)
        self.assertEqual(st.top, 40)
        step(st, "pgup", 50, 10)
        self.assertEqual(st.top, 31)
        step(st, "g", 50, 10)
        self.assertEqual(st.top, 0)

    def test_toggle_binding_closes_the_overlay_instead_of_stacking_another(self):
        tpl = open(os.path.join(ROOT, "kittymux-keys.conf.tpl"), encoding="utf-8").read()
        self.assertIn("--title kittymux-keys", tpl)
        self.assertIn("map --when-focus-on title:kittymux-keys ctrl+alt+slash close_window", tpl)


class TemplateTests(unittest.TestCase):
    def test_no_unrendered_placeholders_besides_known(self):
        text = open(os.path.join(ROOT, "kittymux-leader.conf.tpl"), encoding="utf-8").read()
        import re
        self.assertEqual(set(re.findall(r"@[A-Z_]+@", text)), {"@KITTYMUX_HOME@", "@KITTYMUX_LEADER@"})

    def test_uses_documented_kitty_syntax(self):
        text = open(os.path.join(ROOT, "kittymux-leader.conf.tpl"), encoding="utf-8").read()
        self.assertIn("map --new-mode leader --on-action end --on-unknown end", text)
        self.assertTrue(all(l.startswith(("map --mode leader ", "map --new-mode leader ", "#")) or not l.strip()
                            for l in text.splitlines()))



class OverlayCloseBindTests(unittest.TestCase):
    """Pressing an overlay's chord a second time must close it (or at least not stack another): every `--type=overlay` bind and every `kitten` bind needs
    a `--when-focus-on` twin on the same chord that runs `close_window`."""

    # ctrl+alt+b opens the deck as a `kitten`, but the DOCKED PANEL is the same program (sidebar-kit.py) in a window of its own, and a twin keyed on its command
    # line would close the panel when ctrl+alt+b is pressed in it. A twin needs a match that tells the two apart (`state:overlay`), checked in a real kitty first.
    EXEMPT = {"ctrl+alt+b": "the docked panel runs the same program"}

    def binds(self):
        tpl = open(os.path.join(ROOT, "kittymux-keys.conf.tpl"), encoding="utf-8").read()
        opens, closes = {}, set()
        for line in tpl.splitlines():
            parts = line.split(None, 3)
            if len(parts) >= 3 and parts[0] == "map" and parts[1] != "--when-focus-on" and parts[1] != "--new-mode" and parts[1] != "--mode":
                action = line.split(None, 2)[2]
                if action.startswith("launch --type=overlay") or action.startswith("kitten "):
                    opens[parts[1]] = action
            elif len(parts) >= 4 and parts[0] == "map" and parts[1] == "--when-focus-on" and line.rstrip().endswith("close_window"):
                closes.add(line.split()[3])
        return opens, closes

    def test_every_overlay_chord_has_a_close_twin(self):
        opens, closes = self.binds()
        missing = sorted(chord for chord in opens if chord not in closes and chord not in self.EXEMPT)
        self.assertEqual(missing, [], "these open an overlay but a second press would stack another: add `map --when-focus-on title:<t> <chord> close_window` and a --title")

    def test_the_exemptions_still_exist(self):
        opens, closes = self.binds()
        for chord in self.EXEMPT:
            self.assertIn(chord, opens)
            self.assertNotIn(chord, closes)


if __name__ == "__main__":
    unittest.main()
