# kittymux deckpx — the sidebar drawn in pixels (cairo + pango + rsvg) for kitty's graphics protocol.
# Pure: no kitty imports. Colours come from a kittymux_theme.Palette (kitty's live colours), never a fixed palette.
# The panel's Agents view uses it when the `deckpx` switch is on (kittymux_deckadapt maps the snapshot). The demo kitten still runs alone.
#
# The look (wave 3, matched to the desktop shell):
#   * identity first, then state: every tab is a capsule whose left end is the agent's mark inside a ring; the ring and
#     one short word ("Working", "Needs you", "Finished", "Error", "Limited") carry the state;
#   * colour only for state: marks are monochrome, spaces have no hue tiles, and the accent appears once, as the hairline
#     around the tab you are in. Selection and hover are lighter surfaces, never a colour;
#   * one hierarchy, Machine → Space → Agents: the header names the session and the machine, each space (a session:
#     repo + branch) heads its own tabs with a rolled-up count in a ring;
#   * calm: nothing moves at rest. A working ring steps a quarter turn every STEP_MS (kitty plays the frames; this module
#     only draws them), and state changes cross-fade (`crossfade`) for about 150 ms;
#   * near-black glass, 1 px hairlines, depth from lighter surfaces and no shadows or gradients.

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

import kittymux_agents  # noqa: E402
import kittymux_place  # noqa: E402   (program text is cleaned before it is drawn)
import kittymux_theme as th  # noqa: E402

ICONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icons")

UI_FONT = "SF Pro Text"
DISPLAY_FONT = "SF Pro Display"
MONO_FONT = "SF Mono"

# White at .96 / .72 / .50 over the bar: hierarchy from weight and tone before size.
TONE_HI, TONE_MID, TONE_LO = 0.96, 0.72, 0.50

# The working ring steps (never spins): STEP_FRAMES positions, one every STEP_MS. Kitty plays them; at rest nothing runs.
STEP_FRAMES = 4
STEP_MS = 3000
# A state change cross-fades in about this long (sidebar-kit draws FADE_STEPS intermediate frames).
FADE_MS = 150
ACCENT_HAIRLINE = 0.45     # the current tab's accent hairline, dimmed so the state colours lead (orange, green, red)
FADE_STEPS = 2

# The fixed type scale (px at scale 1).
T_SMALL, T_META, T_LABEL, T_BODY, T_TITLE = 10, 11, 12, 13, 15

STATE_WORD = kittymux_agents.STATE_WORDS


@dataclass
class Space:
    name: str
    branch: str = ""
    state: str = ""          # waiting | working | done | idle | limited | error | ""
    active: bool = False     # the session that holds the keyboard selection
    current: bool = False    # the session you are in
    counts: dict = field(default_factory=dict)   # state → number of tabs in it (the roll-up ring)


@dataclass
class Agent:
    title: str
    agent: str               # key into kittymux_agents.AGENTS / assets/icons
    brand: int
    space: str
    age: str = ""
    state: str = "idle"      # working | waiting | done | idle | limited | error
    progress: float | None = None   # OSC 9;4, 0..1 (0 and None draw nothing)
    active: bool = False     # the demo's selection, and the panel's keyboard row
    current: bool = False    # the tab you are looking at: the accent hairline, distinct from the selection
    selected: bool = False   # keyboard selection: a lighter surface, distinct from hover
    progress_state: str = "" # set | paused | error | indeterminate
    can_open: bool = False   # a split tab: a chevron, never opened by hover
    opened: bool = False
    row: int = -1            # flat snapshot row, for hit testing
    pane: int = -1           # child pane index, or -1 for the tab row
    children: list = field(default_factory=list)
    meta: str = ""           # quiet facts after the state word: "#123", ":3000"
    panes: int = 1
    muted: bool = False      # `kittymux mute`: a bell-slash, the state word quiet, never "needs you"


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
    phase: float = 0.0            # 0..1: where a still working ring points (kitty steps it when motion is on)
    reveal: float = 1.0           # kept for callers; the flat surfaces do not use it
    scroll: float = 0.0           # logical px into the body under the header
    hover_pane: int | None = None # flat index of the hovered child pane
    hot_key: int | None = None    # index of the key hint under the pointer (len(keys) is `?`)


# The header occupies this many logical px. Everything under it scrolls.
HEADER_END = 60.0
# The key hints along the bottom (when `render` gets `keys`): the panel's own type, never cell keycaps.
FOOTER_H = 30.0


def body_bottom(height: float, keys) -> float:
    """Where the scrolling list ends: the bottom edge, or the top of the key hints."""
    return height - FOOTER_H if keys else height

# Body geometry (logical px).
SPACE_H, AGENT_H, PANE_H, GAP = 30.0, 44.0, 30.0, 4.0
RING_R, MARK = 13.0, 15.0              # the ring around a tab's mark, and the mark inside it
PANE_RING_R, PANE_MARK = 9.0, 11.0



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


def tone(pal: th.Palette, level: float) -> int:
    """The text colour at a level over the bar: TONE_HI, TONE_MID or TONE_LO."""
    return th.blend(pal.text, pal.bar, level)


def step_phase(phase: float) -> float:
    """A phase snapped to one of the STEP_FRAMES positions: the ring points one of four ways, never in between."""
    try:
        phase = float(phase)
    except (TypeError, ValueError):
        phase = 0.0
    if not math.isfinite(phase):
        phase = 0.0
    return (math.floor((phase % 1.0) * STEP_FRAMES) % STEP_FRAMES) / STEP_FRAMES


def state_counts(states) -> dict:
    """state → count, for the states a roll-up ring reports."""
    out: dict = {}
    for s in states:
        if s in ("working", "waiting", "done", "error", "limited"):
            out[s] = out.get(s, 0) + 1
    return out


def rollup(counts: dict) -> tuple[str, int]:
    """(state, n) a space's ring shows, in the one shared order (kittymux_state.PRIORITY: a limit, then a question, then
    failures, work, finished) — the same order that picks the space's colour, so the count and the colour never disagree."""
    import kittymux_state
    for s in sorted(("waiting", "limited", "error", "working", "done"), key=lambda k: -kittymux_state.PRIORITY.get(k, 0)):
        if counts.get(s):
            return s, int(counts[s])
    return "", 0


def needs_you(model: Model) -> int:
    """Tabs and panes that ask for you (waiting or limited): the header chip's count."""
    n = 0
    for ag in model.agents:
        asks = ag.state in ("waiting", "limited") and not ag.muted
        if asks:
            n += 1
        n += sum(1 for ch in ag.children if ch.state in ("waiting", "limited") and not ch.muted and not asks)
    return n


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
    def layout(self, text, size, weight=Pango.Weight.NORMAL, family=UI_FONT, width=None, tnum=False, track=0.0, mid=False):
        key = (text, size, weight, family, width, tnum, track, mid, self.s)
        lo = self.resources.get(self.resources.layouts, key,
                                lambda: self._layout(text, size, weight, family, width, tnum, track, mid))
        PangoCairo.update_layout(self.cr, lo)
        return lo

    def _layout(self, text, size, weight, family, width, tnum, track, mid=False):
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
            lo.set_ellipsize(Pango.EllipsizeMode.MIDDLE if mid else Pango.EllipsizeMode.END)   # middle: a branch keeps its end
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

    # surfaces --------------------------------------------------------------------------------------------------------
    def veil(self, level: float) -> tuple[int, float]:
        """A lighter surface on a dark bar (white at `level`), a slightly darker one on a light bar."""
        return (0xFFFFFF, level) if self.dark else (0x000000, level * 0.75)

    def fill_rrect(self, x, y, w, h, r, color, alpha=1.0):
        s = self.s
        rrect(self.cr, x * s, y * s, w * s, h * s, r * s)
        self.cr.set_source_rgba(*rgb(color, alpha))
        self.cr.fill()

    def surface(self, x, y, w, h, r, level, rim=0.0, rim_color=None, rim_alpha=None):
        """A flat lifted surface: a veil fill and an optional 1 px hairline (white .08 by default, or a colour)."""
        c, a = self.veil(level)
        self.fill_rrect(x, y, w, h, r, c, a)
        if rim or rim_color is not None:
            if rim_color is None:
                rim_color, alpha = self.veil(rim)
            else:
                alpha = 1.0 if rim_alpha is None else rim_alpha
            self.stroke_rrect(x + .5, y + .5, w - 1, h - 1, r - .5, rim_color, alpha, width=1)

    def card(self, x, y, w, h, r, color, lift=1.0):
        """Kept for callers outside the deck: now a flat surface with a hairline, no shadow and no gradient."""
        self.fill_rrect(x, y, w, h, r, color)
        self.stroke_rrect(x + .5, y + .5, w - 1, h - 1, r - .5, *self.veil(0.08), width=1)

    def stroke_rrect(self, x, y, w, h, r, color, alpha=1.0, width=1.5):
        s = self.s
        rrect(self.cr, x * s, y * s, w * s, h * s, r * s)
        self.cr.set_source_rgba(*rgb(color, alpha))
        self.cr.set_line_width(width * s)
        self.cr.stroke()

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

    def circle(self, cx, cy, r, color, alpha=1.0, width=1.5, a0=0.0, sweep=2 * math.pi):
        s, cr = self.s, self.cr
        cr.new_path()
        cr.arc(cx * s, cy * s, r * s, a0, a0 + sweep)
        cr.set_source_rgba(*rgb(color, alpha))
        cr.set_line_width(width * s)
        cr.set_line_cap(cairo.LINE_CAP_ROUND if sweep < 2 * math.pi else cairo.LINE_CAP_BUTT)
        cr.stroke()
        cr.set_line_cap(cairo.LINE_CAP_BUTT)

    def check(self, cx, cy, size, color, width=1.6):
        """A check mark centred on (cx, cy)."""
        s, cr = self.s, self.cr
        cr.new_path()
        cr.move_to((cx - size * .45) * s, (cy + size * .02) * s)
        cr.line_to((cx - size * .12) * s, (cy + size * .32) * s)
        cr.line_to((cx + size * .48) * s, (cy - size * .34) * s)
        cr.set_source_rgba(*rgb(color))
        cr.set_line_width(width * s)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.stroke()
        cr.set_line_cap(cairo.LINE_CAP_BUTT)

    def spinner(self, cx, cy, r, color, phase):
        """The working arc. With a `spinners` list the base image leaves it out and kitty places the stepped frames
        (`ring_frames`) on top; without one it is drawn still, pointing where `phase` says (snapped to a step)."""
        lo, hi = self.spin_clip
        if lo is not None and not (lo <= cy <= hi):
            return
        if lo is not None and not (lo <= cy - r - 1 and cy + r + 1 <= hi):
            self.arc(cx, cy, r, color, phase)        # cut by the header or the key hints: a still arc in the (clipped) base, never an
            return                                   # animated one placed over them
        if self.spinners is not None and abs(r - RING_R) < 0.01:
            self.spinners.append((cx, cy, r, color))
            return
        self.arc(cx, cy, r, color, phase)            # kitty steps one frame set, made at the tab's radius: a pane's smaller ring stays still

    def arc(self, cx, cy, r, color, phase, width=2.0):
        a0 = step_phase(phase) * 2 * math.pi - math.pi / 2
        self.circle(cx, cy, r, color, 1.0, width, a0, math.pi * 0.55)

    def pill(self, right, cy, label, color, bar, size=T_META):
        """A state chip ending at `right`: the colour at .16 behind the word in the colour. Returns its width."""
        w = self.text_w(label, size, weight=Pango.Weight.SEMIBOLD, tnum=True) + 14
        h = 20
        bg = th.blend(color, bar, 0.18 if self.dark else 0.14)
        self.fill_rrect(right - w, cy - h / 2, w, h, h / 2, bg)
        self.text(right - w + 7, cy, label, size, th.ensure_contrast(color, bg, 4.5), weight=Pango.Weight.SEMIBOLD, tnum=True)
        return w


def state_color(p: th.Palette, state: str) -> int | None:
    return {"working": p.working, "waiting": p.waiting, "done": p.done, "error": p.alert, "limited": p.alert}.get(state)


def ring(pt: Painter, cx, cy, r, state, phase, bar, width=2.0, track=True):
    """The state ring around a mark: a hairline track, then the state on it. Working is a stepped arc; needs you,
    error and limited close the ring; finished keeps the track and adds a check badge. Idle is the track alone."""
    p = pt.p
    if track:
        c, a = pt.veil(0.14)
        pt.circle(cx, cy, r, c, a, 1.0)
    col = state_color(p, state)
    if col is None:
        return
    col = th.ensure_contrast(col, bar, 3.0)
    if state == "working":
        pt.circle(cx, cy, r, col, 0.22, width)
        pt.spinner(cx, cy, r, col, phase)
    elif state in ("waiting", "error", "limited"):
        pt.circle(cx, cy, r, col, 1.0, width)
    elif state == "done":
        br = max(4.5, r * 0.42)
        bx, by = cx + r * 0.72, cy + r * 0.72
        pt.dot(bx, by, br + 1.5, bar)                # a cut-out, so the badge sits on the ring and not in it
        pt.dot(bx, by, br, col)
        ink = max((0x111111, 0xFFFFFF), key=lambda c: th.contrast(c, col))
        pt.check(bx, by, br * 1.15, ink, width=1.3)


def ring_frames(pal: th.Palette, scale: float = 1.0, r: float = RING_R, width: float = 2.0):
    """(device size, [surfaces]): the working arc at each of STEP_FRAMES positions, on transparency, for kitty to step
    through every STEP_MS. Only the arc: the faint full ring under it is in the base image."""
    size = int(math.ceil((2 * r + width + 2) * scale))
    out = []
    for i in range(STEP_FRAMES):
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        pt = Painter(cairo.Context(surf), scale, pal)
        col = th.ensure_contrast(pal.working, pal.bar, 3.0)
        pt.arc(size / scale / 2, size / scale / 2, r, col, i / STEP_FRAMES, width)
        surf.flush()
        out.append(surf)
    return size, out


def crossfade(old, new, t: float):
    """`old` faded into `new` at t (0..1), as a new surface of new's size. A state change is drawn through two of these
    (about FADE_MS in all) instead of snapping; a resize or scroll never fades."""
    t = max(0.0, min(1.0, float(t)))
    w, h = new.get_width(), new.get_height()
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(out)
    if old is not None and old.get_width() == w and old.get_height() == h and t < 1:
        cr.set_source_surface(old, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        # SOURCE with an alpha mask interpolates the two images pixel by pixel (no double-counted translucency)
        cr.set_source_surface(new, 0, 0)
        cr.paint_with_alpha(t)
        # paint_with_alpha under SOURCE blends dest→source by t: exactly lerp(old, new, t)
    else:
        cr.set_source_surface(new, 0, 0)
        cr.paint()
    out.flush()
    return out


def status_mark(pt: Painter, right, cy, state, phase, bar):
    """A compact right-hand state mark ending at `right` (used where there is no room for a ring); returns its width."""
    p = pt.p
    if state == "waiting":
        return pt.pill(right, cy, "Needs you", p.waiting, bar)
    if state == "error":
        return pt.pill(right, cy, "Error", p.alert, bar)
    if state == "limited":
        return pt.pill(right, cy, "Limited", p.alert, bar)
    if state in ("working", "done"):
        ring(pt, right - 6, cy, 5, state, phase, bar, width=1.6)
        return 12
    pt.dot(right - 4, cy, 3.2, p.faint, ring=True)
    return 8


def body_items(model: Model) -> list:
    """Rows under the header, in content px: (kind, index, y, h, payload). One hierarchy: each space heads its own
    tabs (Machine → Space → Agents), and a split tab's open panes follow it. The renderer draws these and nothing else
    moves them."""
    y = 6.0
    out = []
    if not model.agents:
        out.append(("empty", 0, y, 52, None))
        return out
    by_space: dict = {}
    for i, ag in enumerate(model.agents):
        by_space.setdefault(ag.space, []).append(i)
    order = [(si, sp) for si, sp in enumerate(model.spaces) if sp.name in by_space]
    known = {sp.name for _si, sp in order}
    flat_of = {}
    flat = 0
    for i, ag in enumerate(model.agents):
        flat_of[i] = flat
        flat += len(ag.children)

    def tabs(indices):
        nonlocal y
        for i in indices:
            ag = model.agents[i]
            out.append(("agent", i, y, AGENT_H, ag))
            y += AGENT_H + GAP
            for k, ch in enumerate(ag.children):
                out.append(("pane", flat_of[i] + k, y, PANE_H, ch))
                y += PANE_H + 2
            if ag.children:
                y += GAP

    first = True
    for si, sp in order:
        if not first:
            y += 10
        first = False
        out.append(("space", si, y, SPACE_H, sp))
        y += SPACE_H + 2
        tabs(by_space[sp.name])
    loose = [i for i, ag in enumerate(model.agents) if ag.space not in known]
    if loose:
        if not first:
            y += 10
        tabs(loose)
    return out


def content_height(model: Model) -> float:
    items = body_items(model)
    if not items:
        return 0.0
    last = items[-1]
    return last[2] + last[3] + 10


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


def _search_glyph(pt: Painter, sx, sy, color):
    s, cr = pt.s, pt.cr
    cr.set_line_width(1.4 * s)
    cr.set_source_rgba(*rgb(color))
    cr.new_path()
    cr.arc((sx - 1.5) * s, (sy - 1.5) * s, 4.2 * s, 0, 2 * math.pi)
    cr.stroke()
    cr.move_to((sx + 1.6) * s, (sy + 1.6) * s)
    cr.line_to((sx + 4.6) * s, (sy + 4.6) * s)
    cr.stroke()


def render(model: Model, pal: th.Palette, width: float, height: float, scale: float = 1.0, frame: Frame | None = None,
           glass: float = 0.84, hits: list | None = None, resources: Resources | None = None,
           spinners: list | None = None, metrics: dict | None = None, keys: list | None = None) -> cairo.ImageSurface:
    """Draw the deck. width/height are logical px; the surface is width*scale × height*scale device px.
    `glass` < 1 leaves the bar translucent so the compositor's blur shows through (kitty background_opacity).
    `hits`, when given, collects (kind, index, x, y, w, h) in logical px for the window's own mouse hit-testing.
    `spinners`, when given, collects (cx, cy, r, colour) for each working ring kitty should step; the base then leaves
    the moving arc out. The header stays put; spaces and agents scroll by `frame.scroll`. `keys`, [(key, label)], draws the
    key hints along the bottom (hits ("key", i), and `?` as ("key", len(keys))); the list then ends above them."""
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
    bottom = body_bottom(height, keys)
    pt.spin_clip = (HEADER_END, bottom)
    p = pal
    bar = p.bar
    hi, mid, lo = tone(p, TONE_HI), tone(p, TONE_MID), tone(p, TONE_LO)

    # the glass sheet: one flat tone (no gradient) and a 1 px hairline on the edge that meets the panes ---------------------
    cr.rectangle(0, 0, W, H)
    cr.set_source_rgba(*rgb(bar, glass))
    cr.fill()
    cr.rectangle(W - 1, 0, 1, H)       # one device pixel, also at fractional scale
    cr.set_source_rgba(*rgb(*pt.veil(0.10)))
    cr.fill()

    pad = 10.0
    inner = width - 2 * pad

    # header, two lines: session over machine · count; the Needs-you chip; search -------------------------------------
    tile = 30.0
    ty = 13.0
    pt.surface(pad, ty, tile, tile, 9, 0.06, rim=0.08)            # a neutral tile: the accent marks only where you are
    pt.icon("kittymux", pad + 7, ty + 7, tile - 14, mid)
    tx = pad + tile + 10
    right = width - pad
    sx, sy = right - 8, ty + 8
    _search_glyph(pt, sx, sy, lo)
    if hits is not None:
        hits.append(("search", 0, right - 22, 6, 24, 26))
    asks = needs_you(model)
    chip_w = 0.0
    if asks:
        label = f"{asks} need{'s' if asks == 1 else ''} you" if inner >= 220 else str(asks)
        chip_w = pt.pill(right, ty + 24, label, p.waiting, bar, size=T_META)
        if hits is not None:
            hits.append(("needs", 0, right - chip_w, ty + 14, chip_w, 20))
    pt.text(tx, ty + 7, model.session, T_TITLE, hi, weight=Pango.Weight.SEMIBOLD, family=DISPLAY_FONT,
            width=right - 26 - tx)
    n = len(model.agents)
    tabs = f"{n} tab{'' if n == 1 else 's'}"
    sub = tabs if model.session == model.host else f"{model.host} · {tabs}"     # an unnamed session is the machine: say it once
    pt.text(tx, ty + 24, sub, T_META, lo, tnum=True, width=max(1, right - chip_w - 8 - tx))
    # a hairline under the header: the body scrolls beneath it
    cr.rectangle(0, (HEADER_END - 1) * scale, W, max(1.0, scale * 0.75))
    cr.set_source_rgba(*rgb(*pt.veil(0.07)))
    cr.fill()

    items = body_items(model)
    content = content_height(model)
    view_h = max(0.0, bottom - HEADER_END)
    scroll = clamp_scroll(frame.scroll, content, view_h)
    if metrics is not None:
        metrics["content"] = content
        metrics["scroll"] = scroll
        metrics["view_h"] = view_h

    def hit(kind, index, hx, hy, hw, hh):
        if hits is None or hw <= 0 or hh <= 0:
            return
        y0, y1 = max(hy, HEADER_END), min(hy + hh, bottom)
        if y1 - y0 >= 1:
            hits.append((kind, index, hx, y0, hw, y1 - y0))

    cr.save()
    cr.rectangle(0, HEADER_END * scale, W, max(1.0, (bottom - HEADER_END) * scale))
    cr.clip()
    for kind, index, y0, h, payload in items:
        y = HEADER_END + y0 - scroll
        if y + h < HEADER_END or y > bottom:
            continue
        if kind == "empty":
            pt.text(pad + 8, y + 16, model.empty or "No tabs yet", T_BODY, hi, weight=Pango.Weight.SEMIBOLD, width=inner - 16)
            if model.empty_hint:
                pt.text(pad + 8, y + 36, model.empty_hint, T_META, lo, width=inner - 16)
        elif kind == "space":
            _paint_space(pt, p, bar, frame, pad, inner, y, h, payload, index, hit, (hi, mid, lo))
        elif kind == "agent":
            _paint_tab(pt, p, bar, frame, pad, inner, y, h, payload, index, hit, (hi, mid, lo))
        elif kind == "pane":
            _paint_pane(pt, p, bar, frame, pad, inner, y, h, payload, index, hit, (hi, mid, lo))
    cr.restore()
    if keys:
        _paint_keys(pt, p, keys, frame.hot_key, pad, width, bottom, hits, (hi, mid, lo))
    surf.flush()
    return surf


def _paint_keys(pt, p, keys, hot, pad, width, top, hits, tones):
    """The key hints: a hairline, then `key label` pairs in the panel's type (the key a step brighter), most important
    first, dropped from the right when the panel is narrow; `?` keeps the right edge. The hint under the pointer gets a
    lighter surface, the same as a hovered row: it is a button before it is pressed."""
    hi, mid, lo = tones
    cr, s = pt.cr, pt.s
    cr.rectangle(0, top * s, int(round(width * s)), max(1.0, s * 0.75))
    cr.set_source_rgba(*rgb(*pt.veil(0.07)))
    cr.fill()
    cy = top + FOOTER_H / 2
    h = 20.0
    help_w = 22.0
    right = width - pad - help_w - 4

    def button(i, x, w):
        if hot == i:
            pt.surface(x, cy - h / 2, w, h, h / 2, 0.06)
        if hits is not None:
            hits.append(("key", i, x, top + 1, w, FOOTER_H - 1))

    x = pad - 2
    for i, (key, label) in enumerate(keys):
        kw = pt.text_w(key, T_META, weight=Pango.Weight.SEMIBOLD, family=MONO_FONT)
        lw = pt.text_w(label, T_META)
        w = 8 + kw + 5 + lw + 8
        if x + w > right:
            break
        button(i, x, w)
        pt.text(x + 8, cy, key, T_META, hi if hot == i else mid, weight=Pango.Weight.SEMIBOLD, family=MONO_FONT)
        pt.text(x + 8 + kw + 5, cy, label, T_META, mid if hot == i else lo)
        x += w + 2
    hx = width - pad - help_w
    button(len(keys), hx, help_w)
    qw = pt.text_w("?", T_META, weight=Pango.Weight.SEMIBOLD)
    pt.text(hx + (help_w - qw) / 2, cy, "?", T_META, hi if hot == len(keys) else lo, weight=Pango.Weight.SEMIBOLD)


def _paint_space(pt, p, bar, frame, pad, inner, y, h, sp, index, hit, tones):
    """A space heads its tabs: the name, '⑂ branch', and on the right its loudest state as a count in a ring."""
    hi, mid, lo = tones
    hit("space", index, pad, y, inner, h)
    cy = y + h / 2 + 2
    right = pad + inner - 6
    counts = sp.counts or ({sp.state: 1} if sp.state and sp.state != "idle" else {})
    state, n = rollup(counts)
    if state:
        r = 8.0
        cx = right - r
        col = th.ensure_contrast(state_color(p, state), bar, 3.0)
        if state == "done":
            pt.circle(cx, cy, r, col, 1.0, 1.4)
            pt.check(cx, cy, 7, col, width=1.4)
        else:
            pt.circle(cx, cy, r, col, 1.0 if state != "working" else 0.9, 1.4)
            label = str(n) if n < 100 else "99"
            lw = pt.text_w(label, T_SMALL, weight=Pango.Weight.SEMIBOLD, tnum=True)
            pt.text(cx - lw / 2, cy, label, T_SMALL, col, weight=Pango.Weight.SEMIBOLD, tnum=True)
        right = cx - r - 8
    x = pad + 6
    name_col = hi if sp.current else mid
    branch = sp.branch
    bw = 0.0
    if branch:
        bw = min(pt.text_w("⑂ " + branch, T_META), max(0.0, (right - x) * 0.45))
    nw = pt.text(x, cy, sp.name, T_LABEL, name_col, weight=Pango.Weight.SEMIBOLD, width=max(1, right - x - (bw + 8 if bw else 0)))
    if branch and bw > 12:
        pt.text(x + nw + 8, cy, "⑂ " + branch, T_META, lo, width=bw)


def _row_surface(pt, p, x, y, w, h, *, current, selected, hovered):
    """Where you are: the accent hairline (the one accent on the panel). The keyboard row: a lighter surface. A hover:
    a fainter one. Nothing else gets a fill."""
    r = h / 2
    if selected or current:
        pt.surface(x, y, w, h, r, 0.075 if selected else 0.05)
    elif hovered:
        pt.surface(x, y, w, h, r, 0.04)
    if current:
        pt.stroke_rrect(x + .5, y + .5, w - 1, h - 1, r - .5, p.accent, ACCENT_HAIRLINE, width=1)
    elif selected:
        pt.stroke_rrect(x + .5, y + .5, w - 1, h - 1, r - .5, *pt.veil(0.10), width=1)


def _mark(pt, p, ag, cx, cy, size, color):
    icon = kittymux_agents.brand_of(ag.agent) or None      # the one agent → mark table (cursor-agent, agy, droid, vibe too)
    if icon and pt.icon(icon, cx - size / 2, cy - size / 2, size, color):
        return
    pt.text(cx - pt.text_w(">_", size * 0.62, family=MONO_FONT, weight=Pango.Weight.BOLD) / 2, cy, ">_", size * 0.62,
            color, family=MONO_FONT, weight=Pango.Weight.BOLD)


def _second_line(p, ag, bar, lo):
    """[(text, colour, bold)] after the title: the state word, then age, progress and quiet facts."""
    is_agent = bool(ag.agent) and ag.agent != "shell"
    parts = []
    word = STATE_WORD.get(ag.state, "")
    col = state_color(p, ag.state)
    if not is_agent and ag.state == "idle":
        word, col = "Shell", None
    if ag.muted:
        col = None                       # muted: the state stays true, but it is not drawn in its colour (the bell-slash says why)
    if word:
        parts.append((word, th.ensure_contrast(col, bar, 4.5) if col is not None else lo, col is not None))
    if ag.progress:
        pct = f"{round(ag.progress * 100)}%"
        if ag.progress_state == "error":
            parts.append(("failed", th.ensure_contrast(p.alert, bar, 4.5), False))
        else:
            parts.append((pct, lo, False))
    if ag.meta:
        parts.append((ag.meta, lo, False))
    return parts


def _paint_tab(pt, p, bar, frame, pad, inner, y, h, ag, index, hit, tones):
    """A vertical pill tab: the mark in its state ring at the left cap, the title, then the state word on line two."""
    hi, mid, lo = tones
    hovered = frame.hover == index
    selected = ag.active or ag.selected
    _row_surface(pt, p, pad, y, inner, h, current=ag.current, selected=selected, hovered=hovered)
    hit("agent", index, pad, y, inner, h)
    cx, cy = pad + h / 2, y + h / 2
    ring(pt, cx, cy, RING_R, _ring_state(ag), frame.phase, bar)
    lit = selected or ag.current or ag.state not in ("idle", "")
    _mark(pt, p, ag, cx, cy, MARK, hi if lit else mid)
    tx = pad + h + 4
    right = pad + inner - 12
    # line one: title … age
    meta_right = right
    if ag.can_open:
        chev = "▾" if ag.opened else "▸"
        label = f"{ag.panes}" if ag.panes > 1 else ""
        cw = pt.text_w(label, T_META, tnum=True) + 14 if label else 12
        cxr = right - cw
        if label:
            pt.text(cxr, cy - 8, label, T_META, lo, tnum=True)
        pt.text(right - 9, cy - 8, chev, T_META, mid if selected else lo, weight=Pango.Weight.MEDIUM)
        hit("toggle", index, pad + inner - cw - 20, y, cw + 20, h)
        meta_right = cxr - 6
    if ag.muted:
        _bell_slash(pt, meta_right - 5, cy - 8, lo)
        meta_right -= 16
    aw = 0.0
    if ag.age:
        aw = pt.text_w(ag.age, T_META, tnum=True)
        pt.text(meta_right - aw, cy - 8, ag.age, T_META, lo, tnum=True)
        aw += 8
    pt.text(tx, cy - 8, kittymux_place.clean(ag.title), T_BODY, hi if lit else mid,
            weight=Pango.Weight.SEMIBOLD if selected or ag.current else Pango.Weight.MEDIUM,
            width=max(1, meta_right - aw - tx))
    # line two: state word · progress · facts
    x = tx
    for k, (text, col, bold) in enumerate(_second_line(p, ag, bar, lo)):
        if k:
            x += pt.text(x, cy + 9, " · ", T_META, lo)
        room = right - x
        if room < 14:
            break
        x += pt.text(x, cy + 9, text, T_META, col, weight=Pango.Weight.SEMIBOLD if bold else Pango.Weight.NORMAL,
                     tnum=True, width=room)
    if ag.progress and ag.progress_state != "error":
        # a hairline under the second line: the OSC 9;4 fraction, in the state's colour
        bw = max(2.0, right - tx)
        c, a = pt.veil(0.08)
        pt.fill_rrect(tx, y + h - 5, bw, 1.5, .75, c, a)
        pt.fill_rrect(tx, y + h - 5, max(2.0, bw * ag.progress), 1.5, .75, _progress_color(p, ag.progress_state))


def _ring_state(ag) -> str:
    """A muted agent that asks for you draws a neutral ring: orange means "needs you", and a muted one never does."""
    return "idle" if ag.muted and ag.state in ("waiting", "limited") else ag.state


def _bell_slash(pt, cx, cy, color):
    """A small bell with a slash through it, centred on (cx, cy): a muted agent. Drawn, so it needs no font."""
    s, cr = pt.s, pt.cr
    cr.new_path()
    cr.set_source_rgba(*rgb(color))
    cr.set_line_width(1.2 * s)
    cr.arc(cx * s, (cy - 0.5) * s, 3.2 * s, math.pi, 2 * math.pi)        # the dome
    cr.line_to((cx + 3.2) * s, (cy + 2.2) * s)
    cr.line_to((cx + 4.4) * s, (cy + 3.4) * s)                              # the flare
    cr.line_to((cx - 4.4) * s, (cy + 3.4) * s)
    cr.line_to((cx - 3.2) * s, (cy + 2.2) * s)
    cr.close_path()
    cr.stroke()
    cr.new_path()
    cr.arc(cx * s, (cy + 4.9) * s, 1.0 * s, 0, 2 * math.pi)                 # the clapper
    cr.fill()
    cr.new_path()
    cr.move_to((cx - 5.0) * s, (cy - 4.6) * s)                              # the slash
    cr.line_to((cx + 5.0) * s, (cy + 5.6) * s)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.stroke()
    cr.set_line_cap(cairo.LINE_CAP_BUTT)


def _paint_pane(pt, p, bar, frame, pad, inner, y, h, ch, index, hit, tones):
    """An open split's pane: indented under its tab's ring, a smaller ring and mark, the title, the state word right."""
    hi, mid, lo = tones
    hovered = frame.hover_pane == index
    selected = ch.active or ch.selected
    x0 = pad + AGENT_H / 2 - 2
    _row_surface(pt, p, x0, y, pad + inner - x0, h, current=False, selected=selected, hovered=hovered)
    hit("pane", index, x0, y, pad + inner - x0, h)
    # the guide: a hairline from the parent ring down the left of its panes
    c, a = pt.veil(0.10)
    pt.fill_rrect(pad + AGENT_H / 2 - 0.5, y - 2, 1, h + 4, 0.5, c, a)
    cx, cy = x0 + h / 2, y + h / 2
    ring(pt, cx, cy, PANE_RING_R, _ring_state(ch), frame.phase, bar, width=1.6)
    _mark(pt, p, ch, cx, cy, PANE_MARK, hi if selected or ch.state not in ("idle", "") else mid)
    right = pad + inner - 12
    word = STATE_WORD.get(ch.state, "") if ch.state != "idle" else ""
    ww = 0.0
    if ch.muted:
        _bell_slash(pt, right - 5, cy, lo)
        right -= 16
    if word:
        col = lo if ch.muted else th.ensure_contrast(state_color(p, ch.state), bar, 4.5)
        ww = pt.text_w(word, T_META, weight=Pango.Weight.SEMIBOLD)
        pt.text(right - ww, cy, word, T_META, col, weight=Pango.Weight.SEMIBOLD)
        ww += 8
    tx = x0 + h + 2
    pt.text(tx, cy, kittymux_place.clean(ch.title), T_LABEL, hi if selected else mid, weight=Pango.Weight.MEDIUM if selected else Pango.Weight.NORMAL,
            width=max(1, right - ww - tx))
