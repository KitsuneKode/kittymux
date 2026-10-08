import os
import re
import sys
import unicodedata
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_helpview as H  # noqa: E402
import kittymux_theme as T  # noqa: E402
import kittymux_ui as U  # noqa: E402

TOKYO = {"background": 0x1a1b26, "foreground": 0xc0caf5, "active_border_color": 0xf08fb8, "color9": 0xf7768e, "color10": 0x9ece6a, "color11": 0xe0af68, "color12": 0x7aa2f7}
LATTE = {"background": 0xeff1f5, "foreground": 0x4c4f69, "active_border_color": 0x1e66f5, "color9": 0xd20f39, "color10": 0x40a02b, "color11": 0xdf8e1d, "color12": 0x1e66f5}
SIDEBAR = os.path.join(os.path.dirname(__file__), "..", "python", "sidebar-kit.py")


def wide(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def kits():
    for colors in (TOKYO, LATTE):
        for kw in ({}, {"cells": wide, "rounded": False}):
            yield U.Kit(T.from_colors(colors), **kw)


class CardTests(unittest.TestCase):
    def test_every_line_is_exactly_the_width_for_every_view_theme_and_width(self):
        for k in kits():
            for name in ("agents", "usage", "inbox", "settings", "nonsense"):
                for cols in (8, 12, 16, 20, 26, 30, 38, 52, 80):
                    for i, line in enumerate(H.view(name, cols, k)):
                        self.assertEqual(U.line_cells(line, k.cells), max(8, cols), (name, cols, i))

    def test_the_card_names_the_view_and_how_to_leave(self):
        k = next(kits())
        for name, title in (("agents", "Agents"), ("usage", "Usage"), ("inbox", "Inbox"), ("settings", "Settings")):
            body = "\n".join(U.plain(l) for l in H.view(name, 40, k))
            self.assertIn(f"{title} keys", body)
            self.assertIn("esc closes", body)
        self.assertIn("Agents keys", "\n".join(U.plain(l) for l in H.view("nonsense", 40, k)))

    def test_no_text_is_lost_or_cut_to_nothing_at_a_usable_width(self):
        k = next(kits())
        body = "\n".join(U.plain(l) for l in H.view("agents", 38, k))
        for want in ("find a tab", "open / close a split", "pull this tab", "quit the panel"):
            self.assertIn(want.split()[0], body)

    def test_no_description_is_split_in_the_middle_of_a_word(self):
        k = next(kits())
        for name in H.KEYS:
            for cols in (30, 38, 52):
                body = [U.plain(l) for l in H.view(name, cols, k)]
                joined = " ".join(body)
                for _keys, text in H.KEYS[name] + H.MOUSE[name]:
                    for word in text.split():
                        if len(word) > 3 and word.isalpha() and cols >= 30:
                            self.assertIn(word, joined, (name, cols, word))

    def test_the_descriptions_start_in_one_column_within_a_group(self):
        k = next(kits())
        body = [U.plain(l) for l in H.view("agents", 40, k)]
        starts = []
        for _keys, text in H.KEYS["agents"]:
            first = text.split()[0]
            line = next(l for l in body if first in l and not l.strip().startswith(first))
            starts.append(line.index(first))
        self.assertEqual(len(set(starts)), 1, starts)

    def test_the_card_is_bounded(self):
        k = next(kits())
        for name in H.KEYS:
            self.assertLess(len(H.view(name, 12, k)), 80)


class TheKeysItNamesAreRealKeys(unittest.TestCase):
    """The card is data; this keeps it honest: every single-letter key it names appears as a handled token in the panel's own key code."""

    def test_letters_digits_and_named_keys_exist_in_the_handlers(self):
        with open(SIDEBAR, encoding="utf-8") as f:
            src = f.read()
        named = {"space": "SPACE", "⏎": "ENTER", "→": "RIGHT", "←": "LEFT", "↑": "UP", "↓": "DOWN", "tab": "TAB", "esc": "ESCAPE"}
        for view, rows in H.KEYS.items():
            for keys, _text in rows:
                for token in keys.split():
                    if re.fullmatch(r"\d-\d", token):
                        continue
                    want = named.get(token, token.upper() if len(token) == 1 else None)
                    if want:
                        self.assertTrue(f'"{want}"' in src or f"'{want}'" in src, (view, keys, token, want))


if __name__ == "__main__":
    unittest.main()
