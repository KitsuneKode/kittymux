# kittymux pane titles — the header row in kitty's per-pane title bars (ctrl+alt+shift+c shows them).
#
# kitty draws a one-row title bar above each pane when `window_title_bar_min_windows` says so; its text is `window_title_template`, and `{custom}` in
# that template is what `draw_window_title(data)` of the config dir's `window_title_bar.py` returns. kitty loads that file ONCE per process, so it is a
# trampoline into `draw` here — this module is reloaded by tab_bar.py on every config load, like the other helpers.
#
# The row is the deck's pane header, in cells, keeping the bar's place: [icon] bold name, then the SAME folder line the vertical bar draws
# (`kittymux_place.layout` / `style`: project hue, `project[:worktree]/inner`, branch). A name that already is the project is not repeated — only the
# rest of the path and the branch. The state mark and the OSC 9;4 percent sit on the right. A focused pane is bright; an unfocused one recedes.
# Truncation gives up the path (cut in the middle), then the branch, then the name. The state mark stays.
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
_ICON_BRANCH = ""                    # nerd-font git-branch, the same glyph the vertical bar's folder line uses
_PATH_ROLES = ("inner", "where")
_PLACE_WIDE = 10_000                   # ask layout for the full place; this row truncates in its own order
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
_CAP_L, _CAP_R = "\ue0b6", "\ue0b4"   # nerd-font round caps: with a background colour between them, a pill in cells


def _sgr_fg(rgb: int) -> str:
    return f"\x1b[38;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"


def _sgr_bg(rgb: int) -> str:
    return f"\x1b[48;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"


def pill_colours(state_rgb: int, bar_bg: int) -> tuple[int, int]:
    """(fill, ink) of a state pill on a title bar: the state colour at a low weight over the bar, the word in the state
    colour lifted to 4.5:1 on that fill."""
    fill = kittymux_theme.blend(state_rgb, bar_bg, 0.2)
    return fill, kittymux_theme.ensure_contrast(state_rgb, fill, 4.5)


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def says_folder(title: str, f: kittymux_place.Facts) -> bool:
    """A shell names its window with the folder. That is not a task, so the bold name is the project instead."""
    t = _norm(title)
    if not t or t in _GENERIC or (title or "").startswith(("~", "/")):
        return True
    if kittymux_place.redundant(title, f) or kittymux_place.worktree_named(title, f):
        return True
    if f.worktree and t == f.worktree.lower():
        return True
    if f.inner and t in {f.inner.lower(), f.inner.rsplit("/", 1)[-1].lower()}:
        return True
    if f.where and t == f.where.lower():
        return True
    return False


def hides(name: str, f: kittymux_place.Facts) -> tuple[bool, bool]:
    """(hide project, hide worktree) for the place line: the bold name already says them. The same two questions the bar asks
    (`redundant`, `worktree_named`), plus a name that is only the worktree directory."""
    hide_wt = kittymux_place.worktree_named(name, f) or bool(f.worktree and _norm(name) == f.worktree.lower())
    return kittymux_place.redundant(name, f), hide_wt


def place_pieces(f: kittymux_place.Facts, name: str, cells=len, branch_icon: str = _ICON_BRANCH):
    """The folder line, uncut. `kittymux_place.layout` owns the grammar (no second copy): project-relative, no leading slash
    once the project is hidden, branch included."""
    hide, hide_wt = hides(name, f)
    return kittymux_place.layout(f, _PLACE_WIDE, branch_icon=branch_icon, hide_project=hide,
                                 hide_worktree=hide_wt, cells=cells)


def _basename(value: str) -> str:
    return os.path.basename(value) or value


def _title_from_cmdline(cmdline: list[str]) -> str:
    """The program a command line runs, by its position only (as `kittymux_agents.tool_in`): argv[0], else what follows a `--`
    launcher or an env/sudo-style wrapper, else the script a runtime (`node …/claude`) runs. Never an argument: `git commit -m vim`
    is git, and `git diff -- src/nvim` is git."""
    argv, _shift = kittymux_agents.command_argv(cmdline or [])
    if argv and _basename(argv[0]).lower() in kittymux_agents._LAUNCHERS and "--" in argv:
        argv = argv[argv.index("--") + 1:]
    while argv and _basename(argv[0]).lower() in kittymux_agents._WRAPPERS:
        argv = argv[1:]
        while argv and argv[0].startswith("-"):
            argv = argv[1:]
    if len(argv) > 1 and _basename(argv[0]).lower() in kittymux_agents._RUNTIMES and not argv[1].startswith("-"):
        argv = argv[1:]
    if not argv:
        return ""
    first = _basename(argv[0]).lower().lstrip("-")
    return _APP_LABELS.get(first, first)


def pane_name(raw_title: str, agent: str | None, cmd: str, f: kittymux_place.Facts, *, titles: bool = True) -> str:
    """Bold label: the agent's product name or its task, the program (`nvim src/main.rs`), or — a plain shell — the project."""
    title = kittymux_place.clean(raw_title or "")
    if agent:
        if titles and title and not kittymux_agents.is_default_title(title, agent):
            shown = kittymux_titles.tidy(title, agent, f.project).text
            if shown and _norm(shown) not in _GENERIC and not says_folder(shown, f):
                return shown
        return kittymux_agents.product_label(agent)
    if titles and title and not says_folder(title, f):
        shown = kittymux_titles.tidy(title, None, f.project).text
        if shown and _norm(shown) not in _GENERIC and not says_folder(shown, f):
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


def _tail_text(state_mark: str, progress_text: str, word: str = "") -> str:
    parts = []
    if progress_text:
        parts.append(progress_text)
    if word:
        parts.append(_CAP_L + word + _CAP_R)
    elif state_mark:
        parts.append(state_mark)
    return " ".join(parts)


def _plain(icon_seg: str, name_text: str, pieces) -> str:
    body = icon_seg + name_text
    if not pieces:
        return body
    first = pieces[0][0]
    gap = "" if (not name_text or first.startswith(" ")) else "  "
    return body + gap + "".join(text for text, _role in pieces)


def _over(icon_seg, name_text, pieces, tail, avail, cells) -> bool:
    gap = 1 if tail else 0
    return cells(_plain(icon_seg, name_text, pieces)) + gap + cells(tail) > avail


def _shrink_path(pieces, cells):
    """Cut one cell from the middle of the path. Returns (pieces, changed). A path that cannot shrink is dropped."""
    out = []
    changed = False
    for text, role in pieces:
        if not changed and role in _PATH_ROLES and text:
            width = cells(text)
            nxt = kittymux_place.mid_ellipsis(text, width - 1, cells) if width > 1 else ""
            changed = True
            if nxt and cells(nxt) < width and cells(nxt) > 1:
                out.append((nxt, role))
            continue
        out.append((text, role))
    return out, changed


def _styled(role: str, text: str, style: dict, *, bold_override: bool | None = None) -> str:
    rgb, bold = style[role]
    if bold_override is not None:
        bold = bold_override
    body = (_BOLD if bold else "") + text + (_NOBOLD if bold else "")
    return _sgr_fg(rgb) + body


def render(f: kittymux_place.Facts, columns: int, style: dict, *, active: bool,
           icon: str = "", name: str = "", cells=len, state: str = "",
           state_mark: str = "", progress: tuple[str, int] | None = None,
           branch_icon: str = _ICON_BRANCH, state_word: str = "", pill: tuple[int, int] | None = None) -> str:
    """One pane header: icon, bold name, the bar's place line, then progress and the state mark on the right.

    The place comes from `kittymux_place.layout`. What is given up, in order: the path (middle), the branch, the percent,
    the pill (a `state_word` with `pill` = (fill, ink) colours shrinks to the state mark), then the name. The mark stays. A name that is the project takes the project's colour and is not drawn twice."""
    avail = max(columns, 4) - 1
    name = kittymux_place.clean(name)
    mark = kittymux_place.clean(state_mark)
    progress_text = kittymux_progress.label(*progress) if progress else ""
    if state != "error" and kittymux_place.redundant(name, f) and "project" in style:
        style = dict(style)
        style["name"] = style["project"]
    pieces = list(place_pieces(f, name, cells, branch_icon))
    icon_seg = (icon + " ") if icon else ""
    name_text = name
    progress_on = bool(progress_text)
    word = kittymux_place.clean(state_word)
    pill_on = bool(word and pill and mark)

    def tail():
        return _tail_text(mark, progress_text if progress_on else "", word if pill_on else "")

    def too_wide() -> bool:
        return _over(icon_seg, name_text, pieces, tail(), avail, cells)

    while too_wide() and any(role in _PATH_ROLES for _text, role in pieces):
        pieces, changed = _shrink_path(pieces, cells)
        if not changed:
            pieces = [(text, role) for text, role in pieces if role not in _PATH_ROLES]
            break
    if too_wide():
        pieces = [(text, role) for text, role in pieces if role != "branch"]
    if too_wide() and progress_on:
        progress_on = False
    if too_wide() and pill_on:
        pill_on = False
    while too_wide() and cells(name_text) > 1:
        nxt = kittymux_place.mid_ellipsis(name_text, max(1, cells(name_text) - 1), cells)
        if not nxt or cells(nxt) >= cells(name_text):
            break
        name_text = nxt
    while too_wide() and icon_seg:
        icon_seg = icon_seg[:-1]
    guard = 0
    while too_wide() and pieces and guard < 400:
        guard += 1
        shrunk = False
        for role in ("worktree", "where", "inner", "project", "icon"):
            for index, (text, piece_role) in enumerate(pieces):
                if piece_role != role or cells(text) <= 1:
                    continue
                nxt = kittymux_place.mid_ellipsis(text, cells(text) - 1, cells)
                if nxt and cells(nxt) < cells(text) and cells(nxt) > 1:
                    pieces[index] = (nxt, piece_role)
                else:
                    del pieces[index]
                shrunk = True
                break
            if shrunk:
                break
        if not shrunk:
            pieces = pieces[1:]

    name_rgb, name_bold = style["name"]
    parts = []
    if icon_seg:
        parts.append(_styled("app", icon_seg, style))
    if name_text:
        parts.append(_sgr_fg(name_rgb) + (_BOLD if name_bold and active else "") + name_text + (_NOBOLD if name_bold and active else ""))
    if pieces:
        if name_text and not pieces[0][0].startswith(" "):
            parts.append(_sgr_fg(style["inner"][0]) + "  ")
        for text, role in pieces:
            parts.append(_styled(role, text, style))
    left = "".join(parts)
    shown_tail = tail()
    pad = max(0, avail - cells(_plain(icon_seg, name_text, pieces)) - cells(shown_tail))
    tail_styled = ""
    if shown_tail:
        chunks = []
        if progress_on and progress_text:
            chunks.append(_sgr_fg(style["progress"][0]) + progress_text)
        if pill_on:
            fill, ink = pill
            chunks.append(_sgr_fg(fill) + _CAP_L + _sgr_bg(fill) + _sgr_fg(ink) + _BOLD + word + _NOBOLD
                          + "\x1b[49m" + _sgr_fg(fill) + _CAP_R)
        elif mark:
            chunks.append(_sgr_fg(style["state"][0]) + mark)
        tail_styled = " ".join(chunks)
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


def derive_colours_full(fg: int, bg: int, pal, brand: int | None, active: bool, state: str, *,
                        project: str = "", hue: int | None = None):
    """Place roles from `kittymux_place.style` (the project hue on the active pane), plus the app icon, the bold name,
    the percent and the state mark. Pass `hue` already resolved, or a project plus `pal.accent`, to colour the place.
    `hue=False` leaves the place in the text colour (the hue switch off)."""
    text = kittymux_theme.ensure_contrast(fg, bg, 4.5)
    muted = kittymux_theme.ensure_contrast(kittymux_theme.blend(fg, bg, 0.62), bg, 3.0)
    faint = kittymux_theme.ensure_contrast(kittymux_theme.blend(fg, bg, 0.45), bg, 3.0)
    if hue is False:
        hue = None
    elif hue is None and project and getattr(pal, "accent", None):
        avoid = tuple(c for c in (getattr(pal, "waiting", None), getattr(pal, "alert", None),
                                  getattr(pal, "working", None), getattr(pal, "done", None)) if c is not None)
        hue = kittymux_theme.project_hue(project, pal.accent, bg, avoid=avoid)
    place = kittymux_place.style(types.SimpleNamespace(text=text, muted=muted, faint=faint), active, hue, False)
    if hue is not None and not active:
        # the bar keeps this hue on the folder icon of an inactive tab. A pane header has no folder icon, so the
        # project word keeps a quieter version of the same hue: the cue stays, and the row still recedes.
        receded = kittymux_theme.ensure_contrast(kittymux_theme.blend(hue, bg, 0.62), bg, 3.0)
        place["project"] = (receded, False)
        place["icon"] = (receded, False)
    icon = brand if brand is not None else muted
    if brand is not None and not active:
        icon = kittymux_theme.ensure_contrast(kittymux_theme.blend(brand, bg, 0.6), bg, 3.0)
    name_rgb = text if active else muted
    if state == "error":
        name_rgb = kittymux_theme.ensure_contrast(pal.alert, bg, 4.5)
    state_rgb = _state_rgb(state, pal, bg, text) if state and state != "idle" else text
    out = dict(place)
    out["app"] = (icon, False)
    out["name"] = (name_rgb, active)
    out["progress"] = (faint, False)
    out["state"] = (state_rgb, state in ("waiting", "limited", "error"))
    return out


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


def close_question(window_id, columns: int, pal, bg: int, cells=len) -> str:
    """The close guard's one-line question in the waiting colour, fitted to the bar; '' when none stands for this window."""
    try:
        import kittymux_closeguard
        if not kittymux_closeguard.asking(window_id):
            return ""
        line = kittymux_closeguard.text()
        short = kittymux_closeguard.short_for([window_id])
    except Exception:
        return ""
    if not line:
        return ""
    ink = kittymux_theme.ensure_contrast(pal.waiting, bg, 4.5)
    room = max(1, columns - 2)
    if cells(line) > room and short:
        line = short                                   # a narrow pane keeps the part that matters: which key, again
    while line and cells(line) > room:
        line = line[:-2] + "…"
    r, g, b = ink >> 16 & 255, ink >> 8 & 255, ink & 255
    return f"\x1b[1;38;2;{r};{g};{b}m {line}\x1b[22m"


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
        asking = close_question(data.window_id, int(window.screen.columns), pal, bg, cells)
        if asking:                                   # closing this busy agent asks first, on this one line (kittymux_closeguard)
            _dump(data.window_id, asking)
            return asking
        f = kittymux_place.facts(cwd, kittymux_git.info(cwd))
        rt = sys.modules.get("_kittymux_scan_rt")
        hook = (getattr(rt, "panes", (None, {}))[1].get(str(data.window_id)) or {})
        entry = kittymux_agents.merge_scan(
            {str(data.window_id): hook},
            {str(data.window_id): (getattr(rt, "verdicts", {}).get(str(data.window_id)) or {})}).get(str(data.window_id)) or {}
        agent = entry.get("agent")
        state = kittymux_agents.fresh_verdict(entry, time.monotonic())
        # calm: a pane header never spins. A pill names the state; the still glyph is what is left when it cannot fit.
        mark = "" if not state or state == "idle" else kittymux_agents.state_glyph(state, animate=False)
        word = "" if not mark else kittymux_agents.STATE_WORDS.get(state, "")
        titles = kittymux_features.enabled("titles")
        name = pane_name(data.title or "", agent, hook.get("cmd") or "", f, titles=titles)
        icon, brand = pane_icon(agent, hook.get("cmd") or "")
        progress = kittymux_progress.of_window(window)
        hue = False
        if kittymux_features.enabled("hue") and f.project:
            hue = kittymux_theme.project_hue(f.project, pal.accent, bg,
                                            avoid=(pal.waiting, pal.alert, pal.working, pal.done))
        style = derive_colours_full(fg, bg, pal, brand, active, state, project=f.project, hue=hue)
        pill = pill_colours(style["state"][0], bg) if word else None
        out = render(f, int(window.screen.columns), style, active=active, icon=icon, name=name, cells=cells,
                     state=state, state_mark=mark, progress=progress, state_word=word, pill=pill)
        _dump(data.window_id, out)
        return out
    except Exception:
        return ""
