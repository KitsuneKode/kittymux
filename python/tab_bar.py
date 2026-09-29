# Custom kitty tab bar.
#
# Horizontal (bottom/top):  [session] ▌1:title ┃ 2:title ┃ 3:title●      cwd  branch
# Vertical   (left/right):  shadcn/cmux-style rows —
#
#     SESSION                     <- header row (tab 1 only; needs tab_title_max_lines 3)
#   ▌ ◉ active title          ●   <- accent rail + filled row, agent glyph, status dot
#   ▌   ⎇ main · 2 panes  1
#     ◉ other title
#       ⎇ feat/x · waiting    2
#
# Every colour is derived from the live kitty theme (kittymux_theme), so the
# bar follows theme switches. Status dot: working / waiting (needs you) / done.

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from kitty.fast_data_types import Screen, get_boss, get_options, wcswidth
from kitty.tab_bar import DrawData, ExtraData, TabBarData, as_rgb
from kitty.utils import color_as_int

# The token/agent modules live next to this file (repo checkout) or, when the
# installer copied/symlinked them, in the kitty config dir.
_here = globals().get("__file__")
for _d in ((os.path.dirname(os.path.realpath(_here)) if _here else ""),
           os.environ.get("KITTY_CONFIG_DIRECTORY") or os.path.expanduser("~/.config/kitty")):
    if _d and _d not in sys.path:
        sys.path.insert(0, _d)
import kittymux_agents  # noqa: E402
import kittymux_theme  # noqa: E402

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

_ICON_BRANCH = ""   # nerd-font git-branch
_ICON_FOLDER = ""   # nerd-font folder
_RAIL = "▌"
_DOT = "●"


# ── palette (derived from the live kitty theme) ──────────────────────────────
_PAL_CACHE: dict = {"key": None, "pal": None}


def _palette(draw_data: DrawData) -> "kittymux_theme.Palette":
    try:
        o = get_options()
        colors = {
            "background": color_as_int(draw_data.default_bg),
            "foreground": color_as_int(o.foreground),
        }
        abc = o.active_border_color
        if abc is not None:
            colors["active_border_color"] = color_as_int(abc)
        for n in range(1, 16):
            colors[f"color{n}"] = int(o.color_table[n]) & 0xFFFFFF
    except Exception:
        colors = {}
    key = (tuple(sorted(colors.items())), os.environ.get("KITTYMUX_ACCENT", ""))
    if _PAL_CACHE["key"] != key:
        _PAL_CACHE["key"] = key
        _PAL_CACHE["pal"] = kittymux_theme.from_colors(colors)
    return _PAL_CACHE["pal"]


def _rgb(value: int) -> int:
    return as_rgb(value)


def _mute(brand: int, pal) -> int:
    """Inactive brand mark: the brand colour receded toward the bar background
    (stays legible on any theme, unlike scaling channels toward black)."""
    return kittymux_theme.blend(brand, pal.bg, 0.6)


# ── text helpers ─────────────────────────────────────────────────────────────
def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "…"


def _cells(text: str) -> int:
    return max(0, wcswidth(text))


def _fit(text: str, width: int) -> str:
    """Truncate to `width` terminal cells, marking the cut with …"""
    if width <= 0:
        return ""
    if _cells(text) <= width:
        return text
    out, used = "", 0
    for ch in text:
        w = _cells(ch)
        if used + w > width - 1:
            break
        out += ch
        used += w
    return out + "…"


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


# draw_tab runs twice per tab per redraw (kitty measures, then draws) and the
# foreground-process read is not free — cache it briefly.
_AWI_CACHE: dict[int, tuple[float, tuple[str, list[list[str]], str]]] = {}
_AWI_TTL = 0.25


def _active_window_info(tab_id: int) -> tuple[str, list[list[str]], str]:
    now = time.monotonic()
    hit = _AWI_CACHE.get(tab_id)
    if hit is not None and now - hit[0] < _AWI_TTL:
        return hit[1]
    result: tuple[str, list[list[str]], str] = ("", [], "")
    try:
        tab = get_boss().tab_for_id(tab_id)
        window = tab.active_window if tab else None
        if window:
            cwd = window.child.current_cwd or window.child.cwd or ""
            last_cmd = getattr(window, "last_cmd_cmdline", "") or ""
            foreground = []
            for process in window.child.foreground_processes:
                cmdline = process.get("cmdline") or []
                if cmdline:
                    foreground.append(list(cmdline))
            result = (cwd, foreground, last_cmd)
    except Exception:
        pass
    if len(_AWI_CACHE) > 64:
        for k in [k for k, v in _AWI_CACHE.items() if now - v[0] > 5.0]:
            del _AWI_CACHE[k]
    _AWI_CACHE[tab_id] = (now, result)
    return result


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
_AGENT_FALLBACK = kittymux_agents.FALLBACK


def _agent_from_fg(foreground: list[list[str]]) -> tuple[str, int, str] | None:
    """(glyph, brand_rgb, name) for the foreground agent CLI, else None.
    brand_rgb is a plain 0xRRGGBB int — tag it with as_rgb() only at draw time."""
    for cmdline in foreground:
        name = kittymux_agents.agent_in(cmdline)
        if name:
            agent = kittymux_agents.AGENTS.get(name, _AGENT_FALLBACK)
            return agent.glyph, agent.brand, name
    return None


def _agent_info(tab_id: int) -> tuple[str, int, str] | None:
    return _agent_from_fg(_active_window_info(tab_id)[1])


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
_usage_state: list = [0.0, None]  # [checked_at, (provider, pct) | None]
_USAGE_SPAWN_AT = 0.0


def _usage_alert() -> tuple[str, int] | None:
    """(provider, pct) of the worst cached quota window >= 85%, else None.
    Spawns a collector at most once a minute when the cache is stale; never
    blocks redraws."""
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
        worst = None
        try:
            data = json.loads(_USAGE_CACHE.read_text())
            for p in data.get("providers", []):
                for r in p.get("rows", []):
                    pct = int(r.get("pct", 0) or 0)
                    if pct >= 85 and (worst is None or pct > worst[1]):
                        worst = (str(p.get("name", "")), pct)
        except (OSError, ValueError):
            pass
        _usage_state[1] = worst
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


# ── horizontal bar ───────────────────────────────────────────────────────────
def _draw_cwd_anchor(screen: Screen, tab_id: int, pal) -> None:
    cwd = _os_window_active_cwd(tab_id)
    if not cwd:
        return
    path, branch = _git_anchor(cwd)

    path = _truncate(path, 34)
    branch_label = _truncate(branch, 18) if branch else ""
    alert = _usage_alert()
    alert_text = f" ⚠ {alert[0]} {alert[1]}%" if alert else ""
    text_w = len(path) + 2  # leading space + icon + space
    if branch_label:
        text_w += len(branch_label) + 3  # '  ' + icon + ' '
    text_w += _cells(alert_text)

    right_x = screen.columns - text_w - 1
    if right_x - screen.cursor.x < 2:
        return
    screen.cursor.x = right_x
    screen.cursor.bold = False
    screen.cursor.bg = 0

    screen.cursor.fg = _rgb(pal.faint)
    screen.draw(" ")
    screen.cursor.fg = _rgb(pal.muted)
    screen.draw(" " + path)
    if branch_label:
        screen.cursor.fg = _rgb(pal.faint)
        screen.draw("  ")
        screen.cursor.fg = _rgb(pal.done)
        screen.draw(" " + branch_label)
    if alert:
        screen.cursor.fg = _rgb(pal.alert)
        screen.cursor.bold = True
        screen.draw(alert_text)


def _draw_horizontal(max_title_length, screen, tab, index, extra_data, pal) -> int:
    session_name = _compact_session_name(getattr(tab, "session_name", "") or "")

    # Session name prefix before the first tab
    if index == 1:
        screen.cursor.bg = 0
        screen.cursor.fg = _rgb(pal.faint)
        screen.draw("[")
        screen.cursor.fg = _rgb(pal.info) if session_name != "—" else _rgb(pal.muted)
        screen.draw(session_name)
        screen.cursor.fg = _rgb(pal.faint)
        screen.draw("] ")

    last = extra_data.next_tab is None
    activity = _DOT if tab.needs_attention or tab.has_activity_since_last_focus else ""
    cwd, foreground, _last_cmd = _active_window_info(tab.tab_id)
    info = _agent_from_fg(foreground)
    waiting = bool(info) and _agent_waiting(tab.tab_id)
    marks_w = (1 if activity else 0) + (2 if waiting else 0)
    title_limit = _title_limit(max_title_length, index, session_name, tab.is_active, marks_w)
    title = _compact_title(tab, title_limit)

    chip = _rgb(pal.surface_hi) if tab.is_active else 0
    screen.cursor.bg = chip
    x0 = screen.cursor.x
    screen.cursor.fg = _rgb(pal.accent) if tab.is_active else _rgb(pal.faint)
    screen.cursor.bold = False
    screen.draw(_RAIL if tab.is_active else " ")
    if info:
        glyph, brand, _name = info
        screen.cursor.fg = _rgb(brand if tab.is_active else _mute(brand, pal))
        screen.draw(glyph)
    if screen.cursor.x < x0 + 3:
        screen.cursor.x = x0 + 3

    screen.cursor.fg = _rgb(pal.text) if tab.is_active else _rgb(pal.muted)
    screen.cursor.bold = tab.is_active
    screen.draw(f"{index}:{title}")
    screen.cursor.bold = False
    if activity:
        screen.cursor.fg = _rgb(pal.done)
        screen.draw(activity)
    if waiting:
        screen.cursor.fg = _rgb(pal.waiting)
        screen.draw(" !")
    screen.draw(" " if tab.is_active else "")

    if not last:
        screen.cursor.fg = _rgb(pal.faint)
        screen.cursor.bg = 0
        screen.draw(" ┃ ")
    else:
        screen.cursor.bg = 0
        _draw_cwd_anchor(screen, tab.tab_id, pal)

    screen.cursor.bold = False
    return screen.cursor.x


# ── vertical bar ─────────────────────────────────────────────────────────────
def _paint_rows(screen: Screen, y0: int, n: int, bg: int) -> None:
    """Repaint n rows from y0 with `bg` (0 = the bar's default background).
    Kitty pre-fills a vertical tab's rows with kitty's own tab colours; we
    replace that so the palette is ours end to end."""
    screen.cursor.bg = bg
    for r in range(n):
        y = y0 + r
        if y >= screen.lines:
            break
        screen.cursor.x = 0
        screen.cursor.y = y
        screen.draw(" " * screen.columns)
    screen.cursor.x = 0
    screen.cursor.y = y0


def _sep_column(screen: Screen, y0: int, n: int, bg: int, fg: int) -> None:
    """Right-edge separator line between the bar and the panes."""
    screen.cursor.bg = bg
    screen.cursor.fg = fg
    for r in range(n):
        y = y0 + r
        if y >= screen.lines:
            break
        screen.cursor.y = y
        screen.cursor.x = screen.columns - 1
        screen.draw("▕")


def _put(screen: Screen, x: int, text: str, fg: int, bold: bool = False) -> int:
    screen.cursor.x = x
    screen.cursor.fg = fg
    screen.cursor.bold = bold
    screen.draw(text)
    return screen.cursor.x


def _tab_state(tab: TabBarData, info) -> str:
    if info:
        return "waiting" if _agent_waiting(tab.tab_id) else "working"
    if tab.needs_attention or tab.has_activity_since_last_focus:
        return "done"
    return ""


def _session_stats(tab: TabBarData) -> tuple[int, int]:
    """(tabs in the active session, agent tabs waiting on the user)."""
    try:
        boss = get_boss()
        tab_obj = boss.tab_for_id(tab.tab_id)
        tm = boss.os_window_map.get(tab_obj.os_window_id) if tab_obj else None
        if tm is None:
            return 0, 0
        active = tab.active_session_name
        visible = [t for t in tm.tabs if t.created_in_session_name == active]
        waiting = 0
        for t in visible:
            if _agent_from_fg(_active_window_info(t.id)[1]) and _agent_waiting(t.id):
                waiting += 1
        return len(visible), waiting
    except Exception:
        return 0, 0


def _draw_vertical(draw_data, screen, tab, index, extra_data, pal) -> int:
    cols = screen.columns
    y0 = screen.cursor.y
    lines_avail = min(max(1, draw_data.max_tab_title_lines), screen.lines - y0)
    active = tab.is_active

    cwd, foreground, _last_cmd = _active_window_info(tab.tab_id)
    info = _agent_from_fg(foreground)
    state = _tab_state(tab, info)
    state_fg = {"waiting": pal.waiting, "working": pal.working, "done": pal.done}.get(state)

    branch = _git_anchor(cwd)[1] if cwd else ""
    subtitle: list[tuple[str, int]] = []
    if branch:
        subtitle.append((f"{_ICON_BRANCH} {branch}", pal.muted if active else pal.faint))
    elif cwd:
        subtitle.append((f"{_ICON_FOLDER} {_short_cwd(cwd, 24)}", pal.muted if active else pal.faint))
    if tab.num_windows > 1:
        subtitle.append((f"{tab.num_windows} panes", pal.faint))
    if state in ("waiting", "working"):
        subtitle.append((state, state_fg))

    header = index == 1 and lines_avail >= 3
    want_sub = lines_avail >= (3 if header else 2) and bool(subtitle)
    n_rows = (1 if header else 0) + 1 + (1 if want_sub else 0)
    n_rows = min(n_rows, lines_avail)

    bar = _rgb(pal.bar)
    row_bg = _rgb(pal.surface_hi) if active else bar
    if header:
        _paint_rows(screen, y0, 1, bar)  # the session header never takes the tab's fill
        _paint_rows(screen, y0 + 1, n_rows - 1, row_bg)
    else:
        _paint_rows(screen, y0, n_rows, row_bg)
    if index == 1 and not extra_data.for_layout:
        # one full-height separator line, drawn once; each tab re-asserts its rows
        _sep_column(screen, 0, screen.lines, bar, _rgb(pal.line))

    y = y0
    if header:
        name = _compact_session_name(getattr(tab, "session_name", "") or "")
        name = "TABS" if name == "—" else name.upper()
        total, waiting_n = _session_stats(tab)
        right = f"{total} tabs" if total else ""
        w_right = f"! {waiting_n}  " if waiting_n else ""
        room = cols - 2 - _cells(right) - _cells(w_right) - 2
        screen.cursor.bg = bar
        screen.cursor.y = y
        _put(screen, 1, _fit(name, max(4, room)), _rgb(pal.faint), True)
        rx = cols - 1 - _cells(right)
        if right and rx > 1 + _cells(name) + 1:
            xr = rx - _cells(w_right)
            if w_right:
                _put(screen, xr, w_right, _rgb(pal.waiting), True)
            _put(screen, rx, right, _rgb(pal.faint))
        y += 1

    # Title row: [rail][glyph][space] title ............ dot
    screen.cursor.bg = row_bg
    screen.cursor.y = y
    _put(screen, 0, _RAIL if active else " ", _rgb(pal.accent))
    if info:
        glyph, brand, _n = info
        _put(screen, 1, glyph, _rgb(brand if active else _mute(brand, pal)))
    title_room = cols - 3 - 2
    if title_room >= 3:
        title = _fit(_compact_title(tab, max(4, title_room)), title_room)
        _put(screen, 3, title,
             _rgb(pal.text) if active else _rgb(pal.muted), bold=active)
    if state_fg is not None and cols >= 6:
        _put(screen, cols - 2, _DOT, _rgb(state_fg))
    title_y = y

    if want_sub and n_rows > (2 if header else 1):
        y += 1
        screen.cursor.bg = row_bg
        screen.cursor.y = y
        if active:
            _put(screen, 0, _RAIL, _rgb(pal.accent))
        idx = str(index)
        _put(screen, cols - 1 - len(idx), idx, _rgb(pal.faint))
        room = cols - 3 - 1 - len(idx) - 1
        # The state word (waiting/working) outranks the branch/path: reserve
        # its room first and give the rest to the leading pieces.
        tail = [p for p in subtitle if p[0] in ("working", "waiting")]
        lead = [p for p in subtitle if p not in tail]
        reserve = sum(_cells(t) + 2 for t, _c in tail)
        x = 3
        for i, (text, color) in enumerate(lead):
            sep = "  " if i else ""
            avail = room - (x - 3) - reserve - _cells(sep)
            if avail <= 1:
                break
            x = _put(screen, x, sep + _fit(text, avail), _rgb(color))
        for text, color in tail:
            sep = "  " if x > 3 else ""
            avail = room - (x - 3) - _cells(sep)
            if avail >= _cells(text):
                x = _put(screen, x, sep + text, _rgb(color))

    _sep_column(screen, y0, n_rows, row_bg, _rgb(pal.line))

    # Leave the cursor on the last used row (kitty measures height from it),
    # and never leak our colours into kitty's later erase/draw calls.
    screen.cursor.y = y if want_sub else title_y
    screen.cursor.bg = bar
    screen.cursor.fg = 0
    screen.cursor.bold = False
    return screen.cursor.x


# ── entry point ──────────────────────────────────────────────────────────────
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
    pal = _palette(draw_data)
    if draw_data.tab_bar_edge in ("left", "right"):
        end = _draw_vertical(draw_data, screen, tab, index, extra_data, pal)
    else:
        end = _draw_horizontal(max_title_length, screen, tab, index, extra_data, pal)
    screen.cursor.bold = False
    return end
