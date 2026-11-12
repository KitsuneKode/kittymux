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

import kittymux_deckpx as dp
import kittymux_groups as G
import kittymux_theme as th

UI = "Inter, SF Pro Text, Cantarell, sans-serif"
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
MAP_STEP = 6        # the row map's marker colours: the bar's red channel +6 and +12


@dataclass(frozen=True)
class Hit:
    """A band of the picture, in device pixels: a tab row (tab_id), a group label (kind 'group', project) or the header."""
    kind: str
    y0: int
    y1: int
    tab_id: int = 0
    project: str = ""


@dataclass(frozen=True)
class Picture:
    png: bytes
    hits: tuple
    width: int
    height: int


def _rgb(c: int) -> tuple[float, float, float]:
    return ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255


def marker(bar: int, i: int) -> int:
    """The row map colour of the i-th tab row: the bar with its red channel nudged up (down on a very light bar)."""
    r = (bar >> 16) & 255
    d = MAP_STEP * (1 + i % 2)
    r = r + d if r + d <= 255 else r - d
    return (r << 16) | (bar & 0xFFFF)


def _tile(pt: dp.Painter, x, y, row: G.Row, p: th.Palette):
    if row.tint is not None:
        pt.fill_rrect(x, y, TILE, TILE, 6, row.tint)
        fg, alpha = 0xFFFFFF, 1.0
    else:
        c, a = pt.veil(0.09)
        pt.fill_rrect(x, y, TILE, TILE, 6, c, a)
        fg, alpha = p.muted, 1.0
    size = 12
    if row.mark and pt.icon(row.mark, x + (TILE - size) / 2, y + (TILE - size) / 2, size, fg, alpha):
        return
    _prompt(pt, x, y, fg)


def _prompt(pt: dp.Painter, x, y, color):
    """The shell's mark: a chevron and an underscore, drawn (no font needed)."""
    s, cr = pt.s, pt.cr
    cr.set_source_rgba(*dp.rgb(color))
    cr.set_line_width(1.6 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.move_to((x + 5.5) * s, (y + 6.5) * s); cr.line_to((x + 9) * s, (y + 10) * s); cr.line_to((x + 5.5) * s, (y + 13.5) * s)
    cr.move_to((x + 10.5) * s, (y + 14) * s); cr.line_to((x + 15) * s, (y + 14) * s)
    cr.stroke()


def _stack(pt: dp.Painter, x, y, marks, p):
    """The badge on a tile's corner for the other agents in this tab's splits: their mark, or +N for two or more."""
    if not marks:
        return
    bx, by, bs = x + TILE - 8, y + TILE - 8, 12
    pt.fill_rrect(bx - 1.5, by - 1.5, bs + 3, bs + 3, 5, p.bar)
    if len(marks) == 1:
        pt.fill_rrect(bx, by, bs, bs, 4, p.surface_hi)
        pt.icon(marks[0], bx + 2, by + 2, bs - 4, p.text)
    else:
        pt.fill_rrect(bx, by, bs, bs, 4, p.surface_hi)
        pt.text(bx + 1.5, by + bs / 2, f"+{len(marks)}", 7.5, p.text, weight=dp.Pango.Weight.BOLD, family=UI)


def _wave(pt: dp.Painter, right, cy, color):
    """The working mark's still frame: three bars. The shader moves them (they are drawn in exactly `color`)."""
    for i, h in enumerate((5, 10, 7)):
        x = right - 12 + i * 4
        pt.fill_rrect(x, cy - h / 2, 2, h, 1, color)


def _cross(pt: dp.Painter, cx, cy, color, r=3.5):
    s, cr = pt.s, pt.cr
    cr.set_source_rgba(*dp.rgb(color))
    cr.set_line_width(1.7 * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to((cx - r) * s, (cy - r) * s); cr.line_to((cx + r) * s, (cy + r) * s)
    cr.move_to((cx + r) * s, (cy - r) * s); cr.line_to((cx - r) * s, (cy + r) * s)
    cr.stroke()


def _end(pt: dp.Painter, row: G.Row, right, cy, p, narrow) -> float:
    """The row's end mark; returns how much width it took (the title stops before it)."""
    if row.state == "waiting" and not row.muted:
        label = "!" if narrow else "Needs you"
        w = pt.text_w(label, 10.5, weight=dp.Pango.Weight.SEMIBOLD, family=UI) + 12
        pt.fill_rrect(right - w, cy - 9, w, 18, 9, p.waiting, 0.18)
        pt.text(right - w + 6, cy, label, 10.5, p.waiting, weight=dp.Pango.Weight.SEMIBOLD, family=UI)
        return w
    if row.state == "working":
        _wave(pt, right, cy, p.muted if row.muted else p.working)
        return 14
    if row.state == "done":
        pt.dot(right - 3, cy, 3, p.done)
        return 8
    if row.state == "error":
        _cross(pt, right - 5, cy, p.alert)
        return 12
    if row.age:
        tone = p.waiting if row.state == "limited" else p.faint
        w = pt.text_w(row.age, T_META, family=UI, tnum=True)
        pt.text(right - w, cy, row.age, T_META, tone, family=UI, tnum=True)
        return w
    return 0


RAIL_MAX = 130      # logical px: narrower than this the bar is the rail (tiles only, a state dot on each tile)
RAIL_ROW = 34
PIP = {"waiting": "waiting", "done": "done", "error": "alert", "limited": "waiting", "working": "working"}


def _render_rail(pt, cr, groups, pal, width, height, s, hits):
    cx = width / 2
    _tile(pt, cx - TILE / 2, (HEADER_H - TILE) / 2, G.Row(0, "", "", mark="kittymux"), pal)
    n = G.needs_you(groups)
    if n:
        pt.dot(cx + TILE / 2 - 1, (HEADER_H - TILE) / 2 + 1, 4, pal.waiting)
    hits.append(Hit("header", 0, int(round(HEADER_H * s))))
    y, tab_i = HEADER_H, 0
    for gi, g in enumerate(groups):
        if gi:
            c, a = pt.veil(0.10)
            pt.fill_rrect(cx - 8, y + 5, 16, 1, 0.5, c, a)         # a short rule between groups: the rail has no labels
            y += 11
        if g.hidden:
            label = f"+{g.hidden}"
            pt.text(cx - pt.text_w(label, 10, family=UI) / 2, y + 10, label, 10, pal.faint, family=UI)
            hits.append(Hit("group", int(round(y * s)), int(round((y + 20) * s)), project=g.project))
            y += 20
            continue
        for row in g.rows:
            if y + RAIL_ROW > height:
                return
            y0, y1 = int(round(y * s)), int(round((y + RAIL_ROW) * s))
            if row.active:
                c, a = pt.veil(0.085)
                pt.fill_rrect(cx - 15, y + 2, 30, RAIL_ROW - 4, 9, c, a)
            cr.set_source_rgb(*_rgb(marker(pal.bar, tab_i)))
            cr.rectangle(0, y0, 1, y1 - y0)
            cr.fill()
            tab_i += 1
            ty = y + (RAIL_ROW - TILE) / 2
            _tile(pt, cx - TILE / 2, ty, row, pal)
            _stack(pt, cx - TILE / 2, ty, row.stack, pal)
            tone = PIP.get(row.state) if not row.muted else None
            if tone:
                pt.fill_rrect(cx + TILE / 2 - 5.5, ty - 2.5, 9, 9, 4.5, pal.bar)
                pt.dot(cx + TILE / 2 - 1, ty + 2, 3, getattr(pal, tone))
            if row.progress:
                pst, pct = row.progress
                frac = 1.0 if pst in ("error", "indeterminate") else max(0.0, min(1.0, (pct or 0) / 100))
                pt.fill_rrect(cx - TILE / 2, y + RAIL_ROW - 3, TILE * frac, 2, 1, {"error": pal.alert, "paused": pal.waiting}.get(pst, pal.working))
            hits.append(Hit("tab", y0, y1, tab_id=row.tab_id))
            y += RAIL_ROW


def render(groups, pal: th.Palette, width: int, height: int, *, host: str = "", scale: float = 1.0,
           alpha: float = 1.0, resources=None) -> Picture:
    """Draw the bar. `width`/`height` are logical px; the picture is width*scale × height*scale device px."""
    W, H = int(round(width * scale)), int(round(height * scale))
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    cr.set_source_rgba(*_rgb(pal.bar), alpha)
    cr.paint()
    pt = dp.Painter(cr, scale, pal, resources)
    s = scale
    hits: list[Hit] = []
    narrow = width < 200
    right = width - PAD - INSET
    if width < RAIL_MAX:
        _render_rail(pt, cr, groups, pal, width, height, s, hits)
        return Picture(_png(surf), tuple(hits), W, H)

    # the header: the mascot on a neutral tile, the machine, the needs-you count
    y = 0
    _tile(pt, PAD, (HEADER_H - TILE) / 2, G.Row(0, "", "", mark="kittymux"), pal)
    pt.text(PAD + TILE + 9, HEADER_H / 2, host or "kittymux", T_TITLE, pal.text, weight=dp.Pango.Weight.SEMIBOLD, family=UI,
            width=max(10, right - (PAD + TILE + 9) - 30))
    n = G.needs_you(groups)
    if n:
        label = str(n)
        w = max(18, pt.text_w(label, 11, weight=dp.Pango.Weight.SEMIBOLD, family=UI, tnum=True) + 12)
        pt.fill_rrect(right - w, HEADER_H / 2 - 9, w, 18, 9, pal.waiting, 0.18)
        pt.text(right - w + (w - pt.text_w(label, 11, weight=dp.Pango.Weight.SEMIBOLD, family=UI, tnum=True)) / 2, HEADER_H / 2,
                label, 11, pal.waiting, weight=dp.Pango.Weight.SEMIBOLD, family=UI, tnum=True)
    hits.append(Hit("header", 0, int(round(HEADER_H * s))))
    y = HEADER_H

    tab_i = 0
    for gi, g in enumerate(groups):
        if y >= height:
            break
        if gi:
            y += GAP
        # the group label: the project, faint; its branch at the right when it isn't the default; a fold count
        pt.text(PAD + 2, y + LABEL_H / 2 + 2, g.project, T_LABEL, pal.faint, weight=dp.Pango.Weight.SEMIBOLD, family=UI,
                width=right - PAD - 60)
        tail = f"+{g.hidden}" if g.hidden else g.branch
        if tail and not narrow:
            fam = UI if g.hidden else MONO
            tw = min(pt.text_w(tail, 10.5, family=fam), 120)
            pt.text(right - tw, y + LABEL_H / 2 + 2, tail, 10.5, pal.faint, family=fam, width=tw if not g.hidden else None)
        hits.append(Hit("group", int(round(y * s)), int(round((y + LABEL_H) * s)), project=g.project))
        y += LABEL_H
        for row in g.rows:
            h = ROW2_H if row.meta else ROW_H
            if y + h > height:
                break
            y0, y1 = int(round(y * s)), int(round((y + h) * s))
            if row.active:
                c, a = pt.veil(0.085)
                pt.fill_rrect(INSET, y, width - 2 * INSET, h, 8, c, a)
                hc, ha = pt.veil(0.06)
                pt.fill_rrect(INSET + 8, y, width - 2 * INSET - 16, 1, 0.5, hc, ha)       # the card's top light
            # the row map: column 0, this row's band
            cr.set_source_rgb(*_rgb(marker(pal.bar, tab_i)))
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
            tw = pt.text(tx, title_cy, row.title, T_TITLE, tone, weight=weight, family=UI, width=max(10, room))
            if row.path and not narrow and room - tw > 40:
                pt.text(tx + tw + 5, title_cy, row.path, T_META, pal.faint, family=UI, width=room - tw - 5)
            if row.meta:
                mt = {"waiting": pal.muted, "alert": pal.alert, "working": pal.muted}.get(row.meta_tone, pal.faint)
                pt.text(tx, y + 31, row.meta, T_META, mt, family=UI, width=max(10, right - tx))
            if row.progress:
                pst, pct = row.progress
                frac = 1.0 if pst in ("error", "indeterminate") else max(0.0, min(1.0, (pct or 0) / 100))
                col = {"error": pal.alert, "paused": pal.waiting}.get(pst, pal.working)
                pt.fill_rrect(tx, y + h - 3, (right - tx) * frac, 2, 1, col)
            hits.append(Hit("tab", y0, y1, tab_id=row.tab_id))
            y += h
    buf = _png(surf)
    return Picture(buf, tuple(hits), W, H)


def _png(surf) -> bytes:
    import io
    out = io.BytesIO()
    surf.write_to_png(out)
    return out.getvalue()


def hit_at(hits, y_px: int):
    """The band at device-pixel row y, or None."""
    for h in hits:
        if h.y0 <= y_px < h.y1:
            return h
    return None
