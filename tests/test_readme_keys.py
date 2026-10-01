import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")

# how the README spells a key that kitty's config spells as a word
_NAMES = {",": "comma", ".": "period", ";": "semicolon", "\\": "backslash", "/": "slash", "[": "bracketleft",
          "]": "bracketright", "`": "grave_accent", "←": "left", "→": "right", "↑": "up", "↓": "down",
          "enter": "enter", "space": "space", "=": "equal"}
_CHORD = re.compile(r"^((?:ctrl|alt|shift|super)\+)+[^+]+$")


def tpl_chords() -> set:
    chords = set()
    for path in ("kittymux-keys.conf.tpl", "kittymux-leader.conf.tpl"):
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*map\s+(\S+)", line)
                if m:
                    chords.add(m.group(1).lower())
    return chords


def readme_chords() -> list:
    """Plain chords in the README's keymap table, e.g. `ctrl+alt+u`. Ranges (`1..9`), alternatives
    (`←/→`) and `+shift` suffixes are spelled loosely for humans and are not checked."""
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        text = f.read()
    table = text[text.index("## Keymap spine"):text.index("## Agent status")]
    out = []
    for cell in re.findall(r"`([^`]+)`", table.replace("\\`", "GRAVE")):
        cell = cell.replace("GRAVE", "`")
        if _CHORD.match(cell) and not cell.endswith("+arrows") and " " not in cell and ".." not in cell and "/" not in cell[:-1]:
            *mods, key = cell.split("+") if not cell.endswith("++") else (cell[:-2].split("+") + ["plus"])
            out.append((cell, "+".join(mods + [_NAMES.get(key, key)]).lower()))
    return out


class ReadmeKeyTableTests(unittest.TestCase):
    def test_every_plain_chord_in_the_readme_is_really_bound(self):
        bound = tpl_chords()
        phantom = [shown for shown, want in readme_chords() if want not in bound]
        self.assertEqual(phantom, [], "README documents keys the templates do not bind (renamed? removed?)")

    def test_the_check_sees_the_table(self):
        self.assertGreater(len(readme_chords()), 10)


if __name__ == "__main__":
    unittest.main()
