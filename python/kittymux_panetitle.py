# kittymux pane titles — the header row in kitty's per-pane title bars (ctrl+alt+shift+c shows them).
#
# kitty draws a one-row title bar above each pane when `window_title_bar_min_windows` says so; its text is `window_title_template`, and `{custom}` in
# that template is what `draw_window_title(data)` of the config dir's `window_title_bar.py` returns. kitty loads that file ONCE per process, so it is a
# trampoline into `draw` here — this module is reloaded by tab_bar.py on every config load, like the other helpers.
#
# Each bar reads like the deck pane header: brand glyph, bold program or agent name, faint folder, then the state mark and OSC 9;4 percent on the right.
# Colours come from the title bar's REAL foreground/background and the same state colours as the tab bar.
#
# `render`, `derive_colours`, and helpers are pure; `draw` imports kitty lazily and never raises: "" makes the template fall back to kitty's own title.

import json
import os
import re
import shlex
import sys
import time
import types

import kittymux_agents
import kittymux_features
import kittymux_git
import kittymux_place
import kittymux_progress
import kittymux_theme
import kittymux_titles

_ICON_SHELL = "\uf489"                 # nerd-font terminal: plain shells, same as the tab bar
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
    "zsh": "zsh",
    "bash": "bash",
    "fish": "fish",
    "sh": "sh",
    "kitty": "kitty",
}
_GENERIC = frozenset({"", "kitty", "zsh", "bash", "fish", "sh", "node", "~"})
_BOLD, _NOBOLD, _RESET = "\x1b[1m", "\x1b[22m", "\x1b[0m"


def _sgr_fg(rgb: int) -> str:
    return f"\x1b[38;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"


def folder_caption(f: kittymux_place.Facts) -> str:
    """One faint folder string: repo path, worktree, or home-relative where."""
    if f.inner:
        text = f"/{f.project}/{f.inner.lstrip('/')}" if f.project else f"/{f.inner.lstrip('/')}"
    elif f.worktree:
        text = f"{f.project}:{f.worktree}"
    elif f.where:
        text = f.where
    else:
        text = f.project
    return kittymux_place.clean(text)


def _basename(value: str) -> str:
    return os.path.basename(value) or value


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


def pane_name(raw_title: str, agent: str | None, cmd: str, f: kittymux_place.Facts, *, titles: bool = True) -> str:
    """Bold label: agent product name, the tidied window title, or the foreground program."""
    title = kittymux_place.clean(raw_title or "")
    if agent:
        if titles and title and not kittymux_agents.is_default_title(title, agent):
            shown = kittymux_titles.tidy(title, agent, f.project).text
            if shown and shown.lower() not in _GENERIC:
                return shown
        return _APP_LABELS.get(agent, agent.replace("-", " ").title())
    if titles and title and not kittymux_place.redundant(title, f):
        shown = kittymux_titles.tidy(title, None, f.project).text
        if shown and shown.lower() not in _GENERIC and not title.startswith(("~", "/")):
            return shown
    if cmd:
        try:
            label = _title_from_cmdline(shlex.split(cmd))
        except ValueError:
            label = ""
        if label and label.lower() not in _GENERIC:
            return label
    if f.project:
        return f.project
    return "shell"


def pane_icon(agent: str | None, cmd: str) -> tuple[str, int | None]:
    """(glyph, brand_rgb or None). Plain shells get the terminal glyph with no brand colour."""
    if agent:
        spec = kittymux_agents.AGENTS.get(agent, kittymux_agents.FALLBACK)
        return spec.glyph, spec.brand
    if cmd:
        try:
            name = kittymux_agents.tool_in([shlex.split(cmd)])
        except ValueError:
            name = None
        if name:
            return kittymux_agents.TOOLS.get(name, ""), None
    return _ICON_SHELL, None


def _state_rgb(state: str, pal, bg: int, title_rgb: int) -> int:
    rgb = {"waiting": pal.waiting, "limited": pal.alert, "error": pal.alert, "working": pal.working, "done": pal.done}.get(state, title_rgb)
    return kittymux_theme.ensure_contrast(rgb, bg, 4.5)


def _tail_text(state_mark: str, progress: tuple[str, int] | None, cells=len) -> str:
    parts = []
    if progress:
        parts.append(kittymux_progress.label(*progress))
    if state_mark:
        parts.append(state_mark)
    if not parts:
        return ""
    return " ".join(parts)


def _styled(role: str, text: str, style: dict, *, bold_override: bool | None = None) -> str:
    rgb, bold = style[role]
    if bold_override is not None:
        bold = bold_override
    body = (_BOLD if bold else "") + text + (_NOBOLD if bold else "")
    return _sgr_fg(rgb) + body


def render(f: kittymux_place.Facts, title: str, columns: int, style: dict, *, active: bool,
           icon: str = "", name: str = "", folder: str = "", cells=len,
           state_mark: str = "", progress: tuple[str, int] | None = None) -> str:
    """One pane title bar row in cells: icon, bold name, faint folder, right-aligned progress and state."""
    avail = max(columns, 4) - 1
    tail = _tail_text(state_mark, progress, cells=cells)
    tail_w = cells(tail)
    icon_seg = (icon + " ") if icon else ""
    name = kittymux_place.clean(name)
    folder = kittymux_place.clean(folder)

    def left_plain(name_text: str, folder_text: str) -> str:
        out = icon_seg + name_text
        if folder_text:
            out += " " + folder_text
        return out

    name_text, folder_text = name, folder
    left_w = cells(left_plain(name_text, folder_text))
    while left_w + (1 if tail else 0) + tail_w > avail and folder_text:
        folder_text = kittymux_place.mid_ellipsis(folder_text, max(0, cells(folder_text) - 1), cells)
        if cells(folder_text) <= 1:
            folder_text = ""
        left_w = cells(left_plain(name_text, folder_text))
    while left_w + (1 if tail else 0) + tail_w > avail and name_text:
        name_text = kittymux_place.mid_ellipsis(name_text, max(1, cells(name_text) - 1), cells)
        left_w = cells(left_plain(name_text, folder_text))
    while left_w + (1 if tail else 0) + tail_w > avail and icon_seg:
        icon_seg = icon_seg[:-1]
        left_w = cells(left_plain(name_text, folder_text))

    parts = []
    if icon_seg:
        parts.append(_styled("icon", icon_seg, style))
    parts.append(_styled("name", name_text, style, bold_override=active))
    if folder_text:
        parts.append(_sgr_fg(style["folder"][0]) + " " + folder_text)
    left = "".join(parts)
    left_plain_text = icon_seg + name_text + ((" " + folder_text) if folder_text else "")
    pad = max(0, avail - cells(left_plain_text) - tail_w)
    tail_styled = ""
    if tail:
        chunks = []
        if progress:
            chunks.append(_sgr_fg(style["progress"][0]) + kittymux_progress.label(*progress))
        if state_mark:
            chunks.append(_sgr_fg(style["state"][0]) + state_mark)
        tail_styled = " ".join(chunks) + _RESET
    return left + (" " * pad) + tail_styled + _RESET


def _sgr_strip(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;:]*m", "", text)


def derive_colours(fg: int, bg: int, accent: int, avoid: tuple, project: str, active: bool):
    """(style, title_rgb, dot_rgb) — kept for contrast tests; draw uses derive_colours_full."""
    text = kittymux_theme.ensure_contrast(fg, bg, 4.5)
    muted = kittymux_theme.ensure_contrast(kittymux_theme.blend(fg, bg, 0.62), bg, 3.0)
    faint = kittymux_theme.ensure_contrast(kittymux_theme.blend(fg, bg, 0.45), bg, 3.0)
    hue = kittymux_theme.project_hue(project, accent, bg, avoid=tuple(avoid))
    style = kittymux_place.style(types.SimpleNamespace(text=text, muted=muted, faint=faint), active, hue, False)
    dot = kittymux_theme.ensure_contrast(kittymux_theme.blend(fg, bg, 0.3), bg, 1.5)
    return style, muted, dot


def derive_colours_full(fg: int, bg: int, pal, brand: int | None, active: bool, state: str):
    text = kittymux_theme.ensure_contrast(fg, bg, 4.5)
    muted = kittymux_theme.ensure_contrast(kittymux_theme.blend(fg, bg, 0.62), bg, 3.0)
    faint = kittymux_theme.ensure_contrast(kittymux_theme.blend(fg, bg, 0.45), bg, 3.0)
    icon = brand if brand is not None else muted
    if brand is not None and not active:
        icon = kittymux_theme.ensure_contrast(kittymux_theme.blend(brand, bg, 0.6), bg, 3.0)
    name_rgb = text if active else muted
    if state == "error":
        name_rgb = kittymux_theme.ensure_contrast(pal.alert, bg, 4.5)
    state_rgb = _state_rgb(state, pal, bg, text) if state and state != "idle" else text
    return {
        "icon": (icon, False),
        "name": (name_rgb, active),
        "folder": (faint, False),
        "progress": (faint, False),
        "state": (state_rgb, state in ("waiting", "limited", "error")),
    }


# ── the kitty side ───────────────────────────────────────────────────────────
def _kitty():
    from kitty.fast_data_types import get_boss, get_options, wcswidth
    from kitty.utils import color_as_int
    return get_boss, get_options, color_as_int, wcswidth


def _enabled() -> bool:
    try:
        return kittymux_features.enabled("panetitle")
    except Exception:
        return False


def _bar_colours(opts, active: bool, as_int) -> tuple[int, int]:
    def pick(name, fallback):
        value = getattr(opts, name, None)
        return fallback if value is None else value
    if active:
        fg = pick("window_title_bar_active_foreground", opts.active_tab_foreground)
        bg = pick("window_title_bar_active_background", opts.active_tab_background)
    else:
        fg = pick("window_title_bar_inactive_foreground", opts.inactive_tab_foreground)
        bg = pick("window_title_bar_inactive_background", opts.inactive_tab_background)
    return int(as_int(fg)), int(as_int(bg))


_PAL: dict = {"key": None, "pal": None}


def _palette(opts, as_int):
    colors = kittymux_theme.colors_from_options(opts, int(as_int(opts.background)), as_int)
    key = tuple(sorted(colors.items()))
    if _PAL["key"] != key:
        _PAL["key"], _PAL["pal"] = key, kittymux_theme.from_colors(colors)
    return _PAL["pal"]


def _dump(window_id: int, text: str) -> None:
    if os.environ.get("KITTYMUX_PANETITLE_DUMP") != "1":
        return
    try:
        path = os.path.join(kittymux_features.state_dir(), "panetitle-dump.json")
        try:
            with open(path) as f:
                rows = json.load(f)
        except (OSError, ValueError):
            rows = {}
        rows[str(window_id)] = text
        with open(path, "w") as f:
            json.dump(rows, f)
    except Exception:
        pass


def draw(data) -> str:
    try:
        if not _enabled():
            _dump(data.window_id, "")
            return ""
        get_boss, get_options, as_int, cells = _kitty()
        window = get_boss().window_id_map.get(data.window_id)
        if window is None:
            return ""
        cwd = window.child.current_cwd or window.child.cwd or ""
        if not cwd:
            return ""
        opts = get_options()
        active = bool(data.is_active)
        fg, bg = _bar_colours(opts, active, as_int)
        pal = _palette(opts, as_int)
        f = kittymux_place.facts(cwd, kittymux_git.info(cwd))
        rt = sys.modules.get("_kittymux_scan_rt")
        hook = (getattr(rt, "panes", (None, {}))[1].get(str(data.window_id)) or {})
        entry = kittymux_agents.merge_scan(
            {str(data.window_id): hook},
            {str(data.window_id): (getattr(rt, "verdicts", {}).get(str(data.window_id)) or {})}).get(str(data.window_id)) or {}
        agent = entry.get("agent")
        state = kittymux_agents.fresh_verdict(entry, time.monotonic())
        animate = kittymux_features.enabled("motion")
        mark = "" if not state or state == "idle" else kittymux_agents.state_glyph(state, animate=animate)
        titles = kittymux_features.enabled("titles")
        name = pane_name(data.title or "", agent, hook.get("cmd") or "", f, titles=titles)
        icon, brand = pane_icon(agent, hook.get("cmd") or "")
        folder = folder_caption(f)
        progress = kittymux_progress.of_window(window)
        style = derive_colours_full(fg, bg, pal, brand, active, state)
        out = render(f, data.title or "", int(window.screen.columns), style, active=active,
                     icon=icon, name=name, folder=folder, cells=cells,
                     state_mark=mark, progress=progress)
        _dump(data.window_id, out)
        return out
    except Exception:
        return ""
