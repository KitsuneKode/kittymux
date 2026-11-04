# kittymux deckpx — SPIKE: the sidebar drawn in pixels (cairo + pango + rsvg) for kitty's graphics protocol.
# Pure: no kitty imports. Colours come from a kittymux_theme.Palette (kitty's live colours), never a fixed palette.
# Status: spike (docs/superpowers/specs/2026-11-04-deck-pixels-spike.md). Not wired into kitty yet.

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
    state: str = ""          # "waiting" | "working" | "done" | ""
    active: bool = False


@dataclass
class Agent:
    title: str
    agent: str               # key into kittymux_agents.AGENTS / assets/icons
    brand: int
    space: str
    age: str = ""
    state: str = "idle"      # working | waiting | done | idle
    progress: float | None = None   # OSC 9;4, 0..1
    active: bool = False


@dataclass
class Model:
    session: str
    host: str
    spaces: list[Space] = field(default_factory=list)
    agents: list[Agent] = field(default_factory=list)


@dataclass
class Frame:
    hover: int | None = None      # index of the hovered agent row (hover comes from the deck window's own mouse tracking)
    phase: float = 0.0            # 0..1 animation clock (spinner); a frame is drawn only while something moves
    reveal: float = 1.0           # 0..1 spring value for the active card (slides/settles on focus change)


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


def status_mark(pt: Painter, right, cy, state, phase, bar):
    """Draw the right-hand state mark ending at `right`; returns the width it took."""
    p = pt.p
    if state == "waiting":
        return pt.pill(right, cy, "Needs you", p.waiting, bar)
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


def render(model: Model, pal: th.Palette, width: float, height: float, scale: float = 1.0, frame: Frame | None = None,
           glass: float = 0.84, hits: list | None = None, resources: Resources | None = None,
           spinners: list | None = None) -> cairo.ImageSurface:
    """Draw the deck. width/height are logical px; the surface is width*scale × height*scale device px.
    `glass` < 1 leaves the bar translucent so the compositor's blur shows through (kitty background_opacity).
    `hits`, when given, collects (kind, index, x, y, w, h) in logical px for the window's own mouse hit-testing."""
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
    pt.fill_rrect(pad, y, 30, 30, 9, th.blend(p.accent, bar, 0.16))
    pt.icon("kittymux", pad + 6, y + 6, 18, p.accent)
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
    y += 44

    def section(label, y, plus=True):
        pt.text(pad + 4, y + 8, label, 11, p.muted, weight=Pango.Weight.SEMIBOLD, track=0.2)
        if plus:
            pt.text(width - pad - 12, y + 8, "+", 14, p.faint)
        return y + 20

    # spaces ------------------------------------------------------------------------------------------------------------
    y = section("Spaces", y)
    for si, sp in enumerate(model.spaces):
        h = 32
        if hits is not None:
            hits.append(("space", si, pad, y, inner, h))
        if sp.active:
            pt.card(pad, y, inner, h, 9, p.card_hi, lift=frame.reveal)
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
        y += h + 2
    y += 8
    cr.rectangle((pad + 4) * scale, y * scale, (inner - 8) * scale, max(1, scale * 0.75))
    cr.set_source_rgba(*rgb(p.line, 0.5))
    cr.fill()
    y += 10

    # agents, grouped by space -----------------------------------------------------------------------------------------
    y = section("Agents", y, plus=False)
    last = None
    for i, ag in enumerate(model.agents):
        if ag.space != last:
            if last is not None:
                y += 4
            pt.text(pad + 4, y + 8, ag.space, 10.5, p.faint, weight=Pango.Weight.MEDIUM)
            y += 18
            last = ag.space
        h = 30
        if hits is not None:
            hits.append(("agent", i, pad, y, inner, h))
        if ag.active:
            pt.card(pad, y, inner, h, 8, p.card_hi, lift=frame.reveal)
        elif frame.hover == i:
            pt.fill_rrect(pad, y, inner, h, 8, p.card if pt.dark else th.blend(p.fg, bar, 0.05))
        icon = ICON_FILE.get(ag.agent, ag.agent)
        if not (icon and pt.icon(icon, pad + 8, y + 8, 14, th.ensure_contrast(ag.brand, bar, 3.0))):
            pt.fill_rrect(pad + 8, y + 8, 14, 14, 4, p.track)
            pt.text(pad + 10.5, y + 15, ">_", 8, p.muted, family="SF Mono", weight=Pango.Weight.BOLD)
        right = pad + inner - 8
        right -= status_mark(pt, right, y + 15, ag.state, frame.phase, p.card_hi if ag.active else bar) + 6
        aw = 0
        if ag.age and not (ag.state == "waiting" and inner < 200):
            aw = pt.text_w(ag.age, 11, tnum=True)
            pt.text(right - aw, y + 15, ag.age, 11, p.faint, tnum=True)
            aw += 8
        col = p.text if ag.state != "idle" or ag.active else p.muted
        pt.text(pad + 30, y + 15, ag.title, 12.5, col,
                weight=Pango.Weight.MEDIUM if ag.active else Pango.Weight.NORMAL, width=right - aw - pad - 30)
        if ag.progress is not None:          # OSC 9;4: a hairline track under the title
            tx0, tw = pad + 30, right - aw - pad - 30
            pt.fill_rrect(tx0, y + h - 5, tw, 2, 1, p.track)
            pt.fill_rrect(tx0, y + h - 5, max(2, tw * ag.progress), 2, 1, p.working)
        y += h + 1
    surf.flush()
    return surf
