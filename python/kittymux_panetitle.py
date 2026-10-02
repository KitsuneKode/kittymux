# kittymux pane titles — the folder line in kitty's per-pane title bars (ctrl+alt+shift+h shows them).
#
# kitty draws a one-row title bar above each pane when `window_title_bar_min_windows` says so; its text is `window_title_template`, and `{custom}` in
# that template is what `draw_window_title(data)` of the config dir's `window_title_bar.py` returns. kitty loads that file ONCE per process, so it is a
# trampoline into `draw` here — this module is reloaded by tab_bar.py on every config load, like the other helpers.
#
# The line speaks the tab bar's grammar — project[:worktree]/inner  branch — then the pane's own title when it adds something, in colours derived
# from the title bar's REAL foreground/background (so it reads on every theme) and the same per-project tint as the tab bar.
#
# `render` and `derive_colours` are pure; `draw` imports kitty lazily and never raises: "" makes the template fall back to kitty's own title.

import json
import os
import types

import kittymux_features
import kittymux_git
import kittymux_place
import kittymux_theme

_ICON_FOLDER = ""
_ICON_BRANCH = ""
_GENERIC = {"", "kitty", "zsh", "bash", "fish", "sh", "node", "~"}
_DOT = "  ·  "
_MIN_TITLE = 8                       # a title narrower than this is not worth a separator
_BOLD, _NOBOLD, _RESET = "\x1b[1m", "\x1b[22m", "\x1b[0m"


def _sgr_fg(rgb: int) -> str:
    return f"\x1b[38;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"


def _says_nothing_new(title: str, f) -> bool:
    """A shell titles its window with the folder or the shell's name — the folder line already says that."""
    t = " ".join(title.split())
    return (t.lower() in _GENERIC or kittymux_place.redundant(t, f) or kittymux_place.worktree_named(t, f)
            or t.startswith(("~", "/")))


def _fit(text: str, width: int, cells) -> str:
    if cells(text) <= width:
        return text
    out = ""
    for ch in text:
        if cells(out + ch) > width - 1:
            break
        out += ch
    return out + "…"


def render(f, title: str, columns: int, style: dict, title_rgb: int, dot_rgb: int, *, active: bool,
           icon: str = "", branch_icon: str = "", cells=len) -> str:
    """The title bar text for one pane: the folder line first (it gets the room it needs), the pane's own title in what is left.
    Visible width never exceeds the bar. `style` is kittymux_place.style's role → (rgb, bold)."""
    avail = max(columns, 4) - 1
    pieces = kittymux_place.layout(f, avail, icon=icon, branch_icon=branch_icon, cells=cells)
    if not pieces:
        return ""
    used = sum(cells(t) for t, _r in pieces)
    out = []
    for text, role in pieces:
        rgb, bold = style[role]
        out.append(_sgr_fg(rgb) + (_BOLD if bold else "") + text + (_NOBOLD if bold else ""))
    title = kittymux_place.clean(title)                       # the title is whatever the program in the pane set
    shown = "" if _says_nothing_new(title, f) else title
    room = avail - used - len(_DOT)
    if shown and room >= _MIN_TITLE:
        out.append(_sgr_fg(dot_rgb) + _DOT + _sgr_fg(title_rgb) + _fit(shown, room, cells))
    return "".join(out) + _RESET


def derive_colours(fg: int, bg: int, accent: int, avoid: tuple, project: str, active: bool):
    """(style, title_rgb, dot_rgb) for a title bar whose real colours are fg on bg: every role stays readable there, the project's tint is the
    one the tab bar uses (same accent, same state colours kept clear)."""
    text = kittymux_theme.ensure_contrast(fg, bg, 4.5)
    muted = kittymux_theme.ensure_contrast(kittymux_theme.blend(fg, bg, 0.62), bg, 3.0)
    faint = kittymux_theme.ensure_contrast(kittymux_theme.blend(fg, bg, 0.45), bg, 3.0)
    hue = kittymux_theme.project_hue(project, accent, bg, avoid=tuple(avoid))
    style = kittymux_place.style(types.SimpleNamespace(text=text, muted=muted, faint=faint), active, hue, False)
    dot = kittymux_theme.ensure_contrast(kittymux_theme.blend(fg, bg, 0.3), bg, 1.5)
    return style, muted, dot


# ── the kitty side ───────────────────────────────────────────────────────────
def _kitty():
    from kitty.fast_data_types import get_boss, get_options, wcswidth
    from kitty.utils import color_as_int
    return get_boss, get_options, color_as_int, wcswidth


def _enabled() -> bool:
    try:
        return kittymux_features.enabled("panetitle")
    except Exception:
        return False                                  # cannot tell: leave kitty's own title alone


def _bar_colours(opts, active: bool, as_int) -> tuple[int, int]:
    """The title bar's foreground/background the way kitty resolves them (window_title_bar_* option, else the tab colours)."""
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
    """Test hook (tests/smoke_panetitle.sh): the last text drawn per window, escape sequences and all."""
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
    """What `{custom}` becomes in the pane title bar of window `data.window_id`; "" leaves kitty's own title."""
    try:
        if not _enabled():
            _dump(data.window_id, "")                     # (test hook only) so a rig can see the hand-back
            return ""
        get_boss, get_options, as_int, cells = _kitty()
        window = get_boss().window_id_map.get(data.window_id)
        if window is None:
            return ""
        cwd = window.child.current_cwd or window.child.cwd or ""
        if not cwd:
            return ""
        opts = get_options()
        fg, bg = _bar_colours(opts, bool(data.is_active), as_int)
        pal = _palette(opts, as_int)
        f = kittymux_place.facts(cwd, kittymux_git.info(cwd))
        style, title_rgb, dot_rgb = derive_colours(fg, bg, pal.accent, (pal.waiting, pal.alert, pal.working, pal.done),
                                                   f.project, bool(data.is_active))
        out = render(f, data.title or "", int(window.screen.columns), style, title_rgb, dot_rgb, active=bool(data.is_active),
                     icon=_ICON_FOLDER, branch_icon=_ICON_BRANCH, cells=cells)
        _dump(data.window_id, out)
        return out
    except Exception:
        return ""
