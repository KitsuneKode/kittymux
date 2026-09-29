# Custom kitty tab bar — left side only (Waybar handles stats).
#
# Renders:  [session] ▸1:title ┃ 2:title ┃ 3:title●
#           └─ session prefix         └─ tabs with active/activity markers
#
# active tab  = bold + mauve
# inactive    = subtext0
# session prefix = blue
# activity dot (●) = yellow  (tab has output while unfocused)
# separator   = surface1

import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

from kitty.fast_data_types import Screen, get_boss
from kitty.tab_bar import DrawData, ExtraData, TabBarData, as_rgb

# Catppuccin Mocha
_BG          = as_rgb(0x1e1e2e)  # base
_SESSION_FG  = as_rgb(0x89b4fa)  # blue
_ACTIVE_FG   = as_rgb(0xcba6f7)  # mauve
_INACTIVE_FG = as_rgb(0x6c7086)  # overlay0 (dim inactive tabs)
_ACTIVITY_FG = as_rgb(0xa6e3a1)  # emerald — unread output (t3code "done")
_WAITING_FG  = as_rgb(0xb4befe)  # indigo — agent idle, needs input
_SEP_FG      = as_rgb(0x313244)  # surface0 (subtle separator)
_BRACKET_FG  = as_rgb(0x45475a)  # surface1
_CWD_FG      = as_rgb(0x9399b2)  # overlay2 (right-side cwd anchor)
_BRANCH_FG   = as_rgb(0xa6e3a1)  # green (git branch)

_SESSION_SOFT_MAX = 16
_GENERIC_TITLES = {"kitty", "zsh", "bash", "fish", "sh", "node"}
_EDITOR_NAMES = {"nvim", "vim", "vi", "hx", "helix", "micro"}
_APP_LABELS = {
    "claude": "Claude",
    "codex": "Codex",
    "nvim": "nvim",
    "vim": "vim",
    "hx": "hx",
    "helix": "hx",
    "lazygit": "lazygit",
    "git": "git",
    "ssh": "ssh",
    "python": "python",
    "python3": "python",
    "node": "node",
    "bun": "bun",
}


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "…"


def _basename(value: str) -> str:
    return os.path.basename(value) or value


def _strip_spinner(title: str) -> str:
    return re.sub(r"^[\s⠁-⣿✳✻✽✦•●◐◓◑◒∙·.-]+", "", title).strip()


def _compact_session_name(session_name: str) -> str:
    session_name = session_name.strip()
    if not session_name:
        return "—"

    parts = [part for part in session_name.replace("_", "-").split("-") if part]
    if len(session_name) > _SESSION_SOFT_MAX and len(parts) > 1:
        initials = "".join(part[0] for part in parts)
        if 1 < len(initials) <= 5:
            return initials

    return _truncate(session_name, _SESSION_SOFT_MAX)


def _split_window_count(title: str) -> tuple[str, str]:
    if " :" in title and title.endswith(":"):
        prefix, suffix = title.rsplit(" :", 1)
        count = suffix[:-1]
        if count.isdigit():
            return prefix, f"+{count}"
    return title, ""


def _title_from_cmdline(cmdline: list[str]) -> str:
    if not cmdline:
        return ""

    argv = [_basename(arg) for arg in cmdline]
    lowered = [arg.lower() for arg in argv]

    if "--" in cmdline:
        tail = cmdline[cmdline.index("--") + 1:]
        tail_label = _title_from_cmdline(tail)
        if tail_label:
            return tail_label

    for name in ("nvim", "vim", "hx", "helix", "claude", "codex"):
        if name in lowered:
            return _APP_LABELS[name]

    for item in reversed(lowered):
        if item in _APP_LABELS and item not in {"node"}:
            return _APP_LABELS[item]

    first = lowered[0].lstrip("-")
    return _APP_LABELS.get(first, first)


def _active_window_info(tab_id: int) -> tuple[str, list[str], str]:
    try:
        tab = get_boss().tab_for_id(tab_id)
        window = tab.active_window if tab else None
        if not window:
            return "", [], ""
        cwd = window.child.current_cwd or window.child.cwd or ""
        last_cmd = getattr(window, "last_cmd_cmdline", "") or ""
        foreground = []
        for process in window.child.foreground_processes:
            cmdline = process.get("cmdline") or []
            if cmdline:
                foreground.append(list(cmdline))
        return cwd, foreground, last_cmd
    except Exception:
        return "", [], ""


def _best_process_label(foreground: list[list[str]], last_cmd: str) -> str:
    labels = [_title_from_cmdline(cmdline) for cmdline in foreground]
    labels = [label for label in labels if label]

    # Editors and agent CLIs are the user-facing app, even when wrapped by trmw,
    # node, shell integration, or helper processes.
    for preferred in ("nvim", "vim", "hx", "Claude", "Codex"):
        if preferred in labels:
            return preferred

    if last_cmd:
        try:
            last_label = _title_from_cmdline(shlex.split(last_cmd))
            if last_label and last_label not in _GENERIC_TITLES:
                return last_label
        except ValueError:
            pass

    for label in labels:
        if label not in _GENERIC_TITLES:
            return label

    return labels[-1] if labels else ""


def _clean_visible_title(title: str) -> str:
    title = title.strip()
    if title.startswith("[") and "] " in title:
        title = title.split("] ", 1)[1]

    if title.startswith("!scratch"):
        return "scratch"

    title = _strip_spinner(title)
    title = title.replace("$HOME", "~")
    if "/" in title:
        title = title.rstrip("/").split("/")[-1] or title
    return title


_APP_TITLES = frozenset(_APP_LABELS) | _EDITOR_NAMES
_AGENT_GLYPHS = {
    "claude": "\ue0d8", "codex": "\ue0d9", "cursor-agent": "\ue0da",
    "cursor": "\ue0da", "gemini": "\ue0db", "opencode": "\ue0dc",
    "amp": "\ue0dd", "devin": "\ue0de", "aider": "✎",
    "crush": "♥", "grok": "✗",
}
# Brand accent per provider — matches the usage HUD palette.
_AGENT_BRANDS = {
    "claude": 0xd97757, "codex": 0x10a37f, "cursor-agent": 0x5b8ef4,
    "cursor": 0x5b8ef4, "gemini": 0x4e8cff, "opencode": 0xfab283,
    "amp": 0xf5c2e7, "devin": 0x8b5cf6, "aider": 0xa6e3a1,
    "crush": 0xf38ba8, "grok": 0xf9e2af,
}
_AGENT_PROCS = frozenset(_AGENT_GLYPHS)
_AGENT_FALLBACK = "⚡"
_ALERT_FG = as_rgb(0xf38ba8)   # red — provider quota window >= 85%


def _dim(rgb: int, factor: float = 0.55) -> int:
    r, g, b = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
    return (int(r * factor) << 16) | (int(g * factor) << 8) | int(b * factor)


def _agent_info(tab_id: int) -> tuple[str, int, str] | None:
    """(glyph, brand_rgb, name) for the foreground agent CLI, else None."""
    _cwd, foreground, _last = _active_window_info(tab_id)
    for cmdline in foreground:
        for arg in cmdline:
            name = os.path.basename(arg).lower()
            if name in _AGENT_PROCS:
                rgb = _AGENT_BRANDS.get(name, 0x94e2d5)
                return _AGENT_GLYPHS.get(name, _AGENT_FALLBACK), as_rgb(rgb), name
    return None


_PANES_JSON = (Path(os.environ.get("KITTYMUX_STATE",
               os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
               + "/kittymux")) / f"panes-{os.getpid()}.json")
_PANES_CACHE: dict = {"mtime": 0.0, "data": {}}
_STALE_AFTER = 15.0  # seconds without a title change → probably waiting


def _panes_state() -> dict:
    try:
        mtime = _PANES_JSON.stat().st_mtime
    except OSError:
        return _PANES_CACHE["data"]
    if mtime != _PANES_CACHE["mtime"]:
        try:
            _PANES_CACHE["data"] = json.loads(_PANES_JSON.read_text())
            _PANES_CACHE["mtime"] = mtime
        except Exception:
            pass
    return _PANES_CACHE["data"]


def _agent_waiting(tab_id: int) -> bool:
    """True when the tab's active window title has gone quiet — agent CLIs
    animate their title while working; silence usually means 'waiting'."""
    try:
        window = get_boss().tab_for_id(tab_id).active_window
        st = _panes_state().get(str(window.id)) if window else None
        if not st:
            return False
        ts = float(st.get("ts_title") or 0)
        return bool(ts) and (time.monotonic() - ts) > _STALE_AFTER
    except Exception:
        return False


_USAGE_CACHE = (Path(os.environ["KITTYMUX_STATE"])
    if os.environ.get("KITTYMUX_STATE") else
    Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    / "kittymux") / "agent-usage.json"
_usage_state: list = [0.0, False]  # [checked_at, alert]
_USAGE_SPAWN_AT = 0.0


def _usage_alert() -> bool:
    """True when a cached provider window is >=85%. Spawns a collector at most
    once a minute when the cache is stale; never blocks redraws."""
    global _USAGE_SPAWN_AT
    now = time.time()
    try:
        mtime = _USAGE_CACHE.stat().st_mtime
    except OSError:
        mtime = 0.0
    if now - mtime > 300 and now - _USAGE_SPAWN_AT > 60:
        _USAGE_SPAWN_AT = now
        try:
            subprocess.Popen(
                ["python3", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "bin", "mux-usage.py"), "--collect-only"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
    if now - _usage_state[0] > 15:
        _usage_state[0] = now
        alert = False
        try:
            data = json.loads(_USAGE_CACHE.read_text())
            for p in data.get("providers", []):
                for r in p.get("rows", []):
                    if r.get("pct", 0) >= 85:
                        alert = True
        except (OSError, ValueError):
            pass
        _usage_state[1] = alert
    return _usage_state[1]


def _compact_title(tab: TabBarData, limit: int) -> str:
    raw_title, window_count = _split_window_count(tab.title or "")
    title = _clean_visible_title(raw_title)
    cwd, foreground, last_cmd = _active_window_info(tab.tab_id)
    process_label = _best_process_label(foreground, last_cmd)

    if process_label in _EDITOR_NAMES:
        cwd_name = _basename(cwd.rstrip("/")) if cwd else ""
        title = f"{process_label}:{cwd_name}" if cwd_name else process_label
    elif process_label in {"Claude", "Codex"}:
        if not title or title.lower() in _GENERIC_TITLES:
            cwd_name = _basename(cwd.rstrip("/")) if cwd else ""
            title = f"{process_label}:{cwd_name}" if cwd_name else process_label
        elif not title.lower().startswith(process_label.lower()):
            title = f"{process_label}: {title}"
    elif title:
        # Stale title: names an app that no longer owns the foreground.
        head = re.split(r"[:\s]", title.strip(), maxsplit=1)[0].lower()
        if head in _APP_TITLES and process_label.lower() != head:
            if process_label and process_label not in _GENERIC_TITLES:
                title = process_label
            elif cwd:
                title = _basename(cwd.rstrip("/"))
    if not title or title.lower() in _GENERIC_TITLES:
        title = process_label or (_basename(cwd.rstrip("/")) if cwd else "~")

    if title.lower() in {"zsh", "bash", "fish", "sh"}:
        title = _basename(cwd.rstrip("/")) if cwd else "~"

    if window_count:
        title_limit = max(1, limit - len(window_count) - 1)
        return f"{_truncate(title, title_limit)} {window_count}"

    return _truncate(title, limit)


_GIT_CACHE: dict[str, tuple[float, tuple[str, str]]] = {}
_GIT_TTL = 1.0


def _git_anchor(cwd: str) -> tuple[str, str]:
    """(label, branch) — label is project[:worktree]/inner-path inside a repo,
    else the abbreviated ~ path."""
    now = time.monotonic()
    hit = _GIT_CACHE.get(cwd)
    if hit is not None and now - hit[0] < _GIT_TTL:
        return hit[1]

    label, branch = _short_cwd(cwd, 34), ""
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel",
             "--abbrev-ref", "HEAD", "--git-dir", "--git-common-dir"],
            capture_output=True, text=True, timeout=0.15)
        if out.returncode == 0:
            top, branch, gitdir, common = (out.stdout.splitlines() + [""] * 4)[:4]
            if branch == "HEAD":
                branch = "detached"
            if not os.path.isabs(common):
                common = os.path.normpath(os.path.join(cwd, common))
            project = os.path.basename(os.path.dirname(common)) or os.path.basename(top)
            label = project
            # worktree: gitdir lives under <main>/.git/worktrees/<name>
            if "worktrees" in gitdir.split(os.sep):
                label += ":" + (os.path.basename(top) or "worktree")
            if top and cwd != top:
                rel = os.path.relpath(cwd, top)
                if rel != ".":
                    label += "/" + rel
    except Exception:
        pass
    _GIT_CACHE[cwd] = (now, (label, branch))
    return label, branch


def _os_window_active_cwd(tab_id: int) -> str:
    # cwd of the active window in the OS window that owns this tab bar
    try:
        boss = get_boss()
        tab_obj = boss.tab_for_id(tab_id)
        tm = boss.os_window_map.get(tab_obj.os_window_id) if tab_obj else None
        active = tm.active_tab if tm else None
        window = active.active_window if active else None
        if window is None:
            return ""
        return window.child.current_cwd or window.child.cwd or ""
    except Exception:
        return ""


def _short_cwd(cwd: str, limit: int) -> str:
    home = os.path.expanduser("~")
    if cwd == home:
        path = "~"
    elif cwd.startswith(home + "/"):
        path = "~/" + cwd[len(home) + 1:]
    else:
        path = cwd
    if len(path) <= limit:
        return path
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        prefix = "~/" if path.startswith("~/") else ""
        path = f"{prefix}…/{parts[-2]}/{parts[-1]}"
    return _truncate(path, limit)


def _draw_cwd_anchor(screen: Screen, tab_id: int) -> None:
    cwd = _os_window_active_cwd(tab_id)
    if not cwd:
        return
    path, branch = _git_anchor(cwd)

    path = _truncate(path, 34)
    branch_label = _truncate(branch, 18) if branch else ""
    alert = _usage_alert()
    text_w = len(path) + 2  # leading space + icon + space
    if branch_label:
        text_w += len(branch_label) + 3  # '  ' + icon + ' '
    if alert:
        text_w += 2

    right_x = screen.columns - text_w - 1
    if right_x - screen.cursor.x < 2:
        return
    screen.cursor.x = right_x
    screen.cursor.bold = False
    screen.cursor.bg = _BG

    screen.cursor.fg = _SEP_FG
    screen.draw(" ")
    screen.cursor.fg = _CWD_FG
    screen.draw(" " + path)
    if branch_label:
        screen.cursor.fg = _SEP_FG
        screen.draw("  ")
        screen.cursor.fg = _BRANCH_FG
        screen.draw(" " + branch_label)
    if alert:
        screen.cursor.fg = _ALERT_FG
        screen.cursor.bold = True
        screen.draw(" ⚠")


def _title_limit(max_tab_length: int, index: int, session_name: str, is_active: bool,
                 marks_w: int) -> int:
    chrome = len(f"{index}:") + 1 + 3 + marks_w  # edge+icon column is always 3
    if index == 1:
        chrome += len(session_name) + 3

    budget = max(6, max_tab_length - chrome)
    if max_tab_length >= 42:
        preferred = 34 if is_active else 26
    elif max_tab_length >= 30:
        preferred = 28 if is_active else 22
    elif max_tab_length >= 22:
        preferred = 22 if is_active else 16
    elif max_tab_length >= 16:
        preferred = 16 if is_active else 12
    else:
        preferred = 12 if is_active else 8

    return max(6, min(preferred, budget))


def draw_tab(
    draw_data: DrawData,
    screen: Screen,
    tab: TabBarData,
    before: int,
    max_title_length: int,
    index: int,
    is_last: bool,
    extra_data: ExtraData,
) -> int:
    session_name = _compact_session_name(getattr(tab, "session_name", "") or "")

    # Draw session name prefix before the first tab
    if index == 1:
        screen.cursor.fg = _BRACKET_FG
        screen.cursor.bg = _BG
        screen.draw("[")
        screen.cursor.fg = _SESSION_FG if session_name != "—" else _INACTIVE_FG
        screen.draw(session_name)
        screen.cursor.fg = _BRACKET_FG
        screen.draw("] ")

    # Tab body — cmux/t3code anatomy per row:
    #   line 1: [▌][icon] N:title  + status marks right-aligned (vertical)
    #   line 2: (vertical only) dim subtitle — git branch · pane count
    # All horizontal budgets are clamped to screen.columns (the real bar
    # width): max_title_length can exceed it and would wrap/bleed to the edge.
    is_vert = draw_data.tab_bar_edge in ("left", "right")
    last = extra_data.next_tab is None
    activity = "●" if tab.needs_attention or tab.has_activity_since_last_focus else ""
    info = _agent_info(tab.tab_id)
    waiting = bool(info) and _agent_waiting(tab.tab_id)
    marks_w = (1 if activity else 0) + (2 if waiting else 0)
    title_limit = _title_limit(max_title_length, index, session_name, tab.is_active, marks_w)
    title = _compact_title(tab, title_limit)

    screen.cursor.bg = _BG
    x0 = screen.cursor.x
    screen.cursor.fg = _ACTIVE_FG if tab.is_active else _SEP_FG
    screen.cursor.bold = False
    screen.draw("▌" if tab.is_active else " ")
    if info:
        glyph, brand, _name = info
        screen.cursor.fg = brand if tab.is_active else _dim(brand)
        screen.draw(glyph)
    if screen.cursor.x < x0 + 3:
        screen.cursor.x = x0 + 3

    num = f"{index}:"
    if is_vert:
        # Fit title to the bar width: prefix + num + title + marks + 1 margin.
        limit = screen.columns - 2 - screen.cursor.x - len(num) - marks_w
        if limit >= 4 and limit < len(title):
            title = _truncate(title, limit)
        elif limit < 4:
            title = title[:max(0, limit)]  # degenerate narrow bar
    screen.cursor.fg = _ACTIVE_FG if tab.is_active else _INACTIVE_FG
    screen.cursor.bold = tab.is_active
    screen.draw(num + title)

    def _draw_marks() -> None:
        if activity:
            screen.cursor.fg = _ACTIVITY_FG
            screen.cursor.bold = False
            screen.draw(activity)
        if waiting:
            screen.cursor.fg = _WAITING_FG
            screen.cursor.bold = False
            screen.draw(" !")

    if is_vert:
        # Right-align status marks against the bar's inner edge (last cell
        # stays empty); if the title filled the row, the subtitle still
        # carries the status word so nothing is lost.
        pad = screen.columns - 2 - screen.cursor.x - marks_w
        if marks_w and pad >= 0:
            screen.cursor.x += pad
            _draw_marks()
        # Line 2: dim subtitle under the title (branch · split count · status).
        if draw_data.max_tab_title_lines >= 2 and screen.cursor.y + 1 < screen.lines:
            cwd, _fg, _last_cmd = _active_window_info(tab.tab_id)
            _label, branch = _git_anchor(cwd) if cwd else ("", "")
            sub = ""
            if branch:
                sub = _truncate(branch, 18)
            if tab.num_windows > 1:
                sub += ("  " if sub else "") + f"{tab.num_windows} panes"
            if waiting and not activity:
                sub += ("  " if sub else "") + "waiting"
            elif not waiting and info:
                sub += ("  " if sub else "") + "working"
            if sub:
                sub_x = x0 + 3 + len(num)
                sub_limit = screen.columns - 2 - sub_x
                if sub_limit >= 4:
                    screen.cursor.y += 1  # occupies the tab's 2nd row — kitty
                    # measures vertical height from cursor.y, so leave it here
                    screen.cursor.x = sub_x
                    screen.cursor.fg = _WAITING_FG if waiting else _CWD_FG
                    screen.cursor.bold = False
                    screen.draw(_truncate(sub, sub_limit))
    else:
        _draw_marks()

    # Separators: horizontal bars get ┃ between tabs. On vertical edges kitty
    # passes is_last=True for every row, so use next_tab to find the real end;
    # it also inserts a blank spacing row between tabs on its own.
    if is_vert:
        pass
    elif not last:
        screen.cursor.fg = _SEP_FG
        screen.cursor.bold = False
        screen.cursor.bg = _BG
        screen.draw(" ┃ ")
    else:
        _draw_cwd_anchor(screen, tab.tab_id)

    screen.cursor.bold = False
    return screen.cursor.x
