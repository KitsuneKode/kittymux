"""The panel's Inbox view (pure): typed events in (kittymux_inbox), styled cards and click regions out.

One card per event, newest and most pressing first: a kind badge (`!` permission, `?` question, `⊘` limit, `✓` done, `✕` error), the agent and
its tab, how long ago, what it said, and for a limit a full gauge with the time to reset. Buttons (Jump, Dismiss) are drawn only on the picked
card, so the list stays calm. Read events stay under the unread ones, dimmed, until they are dismissed.

What an agent wrote is untrusted: every string is `kittymux_place.clean`ed and bounded before it is drawn. This view never sends anything to an
agent; Jump focuses its window, Dismiss only changes the event's status."""
from __future__ import annotations

import time
from typing import NamedTuple

import kittymux_deck
import kittymux_meters as M
import kittymux_place
import kittymux_ui as U
import kittymux_usageview as V

FILTERS = (("all", "All"), ("needs", "Needs you"), ("done", "Done"), ("limits", "Limits"))
KIND = {"permission": ("!", "warm"), "question": ("?", "warm"), "limit": ("⊘", "hot"), "done": ("✓", "calm"), "error": ("✕", "hot"),
        "info": ("·", "muted")}
SHOWN_MAX = 40
TEXT_ROWS = 2


class InboxView(NamedTuple):
    header: list
    chips: list            # [(x0, x1, filter)] on the filter row (body y = 0)
    lines: list            # the body under the tab strip
    cards: list            # [(y0, y1, index)] body coordinates
    buttons: list          # [(x0, x1, y, index, action)] body coordinates, only for the picked card
    sel: int
    count: int


def unread(events) -> int:
    return sum(1 for e in events if isinstance(e, dict) and e.get("status") == "unread")


def needs_you(events) -> int:
    return sum(1 for e in events if isinstance(e, dict) and e.get("status") == "unread" and e.get("severity") == "needs-you")


def _matches(ev: dict, filt: str) -> bool:
    if ev.get("status") == "dismissed":
        return False
    if filt == "needs":
        return ev.get("status") == "unread" and ev.get("severity") == "needs-you"
    if filt == "done":
        return ev.get("kind") == "done"
    if filt == "limits":
        return ev.get("kind") == "limit"
    return True


def visible(events, filt: str = "all") -> list:
    """Events to list: not dismissed, filtered, unread first (needs-you before the rest), newest first inside each group."""
    keep = [e for e in events if isinstance(e, dict) and e.get("kind") in KIND and _matches(e, filt)] if isinstance(events, list) else []
    keep.sort(key=lambda e: (e.get("status") != "unread", e.get("severity") != "needs-you", -(M.num(e.get("t")) or 0.0)))
    return keep[:SHOWN_MAX]


def counts(events) -> dict:
    return {f: sum(1 for e in events if isinstance(e, dict) and e.get("kind") in KIND and _matches(e, f)) if isinstance(events, list) else 0
            for f, _ in FILTERS}


def _age(t, now: float) -> str:
    v = M.num(t)
    if v is None:
        return ""
    s = max(0.0, now - v)
    return "now" if s < 60 else V.fmt_span(s)


def _wrap(kit: U.Kit, text: str, width: int, rows: int) -> list:
    """Greedy word wrap into at most `rows` lines; what does not fit ends the last line with an ellipsis."""
    if width <= 0 or rows <= 0:
        return []
    lines, cur, cut = [], "", False
    for word in kittymux_place.clean(text).split():
        word = kittymux_deck.fit(word, width, kit.cells)
        cand = (cur + " " + word).strip()
        if kit.cells(cand) <= width:
            cur = cand
            continue
        lines.append(cur)
        cur = word
        if len(lines) == rows:
            cut, cur = True, ""
            break
    if cur:
        lines.append(cur)
    if cut and lines:
        lines[-1] = kittymux_deck.fit(lines[-1] + "…", width, kit.cells)
    return lines[:rows]


def _event_rows(kit: U.Kit, ev: dict, inner: int, selected: bool, now: float) -> tuple:
    """Returns (rows, button_row_index or None, [(x0, x1, action)] for that row relative to the card's inner left edge)."""
    p = kit.p
    bg = p.card_hi if selected else p.card
    glyph, tone = KIND[ev["kind"]]
    read = ev.get("status") != "unread"
    dim = read and not selected
    agent = kittymux_place.clean(str(ev.get("agent") or "agent")).title()
    tab = kittymux_place.clean(str(ev.get("tab") or ""))
    head = kit.monogram(glyph, kit.tone(tone), bg) + [U.S(" ", None, bg), U.S(agent, kit.ink(p.muted if dim else p.text, bg), bg, bold=not dim)]
    if tab and tab.lower() != agent.lower():
        head.append(U.S(f"  {tab}", kit.ink(p.muted, bg), bg))
    right = []
    n = int(M.num(ev.get("count")) or 1)
    if n > 1:
        right.append(U.S(f"×{min(n, 99)} ", kit.ink(p.muted, bg), bg))
    right.append(U.S(_age(ev.get("t"), now), kit.ink(p.faint if dim else p.muted, bg, 3.0), bg))
    rows = [V._row(kit, head, right, inner, bg)]
    title = str(ev.get("title") or "")
    body = kittymux_place.clean(str(ev.get("body") or ""))
    text = title or body
    for line in _wrap(kit, text, inner, TEXT_ROWS):
        rows.append(kit.fit_line([U.S(line, kit.ink(p.muted if dim else p.text, bg), bg)], inner, bg))
    if body and title and ev["kind"] in ("permission", "question"):
        rows.append(kit.fit_line([U.S(" " + body + " ", kit.ink(p.text, p.bar), p.bar)], inner, bg))
    if ev["kind"] == "limit":
        reset = M.num(ev.get("reset_at"))
        rows.append(kit.gauge(100.0, inner, bg, tone="hot"))
        if reset:
            rows.append(kit.fit_line(kit.chip("↻ " + V.fmt_span(reset - now), "muted", on=bg), inner, bg))
    button_row, regions = None, []
    if selected:
        jump = kit.button("Jump", "⏎", primary=True, on=bg)
        dismiss = kit.button("Dismiss", "x", on=bg)
        jw = U.line_cells(jump, kit.cells)
        dw = U.line_cells(dismiss, kit.cells)
        if jw + 1 + dw <= inner:
            rows.append(kit.fit_line(jump + [U.S(" ", None, bg)] + dismiss, inner, bg))
            button_row = len(rows) - 1
            regions = [(0, jw, "jump"), (jw + 1, jw + 1 + dw, "dismiss")]
    return rows, button_row, regions


def _chips(kit: U.Kit, filt: str, tally: dict, cols: int) -> tuple:
    p = kit.p
    line, regions, x = [U.S(" ", None, p.bar)], [], 1
    for key, label in FILTERS:
        active = key == filt
        text = f"{label} {tally[key]}" if tally[key] else label
        chip = kit.chip(text, "text" if active else "muted", on=p.bar, strong=active)
        w = U.line_cells(chip, kit.cells)
        if x + w > cols:
            break
        line += chip + [U.S(" ", None, p.bar)]
        regions.append((x, x + w, key))
        x += w + 1
    return kit.fit_line(line, cols, p.bar), regions


def view(events, filt: str, sel: int, cols: int, kit: U.Kit, now: float | None = None) -> InboxView:
    """Never raises. `sel` indexes the VISIBLE list (clamped); the caller keeps it in range across refreshes."""
    p = kit.p
    now = time.time() if now is None else now
    cols = max(8, int(cols))
    filt = filt if filt in dict(FILTERS) else "all"
    events = events if isinstance(events, list) else []
    items = visible(events, filt)
    tally = counts(events)
    sel = max(0, min(int(sel) if M.num(sel) is not None else 0, max(0, len(items) - 1)))
    un, ny = unread(events), needs_you(events)
    left = [U.S(f" {un} unread" if un else " all read", kit.ink(p.muted, p.bar), p.bar)]
    if ny:
        left.append(U.S(f"  ! {ny} need{'s' if ny == 1 else ''} you", kit.ink(p.waiting, p.bar), p.bar, bold=True))
    header = kit.fit_line(left, cols, p.bar)
    chip_line, chips = _chips(kit, filt, tally, cols)
    lines = [chip_line, kit.blank(cols, p.bar)]
    cards, buttons = [], []
    inner = kit.inner_width(cols)
    if not items:
        empty = [kit.fit_line([U.S("✓ ", kit.ink(p.done, p.card), p.card, bold=True), U.S("All clear", kit.ink(p.text, p.card), p.card, bold=True)], inner, p.card),
                 kit.fit_line([U.S("nothing waits on you" if filt == "all" else "nothing in this filter", kit.ink(p.muted, p.card), p.card)], inner, p.card)]
        lines += kit.card(empty, cols)
        return InboxView(header, chips, lines, [], [], 0, 0)
    for i, ev in enumerate(items):
        selected = i == sel
        rows, button_row, regions = _event_rows(kit, ev, inner, selected, now)
        card = kit.card(rows, cols, selected=selected, accent=selected)
        y0 = len(lines)
        lines += card
        cards.append((y0, len(lines), i))
        if button_row is not None:
            y = y0 + 1 + button_row                              # +1: the card's top edge row
            buttons += [(2 + a, 2 + b, y, i, act) for a, b, act in regions]      # 2 = margin + padx
        lines.append(kit.blank(cols, p.bar))
    return InboxView(header, chips, lines, cards, buttons, sel, len(items))
