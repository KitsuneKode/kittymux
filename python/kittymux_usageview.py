"""The panel's Usage view (pure): provider data in, styled lines and click regions out.

Layout, top to bottom: a summary line (how many providers, the one closest to a wall), a STRIP of provider tiles (monogram, the worst share or a
status dot, a thin gauge), ONE focus card for the picked provider (its meters drawn by kind: gauges with a pace tick and a countdown, a big
number with a week of bars, state chips), a 7-day heat strip when any provider has history, and one quiet footer line. Details are drawn for the
picked provider only, so the default view is mostly shapes, not sentences.

Everything is drawn by `kittymux_ui.Kit` from the live palette; every provider is drawn by `kittymux_meters`, so a provider this file has
never heard of still gets a card."""
from __future__ import annotations

import time
from datetime import datetime
from typing import NamedTuple

import kittymux_agents
import kittymux_meters as M
import kittymux_place
import kittymux_ui as U

DOTS = {"calm": "●", "warm": "◐", "hot": "⊘", "muted": "◌"}
STALE_S = 120.0
TILE_MIN = 8                                    # narrowest a tile can be and still show a monogram and two digits
STRIP_MAX_ROWS = 2


class View(NamedTuple):
    header: list           # one Line: the summary the panel draws above its tab strip
    lines: list            # list[Line], the body under the strip
    tiles: list            # [(x0, x1, y0, y1, provider_index)] in body coordinates (y counts lines of `lines`)
    sel: int               # the picked provider, clamped
    count: int             # providers drawn


def fmt_span(seconds) -> str:
    """3h 50m / 4d 19h / 9m / now."""
    s = M.num(seconds)
    if s is None:
        return ""
    m = int(s // 60)
    if m <= 0:
        return "now"
    d, rem = divmod(m, 1440)
    h, mm = divmod(rem, 60)
    return (f"{d}d {h}h" if h else f"{d}d") if d else (f"{h}h {mm}m" if mm else f"{h}h") if h else f"{m}m"


def fmt_amount(value, unit: str = "") -> str:
    v = M.num(value)
    if v is None:
        return "?"
    if unit == "tok" or v >= 1000:
        return M._short(v) if v >= 1000 else str(int(v))
    return str(int(round(v)))


def week_letters(today: datetime | None = None, n: int = 7) -> str:
    """One initial per day, oldest first, ending today."""
    today = today or datetime.fromtimestamp(time.time())
    return "".join("MTWTFSS"[(today.weekday() - back) % 7] for back in range(n - 1, -1, -1))


def brand(name: str, kit: U.Kit) -> int:
    agent = kittymux_agents.AGENTS.get(name)
    return agent.brand if agent else kit.p.muted


def _dot(kit: U.Kit, tone: str, on: int) -> list:
    return [kit.text(DOTS.get(tone, "◌"), kit.ink(kit.tone(tone), on, 3.0), on)]


def _row(kit: U.Kit, left: list, right: list, width: int, bg: int) -> list:
    """`left` at the left edge, `right` at the right edge; the right side yields first when they collide."""
    lw, rw = U.line_cells(left, kit.cells), U.line_cells(right, kit.cells)
    if lw + rw + 1 > width:
        right, rw = [], 0
    return kit.fit_line(left + [U.S(" " * max(0, width - lw - rw), None, bg)] + right, width, bg)


def _wrap(kit: U.Kit, pieces: list, width: int, bg: int) -> list:
    """Chips (each a line of spans) laid out greedily, one space apart, as many rows as it takes."""
    rows, cur, used = [], [], 0
    for piece in pieces:
        w = U.line_cells(piece, kit.cells)
        if cur and used + 1 + w > width:
            rows.append(kit.fit_line(cur, width, bg))
            cur, used = [], 0
        if cur:
            cur.append(U.S(" ", None, bg))
            used += 1
        cur += piece
        used += w
    if cur:
        rows.append(kit.fit_line(cur, width, bg))
    return rows


def _pace(m: dict):
    """Where an even spend would be now (0..100), when the meter knows its window and its reset; None when it cannot say."""
    window, rem = M.num(m.get("window_s")), M.num(m.get("rem_s"))
    if m.get("clock") or not window or window <= 0 or rem is None:
        return None
    return max(0.0, min(100.0, (1 - rem / window) * 100))


def _quota(kit: U.Kit, m: dict, inner: int, bg: int) -> list:
    tone = "muted" if m.get("clock") else kit.ramp(m["pct"])
    left = kit.chip(m["label"] or "quota", "muted", on=bg, strong=True)
    rem = M.num(m.get("rem_s"))
    if rem is not None and m["label"] != "cap":
        left += [U.S(" ", None, bg)] + kit.chip("↻ " + fmt_span(rem), "muted", on=bg)
    pct = [U.S(f"{round(m['pct'])}%", kit.ink(kit.tone(tone), bg), bg, bold=True)]
    if m.get("clock"):
        pct = [U.S(f"{round(m['pct'])}% of window", kit.ink(kit.p.muted, bg), bg)]
    return [_row(kit, left, pct, inner, bg), kit.gauge(m["pct"], inner, bg, tone=tone, pace=_pace(m))]


def _counter(kit: U.Kit, m: dict, inner: int, bg: int, letters: str) -> list:
    big = [U.S(fmt_amount(m["value"], m["unit"]), kit.ink(kit.p.text, bg), bg, bold=True),
           U.S(f" {m['unit']}", kit.ink(kit.p.muted, bg), bg)]
    rows = [kit.fit_line(big, inner, bg)]
    series = m.get("series")
    if series:
        rows += kit.bars(series, inner, rows=2, tone="accent", on=bg, labels=letters)
    rows += _wrap(kit, [kit.chip(c, "muted", on=bg) for c in m.get("chips") or []], inner, bg)
    return rows


def _states(kit: U.Kit, ms: list, inner: int, bg: int) -> list:
    chips = []
    for m in ms:
        text = m["text"] if m["label"] in ("plan", "status", "model", "info", "") else f"{m['label']} {m['text']}"
        icon = {"hot": "⊘ ", "warm": "◐ ", "calm": "● ", "muted": ""}[m["tone"]]
        chips.append(kit.chip(icon + text, m["tone"], on=bg))
    return _wrap(kit, chips, inner, bg)


def _focus_lines(kit: U.Kit, provider: dict, summary: dict, history: dict | None, inner: int, letters: str, today) -> list:
    bg = kit.p.card
    name = summary["name"]
    status = summary["status"]
    head_left = kit.monogram(name[:1], brand(name, kit), bg) + [U.S(" ", None, bg), U.S(name.title(), kit.ink(kit.p.text, bg), bg, bold=True)]
    head_right = (kit.chip(summary["plan"], "muted", on=bg) + [U.S(" ", None, bg)] if summary["plan"] else []) + _dot(kit, summary["tone"], bg)
    rows = [_row(kit, head_left, head_right, inner, bg)]
    if status == "pending":
        rows += [kit.fit_line([U.S("▒" * max(3, inner * 2 // 3), kit.p.track, bg)], inner, bg), kit.gauge(None, inner, bg),
                 kit.fit_line([U.S("collecting…", kit.ink(kit.p.muted, bg), bg)], inner, bg)]
        return rows
    if status == "error":
        msg = kittymux_place.clean(str(provider.get("err") or "usage unavailable"))[:60]
        rows += [kit.fit_line(kit.chip("⊘ " + msg, "hot", on=bg), inner, bg)]
        return rows
    if status in ("missing", "empty"):
        text = "not installed" if status == "missing" else "no usage data yet"
        return rows + [kit.fit_line([U.S(text, kit.ink(kit.p.muted, bg), bg)], inner, bg), kit.gauge(None, inner, bg)]
    ms = M.meters(provider, history, today)
    quotas = [m for m in ms if m["kind"] == "quota"]
    for i, m in enumerate(quotas):
        if i:
            rows.append(kit.blank(inner, bg))
        rows += _quota(kit, m, inner, bg)
    for m in (m for m in ms if m["kind"] == "counter"):
        rows.append(kit.blank(inner, bg))
        rows += _counter(kit, m, inner, bg, letters)
    states = [m for m in ms if m["kind"] == "state"]
    if states:
        rows.append(kit.blank(inner, bg))
        rows += _states(kit, states, inner, bg)
    for m in (m for m in ms if m["kind"] == "spend" and m["text"]):
        rows.append(kit.fit_line([U.S(m["text"], kit.ink(kit.p.text, bg), bg)], inner, bg))
    return rows


def _tile(kit: U.Kit, provider: dict, summary: dict, width: int, selected: bool) -> list:
    bg = kit.p.card_hi if selected else kit.p.card
    inner = kit.inner_width(width, margin=0, padx=1)
    worst, tone = summary["worst"], summary["tone"]
    if summary["status"] == "pending":
        value = [kit.text("…", kit.ink(kit.p.muted, bg), bg)]
    elif summary["status"] == "error":
        value = [kit.text("!", kit.ink(kit.p.alert, bg), bg, bold=True)]
    elif worst is not None:
        value = [kit.text(f"{round(worst)}", kit.ink(kit.tone(tone), bg), bg, bold=True)]
    else:
        value = _dot(kit, tone if summary["status"] == "ok" else "muted", bg)
    name = summary["name"]
    row1 = _row(kit, kit.monogram(name[:1], brand(name, kit), bg), value, inner, bg)
    row2 = kit.gauge(worst if summary["status"] == "ok" else None, inner, bg, tone=tone)
    return kit.card([row1, row2], width, on=kit.p.bar, selected=selected, margin=0, padx=1, accent=selected)


def _strip(kit: U.Kit, providers: list, summaries: list, sel: int, cols: int, y0: int) -> tuple:
    """Tiles side by side (one space apart), wrapped to a second row when they do not fit, windowed around the pick when there are too many;
    returns (lines, tile regions) with regions as (x0, x1, y0, y1, provider index)."""
    margin = 1
    room = max(1, cols - 2 * margin)
    n = len(providers)
    per_fit = max(1, (room + 1) // (TILE_MIN + 1))
    cap = per_fit * STRIP_MAX_ROWS
    start = 0 if n <= cap else max(0, min(sel - cap // 2, n - cap))
    shown = list(range(start, min(n, start + cap)))
    rows = -(-len(shown) // per_fit)
    per = -(-len(shown) // rows)                                         # balance the rows (7 tiles: 4 + 3, not 6 + 1)
    width = max(TILE_MIN, (room - (per - 1)) // per)
    lines, regions = [], []
    for r in range(rows):
        chunk = shown[r * per:(r + 1) * per]
        tiles = [_tile(kit, providers[i], summaries[i], width, i == sel) for i in chunk]
        height = len(tiles[0])
        for k in range(height):
            line = [U.S(" " * margin, None, kit.p.bar)]
            for j, t in enumerate(tiles):
                line += t[k]
                if j < len(tiles) - 1:
                    line.append(U.S(" ", None, kit.p.bar))
            lines.append(kit.fit_line(line, cols, kit.p.bar))
        for j, i in enumerate(chunk):
            x0 = margin + j * (width + 1)
            regions.append((x0, x0 + width, y0 + len(lines) - height, y0 + len(lines), i))
        if r < rows - 1:
            lines.append(kit.blank(cols, kit.p.bar))
    return lines, regions


def _heat_card(kit: U.Kit, series: list, cols: int, letters: str) -> list:
    """series: [(name, [7 values])]. One row per provider, a tinted block per day."""
    bg = kit.p.card
    inner = kit.inner_width(cols)
    rows = [_row(kit, kit.chip("7d", "muted", on=bg, strong=True), [U.S("tokens per day", kit.ink(kit.p.muted, bg), bg)], inner, bg)]
    pad = U.S("    ", None, bg)
    rows.append(kit.fit_line([pad, U.S("".join(c.ljust(3) for c in letters).rstrip(), kit.ink(kit.p.faint, bg, 3.0), bg)], inner, bg))
    for name, values in series:
        rows.append(kit.fit_line(kit.monogram(name[:1], brand(name, kit), bg) + [U.S(" ", None, bg)] + kit.heat(values, "accent", bg), inner, bg))
    return kit.card(rows, cols)


def view(data, history: dict | None, cols: int, sel: int, kit: U.Kit, now: float | None = None, today: datetime | None = None) -> View:
    """The whole Usage body for a panel `cols` wide. Never raises: what it cannot read becomes an honest placeholder."""
    p = kit.p
    now = time.time() if now is None else now
    cols = max(8, int(cols))
    providers = [x for x in (data.get("providers") if isinstance(data, dict) else None) or [] if isinstance(x, dict)]
    out: list = [kit.blank(cols, p.bar)]
    if not providers:
        inner = kit.inner_width(cols)
        rows = [kit.fit_line([U.S("Collecting local usage…", kit.ink(p.muted, p.card), p.card)], inner, p.card), kit.gauge(None, inner, p.card)]
        header = kit.fit_line([U.S(" no providers yet", kit.ink(p.muted, p.bar), p.bar)], cols, p.bar)
        return View(header, out + kit.card(rows, cols), [], 0, 0)
    summaries = [M.summary(x) for x in providers]
    sel = max(0, min(int(sel) if M.num(sel) is not None else 0, len(providers) - 1))
    letters = week_letters(today)

    ts = M.num(data.get("ts")) if isinstance(data, dict) else None
    age = max(0.0, now - ts) if ts else None
    worst = M.worst_provider(providers)
    left = [U.S(f" {len(providers)} provider{'s' if len(providers) != 1 else ''}", kit.ink(p.muted, p.bar), p.bar)]
    if worst:
        hot = worst["worst"] >= 80
        label = f"  {'▲' if hot else '●'} {worst['name'].title()} {round(worst['worst'])}%"
        left.append(U.S(label, kit.ink(kit.tone(worst["tone"]), p.bar), p.bar, bold=hot))
    if age is not None and age > STALE_S:
        right = [U.S(f"stale {fmt_span(age)} ", kit.ink(p.waiting, p.bar), p.bar)]
    else:
        right = [U.S(f"↻ {fmt_span(age) or '0m'} " if age is not None and age >= 60 else "", kit.ink(p.faint, p.bar, 3.0), p.bar)]
    header = _row(kit, left, right, cols, p.bar)

    strip, regions = _strip(kit, providers, summaries, sel, cols, len(out))
    out += strip
    out.append(kit.blank(cols, p.bar))

    inner = kit.inner_width(cols)
    focus = _focus_lines(kit, providers[sel], summaries[sel], history, inner, letters, today)
    out += kit.card(focus, cols)

    heat = []
    for x, s in zip(providers, summaries):
        for m in M.meters(x, history, today):
            if m["kind"] == "counter" and m.get("series"):
                heat.append((s["name"], m["series"]))
                break
    if heat:
        out.append(kit.blank(cols, p.bar))
        out += _heat_card(kit, heat, cols, letters)

    if not (isinstance(data, dict) and data.get("live")):
        out.append(kit.blank(cols, p.bar))
        out.append(kit.fit_line([U.S(" local data · live quotas are opt-in", kit.ink(p.faint, p.bar, 3.0), p.bar)], cols, p.bar))
    return View(header, out, regions, sel, len(providers))
