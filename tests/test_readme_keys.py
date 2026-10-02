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
                if re.match(r"\s*map\s+--new-mode\b", line):          # `map --new-mode NAME [--opts…] CHORD`: the chord that enters the mode is the last token
                    chords.add(line.split()[-1].lower())
                    continue
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


def _norm(chord: str) -> str:
    parts = chord.lower().split("+")
    return "+".join(sorted(parts[:-1]) + [parts[-1]])               # ctrl+shift+alt+r == ctrl+alt+shift+r


class NoChordBoundTwiceTests(unittest.TestCase):
    def test_no_chord_is_bound_twice_in_one_mode_whatever_the_modifier_order(self):
        """A second binding of one chord silently wins or loses (the spawn chord once collided with the reload chord, spelled ctrl+shift+alt+r)."""
        seen: dict = {}
        dupes = []
        for path in ("kittymux.conf", "kittymux-keys.conf.tpl", "kittymux-leader.conf.tpl"):
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if line.lstrip().startswith("#"):
                        continue
                    m = re.match(r"\s*map\s+((?:--\S+(?:\s+\S+)?\s+)*)(\S+)\s", line + " ")
                    if not m:
                        continue
                    opts, chord = m.group(1), m.group(2)
                    mode = re.search(r"--mode\s+(\S+)", opts)
                    when = re.search(r"--when-focus-on\s+(\S+)", opts)
                    if "--new-mode" in opts:
                        chord = line.split()[-1]
                    key = (mode.group(1) if mode else "", when.group(1) if when else "", _norm(chord))
                    if key in seen:
                        dupes.append(f"{path}:{n} duplicates {seen[key]} ({chord})")
                    seen[key] = f"{path}:{n}"
        self.assertEqual(dupes, [])


if __name__ == "__main__":
    unittest.main()
