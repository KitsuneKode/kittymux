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
for _d in (os.environ.get("KITTY_CONFIG_DIRECTORY") or os.path.expanduser("~/.config/kitty"),
           (os.path.dirname(os.path.realpath(_here)) if _here else "")):   # own dir inserted LAST → searched FIRST
    if _d and _d not in sys.path:
        sys.path.insert(0, _d)
import importlib  # noqa: E402
import kittymux_agents  # noqa: E402
import kittymux_barsize  # noqa: E402
import kittymux_git  # noqa: E402
import kittymux_layout  # noqa: E402
import kittymux_scan  # noqa: E402
import kittymux_state  # noqa: E402
import kittymux_theme  # noqa: E402

# kitty re-runs this file on every config reload, but Python keeps imported modules
# for the life of the process — so after an upgrade a running kitty would keep serving
# the OLD helpers to the NEW tab bar (AttributeError on any name added since). Reload
# them every time this file runs.
for _mod in (kittymux_theme, kittymux_agents, kittymux_git, kittymux_layout, kittymux_state, kittymux_scan,
             kittymux_barsize):
    try:
        importlib.reload(_mod)
    except Exception:
        pass
try:
    kittymux_scan.restart()          # the scan timer must run the reloaded code, and never stack
    kittymux_barsize.install()       # drag-to-resize + spacer-aware tab hit test (idempotent; the
except Exception:                    # watcher's on_load only runs once per kitty process)
    pass

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
_COLLAPSE, _EXPAND = "«", "»"   # sidebar collapse / expand button glyphs (kittymux_layout.toggle_collapsed)
COMPACT_MAX_COLS = kittymux_layout.COMPACT_MAX_COLS   # a vertical bar at most this wide draws compact one-line rows
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


def _bar_hot() -> bool:
    """True while the pointer is over the bar's drag handle or dragging it."""
    try:
        import kittymux_barsize
        return kittymux_barsize.is_hot()
    except Exception:
        return False


def _kb_mode() -> str:
    """Name of the active kitty keyboard mode (e.g. 'leader'), or ''."""
    try:
        return get_boss().mappings.current_keyboard_mode_name or ""
    except Exception:
        return ""


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
    return kittymux_agents.strip_title_prefix(title)


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
_AWI_CACHE: dict[int, tuple[float, tuple[str, list[list[str]], str], bool]] = {}
_AWI_TTL = 0.25


def _leader_cmdlines(window) -> list[list[str]] | None:
    """Command line of the pty's foreground process-group leader — two cheap syscalls
    (tcgetpgrp + one /proc read). kitty's own `foreground_processes` also lists every
    member of the group, which walks ALL of /proc (~7 ms each; 88% of our draw time in a
    20-tab profile). The leader is enough: wrappers (`trmw -- claude`, `node …/codex`)
    still carry the agent's name in their arguments."""
    fd = getattr(window.child, "child_fd", None)
    if fd is None:
        return None
    pgrp = os.tcgetpgrp(fd)
    if pgrp <= 0:
        return None
    with open(f"/proc/{pgrp}/cmdline", "rb") as f:
        args = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
    return [args] if args else None


_SLOW_TTL = 3.0        # the /proc-scanning fallback is cached much longer


def _active_window_info(tab_id: int) -> tuple[str, list[list[str]], str]:
    now = time.monotonic()
    hit = _AWI_CACHE.get(tab_id)
    if hit is not None and now - hit[0] < (_SLOW_TTL if hit[2] else _AWI_TTL):
        return hit[1]
    result: tuple[str, list[list[str]], str] = ("", [], "")
    slow = False
    try:
        tab = get_boss().tab_for_id(tab_id)
        window = tab.active_window if tab else None
        if window:
            cwd = window.child.current_cwd or window.child.cwd or ""
            last_cmd = getattr(window, "last_cmd_cmdline", "") or ""
            try:
                foreground = _leader_cmdlines(window)
            except Exception:
                foreground = None
            if foreground is None:                       # unusual pty state: use kitty's scan, rarely
                slow = True
                foreground = []
                for process in window.child.foreground_processes:
                    cmdline = process.get("cmdline") or []
                    if cmdline:
                        foreground.append(list(cmdline))
            result = (cwd, foreground, last_cmd)
    except Exception:
        pass
    if len(_AWI_CACHE) > 64:
        for k in [k for k, v in _AWI_CACHE.items() if now - v[0] > 10.0]:
            del _AWI_CACHE[k]
    _AWI_CACHE[tab_id] = (now, result, slow)
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


def _tool_glyph(foreground: list) -> str:
    """Quiet glyph for a recognised non-agent tool (editor, git, ssh, …), else ''."""
    name = kittymux_agents.tool_in(foreground)
    return kittymux_agents.TOOLS.get(name, "") if name else ""


def _agent_info(tab_id: int) -> tuple[str, int, str] | None:
    return _agent_from_fg(_active_window_info(tab_id)[1])


_PANES_JSON = (Path(os.environ.get("KITTYMUX_STATE",
               os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
               + "/kittymux")) / f"panes-{os.getpid()}.json")
_SCAN_JSON = _PANES_JSON.with_name(f"scan-{os.getpid()}.json")
_PANES_CACHE: dict = {"mtime": (0.0, 0.0), "data": {}}
_STALE_AFTER = 15.0  # legacy arg of resolve_status; the watcher's verdict (kittymux_state) normally decides


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _panes_state() -> dict:
    """Hook status (panes-<pid>.json) merged with the scanner's verdicts (scan-<pid>.json),
    re-read only when either file changed."""
    stamp = (_mtime(_PANES_JSON), _mtime(_SCAN_JSON))
    if stamp != _PANES_CACHE["mtime"]:
        _PANES_CACHE["data"] = kittymux_agents.merge_scan(_read_json(_PANES_JSON), _read_json(_SCAN_JSON))
        _PANES_CACHE["mtime"] = stamp
    return _PANES_CACHE["data"]


def _tab_verdict(tab_id: int) -> tuple[str, dict | None]:
    """(state, entry) for a tab: every pane rolled up (kittymux_agents.tab_verdict), plus the
    entry of the pane that decided it (its message says what the agent wants)."""
    try:
        tab = get_boss().tab_for_id(tab_id)
        window = tab.active_window if tab else None
        if window is None:
            return "", None
        has_agent = _agent_from_fg(_active_window_info(tab_id)[1]) is not None
        panes = _panes_state()
        state, wid = kittymux_agents.tab_verdict(panes, [w.id for w in tab.windows], window.id,
                                                 has_agent, time.monotonic(), _STALE_AFTER)
        return state, panes.get(wid)
    except Exception:
        return "", None


def _pane_chips(tab_id: int, pal, active: bool) -> list[tuple[str, int]]:
    """Runs [(text, rgb)] for a split tab: each agent pane as its logo plus its state mark, e.g.
    `⠋  !` — so a question in a split you are not in is visible. [] when it has no agent panes."""
    try:
        tab = get_boss().tab_for_id(tab_id)
        chips = kittymux_agents.pane_chips(_panes_state(), [w.id for w in tab.windows], time.monotonic())
    except Exception:
        return []
    runs: list[tuple[str, int]] = []
    for name, state in chips:
        agent = kittymux_agents.AGENTS.get(name, _AGENT_FALLBACK)
        if runs:
            runs.append((" ", pal.faint))
        runs.append((agent.glyph, agent.brand if active else _mute(agent.brand, pal)))
        mark = "" if state == "idle" else kittymux_agents.state_glyph(state)
        if mark:
            runs.append((mark, _state_color(state, pal)))
    return runs


def _agent_status(tab_id: int) -> str:
    """working | waiting | limited | done | idle | "" for the tab (all its panes). A scanner
    verdict (screen + hooks) wins; see kittymux_agents.resolve_status for the fallbacks."""
    return _tab_verdict(tab_id)[0]


def _agent_waiting(tab_id: int) -> bool:
    return _agent_status(tab_id) in kittymux_agents.NEEDS_YOU


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


def _git_anchor(cwd: str) -> tuple[str, str]:
    """(label, branch): project[:worktree]/inner-path inside a repo, else the ~ path.
    Reads .git/HEAD directly (kittymux_git) — no subprocess on the draw path."""
    return kittymux_git.label(cwd)


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
    return kittymux_git.short_path(cwd, None, limit)


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
    mode = _kb_mode() if index == 1 else ""
    if index == 1 and mode:
        screen.cursor.bg = _rgb(pal.accent)
        screen.cursor.fg = _rgb(pal.bg)
        screen.cursor.bold = True
        screen.draw(f" {mode.upper()} ")
        screen.cursor.bold = False
        screen.cursor.bg = 0
        screen.draw(" ")
    elif index == 1:
        screen.cursor.bg = 0
        screen.cursor.fg = _rgb(pal.faint)
        screen.draw("[")
        screen.cursor.fg = _rgb(pal.info) if session_name != "—" else _rgb(pal.muted)
        screen.draw(session_name)
        screen.cursor.fg = _rgb(pal.faint)
        screen.draw("] ")
        _total, counts = _session_stats(tab)
        for text, color, bold in _attention_parts(counts, pal):
            screen.cursor.fg = _rgb(color)
            screen.cursor.bold = bold
            screen.draw(text)
        screen.cursor.bold = False

    last = extra_data.next_tab is None
    cwd, foreground, _last_cmd = _active_window_info(tab.tab_id)
    info = _agent_from_fg(foreground)
    state = _tab_state(tab)
    marks_w = 2 if state else 0
    title_limit = _title_limit(max_title_length, index, session_name, tab.is_active, marks_w)
    title = kittymux_agents.strip_agent_prefix(_compact_title(tab, title_limit), info[2] if info else None)

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
    else:
        tool = _tool_glyph(foreground)
        if tool:
            screen.cursor.fg = _rgb(pal.muted if tab.is_active else pal.faint)
            screen.draw(tool)
    if screen.cursor.x < x0 + 3:
        screen.cursor.x = x0 + 3

    screen.cursor.fg = _rgb(pal.text) if tab.is_active else _rgb(pal.muted)
    screen.cursor.bold = tab.is_active
    screen.draw(f"{index}:{title}")
    screen.cursor.bold = False
    if state:
        screen.cursor.fg = _rgb(_state_color(state, pal))
        screen.cursor.bold = state in kittymux_agents.NEEDS_YOU
        screen.draw(" " + kittymux_agents.state_glyph(state))
        screen.cursor.bold = False
    screen.draw(" " if tab.is_active else "")

    if not last:
        screen.cursor.fg = _rgb(pal.line)
        screen.cursor.bg = 0
        screen.draw(" │ ")
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


def _tab_state(tab: TabBarData) -> str:
    """working | waiting | limited | done (any pane runs an agent) · unread (any other tab with fresh output) · ''."""
    st = _agent_status(tab.tab_id)
    if st:
        return "" if st == "idle" else st
    if tab.needs_attention or tab.has_activity_since_last_focus:
        return "unread"
    return ""


def _state_color(state: str, pal) -> int | None:
    """Calm palette: only `waiting` shouts; done recedes; unread is barely there."""
    return {
        "working": pal.working,
        "waiting": pal.waiting,
        "limited": pal.alert,
        "done": kittymux_theme.blend(pal.done, pal.bg, 0.65),
        "unread": pal.faint,
    }.get(state)


def _session_stats(tab: TabBarData) -> tuple[int, dict[str, int]]:
    """(tabs in the active session, {state: agent tabs in it}). The counts cover EVERY tab of the
    window — an agent in another session still asks for you."""
    try:
        boss = get_boss()
        tab_obj = boss.tab_for_id(tab.tab_id)
        tm = boss.os_window_map.get(tab_obj.os_window_id) if tab_obj else None
        if tm is None:
            return 0, {}
        active = tab.active_session_name
        total = sum(1 for t in tm.tabs if t.created_in_session_name == active)
        counts: dict[str, int] = {}
        for t in tm.tabs:
            st = _agent_status(t.id)
            if st in ("waiting", "limited", "done"):
                counts[st] = counts.get(st, 0) + 1
        return total, counts
    except Exception:
        return 0, {}


def _attention_parts(counts: dict[str, int], pal) -> list[tuple[str, int, bool]]:
    """Right-aligned header badges, each with the SAME glyph and colour its tabs carry:
    `! 2` waiting, `⊘ 1` limited, `✓ 3` finished unseen — (text, rgb, bold)."""
    parts = []
    for state in ("waiting", "limited", "done"):
        if counts.get(state):
            parts.append((f"{kittymux_agents.state_glyph(state)} {counts[state]}  ", _state_color(state, pal),
                          state in kittymux_agents.NEEDS_YOU))
    return parts


def _draw_vertical(draw_data, screen, tab, index, extra_data, pal) -> int:
    cols = screen.columns
    y0 = screen.cursor.y
    # A slim rail (kittymux_layout "compact", ≤ 12 columns): one line per tab — logo,
    # a few title characters, status — no session header, no subtitle.
    compact = cols <= COMPACT_MAX_COLS
    # (the rail still gets a header row for the first tab: it carries the expand button)
    lines_avail = (2 if index == 1 else 1) if compact else min(max(1, draw_data.max_tab_title_lines), screen.lines - y0)
    active = tab.is_active

    cwd, foreground, _last_cmd = _active_window_info(tab.tab_id)
    info = _agent_from_fg(foreground)
    state = _tab_state(tab)
    state_fg = _state_color(state, pal)

    branch = _git_anchor(cwd)[1] if cwd else ""
    subtitle: list[tuple[str, int]] = []
    if branch:
        subtitle.append((f"{_ICON_BRANCH} {branch}", pal.muted if active else pal.faint))
    elif cwd:
        subtitle.append((f"{_ICON_FOLDER} {_short_cwd(cwd, 24)}", pal.muted if active else pal.faint))
    if tab.num_windows > 1:
        chips = _pane_chips(tab.tab_id, pal, active)
        subtitle.append((chips, pal.faint) if chips else (f"{tab.num_windows} panes", pal.faint))
    msg = kittymux_agents.resolve_msg(_tab_verdict(tab.tab_id)[1], state)
    if msg:
        subtitle = [(msg, state_fg)]          # what it is waiting for beats the branch
    elif state in kittymux_agents.NEEDS_YOU:
        subtitle.append((state, state_fg))    # working needs no word — the spinner says it

    header = index == 1 and (lines_avail >= 3 or compact)
    want_sub = lines_avail >= (3 if header else 2) and bool(subtitle)
    n_rows = (1 if header else 0) + 1 + (1 if want_sub else 0)
    n_rows = min(n_rows, lines_avail)

    bar = _rgb(pal.bar)
    row_bg = _rgb(pal.surface_hi) if active else bar
    mode = _kb_mode() if header else ""
    if header:
        # the session header never takes the tab's fill; an armed keyboard mode
        # (leader) turns it into an accent badge so you always know you're in it
        _paint_rows(screen, y0, 1, _rgb(pal.accent) if mode else bar)
        _paint_rows(screen, y0 + 1, n_rows - 1, row_bg)
    else:
        _paint_rows(screen, y0, n_rows, row_bg)
    if index == 1 and not extra_data.for_layout:
        # one full-height separator line, drawn once; each tab re-asserts its rows
        _sep_column(screen, 0, screen.lines, bar, _rgb(pal.accent if _bar_hot() else pal.line))

    y = y0
    if header and mode:
        screen.cursor.y = y
        screen.cursor.bg = _rgb(pal.accent)
        badge = f" {mode.upper()} "
        x = _put(screen, 0, badge, _rgb(pal.bg), True)
        _put(screen, x + 1, _fit("hjkl cnp saw g ?", max(0, cols - x - 2)), _rgb(pal.bg))
        y += 1
    elif header and compact:
        screen.cursor.bg = bar
        screen.cursor.y = y
        x = _put(screen, 1, _EXPAND, _rgb(pal.muted), True)               # the expand button
        counts = _session_stats(tab)[1]
        badge = " ".join(f"{kittymux_agents.state_glyph(st)}{counts[st]}" for st in ("waiting", "limited", "done") if counts.get(st))
        if badge and cols - x - 2 >= 3:
            _put(screen, x + 1, _fit(badge, cols - x - 2), _rgb(pal.waiting), True)
        y += 1
    elif header:
        name = _compact_session_name(getattr(tab, "session_name", "") or "")
        name = "TABS" if name == "—" else name.upper()
        total, counts = _session_stats(tab)
        right = f"{total} tabs" if total else ""
        badges = _attention_parts(counts, pal)
        w_right = "".join(text for text, _c, _b in badges)
        end = cols - kittymux_layout.TOGGLE_CELLS - 1          # the collapse button owns the cells after this
        room = end - 1 - _cells(right) - _cells(w_right) - 2
        screen.cursor.bg = bar
        screen.cursor.y = y
        _put(screen, 1, _fit(name, max(4, room)), _rgb(pal.faint), True)
        rx = end - _cells(right)
        if right and rx > 1 + _cells(name) + 1:
            xr = rx - _cells(w_right)
            for text, color, bold in badges:
                _put(screen, xr, text, _rgb(color), bold)
                xr += _cells(text)
            _put(screen, rx, right, _rgb(pal.faint))
        _put(screen, cols - kittymux_layout.TOGGLE_CELLS, _COLLAPSE, _rgb(pal.muted), True)   # the collapse button
        y += 1

    # Title row: [rail][glyph][space] title ............ dot
    screen.cursor.bg = row_bg
    screen.cursor.y = y
    # rail: accent on the active tab; a waiting tab keeps a stripe in the waiting colour
    stripe = state in kittymux_agents.NEEDS_YOU and not active
    _put(screen, 0, _RAIL if (active or stripe) else " ",
             _rgb((pal.alert if state == "limited" else pal.waiting) if stripe else pal.accent))
    if info:
        glyph, brand, _n = info
        _put(screen, 1, glyph, _rgb(brand if active else _mute(brand, pal)))
    elif _tool_glyph(foreground):
        _put(screen, 1, _tool_glyph(foreground), _rgb(pal.muted if active else pal.faint))
    title_room = cols - 3 - 2
    if compact:
        # the slim rail is icons only: the logo (or tool glyph), the tab number, the state mark — no title
        if not info and not _tool_glyph(foreground):
            _put(screen, 1, "›", _rgb(pal.faint))
        _put(screen, 3, str(index), _rgb(pal.muted if active else pal.faint))
    elif title_room >= 3:
        title = _fit(kittymux_agents.strip_agent_prefix(_compact_title(tab, max(4, title_room)), info[2] if info else None),
                     title_room)
        _put(screen, 3, title,
             _rgb(pal.text) if active else _rgb(pal.muted), bold=active)
    if state_fg is not None and cols >= 6:
        _put(screen, cols - 2, kittymux_agents.state_glyph(state), _rgb(state_fg), bold=state == "waiting")
    title_y = y

    if want_sub and n_rows > (2 if header else 1):
        y += 1
        screen.cursor.bg = row_bg
        screen.cursor.y = y
        if active or stripe:
            _put(screen, 0, _RAIL, _rgb(pal.waiting if stripe else pal.accent))
        idx = str(index)
        _put(screen, cols - 1 - len(idx), idx, _rgb(pal.faint))
        room = cols - 3 - 1 - len(idx) - 1
        # The state word (waiting/working) outranks the branch/path: reserve
        # its room first and give the rest to the leading pieces.
        tail = [p for p in subtitle if isinstance(p[0], str) and p[0] in ("working", "waiting")]
        lead = [p for p in subtitle if p not in tail]
        reserve = sum(_cells(t) + 2 for t, _c in tail)
        x = 3
        for i, (text, color) in enumerate(lead):
            sep = "  " if i else ""
            avail = room - (x - 3) - reserve - _cells(sep)
            if avail <= 1:
                break
            if isinstance(text, list):                       # pane chips: coloured runs, drawn whole or not at all
                if sum(_cells(t) for t, _c in text) <= avail:
                    x = _put(screen, x, sep, _rgb(color))
                    for run, run_color in text:
                        x = _put(screen, x, run, _rgb(run_color))
                continue
            x = _put(screen, x, sep + _fit(text, avail), _rgb(color))
        for text, color in tail:
            sep = "  " if x > 3 else ""
            avail = room - (x - 3) - _cells(sep)
            if avail >= _cells(text):
                x = _put(screen, x, sep + text, _rgb(color))

    _sep_column(screen, y0, n_rows, row_bg, _rgb(pal.accent if _bar_hot() else pal.line))

    # Leave the cursor on the last used row (kitty measures height from it),
    # and never leak our colours into kitty's later erase/draw calls.
    screen.cursor.y = y if want_sub else title_y
    screen.cursor.bg = bar
    screen.cursor.fg = 0
    screen.cursor.bold = False
    return screen.cursor.x


# ── entry point ──────────────────────────────────────────────────────────────
_PROFILE = os.environ.get("KITTYMUX_PROFILE") == "1"     # opt-in: per-draw timing → tab_bar-profile.log
_prof = {"n": 0, "total": 0.0, "max": 0.0, "since": 0.0}


def _profile_record(elapsed: float) -> None:
    try:
        p = _prof
        p["n"] += 1
        p["total"] += elapsed
        p["max"] = max(p["max"], elapsed)
        now = time.monotonic()
        if p["since"] == 0.0:
            p["since"] = now
        if p["n"] >= 200:
            _ERR_LOG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            plog = _ERR_LOG.parent / "tab_bar-profile.log"
            if plog.exists() and plog.stat().st_size > 64 * 1024:
                plog.write_text("")
            with open(plog, "a", encoding="utf-8") as f:
                f.write(f"draw_tab calls={p['n']} avg_ms={p['total'] / p['n'] * 1000:.3f} "
                        f"max_ms={p['max'] * 1000:.3f} calls_per_sec={p['n'] / max(now - p['since'], 1e-6):.1f}\n")
            p.update(n=0, total=0.0, max=0.0, since=0.0)
    except Exception:
        pass


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
    if not _PROFILE:
        return _draw_tab(draw_data, screen, tab, before, max_title_length, index, is_last, extra_data)
    t0 = time.perf_counter()
    try:
        return _draw_tab(draw_data, screen, tab, before, max_title_length, index, is_last, extra_data)
    finally:
        _profile_record(time.perf_counter() - t0)


def _draw_tab(
    draw_data: DrawData,
    screen: Screen,
    tab: TabBarData,
    before: int,
    max_title_length: int,
    index: int,
    is_last: bool,
    extra_data: ExtraData,
) -> int:
    x0, y0 = screen.cursor.x, screen.cursor.y
    try:
        kittymux_scan.ensure_started()          # idempotent: a no-op once the timer runs
        pal = _palette(draw_data)
        if draw_data.tab_bar_edge in ("left", "right"):
            end = _draw_vertical(draw_data, screen, tab, index, extra_data, pal)
        else:
            end = _draw_horizontal(max_title_length, screen, tab, index, extra_data, pal)
        screen.cursor.bold = False
        return end
    except Exception:
        # Never let a bug turn the whole bar into kitty's anonymous fallback. Record
        # the traceback (kitty's own stderr is usually /dev/null) and draw a plain but
        # still readable tab so the bar degrades gracefully.
        _log_exception(tab, index)
        screen.cursor.x, screen.cursor.y = x0, y0
        return _draw_safe(draw_data, screen, tab, index, max_title_length)


_ERR_LOG = Path(os.environ.get("KITTYMUX_STATE") or (
    os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")) + "/kittymux") / "tab_bar-error.log"
_ERR_SEEN: dict = {}


_ERR_DEDUPE = float(os.environ.get("KITTYMUX_ERR_DEDUPE", "60"))     # seconds; tests set 0 to see every repeat


def _log_exception(tab, index: int) -> None:
    """Append the current traceback to tab_bar-error.log (deduplicated, bounded)."""
    try:
        import traceback
        text = traceback.format_exc()
        key = text.strip().splitlines()[-1] if text.strip() else ""
        now = time.monotonic()
        if now - _ERR_SEEN.get(key, -1e9) < _ERR_DEDUPE:
            return
        _ERR_SEEN[key] = now
        _ERR_LOG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if _ERR_LOG.exists() and _ERR_LOG.stat().st_size > 64 * 1024:
            _ERR_LOG.write_text("")
        fd = os.open(_ERR_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%F %T')} pid={os.getpid()} tab={index} "
                    f"active={getattr(tab, 'is_active', '?')}\n{text}\n")
    except Exception:
        pass


def _draw_safe(draw_data, screen, tab, index: int, max_title_length: int) -> int:
    """Last-resort renderer: numbered title in the tab's own kitty colours. Cannot
    depend on anything the main renderer uses."""
    try:
        screen.cursor.bg = as_rgb(int(draw_data.tab_bg(tab)))
        screen.cursor.fg = as_rgb(int(draw_data.tab_fg(tab)))
        screen.cursor.bold = bool(tab.is_active)
        room = max(4, min(max_title_length, screen.columns - 2))
        text = f" {index}:{' '.join((tab.title or '').split())}"
        screen.draw(text[:room] + ("…" if len(text) > room else "") + " ")
        screen.cursor.bold = False
        return screen.cursor.x
    except Exception:
        return screen.cursor.x
