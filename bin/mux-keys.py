#!/usr/bin/env python3
"""mux-keys.py — the keymap overlay (ctrl+alt+/): every kittymux key, mouse gesture and command, parsed
live from the keybinds conf so it never drifts. Scrollable, searchable (just type, or /), responsive
(1–3 columns by width). q / esc closes, and so does ctrl+alt+/ again.

Usage: mux-keys.py [conf-path] [--leader]
"""

import os
import re
import select
import signal
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
    "SESSIONS": 0, "TABS": 1, "PANES": 2, "LAYOUTS": 3, "RESIZE, SCROLLBACK & HELP": 4, "HUDS": 5,
    "PROJECT PICKER + SCRATCH CONFIG TAB": 6, "OTHER": 9,
}

_KEY_WORDS = {"slash": "/", "comma": ",", "period": ".", "semicolon": ";", "backslash": "\\", "bracketleft": "[",
              "bracketright": "]", "grave_accent": "`", "minus": "-", "equal": "=", "page_up": "PgUp", "page_down": "PgDn",
              "left": "←", "right": "→", "up": "↑", "down": "↓", "enter": "enter", "home": "Home", "end": "End"}


def display_key(key: str) -> str:
    """`ctrl+alt+shift+bracketleft` → `ctrl+alt+shift+[`: kitty's spelling is for the config, not for reading."""
    head, sep, tail = key.rpartition("+")
    return head + sep + _KEY_WORDS.get(tail, tail) if sep else _KEY_WORDS.get(key, key)


def _comment_key(key: str) -> str:
    """The conf spells a key `ctrl+alt+slash`; its comment may say `ctrl+alt+/`. Compare them in one spelling."""
    head, sep, tail = key.rpartition("+")
    back = {v: k for k, v in _KEY_WORDS.items() if len(v) == 1}
    return (head + sep + back.get(tail, tail)).lower() if sep else key.lower()


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
                key_comments[_comment_key(m.group(1).strip())] = m.group(2).strip()
                continue
            m = _MAP_LINE.match(line)
            if m and not line.startswith("map --when-focus-on"):
                key, rest = m.group(1), m.group(2)
                desc = key_comments.pop(_comment_key(key), None) or _humanize(rest)
                for s, rows in sections:
                    if s == current:
                        rows.append((key, desc))
                        break
                else:
                    sections.append((current, [(key, desc)]))
    return [(_clean_section(s), [(display_key(k), d) for k, d in _collapse_digit_runs(r)]) for s, r in sections if r]


# ── leader-mode card ────────────────────────────────────────────────────────

_LEADER_KEYS = {"backslash": "\\", "minus": "-", "equal": "=", "space": "␣",
                "semicolon": ";", "slash": "/", "shift+slash": "?", "comma": ",", "period": "."}


def _leader_key(k: str) -> str:
    if k in _LEADER_KEYS:
        return _LEADER_KEYS[k]
    if k.startswith("shift+") and len(k) == 7:
        return k[-1].upper()
    return k


def parse_leader(conf: str) -> tuple[str, list[list[tuple[str, str]]]]:
    """(leader key, groups of (key, description)) from kittymux-leader.conf.
    A `# description` line documents the `map --mode leader KEY …` line below it;
    blank lines separate groups."""
    leader, groups, cur, pending = "leader", [], [], ""
    try:
        text = open(conf, encoding="utf-8").read().splitlines()
    except OSError:
        return leader, []
    for line in text:
        line = line.strip()
        if not line:
            if cur:
                groups.append(cur)
                cur = []
            pending = ""
            continue
        m = re.match(r"^map\s+--new-mode\s+leader\b.*\s(\S+)$", line)
        if m:
            leader = m.group(1)
            continue
        m = re.match(r"^map\s+--mode\s+leader\s+(\S+)\s+.*$", line)
        if m:
            cur.append((_leader_key(m.group(1)), pending or "?"))
            pending = ""
            continue
        if line.startswith("#"):
            pending = line.lstrip("#").strip()
    if cur:
        groups.append(cur)
    # collapse "jump to tab N" runs into one row
    out = []
    for g in groups:
        rows, digits = [], [r for r in g if r[1].startswith("jump to tab")]
        for r in g:
            if r in digits:
                if r is digits[0] and len(digits) > 1:
                    rows.append((f"{digits[0][0]}…{digits[-1][0]}", "jump to tab N"))
                elif len(digits) == 1:
                    rows.append(r)
                continue
            rows.append(r)
        out.append(rows)
    return leader, out


def extra_groups() -> list[tuple[str, list[tuple[str, str]]]]:
    """Everything kittymux does that is not a key in the conf: the deck, the mouse, the CLI, switches."""
    return [
        ("DECK  (ctrl+alt+b)", [
            ("j / k", "move down / up"),
            ("J / K", "previous / next session"),
            ("enter", "go to the tab or pane"),
            ("/  or just type", "find by title, branch, folder, agent, state"),
            ("a", "absorb the pane into the tab you came from"),
            ("t", "promote the pane to its own tab"),
            ("hover · click", "preview a tab or pane · focus it"),
            ("q / esc", "close (esc clears a search first)"),
        ]),
        ("TAB BAR  (mouse)", [
            ("click a tab", "switch to it"),
            ("right-click a tab", "peek card: its panes and live screen"),
            ("drag a tab", "reorder"),
            ("drag a pane title onto a tab", "move that split into the tab (ctrl+alt+shift+h shows the titles)"),
            ("drag a pane title onto the bar", "turn the split into its own tab"),
            ("drag the bar's edge", "resize the sidebar"),
            ("click « / »", "collapse to the rail / expand"),
        ]),
        ("FILE REFERENCES", [
            ("ctrl+shift+click", "src/app.py:42 → open in $EDITOR at that line (kitty ≥ 0.49.2)"),
        ]),
        ("COMMANDS  (kittymux …)", [
            ("doctor", "check the install and your window manager's key conflicts"),
            ("inbox [ack|jump|clear|watch]", "questions, permissions, usage limits and finished runs — jump to the one that needs you"),
            ("sessions save|restore|new|list", "save/restore sessions WITH agent conversations (--resume), new ones from templates; autosaves too"),
            ("sessions history|recover", "every agent session journaled as it runs: insights, and a session rebuilt after a crash (restored agents ask before resuming)"),
            ("explain", "why each agent pane is in its state + every recent decision (sent or held-back notifications)"),
            ("upgrade", "after a git pull: reload every kitty and re-check"),
            ("layout mode|edge|width|pick", "tab bar: full / rail / hidden, side, width, presets"),
            ("dim on|off|toggle", "dim the panes that are not focused (kitty ≥ 0.49.2)"),
            ("screenshot [--tab|--window] [file]", "PNG of this kitty window, rendered by kitty"),
            ("hooks --install", "Claude Code status hooks (backs up settings first)"),
            ("demo · uninstall", "try it in a scratch window · take it back out"),
        ]),
        ("NOTIFICATIONS  (~/.local/state/kittymux)", [
            ("touch notify-off", "no desktop notifications at all"),
            ("touch notify-done-off", "only needs-you ones, not completions"),
            ("touch notify-private", "show \"<agent> needs you\" instead of the question"),
            ("touch bell-off", "no window-manager urgency flash"),
        ]),
        ("SCROLLBACK & HINTS  (kitty built-ins)", [
            ("ctrl+shift+↑ ↓  or  j k", "scroll a line"),
            ("ctrl+shift+PgUp / PgDn", "scroll a page"),
            ("ctrl+shift+Home / End", "oldest output / live screen"),
            ("ctrl+shift+z / x", "previous / next shell prompt"),
            ("ctrl+shift+h", "scrollback in a pager (/ searches)"),
            ("ctrl+shift+g", "last command's output"),
            ("ctrl+shift+e", "open a URL by typing its letter"),
            ("ctrl+shift+p, n", "pick a file:line on screen, open it in the editor"),
            ("ctrl+shift+p, f / w / h", "insert a path / word / hash from the screen"),
            ("ctrl+shift+f3", "command palette: search every kitty action"),
        ]),
        ("KITTY BUILT-INS", [
            ("ctrl+shift+c / v", "copy / paste"),
            ("ctrl+shift+u", "unicode input"),
            ("ctrl+shift+alt+r", "reload config"),
            ("drag a split border", "resize panes"),
        ]),
    ]


# ── search / layout (pure) ──────────────────────────────────────────────────

def words_of(query: str) -> list[str]:
    return [w for w in query.lower().split() if w]


def filter_sections(sections, query: str):
    """Rows whose section, key or description contain every word of `query` (case-insensitive); empty sections drop out."""
    words = words_of(query)
    if not words:
        return sections
    out = []
    for name, rows in sections:
        keep = [(k, d) for k, d in rows if all(w in f"{name} {k} {d}".lower() for w in words)]
        if keep:
            out.append((name, keep))
    return out


def column_count(width: int) -> int:
    return 3 if width >= 150 else 2 if width >= 96 else 1


def _highlight(text: str, words: list[str]) -> str:
    """Reverse-video every occurrence of a search word in `text` (plain text in, SGR out)."""
    if not words:
        return text
    low, marks = text.lower(), [False] * len(text)
    for w in words:
        i = low.find(w)
        while i != -1:
            for j in range(i, i + len(w)):
                marks[j] = True
            i = low.find(w, i + len(w))
    out, on = "", False
    for ch, m in zip(text, marks):
        if m != on:
            out += "\033[7m" if m else "\033[27m"
            on = m
        out += ch
    return out + ("\033[27m" if on else "")


def build_body(sections, width: int, query: str = "") -> list[str]:
    """The scrollable text for a terminal `width` cells wide: sections packed into 1–3 columns."""
    words = words_of(query)
    inner = max(20, width - 3)                       # one cell of margin each side + the scrollbar
    ncols = column_count(inner)
    col_w = (inner - 2 * (ncols - 1)) // ncols
    key_w = max(10, min(26 if ncols > 1 else 30, col_w * 2 // 5 if ncols > 1 else col_w // 2))
    desc_w = max(8, col_w - key_w - 3)
    heights, buckets = [0] * ncols, [[] for _ in range(ncols)]
    for name, rows in sections:
        c = heights.index(min(heights))
        buckets[c].append((name, rows))
        heights[c] += len(rows) + (2 if name else 1)
    cols: list[list[str]] = []
    for bucket in buckets:
        lines: list[str] = []
        for name, rows in bucket:
            if name:
                lines.append(f"{C['head']}{_highlight(_truncate(name, col_w), words)}{C['reset']}")
            for key, desc in rows:
                k, d = _truncate(key, key_w), _truncate(desc, desc_w)
                gap = " " * (key_w - len(k))
                lines.append(f"  {C['key']}{_highlight(k, words)}{C['reset']}{gap} {C['desc']}{_highlight(d, words)}{C['reset']}")
            lines.append("")
        cols.append(lines)
    body = []
    for i in range(max((len(c) for c in cols), default=0)):
        row = ""
        for n, c in enumerate(cols):
            cell = c[i] if i < len(c) else ""
            row += cell + " " * max(0, col_w - _vlen(cell)) + ("  " if n < ncols - 1 else "")
        body.append(" " + row.rstrip())
    while body and not body[-1].strip():
        body.pop()
    return body


def _truncate(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[:max(0, limit - 1)] + "…"


# ── input (pure) ────────────────────────────────────────────────────────────

_MOUSE = re.compile(r"\x1b\[<(\d+);\d+;\d+[Mm]")
_CSI = re.compile(r"\x1b\[[0-9;?<]*[ -/]*[@-~]")
_KEYS = {"\x1b[A": "up", "\x1b[B": "down", "\x1bOA": "up", "\x1bOB": "down", "\x1b[5~": "pgup", "\x1b[6~": "pgdn",
         "\x1b[H": "home", "\x1b[F": "end", "\x1b[1~": "home", "\x1b[4~": "end", "\x1bOH": "home", "\x1bOF": "end"}
_CTRL = {"\x03": "ctrl-c", "\x04": "ctrl-d", "\x07": "esc", "\x0e": "down", "\x10": "up", "\x15": "ctrl-u",
         "\r": "enter", "\n": "enter", "\x7f": "backspace", "\x08": "backspace"}


def parse_input(data: str) -> list[str]:
    """Raw terminal input → key tokens ('up', 'pgdn', 'wheel_down', 'esc', 'a', …). A lone ESC byte is Escape
    (it arrives alone; arrow keys and mouse reports arrive as one chunk)."""
    toks, i = [], 0
    while i < len(data):
        rest = data[i:]
        m = _MOUSE.match(rest)
        if m:
            btn = int(m.group(1))
            if btn in (64, 65):
                toks.append("wheel_up" if btn == 64 else "wheel_down")
            i += m.end()
            continue
        if rest[0] == "\x1b":
            if len(rest) == 1:
                toks.append("esc")
                i += 1
                continue
            hit = next((k for k in _KEYS if rest.startswith(k)), None)
            if hit:
                toks.append(_KEYS[hit])
                i += len(hit)
                continue
            m = _CSI.match(rest)
            i += m.end() if m else 1                  # an unknown escape sequence: swallow it whole
            continue
        ch = rest[0]
        i += 1
        if ch in _CTRL:
            toks.append(_CTRL[ch])
        elif ch >= " " and ch != "\x7f":
            toks.append(ch)
    return toks


class State:
    def __init__(self):
        self.query, self.searching, self.top = "", False, 0


def step(st: State, tok: str, body_len: int, view_h: int) -> str | None:
    """Apply one key to the state; returns "quit" to close. Pure: no terminal access."""
    page = max(1, view_h - 1)
    scroll = {"up": -1, "down": 1, "wheel_up": -3, "wheel_down": 3, "pgup": -page, "pgdn": page}
    if tok in scroll:
        st.top += scroll[tok]
    elif tok == "home":
        st.top = 0
    elif tok == "end":
        st.top = body_len
    elif tok == "ctrl-c":
        return "quit"
    elif tok == "esc":
        if st.query or st.searching:
            st.query, st.searching, st.top = "", False, 0       # esc backs out of a search first…
        else:
            return "quit"                                        # …then closes
    elif st.searching:
        if tok == "enter":
            st.searching = False
        elif tok == "backspace":
            st.query = st.query[:-1]
            st.searching, st.top = bool(st.query), 0
        elif tok == "ctrl-u":
            st.query, st.top = "", 0
        elif len(tok) == 1:
            st.query, st.top = st.query + tok, 0
    elif tok == "/":
        st.searching = True
    elif tok in ("q",):
        return "quit"
    elif tok in ("j",):
        st.top += 1
    elif tok in ("k",):
        st.top -= 1
    elif tok in (" ", "f", "ctrl-d"):
        st.top += page if tok != "ctrl-d" else page // 2
    elif tok in ("b", "ctrl-u"):
        st.top -= page if tok != "ctrl-u" else page // 2
    elif tok == "g":
        st.top = 0
    elif tok == "G":
        st.top = body_len
    elif tok == "backspace" and st.query:
        st.query = st.query[:-1]
    elif len(tok) == 1:                                           # any other character starts a search
        st.query, st.searching, st.top = tok, True, 0
    st.top = max(0, min(st.top, max(0, body_len - view_h)))
    return None


# ── screen ──────────────────────────────────────────────────────────────────

def frame(st: State, sections, rows: int, cols: int) -> list[str]:
    """The whole screen as exactly `rows` lines (each at most `cols` wide). Clamps st.top."""
    cols, rows = max(30, cols), max(6, rows)
    shown = filter_sections(sections, st.query)
    body = build_body(shown, cols, st.query)
    view_h = rows - 4
    st.top = max(0, min(st.top, max(0, len(body) - view_h)))
    n = sum(len(r) for _, r in shown)
    total = sum(len(r) for _, r in sections)
    title = f" {C['title']}keymap{C['reset']}{C['dim']} · {n if st.query else total} bindings · parsed from your conf{C['reset']}"
    if st.searching:
        search = f" {C['key']}/{C['reset']} {C['desc']}{st.query}{C['reset']}{C['key']}▏{C['reset']}"
    elif st.query:
        search = f" {C['key']}/{C['reset']} {C['desc']}{st.query}{C['reset']}{C['dim']}  · esc clears{C['reset']}"
    else:
        search = f" {C['dim']}type to search · / also works{C['reset']}"
    out = [title, search, f"{C['border']}{'─' * cols}{C['reset']}"]
    window = body[st.top:st.top + view_h]
    if not body:
        window = [f" {C['dim']}no bindings match “{st.query}”{C['reset']}"]
    thumb = (0, 0)
    if len(body) > view_h:
        size = max(1, view_h * view_h // len(body))
        start = (view_h - size) * st.top // max(1, len(body) - view_h)
        thumb = (start, start + size)
    for i in range(view_h):
        line = window[i] if i < len(window) else ""
        bar = f"{C['border']}┃{C['reset']}" if thumb[0] <= i < thumb[1] else (f"{C['dim']}│{C['reset']}" if thumb[1] else " ")
        out.append(line + " " * max(0, cols - 1 - _vlen(line)) + bar)
    pos = "" if len(body) <= view_h else (" top" if st.top == 0 else " end" if st.top >= len(body) - view_h
                                          else f" {100 * (st.top + view_h) // len(body)}%")
    help_text = "↑↓ j/k scroll · space/b page · g/G ends · / search · q or esc close"
    help_text = help_text if len(help_text) + len(pos) + 2 <= cols else "↑↓ scroll · / search · q close"
    out.append(f" {C['dim']}{help_text}{' ' * max(0, cols - len(help_text) - len(pos) - 2)}{pos}{C['reset']}")
    return out


def sections_for(conf: str, leader: bool) -> list:
    if leader:
        key, groups = parse_leader(conf)
        if not groups:
            groups = [[("—", "leader mode is not installed — run install.sh --leader")]]
        return [((f"LEADER · {key} then a key" if i == 0 else ""), g) for i, g in enumerate(groups)]
    ordered = sorted(parse_conf(conf), key=lambda sr: _SECTION_ORDER.get(sr[0].upper(), 99))
    return ordered + extra_groups()


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    leader = "--leader" in sys.argv
    cfg_dir = os.environ.get("KITTY_CONFIG_DIRECTORY") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "kitty")
    conf = args[0] if args else os.path.join(cfg_dir, "kittymux-leader.conf" if leader else "kittymux-keys.conf")
    sections = sections_for(conf, leader)
    st = State()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    resized = [True]
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\033[?1049h\033[?25l\033[?1000h\033[?1006h")
        while True:
            if resized[0]:
                resized[0] = False
                size = os.get_terminal_size()
                lines = frame(st, sections, size.lines, size.columns)
                sys.stdout.write("\033[H" + "\033[K\n".join(lines) + "\033[K")
                sys.stdout.flush()
            try:
                ready, _, _ = select.select([fd], [], [], 0.5)
            except InterruptedError:
                continue
            if not ready:
                continue
            data = os.read(fd, 4096).decode("utf-8", "ignore")
            if data == "\x1b":                       # a lone ESC may be the start of a sequence split by the tty: peek briefly
                if select.select([fd], [], [], 0.02)[0]:
                    data += os.read(fd, 4096).decode("utf-8", "ignore")
            size = os.get_terminal_size()
            body_len = len(build_body(filter_sections(sections, st.query), size.columns, st.query))
            for tok in parse_input(data):
                if step(st, tok, body_len, size.lines - 4) == "quit":
                    return 0
                body_len = len(build_body(filter_sections(sections, st.query), size.columns, st.query))
            resized[0] = True
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\033[?1006l\033[?1000l\033[?25h\033[?1049l")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
