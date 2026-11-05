# kittymux deckpx — the sidebar drawn in pixels (cairo + pango + rsvg) for kitty's graphics protocol.
# Pure: no kitty imports. Colours come from a kittymux_theme.Palette (kitty's live colours), never a fixed palette.
# The panel's Agents view uses it when the `deckpx` switch is on (kittymux_deckadapt maps the snapshot). The demo kitten still runs alone.

import math
import os
from collections import OrderedDict
from dataclasses import dataclass, field

import gi
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
gi.require_version("Rsvg", "2.0")
import cairo  # noqa: E402
from gi.repository import Pango, PangoCairo, Rsvg  # noqa: E402

import kittymux_theme as th  # noqa: E402

ICONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icons")

UI_FONT = "SF Pro Text"
DISPLAY_FONT = "SF Pro Display"
ROUNDED_FONT = "SF Pro Rounded"


@dataclass
class Space:
    name: str
    branch: str = ""
    state: str = ""          # waiting | working | done | idle | limited | error | ""
    active: bool = False     # the session that holds the keyboard selection (raised card)
    current: bool = False    # the session you are in


@dataclass
class Agent:
    title: str
    agent: str               # key into kittymux_agents.AGENTS / assets/icons
    brand: int
    space: str
    age: str = ""
    state: str = "idle"      # working | waiting | done | idle | limited | error
    progress: float | None = None   # OSC 9;4 hairline, 0..1 (0 and None draw nothing)
    active: bool = False     # raised card (the demo's selection, and the panel's keyboard row)
    current: bool = False    # the tab you are looking at: an accent bar, distinct from the selection
    selected: bool = False   # keyboard selection: the same raised card as the active row, distinct from hover
    progress_state: str = "" # set | paused | error | indeterminate (the hairline's colour)
    can_open: bool = False   # a split tab: a chevron, never opened by hover
    opened: bool = False
    row: int = -1            # flat snapshot row, for hit testing
    pane: int = -1           # child pane index, or -1 for the tab row
    children: list = field(default_factory=list)


@dataclass
class Model:
    session: str
    host: str
    spaces: list[Space] = field(default_factory=list)
    agents: list[Agent] = field(default_factory=list)
    empty: str = ""
    empty_hint: str = ""


@dataclass
class Frame:
    hover: int | None = None      # index of the hovered agent row
    phase: float = 0.0            # 0..1 animation clock (spinner); a frame is drawn only while something moves
    reveal: float = 1.0           # 0..1 spring value for the active card (slides/settles on focus change)
    scroll: float = 0.0           # logical px into the body under the header
    hover_pane: int | None = None # flat index of the hovered child pane


# The header occupies this many logical px. Everything under it scrolls.
HEADER_END = 56.0


ICON_FILE = {"claude": "claude", "codex": "openai", "gemini": "googlegemini", "opencode": "opencode", "cursor": "cursor",
             "amp": "amp", "devin": "devin", "shell": None}


def rgb(c: int, a: float = 1.0) -> tuple[float, float, float, float]:
    return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255, a)


def rrect(cr, x, y, w, h, r):
    r = min(r, h / 2, w / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class Resources:
    """Bounded, window-owned Pango/SVG caches. No context or timer survives the window."""
    def __init__(self, limit=256):
        self.limit = max(1, limit)
        self.layouts, self.fonts, self.icons = OrderedDict(), OrderedDict(), OrderedDict()

    def get(self, cache, key, create):
        if key not in cache:
            cache[key] = create()
            if len(cache) > self.limit:
                cache.popitem(last=False)
        cache.move_to_end(key)
        return cache[key]


class Painter:
    def __init__(self, cr, scale: float, pal: th.Palette, resources=None, spinners=None):
        self.cr, self.s, self.p = cr, scale, pal
        self.dark = th.luminance(pal.bg) < 0.4
        self.resources = resources or Resources()
        self.spinners = spinners
        self.spin_clip = (None, None)

    # text ------------------------------------------------------------------------------------------------------------
    def layout(self, text, size, weight=Pango.Weight.NORMAL, family=UI_FONT, width=None, tnum=False, track=0.0):
        key = (text, size, weight, family, width, tnum, track, self.s)
        lo = self.resources.get(self.resources.layouts, key,
                                lambda: self._layout(text, size, weight, family, width, tnum, track))
        PangoCairo.update_layout(self.cr, lo)
        return lo

    def _layout(self, text, size, weight, family, width, tnum, track):
        lo = PangoCairo.create_layout(self.cr)
        def font():
            fd = Pango.FontDescription.from_string(family)
            fd.set_weight(weight)
            fd.set_absolute_size(size * self.s * Pango.SCALE)
            return fd
        fd = self.resources.get(self.resources.fonts, (family, weight, size, self.s), font)
        lo.set_font_description(fd)
        attrs = Pango.AttrList()
        if tnum:
            attrs.insert(Pango.attr_font_features_new("tnum"))
        if track:
            attrs.insert(Pango.attr_letter_spacing_new(int(track * self.s * Pango.SCALE)))
        lo.set_attributes(attrs)
        lo.set_text(text, -1)
        if width is not None:
            lo.set_width(int(max(1, width) * self.s * Pango.SCALE))
            lo.set_ellipsize(Pango.EllipsizeMode.END)
        return lo

    def text(self, x, cy, text, size, color, alpha=1.0, **kw):
        """Draw text vertically centred on cy (logical px); returns its logical width."""
        lo = self.layout(text, size, **kw)
        _ink, logical = lo.get_pixel_extents()
        self.cr.set_source_rgba(*rgb(color, alpha))
        self.cr.move_to(x * self.s, cy * self.s - logical.height / 2)
        PangoCairo.show_layout(self.cr, lo)
        return logical.width / self.s

    def text_w(self, text, size, **kw):
        _ink, logical = self.layout(text, size, **kw).get_pixel_extents()
        return logical.width / self.s

    # shapes ----------------------------------------------------------------------------------------------------------
    def fill_rrect(self, x, y, w, h, r, color, alpha=1.0):
        s = self.s
        rrect(self.cr, x * s, y * s, w * s, h * s, r * s)
        self.cr.set_source_rgba(*rgb(color, alpha))
        self.cr.fill()

    def card(self, x, y, w, h, r, color, lift=1.0):
        """A raised glass card: soft stacked shadow, the fill, a top sheen and a hairline rim."""
        s, cr = self.s, self.cr
        if lift > 0:
            for i, a in enumerate((0.10, 0.06, 0.035)):
                grow = (i + 1) * 1.2
                rrect(cr, (x - grow / 2) * s, (y + grow * 0.9) * s, (w + grow) * s, (h + grow * 0.4) * s, (r + grow) * s)
                cr.set_source_rgba(0, 0, 0, a * lift * (1.6 if self.dark else 1.0))
                cr.fill()
        rrect(cr, x * s, y * s, w * s, h * s, r * s)
        g = cairo.LinearGradient(0, y * s, 0, (y + h) * s)
        top = th.blend(0xFFFFFF, color, 0.05 if self.dark else 0.5)
        g.add_color_stop_rgba(0, *rgb(top))
        g.add_color_stop_rgba(1, *rgb(color))
        cr.set_source(g)
        cr.fill_preserve()
        cr.set_line_width(1 * s)
        cr.set_source_rgba(1, 1, 1, 0.07 if self.dark else 0.0)
        cr.stroke()
        if not self.dark:          # a light card needs a darker rim to separate from a light bar
            rrect(cr, x * s + .5, y * s + .5, w * s - 1, h * s - 1, r * s)
            cr.set_source_rgba(0, 0, 0, 0.07)
            cr.set_line_width(1)
            cr.stroke()
        # the 1px sheen at the top edge is what makes it read as glass and not a flat fill
        cr.save()
        rrect(cr, x * s, y * s, w * s, h * s, r * s)
        cr.clip()
        cr.move_to((x + r) * s, y * s + 0.5 * s)
        cr.line_to((x + w - r) * s, y * s + 0.5 * s)
        cr.set_source_rgba(1, 1, 1, 0.10 if self.dark else 0.6)
        cr.set_line_width(1 * s)
        cr.stroke()
        cr.restore()

    def icon(self, name, x, y, size, color, alpha=1.0):
        path = os.path.join(ICONS, f"{name}.svg")
        if not os.path.exists(path):
            return False
        s, cr = self.s, self.cr
        handle = self.resources.get(self.resources.icons, path, lambda: Rsvg.Handle.new_from_file(path))
        cr.push_group()
        vp = Rsvg.Rectangle()
        vp.x, vp.y, vp.width, vp.height = x * s, y * s, size * s, size * s
        handle.render_document(cr, vp)
        mask = cr.pop_group()
        cr.set_source_rgba(*rgb(color, alpha))
        cr.mask(mask)
        return True

    def dot(self, cx, cy, r, color, alpha=1.0, ring=False):
        s, cr = self.s, self.cr
        cr.new_path()        # Pango leaves a current point behind; arc() would join a line from it
        cr.arc(cx * s, cy * s, r * s, 0, 2 * math.pi)
        cr.set_source_rgba(*rgb(color, alpha))
        if ring:
            cr.set_line_width(1.3 * s)
            cr.stroke()
        else:
            cr.fill()

    def spinner(self, cx, cy, r, color, phase):
        lo, hi = self.spin_clip
        if lo is not None and not (lo <= cy <= hi):
            return
        if self.spinners is not None:
            self.spinners.append((cx, cy, r, color))
            return
        s, cr = self.s, self.cr
        cr.set_line_width(1.6 * s)
        cr.new_path()
        cr.arc(cx * s, cy * s, r * s, 0, 2 * math.pi)
        cr.set_source_rgba(*rgb(color, 0.22))
        cr.stroke()
        a0 = phase * 2 * math.pi - math.pi / 2
        cr.new_path()
        cr.arc(cx * s, cy * s, r * s, a0, a0 + math.pi * 0.62)
        cr.set_source_rgba(*rgb(color))
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.stroke()
        cr.set_line_cap(cairo.LINE_CAP_BUTT)

    def pill(self, right, cy, label, color, bar):
        w = self.text_w(label, 10.5, weight=Pango.Weight.SEMIBOLD) + 12
        h = 18
        self.fill_rrect(right - w, cy - h / 2, w, h, h / 2, th.blend(color, bar, 0.20 if self.dark else 0.16))
        self.text(right - w + 6, cy, label, 10.5, th.ensure_contrast(color, th.blend(color, bar, 0.2), 4.5),
                  weight=Pango.Weight.SEMIBOLD)
        return w

    def stroke_rrect(self, x, y, w, h, r, color, alpha=1.0, width=1.5):
        s = self.s
        rrect(self.cr, x * s, y * s, w * s, h * s, r * s)
        self.cr.set_source_rgba(*rgb(color, alpha))
        self.cr.set_line_width(width * s)
        self.cr.stroke()


def status_mark(pt: Painter, right, cy, state, phase, bar):
    """Draw the right-hand state mark ending at `right`; returns the width it took."""
    p = pt.p
    if state == "waiting":
        return pt.pill(right, cy, "Needs you", p.waiting, bar)
    if state == "error":
        return pt.pill(right, cy, "Error", p.alert, bar)
    if state == "limited":
        return pt.pill(right, cy, "Limited", p.alert, bar)
    if state == "working":
        pt.spinner(right - 5, cy, 4.6, p.working, phase)
        return 11
    if state == "done":
        pt.dot(right - 4, cy, 3.4, p.done)
        return 8
    pt.dot(right - 4, cy, 3.2, p.faint, ring=True)
    return 8


def body_items(model: Model) -> list:
    """Rows under the header, in content px: (kind, index, y, h, payload). The renderer draws these and nothing else moves them."""
    y = 0.0
    out = []
    if model.spaces:
        out.append(("label", 0, y, 20, ("section", "Spaces", True)))
        y += 20
        for i, sp in enumerate(model.spaces):
            out.append(("space", i, y, 32, sp))
            y += 34
        y += 8
        out.append(("rule", 0, y, 1, None))
        y += 10
    out.append(("label", 0, y, 20, ("section", "Agents", False)))
    y += 20
    if not model.agents:
        out.append(("empty", 0, y, 48, None))
        return out
    last = None
    flat = 0
    for i, ag in enumerate(model.agents):
        if ag.space != last:
            if last is not None:
                y += 4
            if ag.space:
                out.append(("label", 0, y, 18, ("group", ag.space, False)))
                y += 18
            last = ag.space
        out.append(("agent", i, y, 30, ag))
        y += 31
        for ch in ag.children:
            out.append(("pane", flat, y, 26, ch))
            flat += 1
            y += 27
    return out


def content_height(model: Model) -> float:
    items = body_items(model)
    if not items:
        return 0.0
    last = items[-1]
    return last[2] + last[3] + 8


def clamp_scroll(scroll, content: float, view_h: float) -> float:
    try:
        scroll = float(scroll)
    except (TypeError, ValueError):
        scroll = 0.0
    if not math.isfinite(scroll):
        scroll = 0.0
    room = max(0.0, float(content) - max(0.0, float(view_h)))
    return min(room, max(0.0, scroll))


def scroll_to_item(items, scroll: float, view_h: float, kind: str, index) -> float:
    """Smallest change that puts (kind, index) fully inside the body viewport."""
    for k, i, y, h, _payload in items:
        if k == kind and i == index:
            if y < scroll:
                return float(y)
            if y + h > scroll + view_h:
                return float(y + h - view_h)
            return float(scroll)
    return float(scroll)


def hit_at(hits, x: float, y: float):
    """The topmost (kind, index) whose rect contains (x, y), else None. Later rects win, so a chevron beats its row."""
    if not hits:
        return None
    for item in reversed(hits):
        kind, idx, hx, hy, hw, hh = item[:6]
        if hw > 0 and hh > 0 and hx <= x < hx + hw and hy <= y < hy + hh:
            return kind, idx
    return None


def _progress_color(p, state: str) -> int:
    return {"paused": p.waiting, "error": p.alert, "indeterminate": p.faint}.get(state, p.working)


def render(model: Model, pal: th.Palette, width: float, height: float, scale: float = 1.0, frame: Frame | None = None,
           glass: float = 0.84, hits: list | None = None, resources: Resources | None = None,
           spinners: list | None = None, metrics: dict | None = None) -> cairo.ImageSurface:
    """Draw the deck. width/height are logical px; the surface is width*scale × height*scale device px.
    `glass` < 1 leaves the bar translucent so the compositor's blur shows through (kitty background_opacity).
    `hits`, when given, collects (kind, index, x, y, w, h) in logical px for the window's own mouse hit-testing.
    The header stays put; spaces and agents scroll by `frame.scroll`."""
    frame = frame or Frame()
    if not all(math.isfinite(v) and v > 0 for v in (width, height, scale)):
        raise ValueError("deck dimensions and scale must be finite and positive")
    W, H = int(round(width * scale)), int(round(height * scale))
    if not (0 < W <= 10000 and 0 < H <= 10000):
        raise ValueError("deck exceeds kitty's image dimensions")
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    fo = cairo.FontOptions()
    fo.set_antialias(cairo.ANTIALIAS_GRAY)       # grey AA: subpixel AA breaks on a translucent surface
    fo.set_hint_style(cairo.HINT_STYLE_SLIGHT)
    fo.set_hint_metrics(cairo.HINT_METRICS_OFF)
    cr.set_font_options(fo)
    pt = Painter(cr, scale, pal, resources, spinners)
    pt.spin_clip = (HEADER_END, height)
    p = pal
    bar = p.bar

    # the glass sheet ---------------------------------------------------------------------------------------------------
    cr.rectangle(0, 0, W, H)
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgba(0, *rgb(th.blend(0xFFFFFF, bar, 0.025 if pt.dark else 0.3), glass))
    g.add_color_stop_rgba(1, *rgb(bar, glass))
    cr.set_source(g)
    cr.fill()
    cr.rectangle(W - 1, 0, 1, H)       # one device pixel, also at fractional scale
    cr.set_source_rgba(*rgb(p.line, 0.55))
    cr.fill()

    pad = 10.0
    inner = width - 2 * pad
    y = 12.0

    # header: mascot · session over 'host · N tabs' ----------------------------------------------------------------------
    pt.card(pad, y, 30, 30, 9, p.card, lift=0.5)          # a neutral tile: the accent marks only where you are
    pt.icon("kittymux", pad + 6, y + 6, 18, p.text)
    tx = pad + 40
    pt.text(tx, y + 9, model.session, 14, p.text, weight=Pango.Weight.SEMIBOLD, family=DISPLAY_FONT, width=inner - 40 - 26)
    pt.text(tx, y + 23, f"{model.host} · {len(model.agents)} agents", 11, p.muted, width=inner - 40 - 26)
    # search glyph
    sx, sy = width - pad - 9, y + 15
    cr.set_line_width(1.4 * scale)
    cr.set_source_rgba(*rgb(p.muted))
    cr.new_path()
    cr.arc((sx - 1.5) * scale, (sy - 1.5) * scale, 4.2 * scale, 0, 2 * math.pi)
    cr.stroke()
    cr.move_to((sx + 1.6) * scale, (sy + 1.6) * scale)
    cr.line_to((sx + 4.6) * scale, (sy + 4.6) * scale)
    cr.stroke()
    if hits is not None:
        hits.append(("search", 0, width - pad - 22, 12, 22, 30))
    y += 44

    items = body_items(model)
    content = content_height(model)
    view_h = max(0.0, height - HEADER_END)
    scroll = clamp_scroll(frame.scroll, content, view_h)
    if metrics is not None:
        metrics["content"] = content
        metrics["scroll"] = scroll
        metrics["view_h"] = view_h

    def hit(kind, index, hx, hy, hw, hh):
        if hits is None or hw <= 0 or hh <= 0:
            return
        y0, y1 = max(hy, HEADER_END), min(hy + hh, height)
        if y1 - y0 >= 1:
            hits.append((kind, index, hx, y0, hw, y1 - y0))

    cr.save()
    cr.rectangle(0, HEADER_END * scale, W, max(1.0, (height - HEADER_END) * scale))
    cr.clip()
    for kind, index, y0, h, payload in items:
        y = HEADER_END + y0 - scroll
        if y + h < HEADER_END or y > height:
            continue
        if kind == "label":
            role, text, plus = payload
            size = 11 if role == "section" else 10.5
            weight = Pango.Weight.SEMIBOLD if role == "section" else Pango.Weight.MEDIUM
            pt.text(pad + 4, y + 8, text, size, p.muted if role == "section" else p.faint, weight=weight,
                    track=0.2 if role == "section" else 0)
            if plus:
                pt.text(width - pad - 12, y + 8, "+", 14, p.faint)
        elif kind == "rule":
            cr.rectangle((pad + 4) * scale, y * scale, (inner - 8) * scale, max(1, scale * 0.75))
            cr.set_source_rgba(*rgb(p.line, 0.5))
            cr.fill()
        elif kind == "empty":
            pt.text(pad + 8, y + 16, model.empty or "No tabs yet", 13, p.text, weight=Pango.Weight.SEMIBOLD, width=inner - 16)
            if model.empty_hint:
                pt.text(pad + 8, y + 36, model.empty_hint, 11, p.muted, width=inner - 16)
        elif kind == "space":
            sp = payload
            hit("space", index, pad, y, inner, h)
            if sp.active:
                pt.card(pad, y, inner, h, 9, p.card_hi, lift=frame.reveal)
            if sp.current:
                pt.fill_rrect(pad + 2, y + 8, 3, h - 16, 1.5, p.accent)
            hue = th.project_hue(sp.name, p.accent, bar, 3.0, avoid=(p.waiting, p.alert, p.done))
            pt.card(pad + 7, y + 7, 18, 18, 5.5, hue, lift=0.6)
            ink = max((0x111111, 0xFFFFFF), key=lambda c: th.contrast(c, hue))
            lw = pt.text_w(sp.name[:1].upper(), 10.5, weight=Pango.Weight.BOLD, family=ROUNDED_FONT)
            pt.text(pad + 16 - lw / 2, y + 16, sp.name[:1].upper(), 10.5, ink, weight=Pango.Weight.BOLD, family=ROUNDED_FONT)
            right = pad + inner - 8
            right -= status_mark(pt, right, y + 16, sp.state, frame.phase, p.card_hi if sp.active else bar) + 6
            bw = 0
            if sp.branch and inner > 200:
                bw = min(pt.text_w(sp.branch, 11, family=UI_FONT), 70)
                pt.text(right - bw, y + 16, sp.branch, 11, p.faint, width=70)
                bw += 8
            pt.text(pad + 34, y + 16, sp.name, 13, p.text,
                    weight=Pango.Weight.MEDIUM if sp.active else Pango.Weight.NORMAL, width=right - bw - pad - 34)
        elif kind == "agent":
            _paint_row(pt, p, bar, frame, pad, inner, y, h, payload, index, False, hit)
        elif kind == "pane":
            _paint_row(pt, p, bar, frame, pad, inner, y, h, payload, index, True, hit)
    cr.restore()
    surf.flush()
    return surf


def _paint_row(pt, p, bar, frame, pad, inner, y, h, ag, index, pane, hit):
    """One agent or child-pane row. `index` is the agent index or the flat pane index."""
    hovered = (frame.hover_pane == index) if pane else (frame.hover == index)
    # one meaning per colour: the selection (active or keyboard) is a raised neutral card, the accent only marks the
    # tab you are in; a hover is a flatter fill, so the two never read alike
    if ag.active or ag.selected:
        pt.card(pad, y, inner, h, 8, p.card_hi, lift=frame.reveal)
    elif hovered:
        pt.fill_rrect(pad, y, inner, h, 8, p.card if pt.dark else th.blend(p.fg, bar, 0.05))
    if ag.current:
        pt.fill_rrect(pad + 2, y + 6, 3, h - 12, 1.5, p.accent)
    inset = 14 if (not pane and ag.can_open) else (12 if pane else 0)
    # the row rect goes in first; the chevron, appended after, wins the overlap
    hit("pane" if pane else "agent", index, pad, y, inner, h)
    if not pane and ag.can_open:
        pt.text(pad + 5, y + h / 2, "▾" if ag.opened else "▸", 11, p.text if ag.active else p.muted, weight=Pango.Weight.MEDIUM)
        hit("toggle", index, pad, y, 16, h)
    icon_x = pad + 8 + inset
    icon = ICON_FILE.get(ag.agent, ag.agent)
    brand = ag.brand or p.muted
    if not (icon and pt.icon(icon, icon_x, y + (h - 14) / 2, 14, th.ensure_contrast(brand, bar, 3.0))):
        pt.fill_rrect(icon_x, y + (h - 14) / 2, 14, 14, 4, p.track)
        pt.text(icon_x + 2.5, y + h / 2, ">_", 8, p.muted, family="SF Mono", weight=Pango.Weight.BOLD)
    cy = y + h / 2
    right = pad + inner - 8
    right -= status_mark(pt, right, cy, ag.state, frame.phase, p.card_hi if ag.active else bar) + 6
    aw = 0
    if ag.age and not (ag.state == "waiting" and inner < 200):
        aw = pt.text_w(ag.age, 11, tnum=True)
        pt.text(right - aw, cy, ag.age, 11, p.faint, tnum=True)
        aw += 8
    col = p.text if ag.state != "idle" or ag.active or ag.selected else p.muted
    title_x = pad + 30 + inset
    pt.text(title_x, cy, ag.title, 12.5 if not pane else 12, col,
            weight=Pango.Weight.MEDIUM if ag.active or ag.selected else Pango.Weight.NORMAL, width=max(1, right - aw - title_x))
    if ag.progress:
        tx0, tw = title_x, max(2, right - aw - title_x)
        pt.fill_rrect(tx0, y + h - 4, tw, 2, 1, p.track)
        pt.fill_rrect(tx0, y + h - 4, max(2, tw * ag.progress), 2, 1, _progress_color(p, ag.progress_state))

