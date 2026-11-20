"""The pixel tab bar (plan 015): the vertical tab bar drawn as a picture, shown by kitty as the OS window's background
image through blank tab-bar cells. Pure: no kitty imports. Needs cairo, pango and rsvg (kittymux_deckpx's Painter).

Rex's anatomy: a machine header, a faint project label over each group, one row per tab (a tile with the agent's or
program's real mark, the title, one end mark), a second line only when it has something to say. Hover, the close
cross and motion are the shader's (assets/shaders/kittymux-pxbar.slang): column 0 of the picture is a row map it reads,
one marker colour per tab row, alternating, the bar's own colour everywhere else. The shader paints column 0 back.
"""
from __future__ import annotations

from dataclasses import dataclass

import cairo

import kittymux_agents
import kittymux_deckpx as dp
import kittymux_groups as G
import kittymux_theme as th

UI = "SF Pro Text, Inter, Cantarell, sans-serif"     # kuwai's order: SF Pro when installed, else Inter
MONO = "JetBrains Mono, SF Mono, monospace"
PAD = 10            # the side gutter
INSET = 5           # rows and the active card sit this far in from each edge
HEADER_H = 40
LABEL_H = 24
GAP = 10            # extra space above every group label but the first
ROW_H = 32
ROW2_H = 46         # a row with a second line
TILE = 20
T_TITLE, T_META, T_LABEL = 13, 11, 11
MAP_STEP = 6        # the row map's marker colours: the bar's red channel +6 and +12 (rows), +18 (the scale run)
SCALE_RUN = 8       # column 0's last pixels: a run of round(8 × scale) device px in the scale marker, so the shader knows the scale
BOTTOM = 12         # logical px kept clear at the bottom for the scale run
MORE_H = 22         # the "↑ N above" / "↓ N below" bands when the tabs don't all fit
ACTIVE_R = 10       # the active card's corner radius; the shader's hover band uses the same (kittymux-pxbar.slang R)
FOOT_H = 40         # the footer: the filter field that opens the palette, with its chord
PALETTE_CHORD = "⌃⌥⇧ Space"   # kittymux-keys.conf.tpl: ctrl+alt+shift+space opens the command palette
BRAND_OF_MARK = {kittymux_agents.brand_of(n): a.brand for n, a in kittymux_agents.AGENTS.items() if kittymux_agents.brand_of(n)}


@dataclass(frozen=True)
class Hit:
    """A band of the picture, in device pixels: a tab row (tab_id), a group label (kind 'group', project) or the header."""
    kind: str
    y0: int
    y1: int
    tab_id: int = 0
    project: str = ""          # a group's project; for kind "act" the action ("search", "collapse", "palette")
    x0: int = 0                # device px; x0 == x1 == 0: the whole width
    x1: int = 0


@dataclass(frozen=True)
class Picture:
    png: bytes
    hits: tuple
    width: int
    height: int
    start: int = 0      # tab rows scrolled off the top
    shown: int = 0      # tab rows drawn
    total: int = 0      # tab rows in all (folded groups' rows not counted)


def _rgb(c: int) -> tuple[float, float, float]:
    return ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255


def _nudge(bar: int, d: int) -> int:
    r = (bar >> 16) & 255
    r = r + d if r + d <= 255 else r - d
    return (r << 16) | (bar & 0xFFFF)


WORKING_STEP = 5    # a working row's markers sit in their own family (+30/+36): kittymux-pxwave.slang finds the rows to animate


def marker(bar: int, i: int, working: bool = False) -> int:
    """The row map colour of the i-th tab row: the bar with its red channel nudged up (down on a very light bar). A working
    row's markers are a separate, larger family, so the wave shader can tell it from the rest."""
    return _nudge(bar, MAP_STEP * ((WORKING_STEP if working else 0) + 1 + i % 2))


def scale_marker(bar: int) -> int:
    """The colour of the scale run at the bottom of column 0 (never a row's)."""
    return _nudge(bar, MAP_STEP * 3)


def _scale_run(cr, bar: int, H: int, scale: float) -> None:
    n = max(1, int(round(SCALE_RUN * scale)))
    cr.set_source_rgb(*_rgb(scale_marker(bar)))
    cr.rectangle(0, H - 2 - n, 1, n)
    cr.fill()


def _more(pt, cx, y, label, p, hits, kind, s, w=None):
    """A faint band saying how many tabs are out of view; a click pages that way (kittymux_pxbar.page)."""
    tw = pt.text_w(label, 10.5, family=UI)
    pt.text(cx - tw / 2, y + MORE_H / 2, label, 10.5, p.faint, family=UI)
    hits.append(Hit(kind, int(round(y * s)), int(round((y + MORE_H) * s))))


# A brand tile is a diagonal gradient between two of the brand's own colours (Rex's tiles read lit, not flat). Brands
# not listed derive theirs from their tint (gradient_for). Keyed by assets/icons basename.
GRADIENTS = {
    "googlegemini": (0x4285F4, 0x9B72CB),   # Gemini: Google blue into its purple
    "claude": (0xE38B69, 0xC4603E),
    "openai": (0x1DB892, 0x0B7A5E),
    "t3code": (0x5A44C4, 0x1B1446),         # T3 Code's own icon: the night sky, purple into navy
    "antigravity": (0x3186FF, 0x5B4CF0),
    "opencode": (0xFAB283, 0xE3824F),
    "cursor": (0x6A9BF7, 0x3C6BD9),
}


def _mix(c: int, to: int, t: float) -> int:
    ch = [(round(((c >> s) & 255) * (1 - t) + ((to >> s) & 255) * t)) for s in (16, 8, 0)]
    return (ch[0] << 16) | (ch[1] << 8) | ch[2]


def gradient_for(mark: str, tint: int) -> tuple[int, int]:
    """(top-left, bottom-right) colours of a brand tile."""
    return GRADIENTS.get(mark) or (_mix(tint, 0xFFFFFF, 0.12), _mix(tint, 0x000000, 0.16))


def _brand_rrect(pt: dp.Painter, x, y, w, h, r, mark: str, tint: int):
    s, cr = pt.s, pt.cr
    a, b = gradient_for(mark, tint)
    grad = cairo.LinearGradient(x * s, y * s, (x + w) * s, (y + h) * s)
    grad.add_color_stop_rgb(0, *_rgb(a))
    grad.add_color_stop_rgb(1, *_rgb(b))
    dp.rrect(cr, x * s, y * s, w * s, h * s, r * s)
    cr.set_source(grad)
    cr.fill()
    pt.fill_rrect(x + r * 0.6, y + 0.6, w - r * 1.2, 0.8, 0.4, 0xFFFFFF, 0.16)     # light catching the tile's top edge


def _tile(pt: dp.Painter, x, y, row: G.Row, p: th.Palette, side=TILE):
    r = 6 * side / TILE
    if row.tint is not None:
        _brand_rrect(pt, x, y, side, side, r, row.mark, row.tint)
        fg, alpha = 0xFFFFFF, 1.0
    else:
        c, a = pt.veil(0.09)
        pt.fill_rrect(x, y, side, side, r, c, a)
        fg, alpha = p.muted, 1.0
    size = round(12 * side / TILE)
    if row.mark and pt.icon(row.mark, x + (side - size) / 2, y + (side - size) / 2, size, fg, alpha):
        return
    _prompt(pt, x, y, fg, side)


def _prompt(pt: dp.Painter, x, y, color, box=TILE):
    """The shell's mark: a chevron and an underscore, drawn (no font needed), designed in a TILE box and scaled to `box`."""
    s, cr, k = pt.s, pt.cr, box / TILE
    cr.set_source_rgba(*dp.rgb(color))
    cr.set_line_width(max(1.4, 1.6 * k ** 0.5) * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    P = lambda px_, py_: ((x + px_ * k) * s, (y + py_ * k) * s)
    cr.move_to(*P(5.5, 6.5)); cr.line_to(*P(9, 10)); cr.line_to(*P(5.5, 13.5))
    cr.move_to(*P(10.5, 14)); cr.line_to(*P(15, 14))
    cr.stroke()


def _stack(pt: dp.Painter, x, y, marks, p, side=TILE):
    """The badge on a tile's corner for the other agents in this tab's splits: their mark, or +N for two or more."""
    if not marks:
        return
    bx, by, bs = x + side - 8, y + side - 8, 12
    pt.fill_rrect(bx - 1.5, by - 1.5, bs + 3, bs + 3, 5, p.bar)
    if len(marks) == 1:
        tint = BRAND_OF_MARK.get(marks[0])
        if tint is not None:
            _brand_rrect(pt, bx, by, bs, bs, 4, marks[0], tint)
        else:
            pt.fill_rrect(bx, by, bs, bs, 4, p.surface_hi)
        pt.icon(marks[0], bx + 2, by + 2, bs - 4, 0xFFFFFF if tint is not None else p.text)
    else:
        pt.fill_rrect(bx, by, bs, bs, 4, p.surface_hi)
        pt.text(bx + 1.5, by + bs / 2, f"+{len(marks)}", 7.5, p.text, weight=dp.Pango.Weight.BOLD, family=UI)


WAVE = ((5, 10, 7), (8, 6, 10), (10, 8, 5))   # three frames: the bars rise and fall, one step per SPINNER_FPS tick


def _wave(pt: dp.Painter, right, cy, color, phase=0):
    """The working loader: three bars, one frame per step of the bar's calm clock (never a continuous animation)."""
    for i, h in enumerate(WAVE[phase % len(WAVE)]):
        x = right - 12 + i * 4
        pt.fill_rrect(x, cy - h / 2, 2, h, 1, color)


def _branch_icon(pt: dp.Painter, cx, cy, color):
    """A git branch: two commits on a line and a third joined by a curve (the mockup's branch mark), 9 px tall."""
    s, cr = pt.s, pt.cr
    cr.set_source_rgba(*dp.rgb(color))
    cr.set_line_width(1.1 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    x0, x1 = cx - 2.2, cx + 2.4
    cr.move_to(x0 * s, (cy - 3.2) * s)
    cr.line_to(x0 * s, (cy + 3.2) * s)
    cr.move_to(x1 * s, (cy - 2.0) * s)
    cr.curve_to(x1 * s, (cy + 0.6) * s, x0 * s, (cy + 0.2) * s, x0 * s, (cy + 2.0) * s)
    cr.stroke()
    for px, py in ((x0, cy - 3.6), (x0, cy + 3.6), (x1, cy - 2.4)):
        cr.new_sub_path()
        cr.arc(px * s, py * s, 1.15 * s, 0, 6.2832)
        cr.fill()


def _search_icon(pt: dp.Painter, cx, cy, color):
    s, cr = pt.s, pt.cr
    cr.set_source_rgba(*dp.rgb(color))
    cr.set_line_width(1.5 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.new_sub_path()
    cr.arc((cx - 1) * s, (cy - 1) * s, 4.2 * s, 0, 6.2832)
    cr.move_to((cx + 2.2) * s, (cy + 2.2) * s)
    cr.line_to((cx + 5) * s, (cy + 5) * s)
    cr.stroke()


def _sidebar_icon(pt: dp.Painter, cx, cy, color):
    """The collapse button: a window with its sidebar, as macOS draws it."""
    pt.stroke_rrect(cx - 6.5, cy - 5.5, 13, 11, 2.5, color, 1.0, 1.4)
    pt.fill_rrect(cx - 3.6, cy - 3, 1.4, 6, 0.7, color)


def _action(hits, name, x, y, w, h, s):
    hits.append(Hit("act", int(round(y * s)), int(round((y + h) * s)), project=name,
                    x0=int(round(x * s)), x1=int(round((x + w) * s))))


def _inbox_icon(pt, cx, cy, color):
    s, cr = pt.s, pt.cr
    pt.stroke_rrect(cx - 6, cy - 5, 12, 10, 2.5, color, 1.0, 1.4)
    cr.set_source_rgba(*dp.rgb(color))
    cr.set_line_width(1.4 * s)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.move_to((cx - 6) * s, (cy + 0.5) * s)
    for px_, py_ in ((cx - 2.5, cy + 0.5), (cx - 1.5, cy + 2.2), (cx + 1.5, cy + 2.2), (cx + 2.5, cy + 0.5), (cx + 6, cy + 0.5)):
        cr.line_to(px_ * s, py_ * s)
    cr.stroke()


def _gauge_icon(pt, cx, cy, color):
    s, cr = pt.s, pt.cr
    cr.set_source_rgba(*dp.rgb(color))
    cr.set_line_width(1.4 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.new_sub_path()
    cr.arc(cx * s, (cy + 2) * s, 6 * s, 3.4, 6.03)
    cr.stroke()
    cr.move_to(cx * s, (cy + 2) * s)
    cr.line_to((cx + 3) * s, (cy - 1.5) * s)
    cr.stroke()


def _keys_icon(pt, cx, cy, color):
    pt.stroke_rrect(cx - 7, cy - 4.5, 14, 9, 2, color, 1.0, 1.3)
    for i in range(3):
        pt.fill_rrect(cx - 4.5 + i * 3.5, cy - 2, 1.6, 1.6, 0.4, color)
    pt.fill_rrect(cx - 3, cy + 1.2, 6, 1.4, 0.4, color)


FOOT_ICONS = (("inbox", _inbox_icon), ("usage", _gauge_icon), ("keys", _keys_icon))


def _footer(pt, width, height, p, hits, s, narrow=False):
    """The keyboard's way in, made visible: a filter field that opens the command palette (with its chord when there is
    room), then the inbox, usage and the keys sheet. A hairline separates it from the tabs, as Rex's footer is."""
    top = height - BOTTOM - FOOT_H
    c, a = pt.veil(0.07)
    pt.fill_rrect(PAD, top, width - 2 * PAD, 1, 0.5, c, a)
    y, h = top + 8, 24
    icons = () if narrow else FOOT_ICONS      # narrow: the filter alone, so it stays readable
    icons_w = len(icons) * 26
    x, w = INSET + 3, width - 2 * (INSET + 3) - icons_w - 4
    c, a = pt.veil(0.055)
    pt.fill_rrect(x, y, w, h, 7, c, a)
    _search_icon(pt, x + 13, y + h / 2, p.faint)
    pt.text(x + 25, y + h / 2, "Filter", 11.5, p.faint, family=UI)
    kw = pt.text_w(PALETTE_CHORD, 10, family=UI)
    if w - kw - 70 > 0:
        pt.text(x + w - kw - 9, y + h / 2, PALETTE_CHORD, 10, p.faint, family=UI)
    _action(hits, "palette", x, y, w, h, s)
    ix = x + w + 4 + 13
    for name, draw in icons:
        draw(pt, ix, y + h / 2, p.muted)
        _action(hits, name, ix - 13, y, 26, h, s)
        ix += 26


def _diff_line(pt, x, cy, text, room, p):
    """`7 files +142 −30`: the counts in the done and alert colours, the rest faint; tabular figures so they don't jitter."""
    for tok in text.split():
        col = p.done if tok.startswith("+") else p.alert if tok.startswith(("−", "-")) and tok[1:].isdigit() else p.faint
        w = pt.text_w(tok + " ", T_META, family=UI, tnum=True)
        if w > room:
            break
        pt.text(x, cy, tok, T_META, col, family=UI, tnum=True)
        x, room = x + w, room - w


def _cross(pt: dp.Painter, cx, cy, color, r=3.5):
    s, cr = pt.s, pt.cr
    cr.set_source_rgba(*dp.rgb(color))
    cr.set_line_width(1.7 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to((cx - r) * s, (cy - r) * s); cr.line_to((cx + r) * s, (cy + r) * s)
    cr.move_to((cx + r) * s, (cy - r) * s); cr.line_to((cx - r) * s, (cy + r) * s)
    cr.stroke()


def _age_before(pt, row, x_right, cy, p, narrow) -> float:
    """How long a row has needed you, or since it finished, faint, just left of its mark; none on a narrow bar."""
    if not row.age or narrow:
        return 0
    w = pt.text_w(row.age, T_META, family=UI, tnum=True)
    pt.text(x_right - w, cy, row.age, T_META, p.faint, family=UI, tnum=True)
    return w + 6


def _end(pt: dp.Painter, row: G.Row, right, cy, p, narrow) -> float:
    """The row's end mark; returns how much width it took (the title stops before it)."""
    if row.state == "waiting" and not row.muted:
        label = "!" if narrow else "Needs you"
        w = pt.text_w(label, 10.5, weight=dp.Pango.Weight.SEMIBOLD, family=UI) + 12
        pt.fill_rrect(right - w, cy - 9, w, 18, 9, p.waiting, 0.18)
        pt.text(right - w + 6, cy, label, 10.5, p.waiting, weight=dp.Pango.Weight.SEMIBOLD, family=UI)
        return w + _age_before(pt, row, right - w - 6, cy, p, narrow)
    if row.state == "working":
        _wave(pt, right, cy, p.muted if row.muted else p.working, row.phase)
        return 14
    if row.state == "done":
        pt.dot(right - 3, cy, 3, p.done)
        return 8 + _age_before(pt, row, right - 12, cy, p, narrow)
    if row.state == "unread":
        pt.dot(right - 3, cy, 2.5, p.muted)                 # fresh output you haven't seen (kittymux-ui: •)
        return 8
    if row.state == "error":
        _cross(pt, right - 5, cy, p.alert)
        return 12
    if row.age:
        tone = p.waiting if row.state == "limited" else p.faint
        w = pt.text_w(row.age, T_META, family=UI, tnum=True)
        pt.text(right - w, cy, row.age, T_META, tone, family=UI, tnum=True)
        return w
    if row.progress and row.progress[0] not in ("indeterminate",):
        pst, pct = row.progress
        label = "failed" if pst == "error" else f"{max(0, min(100, int(pct or 0)))}%"
        tone = {"error": p.alert, "paused": p.waiting}.get(pst, p.muted)
        w = pt.text_w(label, T_META, family=UI, tnum=True)
        pt.text(right - w, cy, label, T_META, tone, family=UI, tnum=True)
        return w
    return 0


def _progress(pt: dp.Painter, x, y, w, row: G.Row, p):
    """OSC 9;4 progress under the row: a faint track the length of the text column and its fill, so it reads as progress and
    not as an underline. Indeterminate fills the track at half strength."""
    pst, pct = row.progress
    c, a = pt.veil(0.08)
    pt.fill_rrect(x, y, w, 2, 1, c, a)
    col = {"error": p.alert, "paused": p.waiting}.get(pst, p.working)
    if pst == "indeterminate":
        pt.fill_rrect(x, y, w, 2, 1, col, 0.45)
        return
    frac = 1.0 if pst == "error" else max(0.0, min(1.0, (pct or 0) / 100))
    if frac > 0:
        pt.fill_rrect(x, y, max(2.0, w * frac), 2, 1, col)


RAIL_MAX = 130      # logical px: narrower than this the bar is the rail (marks only, a state dot on each)
# The rail (2026-11-20 redesign). kitty makes a custom-drawn left bar title + 8 cells wide at the least, so the rail is ~80 px:
# one column of marks with no chrome; the active row alone gets a tile, and the hover (kittymux-pxbar.slang) is the same
# square. State is a dot inside the tile's top-right corner, clear of the mark, so nothing is ever cut into a tile.
RAIL_ROW = 36       # one tab: its tile and 3 px above and below (Rex's sidebar rhythm: rows ~2.5× the text, not 3×)
RAIL_TILE = 30      # the active tile and the hover square
RAIL_TILE_R = 8     # their corner radius (kuwai's r1)
RAIL_MARK = 16      # the mark inside a tile
RAIL_PIP_IN = 4.5   # the state dot's centre, this far in from the tile's top and right edges
RAIL_PIP_R = 3.0    # its radius (the working ring's too)
RAIL_FOOT_ROW = 30  # the footer's controls, one per row
RAIL_GAP = 10       # between groups: a short rule, the rail has no labels
RAIL_DENSER = 0.5   # the rail keeps half the wide bar's see-through: small marks need a calm surface under them
PIP = {"waiting": "waiting", "done": "done", "error": "alert", "limited": "waiting", "working": "working"}
RAIL_FOOT = (("palette", _search_icon), ("inbox", _inbox_icon), ("keys", _keys_icon))


def rail_alpha(alpha: float) -> float:
    return round(1.0 - (1.0 - alpha) * RAIL_DENSER, 3)


def _rule(pt, cx, y):
    c, a = pt.veil(0.10)
    pt.fill_rrect(cx - 7, y, 14, 1, 0.5, c, a)


def _rail_pip(pt, x, y, row: G.Row, pal):
    """The row's state, in the tile's top-right corner: a dot, or for a working row an open ring the loader turns."""
    tone = PIP.get(row.state) if not row.muted else None
    if not tone:
        return
    cx, cy, color = x + RAIL_TILE - RAIL_PIP_IN, y + RAIL_PIP_IN, getattr(pal, tone)
    if row.state == "working":
        s, cr = pt.s, pt.cr
        cr.new_path()
        cr.arc(cx * s, cy * s, (RAIL_PIP_R - 0.3) * s, -1.5708, 3.1416)     # from the top round to the left: ¾ of a turn
        cr.set_source_rgba(*dp.rgb(color))
        cr.set_line_width(1.5 * s)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.stroke()
        return
    pt.dot(cx, cy, RAIL_PIP_R, color, 0.6 if row.state == "limited" else 1.0)


def _rail_mark(pt, x, y, row: G.Row, pal):
    """The tab's mark, monochrome: bright on the active row and on one that needs you, faint when muted, muted otherwise."""
    if row.active or (row.state == "waiting" and not row.muted):
        tone = pal.text
    else:
        tone = pal.faint if row.muted else pal.muted
    m = RAIL_MARK
    if row.mark and pt.icon(row.mark, x + (RAIL_TILE - m) / 2, y + (RAIL_TILE - m) / 2, m, tone):
        return
    box = TILE * m / 12                       # the prompt is drawn in a TILE box at the weight of a 12 px mark
    _prompt(pt, x + (RAIL_TILE - box) / 2, y + (RAIL_TILE - box) / 2, tone, box)


def _rail_progress(pt, x, y, row: G.Row, pal):
    """OSC 9;4 progress along the tile's foot, inside it (the old bar under the tile clipped the active card's corners)."""
    pst, pct = row.progress
    frac = 1.0 if pst in ("error", "indeterminate") else max(0.0, min(1.0, (pct or 0) / 100))
    col = {"error": pal.alert, "paused": pal.waiting}.get(pst, pal.working)
    w, x0, y0 = RAIL_TILE - 16, x + 8, y + RAIL_TILE - 5
    c, a = pt.veil(0.10)
    pt.fill_rrect(x0, y0, w, 2, 1, c, a)
    if frac > 0:
        pt.fill_rrect(x0, y0, max(2.0, w * frac), 2, 1, col, 0.5 if pst == "indeterminate" else 1.0)


def _rail_footer(pt, width, height, p, hits, s) -> float:
    """The mouse's ways in, as in the wide footer: the palette, the inbox, the keys sheet. Returns the footer's top."""
    top = height - BOTTOM - (RAIL_GAP + len(RAIL_FOOT) * RAIL_FOOT_ROW)
    cx = width / 2
    _rule(pt, cx, top + RAIL_GAP / 2)
    y = top + RAIL_GAP
    for name, draw in RAIL_FOOT:
        draw(pt, cx, y + RAIL_FOOT_ROW / 2, p.faint)
        _action(hits, name, cx - RAIL_TILE / 2, y, RAIL_TILE, RAIL_FOOT_ROW, s)
        y += RAIL_FOOT_ROW
    return top


def _render_rail(pt, cr, groups, pal, width, height, s, hits, start=0):
    """Returns (start, shown, total)."""
    cx = width / 2
    _sidebar_icon(pt, cx, HEADER_H / 2, pal.muted)                 # the way back open: the wide bar's sidebar icon
    if G.needs_you(groups):
        pt.dot(cx + 11, HEADER_H / 2 - 8, RAIL_PIP_R, pal.waiting)     # clear of the icon, as a row's dot is of its mark
    _action(hits, "collapse", 0, 0, width, HEADER_H, s)            # the whole header expands the sidebar again
    c, a = pt.veil(0.07)                                           # one hairline where the rail meets the terminal
    cr.rectangle(width * s - 1, 0, 1, height * s)
    cr.set_source_rgba(*dp.rgb(c, a))
    cr.fill()
    total = sum(len(g.rows) for g in groups)
    start = max(0, min(start, max(0, total - 1)))
    foot_h = RAIL_GAP + len(RAIL_FOOT) * RAIL_FOOT_ROW
    bottom = height - BOTTOM
    if bottom - foot_h - HEADER_H >= 3 * RAIL_ROW + MORE_H:        # a short window keeps its rows and loses the footer
        bottom = _rail_footer(pt, width, height, pal, hits, s)
    need = HEADER_H + sum((RAIL_GAP if gi else 0) + (20 if g.hidden else RAIL_ROW * len(g.rows)) for gi, g in enumerate(groups))
    limit = bottom
    if start or need > limit:
        limit -= MORE_H
    y, tab_i, skip, shown, drew = HEADER_H, 0, start, 0, False
    if start:
        _more(pt, cx, y, f"↑{start}", pal, hits, "up", s)
        y += MORE_H
    for gi, g in enumerate(groups):
        if skip and (not g.rows or skip >= len(g.rows)):
            skip -= len(g.rows)
            continue
        if drew:
            _rule(pt, cx, y + RAIL_GAP / 2)
            y += RAIL_GAP
        drew = True
        if g.hidden:
            if y + 20 > limit:
                break
            label = f"+{g.hidden}"
            pt.text(cx - pt.text_w(label, 10, family=UI, tnum=True) / 2, y + 10, label, 10, pal.faint, family=UI, tnum=True)
            hits.append(Hit("group", int(round(y * s)), int(round((y + 20) * s)), project=g.project))
            y += 20
            continue
        full = False
        for row in g.rows:
            if skip:
                skip -= 1
                continue
            if y + RAIL_ROW > limit:
                full = True
                break
            shown += 1
            y0, y1 = int(round(y * s)), int(round((y + RAIL_ROW) * s))
            tx, ty = cx - RAIL_TILE / 2, y + (RAIL_ROW - RAIL_TILE) / 2
            if row.active:
                c, a = pt.veil(0.11)
                pt.fill_rrect(tx, ty, RAIL_TILE, RAIL_TILE, RAIL_TILE_R, c, a)
            cr.set_source_rgb(*_rgb(marker(pal.bar, tab_i, row.state == "working" and not row.muted)))
            cr.rectangle(0, y0, 1, y1 - y0)
            cr.fill()
            tab_i += 1
            _rail_mark(pt, tx, ty, row, pal)
            _rail_pip(pt, tx, ty, row, pal)
            if row.progress:
                _rail_progress(pt, tx, ty, row, pal)
            hits.append(Hit("tab", y0, y1, tab_id=row.tab_id))
            y += RAIL_ROW
        if full:
            break
    below = total - start - shown
    if below > 0:
        _more(pt, cx, bottom - MORE_H, f"↓{below}", pal, hits, "down", s)
    return start, shown, total


def render(groups, pal: th.Palette, width: int, height: int, *, host: str = "", scale: float = 1.0,
           alpha: float = 1.0, resources=None, start: int = 0) -> Picture:
    """Draw the bar. `width`/`height` are logical px; the picture is width*scale × height*scale device px. `start` tab rows
    are scrolled off the top when the tabs don't all fit (kittymux_pxbar keeps the active one in view)."""
    W, H = int(round(width * scale)), int(round(height * scale))
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    if width < RAIL_MAX:
        alpha = rail_alpha(alpha)
    cr.set_source_rgba(*_rgb(pal.bar), alpha)
    cr.paint()
    _scale_run(cr, pal.bar, H, scale)
    pt = dp.Painter(cr, scale, pal, resources)
    s = scale
    hits: list[Hit] = []
    narrow = width < 200
    right = width - PAD - INSET
    if width < RAIL_MAX:
        st, shown, total = _render_rail(pt, cr, groups, pal, width, height, s, hits, start)
        return Picture(_png(surf), tuple(hits), W, H, st, shown, total)

    # the header: the mascot on a neutral tile, the machine, the needs-you count
    y = 0
    _tile(pt, PAD, (HEADER_H - TILE) / 2, G.Row(0, "", "", mark="kittymux"), pal)
    pt.text(PAD + TILE + 9, HEADER_H / 2, host or "kittymux", T_TITLE, pal.text, weight=dp.Pango.Weight.SEMIBOLD, family=UI,
            width=max(10, right - (PAD + TILE + 9) - (70 if narrow else 96)))
    # the header's actions at its right end: collapse to the rail, then search (the palette); the needs-you count before them
    ax = right - 9
    _sidebar_icon(pt, ax, HEADER_H / 2, pal.muted)
    _action(hits, "collapse", ax - 12, HEADER_H / 2 - 12, 24, 24, s)
    if not narrow:                            # narrow, the host keeps its room: search is the footer's Filter too
        ax -= 26
        _search_icon(pt, ax, HEADER_H / 2, pal.muted)
        _action(hits, "search", ax - 12, HEADER_H / 2 - 12, 24, 24, s)
    chip_right = ax - 16
    n = G.needs_you(groups)
    if n:
        label = str(n)
        w = max(18, pt.text_w(label, 11, weight=dp.Pango.Weight.SEMIBOLD, family=UI, tnum=True) + 12)
        pt.fill_rrect(chip_right - w, HEADER_H / 2 - 9, w, 18, 9, pal.waiting, 0.18)
        pt.text(chip_right - w + (w - pt.text_w(label, 11, weight=dp.Pango.Weight.SEMIBOLD, family=UI, tnum=True)) / 2, HEADER_H / 2,
                label, 11, pal.waiting, weight=dp.Pango.Weight.SEMIBOLD, family=UI, tnum=True)
    hits.append(Hit("header", 0, int(round(HEADER_H * s))))
    y = HEADER_H

    total = sum(len(g.rows) for g in groups)
    start = max(0, min(start, max(0, total - 1)))
    need = HEADER_H + sum((GAP if gi else 0) + LABEL_H + sum(ROW2_H if r.meta else ROW_H for r in g.rows)
                          for gi, g in enumerate(groups))
    limit = height - BOTTOM - FOOT_H
    _footer(pt, width, height, pal, hits, s, narrow)
    if start or need > limit:
        limit -= MORE_H                       # room for the "↓ N below" band
    if start:
        _more(pt, width / 2, y, f"↑ {start} above", pal, hits, "up", s)
        y += MORE_H
    tab_i, skip, shown, drew, full = 0, start, 0, False, False
    for gi, g in enumerate(groups):
        if full:
            break
        if skip and (not g.rows or skip >= len(g.rows)):
            skip -= len(g.rows)               # the whole group is above the view (a folded one before it too)
            continue
        first_h = (ROW2_H if g.rows[skip].meta else ROW_H) if g.rows else 0
        if y + (GAP if drew else 0) + LABEL_H + first_h > limit:
            break                             # never a label without its first row
        if drew:
            y += GAP
        drew = True
        # the group label: the project (muted, semibold: the anchor you scan by); at the right its branch when it isn't the default
        # (one typeface, faint, a branch mark, cut in the MIDDLE so its distinctive end stays) or how many rows are folded
        cy = y + LABEL_H / 2 + 2
        tail = f"+{g.hidden}" if g.hidden else g.branch
        bw = 0.0
        if tail and not narrow:
            room = max(40.0, (right - PAD) * 0.48)
            tw = min(pt.text_w(tail, T_LABEL, family=UI), room)
            pt.text(right - tw, cy, tail, T_LABEL, pal.faint, family=UI, width=None if g.hidden else tw, mid=True)
            bw = tw
            if not g.hidden:
                _branch_icon(pt, right - tw - 7, cy, pal.faint)
                bw += 13
        pt.text(PAD + 2, cy, g.project, T_LABEL, pal.muted, weight=dp.Pango.Weight.SEMIBOLD, family=UI, track=0.2,
                width=max(20.0, right - PAD - 2 - bw - 10))
        hits.append(Hit("group", int(round(y * s)), int(round((y + LABEL_H) * s)), project=g.project))
        y += LABEL_H
        for row in g.rows:
            if skip:
                skip -= 1
                continue
            h = ROW2_H if row.meta else ROW_H
            if y + h > limit:
                full = True
                break
            shown += 1
            y0, y1 = int(round(y * s)), int(round((y + h) * s))
            if row.active:
                c, a = pt.veil(0.085)
                pt.fill_rrect(INSET, y, width - 2 * INSET, h, ACTIVE_R, c, a)
                hc, ha = pt.veil(0.06)
                pt.fill_rrect(INSET + 8, y, width - 2 * INSET - 16, 1, 0.5, hc, ha)       # the card's top light
            # the row map: column 0, this row's band
            cr.set_source_rgb(*_rgb(marker(pal.bar, tab_i, row.state == "working" and not row.muted)))
            cr.rectangle(0, y0, 1, y1 - y0)
            cr.fill()
            tab_i += 1
            title_cy = y + (15 if row.meta else h / 2)
            tx = PAD + TILE + 9
            _tile(pt, PAD, title_cy - TILE / 2, row, pal)
            _stack(pt, PAD, title_cy - TILE / 2, row.stack, pal)
            end_w = _end(pt, row, right, title_cy, pal, narrow)
            live = not G.settled(row) or row.active
            tone = pal.faint if row.muted else (pal.text if live else pal.muted)
            weight = dp.Pango.Weight.MEDIUM if live and not row.muted else dp.Pango.Weight.NORMAL
            room = right - tx - (end_w + 8 if end_w else 0)
            title = row.title or "Untitled"                   # never a row with nothing to name it
            tw = pt.text(tx, title_cy, title, T_TITLE, tone if row.title else pal.faint, weight=weight, family=UI, width=max(10, room))
            if row.path and not narrow and room - tw > 40:
                pt.text(tx + tw + 5, title_cy, row.path, T_META, pal.faint, family=UI, width=room - tw - 5)
            if row.meta and row.meta_tone == "diff":
                _diff_line(pt, tx, y + 31, row.meta, right - tx, pal)
            elif row.meta:
                mt = {"waiting": pal.muted, "alert": pal.alert, "working": pal.muted}.get(row.meta_tone, pal.faint)
                pt.text(tx, y + 31, row.meta, T_META, mt, family=UI, width=max(10, right - tx))
            if row.progress:
                _progress(pt, tx, y + h - 4, right - tx, row, pal)
            hits.append(Hit("tab", y0, y1, tab_id=row.tab_id))
            y += h
    below = total - start - shown
    if below > 0:
        _more(pt, width / 2, height - BOTTOM - FOOT_H - MORE_H, f"↓ {below} below", pal, hits, "down", s)
    buf = _png(surf)
    return Picture(buf, tuple(hits), W, H, start, shown, total)


def _png(surf) -> bytes:
    import io
    out = io.BytesIO()
    surf.write_to_png(out)
    return out.getvalue()


def hit_at(hits, y_px: int, x_px: int | None = None):
    """The band at a device-pixel point, or None: a control with its own x range wins over the full-width band under it."""
    whole = None
    for h in hits:
        if h.y0 <= y_px < h.y1:
            if h.x1 > h.x0:
                if x_px is not None and h.x0 <= x_px < h.x1:
                    return h
            elif whole is None:
                whole = h
    return whole
