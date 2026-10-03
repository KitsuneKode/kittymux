# kittymux keymap — reading YOUR shortcuts, never writing them.
#
# kittymux ships key bindings, and you have your own: kitty maps in kitty.conf and the files it includes (kitty-scrollback in nvim, quick config
# edits …), Hyprland binds for terminals and scratchpads. They must coexist: the keymap overlay lists them next to ours, and `kittymux doctor` says
# when a chord is defined twice (kitty loads kittymux-keys.conf after your files, so for a clash OURS silently wins — which is how a shortcut of yours
# can stop working without a word).
#
# Pure Python, no kitty imports. Every reader is tolerant: nonsense in a config never raises.

import glob
import os
import re

_MODS = (("super", "super"), ("cmd", "super"), ("ctrl", "ctrl"), ("control", "ctrl"), ("alt", "alt"), ("opt", "alt"), ("option", "alt"), ("shift", "shift"))
_MOD_ORDER = {"super": 0, "ctrl": 1, "alt": 2, "shift": 3}
_MOD_NAME = dict(_MODS)
_KEY_WORDS = {"slash": "/", "comma": ",", "period": ".", "semicolon": ";", "backslash": "\\", "bracketleft": "[", "bracketright": "]",
              "grave_accent": "`", "equal": "=", "minus": "-"}
_MOUSE_BUTTON = {"left": "left-click", "right": "right-click", "middle": "middle-click"}
_NOT_OURS = {"include-tab-edge.conf", "include-tab-bar.conf"}          # written by install.sh and the layout engine
_MAP_OPTIONS_WITH_VALUE = {"--when-focus-on", "--mode", "--new-mode", "--on-unknown", "--on-action"}
_DECORATION = re.compile(r"^[=\-_*~#\s]*$")
_KEY_COMMENT = re.compile(r"^((?:[A-Za-z0-9_]+\+)+[^\s+—–]+|[A-Za-z0-9_]+\+\+)\s*[—–]\s*(.+)$|^((?:[A-Za-z0-9_]+\+)+[^\s+—–]+)\s+-\s+(.+)$")
_HYPR_MODS = ((64, "super"), (4, "ctrl"), (8, "alt"), (1, "shift"))
_HYPR_RELEVANT = re.compile(r"terminal|kitty|scratch|special|dropdown|--class|pypr|ghostty|\bfoot\b|alacritty|wezterm|float-term|drop-term", re.I)
_HYPR_CATEGORY = re.compile(r"^\[[^\]]*\]\s*")                         # HyDE writes "[Launcher|Apps] terminal emulator"


def chord_key(chord: str) -> str:
    """One spelling per chord, for comparing: modifier ORDER, case and `slash` vs `/` do not matter."""
    c = chord.strip().lower()
    key = "+" if c.endswith("++") else c.rsplit("+", 1)[-1]
    head = c[:-2] if c.endswith("++") else (c.rpartition("+")[0])
    mods = sorted({_MOD_NAME[m] for m in head.split("+") if m in _MOD_NAME}, key=_MOD_ORDER.get)
    return "+".join(mods + [_KEY_WORDS.get(key, key)])


def _collapse(action: str) -> str:
    return " ".join(action.split())


def _kitty_mod(lines: list[str], default: str = "ctrl+shift") -> str:
    out = default
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "kitty_mod":
            out = parts[1].lower()
    return out


def _parse(lines: list[str], kitty_mod: str) -> list[tuple[str, str, str, str]]:
    """(key as written, description, action, condition) for every map / mouse_map, last definition of a key winning, in order of first appearance.
    `condition` is the `--when-focus-on` text of a conditional map ("" for a plain one): it only applies while that window has focus, so it is
    kept apart from the plain map of the same chord."""
    commented: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if line.startswith("#"):
            m = _KEY_COMMENT.match(line.lstrip("#").strip())
            if m:
                key, desc = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
                commented[chord_key(key)] = desc.strip()
    rows: dict[str, tuple[str, str, str, str]] = {}
    comment = ""
    for raw in lines:
        line = raw.strip()
        if line.startswith("#"):
            text = line.lstrip("#").strip()
            if not text or _DECORATION.match(text):
                comment = ""                                          # a rule or a section banner describes nothing below it
            elif _KEY_COMMENT.match(text):
                pass                                                  # `# key — description`: attached to ITS key, not to the next line
            else:
                comment = text
            continue
        parts = line.split()
        if not parts:
            comment = ""
            continue
        key = action = cond = ""
        if parts[0] == "map":
            args = parts[1:]
            while args and args[0].startswith("--"):
                if args[0] == "--when-focus-on" and len(args) > 1:
                    cond = args[1]
                args = args[2:] if args[0] in _MAP_OPTIONS_WITH_VALUE else args[1:]
            if len(args) >= 2:
                key, action = args[0], " ".join(args[1:])
        elif parts[0] == "mouse_map" and len(parts) >= 4:
            mods, _, button = parts[1].rpartition("+")
            key = (mods + "+" if mods else "") + _MOUSE_BUTTON.get(button.lower(), button)
            if parts[2] != "press":
                key += f" ({parts[2]})"
            action = " ".join(parts[4:])
        if key:
            key = key.lower().replace("kitty_mod", kitty_mod)
            ck = chord_key(key)
            desc = commented.get(ck) or comment or (action if len(action) <= 70 else action[:69] + "…")
            rows[ck + ("@" + cond if cond else "")] = (key, desc, action, cond)
        comment = ""
    return list(rows.values())


def parse_user_maps(text: str, kitty_mod: str = "ctrl+shift") -> list[tuple[str, str]]:
    """(key, description) for every `map` / `mouse_map` line of a kitty config text. The description is the `# key — description` comment that
    names the key, else the plain comment line right above it, else what it runs. A `kitty_mod …` line in the text overrides `kitty_mod`."""
    lines = text.splitlines()
    return [(k, d) for k, d, _a, cond in _parse(lines, _kitty_mod(lines, kitty_mod)) if not cond]


def _segments(cfg_dir: str, conf: str | None) -> list[tuple[str, list[str]]]:
    """[(file name, its own lines)] in kitty's reading order: kitty.conf and everything it includes, minus the files kittymux wrote.
    Missing files and include cycles are skipped."""
    conf = conf or os.path.join(cfg_dir, "kitty.conf")
    seen: set[str] = set()
    out: list[tuple[str, list[str]]] = []

    def visit(path: str) -> None:
        path = os.path.realpath(os.path.expanduser(path))
        if path in seen or not os.path.isfile(path):
            return
        seen.add(path)
        base = os.path.basename(path)
        if base.startswith("kittymux") or base in _NOT_OURS:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            return
        mine: list[str] = []
        out.append((base, mine))
        for line in lines:
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0] == "include":
                target = os.path.expanduser(parts[1].strip())
                if not os.path.isabs(target):
                    target = os.path.join(os.path.dirname(path), target)
                for hit in sorted(glob.glob(target)) or [target]:
                    visit(hit)
                out.append((base, mine := []))                       # what follows the include is read after it
            else:
                mine.append(line)

    try:
        visit(conf)
    except Exception:
        return []
    return [(name, lines) for name, lines in out if lines]


def user_map_sources(cfg_dir: str, conf: str | None = None) -> dict[str, tuple[str, str]]:
    """chord_key → (the file of yours that defines it, its action); the last definition wins, as in kitty."""
    segs = _segments(cfg_dir, conf)
    mod = _kitty_mod([line for _n, ls in segs for line in ls])
    src: dict[str, tuple[str, str]] = {}
    for name, lines in segs:
        for key, _desc, action, cond in _parse(lines, mod):
            if not cond:
                src[chord_key(key)] = (name, action)
    return src


def user_kitty_maps(cfg_dir: str, conf: str | None = None) -> list[tuple[str, str]]:
    """(key, description) for the maps in YOUR kitty config (kitty.conf and its includes, kittymux's own files excluded)."""
    segs = _segments(cfg_dir, conf)
    mod = _kitty_mod([line for _n, ls in segs for line in ls])
    rows: dict[str, tuple[str, str]] = {}
    for _name, lines in segs:
        for key, desc, _action, cond in _parse(lines, mod):
            if not cond:
                rows[chord_key(key)] = (key, desc)
    return list(rows.values())


def conflicts(ours: str, user: dict) -> list[tuple[str, str, str, str]]:
    """(chord, your file, your action, our action) for every chord both define with a DIFFERENT action. `ours` is the text of kittymux-keys.conf
    (or the template); `user` is user_map_sources(). Our file is read later by kitty, so for these ours is the one in effect."""
    lines = ours.splitlines()
    out = []
    for key, _desc, action, cond in _parse(lines, _kitty_mod(lines)):
        hit = None if cond else user.get(chord_key(key))
        if hit and _collapse(hit[1]) != _collapse(action):
            out.append((key, hit[0], hit[1], action))
    return out


def hypr_rows(binds) -> list[tuple[str, str]]:
    """(chord, description) for the Hyprland binds (`hyprctl binds -j`) that open terminals or scratchpads. Never raises."""
    out: list[tuple[str, str]] = []
    for b in binds if isinstance(binds, list) else []:
        try:
            if not isinstance(b, dict):
                continue
            key = str(b.get("key", "")).strip()
            if not key:
                continue
            mask = int(b.get("modmask", 0))
            desc = _HYPR_CATEGORY.sub("", str(b.get("description") or "").strip())
            dispatcher, arg = str(b.get("dispatcher") or ""), str(b.get("arg") or "")
            if not _HYPR_RELEVANT.search(" ".join((desc, dispatcher, arg))):
                continue
            chord = "+".join([name for bit, name in _HYPR_MODS if mask & bit] + [key.lower()])
            out.append((chord, desc or f"{dispatcher} {arg}".strip()))
        except (TypeError, ValueError):
            continue
    return out


def yours_groups(kitty_rows: list, hypr: list) -> list[tuple[str, list[tuple[str, str]]]]:
    out = []
    if kitty_rows:
        out.append(("YOURS · KITTY  (your own config — kittymux leaves these alone)", list(kitty_rows)))
    if hypr:
        out.append(("YOURS · HYPRLAND  (terminals & scratchpads — Hyprland sees these first)", list(hypr)))
    return out


def drop_overridden(groups: list, keys: set) -> list:
    """Kitty's built-in rows you have re-mapped (ctrl+shift+h is YOUR scrollback-in-nvim) must not be listed twice with two meanings."""
    gone = {k.lower() for k in keys}
    return [(title, [(k, d) for k, d in rows if k.lower() not in gone]) for title, rows in groups]
