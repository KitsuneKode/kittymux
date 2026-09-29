#!/usr/bin/env python3
"""key-hud.py — which-key overlay: parse the keybinds conf and render a
grouped cheat-sheet card. Stays open until q/esc. Always accurate because
it reads the same file kitty does.

Usage: key-hud.py [conf-path]
"""

import os
import re
import sys
import termios
import tty

# ── palette: derived from the live kitty theme ─────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "python"))
import kittymux_theme  # noqa: E402

_P = kittymux_theme.palette_from_kitty()


def _sgr(rgb: int) -> str:
    return "\033[38;2;%d;%d;%dm" % (rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255)


C = {
    "reset": "\033[0m",
    "dim": _sgr(_P.faint),
    "title": _sgr(_P.info),
    "key": _sgr(_P.waiting),
    "desc": _sgr(_P.text),
    "head": _sgr(_P.accent),
    "border": _sgr(_P.line),
    "sel": "\033[7m",
}

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _vlen(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


# ── conf parsing ────────────────────────────────────────────────────────────

_KEY_IN_COMMENT = re.compile(
    r"^#\s*((?:ctrl|shift|alt|kitty_mod|cmd|super|caps_lock)\+[+\w;,.\[\]/=-]+"
    r"|[+\w;,.\[\]/=-]+[+][\w;,.\[\]/=-]+)\s*(?:\(.*?\))?\s*[-—–]{1,2}\s*(.+)$")

_SECTION_MARK = re.compile(r"^#\s*=+\s*$")
_MAP_LINE = re.compile(r"^map(?:\s+--when-focus-on\s+\S+)?\s+(\S+)\s+(.*)$")

_LABELS = {
    "kitty-sessionizer": "Kitty Home — session ops",
    "session-cycle": "session cycle",
    "session-nav": "session-scoped tab nav",
    "new-tab-before-scratch": "new tab",
    "move-tab": "move tab to OS window",
    "save_session": "save session",
    "scratch-tab": "scratch tab",
    "project-picker": "project picker",
    "agent-picker": "agent picker",
    "agent-send": "send prompt to agent pane",
    "agent-jump": "cycle agent panes",
    "agent-usage": "agent usage HUD",
    "cwd-hud": "location pill",
    "tab-edge-toggle": "tab bar edge",
    "font-toggle": "font size toggle",
    "snap": "screenshot → ~/Pictures",
    "mux-usage": "agent usage HUD",
    "mux-agents": "agent picker",
    "mux-send": "send prompt to agent pane",
    "mux-jump": "cycle agent panes",
    "mux-cwd": "location pill",
    "mux-edge": "tab bar edge",
    "mux-newtab": "new tab",
    "mux-nav": "session-scoped tab nav",
    "mux-cycle": "session cycle",
    "mux-movetab": "move tab to OS window",
    "mux-save": "save session",
    "mux-scratch": "scratch tab",
    "mux-projects": "project picker",
    "mux-sessionizer": "Kitty Home",
}

_ACTION_LABELS = {
    "neighboring_window": "focus pane",
    "nth_window": "pane",
    "detach_window": "pane →",
    "set_tab_title": "rename tab",
    "new_os_window_with_cwd": "new OS window (cwd)",
    "move_tab_backward": "move tab ←",
    "move_tab_forward": "move tab →",
    "next_layout": "next layout",
    "toggle_layout": "layout",
    "layout_action": "layout",
    "close_tab": "close tab",
    "close_window": "close pane",
    "show_last_command_output": "last command output",
    "show_scrollback": "scrollback pager",
    "scroll_to_prompt": "scroll to prompt",
    "resize_window": "resize pane",
    "send_text": "send text",
    "toggle_fullscreen": "fullscreen",
    "load_config_file": "reload config",
    "goto_session": "session",
}

_TAIL_WORDS = {
    "prev": "prev", "previous": "prev", "next": "next", "last": "last",
    "left": "←", "right": "→", "up": "↑", "down": "↓",
    "hsplit": "horizontal", "vsplit": "vertical",
    "maximize": "zoom/unzoom", "equalize": "equalize",
    "new-tab-right": "→ new tab", "ask": "chooser",
}


def _humanize(rest: str) -> str:
    parts = rest.split()
    action = parts[0] if parts else ""
    for stem, label in _LABELS.items():
        if stem in rest:
            tail = parts[-1] if parts else ""
            suffix = ""
            if tail and tail in _TAIL_WORDS:
                suffix = " " + _TAIL_WORDS[tail]
            elif tail and re.fullmatch(r"\d+", tail):
                suffix = " " + tail
            return label + suffix
    label = _ACTION_LABELS.get(action, "")
    if label:
        if action == "launch":
            return _humanize_launch(rest) or label
        for p in reversed(parts[1:]):
            if p in _TAIL_WORDS:
                return f"{label} {_TAIL_WORDS[p]}"
            if re.fullmatch(r"-?\d+", p):
                return f"{label} {p}" if p != "-1" else "last pane"
        if action == "send_text":
            return "app newline escape"
        return label
    if action == "launch":
        return _humanize_launch(rest) or "launch"
    if action == "combine":
        return "reload config (+ notify)"
    return action


def _clean_section(name: str) -> str:
    name = re.sub(r"\s*[—–].*$", "", name)  # em/en dash separators only
    name = re.sub(r"\s+-\s.*$", "", name)  # spaced ascii hyphen
    name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
    # the header comment and the title often merge: "SPLITS cwd-preserving,
    # same as before" → keep just the leading ALL-CAPS-ish title part
    m = re.match(r"^([A-Z][A-Z0-9 &/\-]+?)(?:\s+[a-z].*)?$", name)
    if m:
        name = m.group(1)
    return name.upper()


def _humanize_launch(rest: str) -> str:
    if "--location=hsplit" in rest:
        return "split horizontal (cwd)"
    if "--location=vsplit" in rest:
        return "split vertical (cwd)"
    return ""

_SECTION_ORDER = {
    "SESSION MANAGEMENT": 0, "TABS & OS WINDOWS": 1, "TAB NAVIGATION": 2,
    "PANE NAVIGATION": 3, "SPLITS": 4, "LAYOUTS": 5, "HUDS": 6,
    "AGENTS": 6, "PROJECT PICKER": 7, "QUICK CONFIG EDITS": 8,
    "FONT TOGGLE": 9, "TMUX PASSTHROUGH": 10, "OTHER": 11,
}


def _collapse_digit_runs(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """ctrl+alt+1..ctrl+alt+9 same-desc runs → one row 'ctrl+alt+1…9'."""
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(rows):
        key, desc = rows[i]
        m = re.match(r"^(.*?)(\d)$", key)
        if m:
            prefix, first = m.group(1), int(m.group(2))
            j = i
            while (j + 1 < len(rows)
                   and rows[j + 1][0] == f"{prefix}{int(rows[j][0][-1]) + 1}"
                   and rows[j + 1][1].rstrip(" 0123456789") == desc.rstrip(" 0123456789")):
                j += 1
            if j - i >= 2:
                base_desc = re.sub(r"\s*\d+\s*$", "", desc)
                out.append((f"{prefix}{first}…{j - i + first}", base_desc))
                i = j + 1
                continue
        out.append((key, desc))
        i += 1
    return out


def parse_conf(path: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """→ [(section, [(key, desc)])] in file order."""
    sections: list[tuple[str, list]] = []
    key_comments: dict[str, str] = {}
    current = "MISC"
    in_header = False
    seen_title = False

    with open(path, encoding="utf-8", errors="replace", ) as f:
        for raw in f:
            line = raw.rstrip("\n")
            if _SECTION_MARK.match(line):
                if not in_header:
                    in_header = True
                    seen_title = False
                else:
                    in_header = False
                continue
            if in_header and not seen_title:
                m = re.match(r"^#\s+(.+?)\s*$", line)
                if m and not _KEY_IN_COMMENT.match(line):
                    current = m.group(1).strip()
                    seen_title = True
                    if not any(s == current for s, _ in sections):
                        sections.append((current, []))
                continue
            m = _KEY_IN_COMMENT.match(line)
            if m:
                key_comments[m.group(1).strip()] = m.group(2).strip()
                continue
            m = _MAP_LINE.match(line)
            if m and not line.startswith("map --when-focus-on"):
                key, rest = m.group(1), m.group(2)
                desc = key_comments.pop(key, None) or _humanize(rest)
                for s, rows in sections:
                    if s == current:
                        rows.append((key, desc))
                        break
                else:
                    sections.append((current, [(key, desc)]))
    return [(_clean_section(s), _collapse_digit_runs(r)) for s, r in sections if r]


def _extra_groups() -> list[tuple[str, list[tuple[str, str]]]]:
    return [
        ("KITTY BUILT-INS", [
            ("ctrl+shift+c / v", "copy / paste"),
            ("ctrl+shift+h", "scrollback in pager"),
            ("ctrl+shift+u", "unicode input"),
            ("ctrl+shift+alt+r", "reload config"),
        ]),
        ("MOUSE", [
            ("drag tab", "reorder"),
            ("drag split border", "resize panes"),
            ("hover edge", "scrollbar appears"),
        ]),
    ]


# ── render ──────────────────────────────────────────────────────────────────

def _truncate(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[:max(0, limit - 1)] + "…"


def _render(sections, term_cols: int = 190) -> list[str]:
    cols = 3
    col_w = max(34, min(58, (term_cols - 8) // cols))
    key_w = 22
    desc_w = col_w - key_w - 3
    # stable, meaningful column order
    ordered = sorted(
        sections,
        key=lambda sr: _SECTION_ORDER.get(sr[0].upper(), 99))
    ordered += _extra_groups()

    # split into column buckets round-robin by height
    heights = [0] * cols
    buckets: list[list] = [[] for _ in range(cols)]
    for name, rows in ordered:
        block_h = len(rows) + 2
        c = heights.index(min(heights))
        buckets[c].append((name, rows))
        heights[c] += block_h

    # render each column as lines
    col_lines: list[list[str]] = []
    for bucket in buckets:
        lines: list[str] = []
        for name, rows in bucket:
            lines.append(f"{C['head']}{name}{C['reset']}")
            for key, desc in rows:
                desc = _truncate(desc, desc_w)
                lines.append(
                    f"  {C['key']}{_truncate(key, key_w):<{key_w}}{C['reset']}{C['desc']}{desc}{C['reset']}")
            lines.append("")
        col_lines.append(lines)

    height = max((len(c) for c in col_lines), default=0)
    body: list[str] = []
    for i in range(height):
        row = ""
        for c in range(cols):
            cell = col_lines[c][i] if i < len(col_lines[c]) else ""
            pad = col_w - _vlen(cell)
            row += cell + " " * max(0, pad)
        body.append(row.rstrip())

    inner_w = max((_vlen(l) for l in body), default=40)
    inner_w = max(inner_w, 40)
    top = (f"{C['border']}╭{C['reset']}"
           f"{C['title']} keymap{C['reset']}{C['dim']} · parsed from your conf{C['reset']}"
           f"{' ' * max(0, inner_w - _vlen(' keymap · parsed from your conf'))}"
           f"{C['border']}╮{C['reset']}")
    bot = (f"{C['border']}╰{C['reset']}"
           f"{C['dim']}any key closes{C['reset']}"
           f"{' ' * max(0, inner_w - _vlen('any key closes'))}"
           f"{C['border']}╯{C['reset']}")
    out = [top]
    for l in body:
        pad = inner_w - _vlen(l)
        out.append(f"{C['border']}│{C['reset']}{l}{' ' * pad}{C['border']}│{C['reset']}")
    out.append(bot)
    return out


def _draw(lines, rows, cols):
    w = _vlen(lines[0]) + 2
    h = len(lines)
    left = max(0, (cols - w) // 2)
    top = max(0, (rows - h) // 2)
    sys.stdout.write("\033[H")
    for i, line in enumerate(lines):
        sys.stdout.write(f"\033[{top + i};{left}f" + line)
    sys.stdout.flush()


def _last_box(lines):
    w = _vlen(lines[0]) + 2
    return len(lines), w


def main() -> int:
    conf = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
        "kitty", "kittymux-keys.conf")
    try:
        term_cols = os.get_terminal_size().columns
    except OSError:
        term_cols = 190
    lines = _render(parse_conf(conf), term_cols)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[2J\033[?25l")
        while True:
            size = os.get_terminal_size()
            _draw(lines, size.lines, size.columns)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                sys.stdin.read(2)  # arrow keys etc.
            break  # any key dismisses
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\033[?25h\033[2J\033[H")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
