"""kittymux_ui — the shared look of every cell-drawn surface (pure: no kitty imports, unit-tested under system python).

A surface asks the `Kit` for components and gets back LINES of styled spans, each exactly the width it asked for. A renderer turns the spans into
escape sequences (`to_ansi`, or kitty's own `styled`). Nothing here knows a colour: every colour is a token of the live `Palette`
(kittymux_theme), so a theme change restyles every surface at once.

The look is built from glyphs kitty draws itself, pixel-exact, with no extra font:
  - cards: half blocks with quadrant corners (`▗▄▖` over `▝▀▘`), so a card starts and ends half a row off the line grid and its corners are chamfered;
  - gauges: lower-half blocks (`▄`), a thin bar sitting under its label;
  - pills (chips, tabs): Powerline round caps (`` ``, in the Symbols Nerd Font kitty bundles), or `▐ ▌` when `rounded=False`.

Shape rule: pills for chips / tabs / toggles, one chamfered radius for cards and buttons, square keycaps. One bright element per row.
Text that came from a program, a directory or a provider is `kittymux_place.clean`ed before it is drawn."""
from __future__ import annotations

import functools
from typing import Callable, NamedTuple

import kittymux_deck
import kittymux_place
import kittymux_theme as T

CAP_L, CAP_R = "", ""            # Powerline round caps
HALF_CAP_L, HALF_CAP_R = "▐", "▌"
LOWER, UPPER = "▄", "▀"
TOP_L, TOP_R, BOT_L, BOT_R = "▗", "▖", "▝", "▘"
EIGHTHS = " ▁▂▃▄▅▆▇█"                          # vertical eighths, bottom up
WIDE_GAUGE_LIMIT = 100                         # a gauge past this many cells is a bug in the caller, not a bar
RAMP_WARM, RAMP_HOT = 80.0, 100.0              # calm below 80 %, warm from 80 %, hot at 100 %


class S(NamedTuple):
    """One styled run: `fg` / `bg` are 0xRRGGBB (None = leave to the renderer), flags are plain bools."""
    text: str
    fg: int | None = None
    bg: int | None = None
    bold: bool = False
    dim: bool = False


Line = list


def plain(line: Line) -> str:
    return "".join(s.text for s in line)


def line_cells(line: Line, cells: Callable[[str], int] = len) -> int:
    return sum(cells(s.text) for s in line)


def to_ansi(line: Line) -> str:
    """Truecolor SGR for one line (what `styled` does in a kitten, for callers that are not in one)."""
    out = []
    for s in line:
        codes = []
        if s.bold:
            codes.append("1")
        if s.dim:
            codes.append("2")
        if s.fg is not None:
            codes.append(f"38;2;{s.fg >> 16 & 255};{s.fg >> 8 & 255};{s.fg & 255}")
        if s.bg is not None:
            codes.append(f"48;2;{s.bg >> 16 & 255};{s.bg >> 8 & 255};{s.bg & 255}")
        out.append((f"\x1b[{';'.join(codes)}m" if codes else "") + s.text + ("\x1b[0m" if codes else ""))
    return "".join(out)


@functools.lru_cache(maxsize=2048)
def _ink(color: int, on: int, minimum: float) -> int:
    return T.ensure_contrast(color, on, minimum)


def spark_level(value: float, peak: float, levels: int = 8) -> int:
    """0 for nothing, else 1..levels: a day with any use never rounds down to an empty column."""
    if not (isinstance(value, (int, float)) and not isinstance(value, bool)) or value != value or value <= 0 or peak <= 0:
        return 0
    return max(1, min(levels, round(value / peak * levels)))


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf") else None


class Kit:
    """The components, bound to one palette and one width function (`cells`: the renderer's wcswidth)."""

    def __init__(self, p: T.Palette, cells: Callable[[str], int] = len, rounded: bool = True):
        self.p, self.cells, self.rounded = p, cells, rounded

    # ── colour ───────────────────────────────────────────────────────────────
    def tone(self, name: str) -> int:
        p = self.p
        return {"calm": p.done, "warm": p.waiting, "hot": p.alert, "accent": p.accent, "text": p.text, "muted": p.muted,
                "faint": p.faint}.get(name, p.muted)

    def ramp(self, pct) -> str:
        v = _num(pct)
        return "muted" if v is None else "hot" if v >= RAMP_HOT else "warm" if v >= RAMP_WARM else "calm"

    def ink(self, color: int, on: int, minimum: float = 4.5) -> int:
        """`color` nudged until it reads on `on` (text is held to 4.5:1 wherever it sits)."""
        return _ink(color, on, minimum)

    # ── primitives ───────────────────────────────────────────────────────────
    def text(self, text, fg: int | None = None, bg: int | None = None, bold: bool = False, dim: bool = False) -> S:
        return S(kittymux_place.clean_line(str(text)), fg, bg, bold, dim)

    def blank(self, width: int, bg: int) -> Line:
        return [S(" " * width, None, bg)] if width > 0 else []

    def fit_line(self, spans: Line, width: int, bg: int) -> Line:
        """Exactly `width` cells: the line that does not fit is cut with an ellipsis, the line that is short is padded with `bg`."""
        if width <= 0:
            return []
        out, used = [], 0
        for s in spans:
            room = width - used
            if room <= 0:
                break
            w = self.cells(s.text)
            if w <= room:
                out.append(s)
                used += w
            else:
                out.append(s._replace(text=kittymux_deck.fit(s.text, room, self.cells)))
                used = width
                break
        if used < width:
            out.append(S(" " * (width - used), None, bg))
        return out

    def rule(self, width: int, on: int, tone: str = "faint") -> Line:
        return [S("─" * max(0, width), self.tone(tone), on)] if width > 0 else []

    # ── pills ────────────────────────────────────────────────────────────────
    def _caps(self):
        return (CAP_L, CAP_R) if self.rounded else (HALF_CAP_L, HALF_CAP_R)

    def chip_width(self, text: str) -> int:
        return self.cells(kittymux_place.clean(str(text))) + 4

    def chip(self, text, tone: str = "muted", on: int | None = None, strong: bool = False) -> Line:
        """` text ` on a tinted pill. A toned chip is the tone at 14 % over the surface; a neutral one is the hover layer."""
        p = self.p
        on = p.card if on is None else on
        color = self.tone(tone)
        bg = p.card_hi if tone in ("muted", "faint", "text") else T.blend(color, on, 0.14)
        if bg == on:
            bg = p.track
        fg = self.ink(color if tone not in ("muted", "faint") else p.muted, bg)
        left, right = self._caps()
        t = kittymux_place.clean(str(text))
        return [S(left, bg, on), S(f" {t} ", fg, bg, bold=strong), S(right, bg, on)]

    def button(self, label, key: str = "", primary: bool = False, on: int | None = None) -> Line:
        p = self.p
        on = p.card if on is None else on
        bg, fg = (p.accent, p.on_accent) if primary else (p.card_hi if p.card_hi != on else p.track, p.text)
        left, right = self._caps()
        body = [S(f" {kittymux_place.clean(str(label))} ", fg, bg, bold=primary)]
        if key:
            body.append(S(f"{kittymux_place.clean(str(key))} ", self.ink(fg, bg, 3.0), bg, dim=not primary))
        return [S(left, bg, on)] + body + [S(right, bg, on)]

    def tabs(self, items: list, width: int, on: int | None = None) -> Line:
        """items: [(icon, label, active, badge)]. The active pill shows its label on the accent; the others are an icon (and a count
        when something waits there), so three views cost one short row instead of a sentence."""
        p = self.p
        on = p.bar if on is None else on
        left, right = self._caps()
        out: Line = [S(left, p.card, on)]
        for icon, label, active, badge in items:
            n = int(badge) if _num(badge) else 0
            icon = kittymux_place.clean(str(icon))
            if active:
                body = f" {icon} {kittymux_place.clean(str(label))}" + (f" {min(n, 99)}" if n else "") + " "
                out += [S(left, p.accent, p.card), S(body, p.on_accent, p.accent, bold=True), S(right, p.accent, p.card)]
            else:
                out.append(S(f" {icon}", self.ink(p.muted, p.card), p.card))
                out.append(S(f"{min(n, 99)}" if n else "", self.ink(p.waiting, p.card), p.card, bold=True))
                out.append(S(" ", None, p.card))
        out.append(S(right, p.card, on))
        return self.fit_line(out, width, on)

    # ── gauges and charts ────────────────────────────────────────────────────
    def gauge(self, pct, width: int, on: int | None = None, tone: str | None = None, pace=None) -> Line:
        """A thin bar (lower-half blocks) `width` cells wide. `pace` (0..100) puts a tick where an even spend would be; the tick takes its cell
        whole, so the bar has a one-cell gap there: a marker, not a stripe. No `pct` draws a dotted groove (nothing to measure)."""
        p = self.p
        on = p.card if on is None else on
        width = max(0, min(int(width), WIDE_GAUGE_LIMIT))
        if width == 0:
            return []
        v = _num(pct)
        if v is None:
            return [S("╌" * width, p.faint, on)]
        v = max(0.0, min(100.0, v))
        fill = round(v / 100 * width)
        color = self.tone(tone or self.ramp(v))
        tick = None
        pv = _num(pace)
        if pv is not None:
            tick = min(width - 1, max(0, round(max(0.0, min(100.0, pv)) / 100 * width)))
            if tick == 0 and width > 1:
                tick = 1
        out: Line = []
        for i in range(width):
            if i == tick:
                out.append(S("▏", p.text, on))
            elif i < fill:
                out.append(S(LOWER, color, on))
            else:
                out.append(S(LOWER, p.track, on))
        return self._merge(out)

    def _merge(self, spans: Line) -> Line:
        """Adjacent runs with the same style become one run (a 25-cell gauge is three spans, not twenty-five)."""
        out: Line = []
        for s in spans:
            if out and out[-1][1:] == s[1:]:
                out[-1] = out[-1]._replace(text=out[-1].text + s.text)
            else:
                out.append(s)
        return out

    def spark(self, values: list, tone: str = "calm", on: int | None = None) -> Line:
        """One cell per value, eight heights. Nothing at all is a flat `▁`, never a gap (a week with no use is still a week)."""
        p = self.p
        on = p.card if on is None else on
        nums = [_num(v) or 0.0 for v in values]
        peak = max(nums, default=0.0)
        cells = "".join(EIGHTHS[max(1, spark_level(v, peak))] if peak > 0 else EIGHTHS[1] for v in nums)
        return [S(cells, self.tone(tone), on)] if cells else []

    def bars(self, values: list, width: int, rows: int = 2, tone: str = "accent", on: int | None = None,
             labels: str = "", highlight_last: bool = True) -> list:
        """Vertical bars, `rows` cells tall (8 levels per cell), `labels` one character per bar underneath. Returns `rows` lines + a label line."""
        p = self.p
        on = p.card if on is None else on
        nums = [_num(v) or 0.0 for v in values][:max(1, width)]
        n = len(nums)
        if n == 0 or width <= 0 or rows <= 0:
            return [self.blank(max(0, width), on) for _ in range(max(0, rows) + (1 if labels else 0))]
        peak = max(nums)
        bw = max(1, (width - (n - 1)) // n)
        used = n * bw + (n - 1)
        lead = max(0, (width - used) // 2)
        base = T.blend(self.tone(tone), p.track, 0.55)
        top = self.tone(tone)
        levels = [spark_level(v, peak, rows * 8) for v in nums]
        lines = []
        for r in range(rows):                                       # r = 0 is the top row
            floor = (rows - 1 - r) * 8
            row: Line = [S(" " * lead, None, on)]
            for i, lv in enumerate(levels):
                eighths = max(0, min(8, lv - floor))
                color = top if (highlight_last and i == n - 1) else base
                row.append(S(EIGHTHS[eighths] * bw if eighths else " " * bw, color, on))
                if i < n - 1:
                    row.append(S(" ", None, on))
            lines.append(self.fit_line(self._merge(row), width, on))
        if labels:
            row = [S(" " * lead, None, on)]
            for i in range(n):
                ch = labels[i] if i < len(labels) else " "
                strong = highlight_last and i == n - 1
                row.append(S(ch.center(bw), p.text if strong else p.faint, on))
                if i < n - 1:
                    row.append(S(" ", None, on))
            lines.append(self.fit_line(self._merge(row), width, on))
        return lines

    def heat(self, values: list, tone: str = "accent", on: int | None = None, cell: int = 2, gap: int = 1) -> Line:
        """One tinted block per value (use over a week), brighter for more. None = no data (the groove colour)."""
        p = self.p
        on = p.card if on is None else on
        nums = [_num(v) for v in values]
        known = [v for v in nums if v is not None and v > 0]
        peak = max(known, default=0.0)
        color = self.tone(tone)
        out: Line = []
        for i, v in enumerate(nums):
            if v is None or peak <= 0:
                bg = p.track
            else:
                bg = T.blend(color, p.track, 0.15 + 0.85 * max(0.0, min(1.0, v / peak))) if v > 0 else p.track
            out.append(S(" " * cell, None, bg))
            if i < len(nums) - 1 and gap:
                out.append(S(" " * gap, None, on))
        return out

    # ── layout ───────────────────────────────────────────────────────────────
    def kv(self, label, value, width: int, on: int | None = None, tone: str | None = None, value_bold: bool = False) -> Line:
        """label left (muted), value right: the label is never cut, the value is, with an ellipsis."""
        p = self.p
        on = p.card if on is None else on
        lab = kittymux_place.clean(str(label))
        val = kittymux_place.clean(str(value))
        lw = self.cells(lab)
        room = width - lw - 1
        if room < 1:
            return self.fit_line([S(lab, self.ink(p.muted, on), on)], width, on)
        if self.cells(val) > room:
            val = kittymux_deck.fit(val, room, self.cells)
        gap = width - lw - self.cells(val)
        color = self.ink(self.tone(tone) if tone else p.text, on)
        return [S(lab, self.ink(p.muted, on), on), S(" " * gap, None, on), S(val, color, on, bold=value_bold)]

    def keycaps(self, pairs: list, width: int, on: int | None = None) -> Line:
        """[(key, label)] as small keycaps with a muted label; whatever does not fit is dropped whole (never a half keycap)."""
        p = self.p
        on = p.bar if on is None else on
        out: Line = []
        used = 0
        for key, label in pairs:
            k = f" {kittymux_place.clean(str(key))} "
            lab = f" {kittymux_place.clean(str(label))}"
            need = self.cells(k) + self.cells(lab) + (2 if out else 0)
            if used + need > width:
                break
            if out:
                out.append(S("  ", None, on))
            out += [S(k, p.text, p.card_hi, bold=True), S(lab, self.ink(p.muted, on), on)]
            used += need
        return self.fit_line(out, width, on)

    def inner_width(self, width: int, margin: int = 1, padx: int = 1) -> int:
        return max(0, width - 2 * margin - 2 * padx)

    def card(self, rows: list, width: int, on: int | None = None, selected: bool = False, margin: int = 1, padx: int = 1,
             accent: bool = False) -> list:
        """Rows (lines already built on `p.card`, or `p.card_hi` when selected) become a card: half a row of padding above and below, quadrant
        corners, `padx` cells inside and `margin` cells of the surface around it. `accent` draws the top edge in the accent colour, the way a
        selected tile shows which one is picked."""
        p = self.p
        on = p.bar if on is None else on
        bg = p.card_hi if selected else p.card
        inner = self.inner_width(width, margin, padx)
        if inner < 3:
            return [self.blank(width, on) for _ in rows]
        edge_top = p.accent if accent else bg
        top = [S(" " * margin, None, on), S(TOP_L, edge_top, on), S(LOWER * (inner + 2 * padx - 2), edge_top, on), S(TOP_R, edge_top, on),
               S(" " * margin, None, on)]
        bottom = [S(" " * margin, None, on), S(BOT_L, bg, on), S(UPPER * (inner + 2 * padx - 2), bg, on), S(BOT_R, bg, on),
                  S(" " * margin, None, on)]
        out = [self.fit_line(top, width, on)]
        for r in rows:
            body = self.fit_line(r, inner, bg)
            out.append([S(" " * margin, None, on), S(" " * padx, None, bg)] + body + [S(" " * padx, None, bg), S(" " * margin, None, on)])
        out.append(self.fit_line(bottom, width, on))
        return out

    def monogram(self, letter: str, color: int, on: int | None = None) -> Line:
        """A provider's mark when its logo glyph is not available: a letter on a tint of the brand colour, 3 cells."""
        p = self.p
        on = p.card if on is None else on
        bg = T.blend(color, on, 0.2)
        ch = (kittymux_place.clean(str(letter)) or "?")[:1].upper()
        return [S(f" {ch} ", self.ink(color, bg), bg, bold=True)]
