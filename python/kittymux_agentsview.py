"""The panel's Agents view, as lines (pure): one tab = two lines, a split tab's panes = one line each, and a row of clickable keycaps under the list.

The list is the thing looked at most, so it follows three rules:
  * ONE bright thing per row: the title. Everything else is muted, and a state shows as a mark at the right edge, never as a sentence.
  * What needs you can be found without reading: a left stripe and a faint warm tint on the whole row, the mark in bold.
  * Detail appears where you point: ports, PR numbers and the pane count only on the picked or hovered row, so a long list stays calm.

Everything is drawn by `kittymux_ui.Kit` from the live palette; every line is exactly the width asked for (`fit_line`). Row geometry (2 lines per tab,
1 per pane, 1 per header) is the deck's (`kittymux_deck.Item`), so hit-testing there still holds."""
from __future__ import annotations

import kittymux_agents
import kittymux_deck
import kittymux_place
import kittymux_theme as T
import kittymux_titles
import kittymux_ui as U

ICON_BRANCH = ""
ICON_FOLDER = ""
RAIL = "▌"
NEEDS = kittymux_agents.NEEDS_YOU
TINT = 0.09                    # how much of the warning colour a needs-you row carries (quiet: the stripe and the mark do the shouting)


def _state_color(p, state: str):
    return {"waiting": p.waiting, "working": p.working, "limited": p.alert, "done": T.blend(p.done, p.bg, 0.65), "unread": p.faint}.get(state)


def row_bg(p, r, selected: bool, hovered: bool) -> int:
    """Selected beats hovered beats a needs-you tint beats the bar."""
    if selected:
        base = p.surface_hi
    elif hovered:
        base = p.surface
    else:
        base = p.bar
    if r.status in NEEDS and not selected:
        return T.blend(_state_color(p, r.status), base, TINT)
    return base


def _short_home(path: str, home: str) -> str:
    return "~" + path[len(home):] if home and path.startswith(home) else path


def title_row(kit: U.Kit, r, selected: bool, hovered: bool, width: int, animate: bool = True) -> list:
    p = kit.p
    bg = row_bg(p, r, selected, hovered)
    lit = selected or hovered or r.current
    needs = r.status in NEEDS
    stripe = (p.accent if r.current else p.waiting if needs else None)
    rail = U.S(RAIL if stripe is not None else " ", stripe, bg)
    brand = kittymux_agents.AGENTS[r.agent].brand if r.agent in kittymux_agents.AGENTS else p.muted
    if r.tool:
        icon_fg = p.muted if lit else p.faint
    else:
        icon_fg = brand if lit or needs else T.blend(brand, p.bg, 0.6)
    icon = U.S(r.glyph or " ", kit.ink(icon_fg, bg, 3.0), bg)
    title_fg = p.text if (lit or needs) else p.muted
    sc = _state_color(p, r.status)
    mark = [U.S(" ", None, bg), U.S(kittymux_agents.state_glyph(r.status, animate=animate), kit.ink(sc, bg, 3.0), bg, bold=needs), U.S(" ", None, bg)] if sc is not None else [U.S("   ", None, bg)]
    left = [rail, icon, U.S(" ", None, bg)]
    room = width - U.line_cells(left, kit.cells) - U.line_cells(mark, kit.cells)
    shown = kittymux_titles.shorten(kittymux_place.clean(r.title or "—"), max(0, room), kit.cells)          # cut at a word, not in the middle of one
    title = U.S(shown, kit.ink(title_fg, bg), bg, bold=lit or needs)
    body = kit.fit_line([title], max(0, room), bg)
    return kit.fit_line(left + body + mark, width, bg)


def context_row(kit: U.Kit, r, selected: bool, hovered: bool, width: int, home: str = "", open_state=None) -> list:
    """Where the tab is (branch, else folder), then — only on the picked or hovered row — PR, ports and pane count; the tab's number sits at the right edge.
    `open_state` is None for a tab with one pane, else whether its panes are listed under it: a ▸ / ▾ in column 2 says so and a click there toggles."""
    p = kit.p
    bg = row_bg(p, r, selected, hovered)
    lit = selected or hovered or r.current
    needs = r.status in NEEDS
    stripe = (p.accent if r.current else p.waiting if needs else None)
    rail = U.S(RAIL if stripe is not None else " ", stripe, bg)
    sub = kit.ink(p.muted if lit else p.faint, bg, 3.0)
    idx = U.S(f" {r.index} ", kit.ink(p.faint, bg, 3.0), bg)
    pieces = []
    if r.branch:
        pieces.append(U.S(f"{ICON_BRANCH} {kittymux_place.clean(r.branch)}", sub, bg))
    elif r.cwd:
        pieces.append(U.S(f"{ICON_FOLDER} {kittymux_place.clean(_short_home(r.cwd, home))}", sub, bg))
    detail = []
    if lit:
        if r.pr:
            detail.append(U.S(kittymux_place.clean(r.pr), kit.ink(p.muted, bg), bg))        # never a state colour: `info` is the same blue as "working"
        if r.ports:
            detail.append(U.S(" ".join(f":{int(n)}" for n in r.ports[:3] if isinstance(n, int)), kit.ink(p.muted, bg), bg))
    if r.panes > 1:
        detail.append(U.S(f"{r.panes} panes", kit.ink(p.muted if lit else p.faint, bg, 3.0), bg))
    # the state's wording, longest first: the mark at the right edge already says "needs you", so the words give way before the place does
    word = "needs you" if r.status == "waiting" else "limit hit" if r.status == "limited" else "done" if r.status == "done" and r.age else ""
    short = "needs" if r.status == "waiting" else "limit" if r.status == "limited" else "done"
    variants = [f"{word} {r.age}".strip(), f"{short} {r.age}".strip(), r.age] if word else []
    if r.status == "limited" and r.age.startswith("\u21bb"):        # a known reset: say when it lifts, not how long ago it hit
        variants = [f"resets in {r.age[1:]}", f"\u21bb{r.age[1:]}"]
    tail_style = (kit.ink(_state_color(p, r.status), bg), True) if needs else (kit.ink(p.faint, bg, 3.0), False)
    marker = U.S(" " if open_state is None else "\u25be" if open_state else "\u25b8", kit.ink(p.accent if lit else p.muted, bg, 3.0), bg)
    left = [rail, U.S(" ", None, bg), marker, U.S(" ", None, bg)]
    room = width - U.line_cells(left, kit.cells) - U.line_cells([idx], kit.cells)
    first = kit.cells(pieces[0].text) if pieces else 0
    need_left = min(first, 12)                      # the place must stay readable: at least its first 12 cells (or all of it, when it is shorter)
    text = next((v for v in dict.fromkeys(variants) if v and room - (kit.cells(v) + 2) >= need_left), "")
    tail = [U.S(text, tail_style[0], bg, bold=tail_style[1])] if text else []
    reserve = sum(kit.cells(s.text) + 2 for s in tail)
    body, used = [], 0
    for i, s in enumerate(pieces + detail):
        sep = 2 if body else 0
        left_room = room - used - sep - reserve
        if left_room <= 1:
            break
        t = s._replace(text=kittymux_deck.fit(s.text, left_room, kit.cells))
        body += ([U.S("  ", None, bg)] if sep else []) + [t]
        used += sep + kit.cells(t.text)
    for s in tail:
        if room - used >= 2 + kit.cells(s.text):
            body += [U.S("  ", None, bg), s]
            used += 2 + kit.cells(s.text)
    return kit.fit_line(left + body + [U.S(" " * max(0, room - used), None, bg), idx], width, bg)


def pane_row(kit: U.Kit, r, j: int, hovered: bool, width: int, animate: bool = True) -> list:
    """One child line of a split tab: `├ ◆ title ........ ⠋` (`└` on the last). Quiet unless it is the focused pane, hovered, or asks for you."""
    p = kit.p
    pd = r.pane_rows[j]
    last = j == min(len(r.pane_rows), kittymux_deck.MAX_PANE_ROWS) - 1
    needs = pd.state in NEEDS
    bg = p.surface if hovered else p.bar
    lit = pd.active or hovered or needs
    brand = kittymux_agents.AGENTS[pd.agent].brand if pd.agent in kittymux_agents.AGENTS else p.muted
    icon_fg = (brand if lit else T.blend(brand, p.bg, 0.6)) if pd.agent else (p.muted if lit else p.faint)
    sc = _state_color(p, pd.state)
    mark = [U.S(" ", None, bg), U.S(kittymux_agents.state_glyph(pd.state, animate=animate), kit.ink(sc, bg, 3.0), bg, bold=needs), U.S(" ", None, bg)] if sc is not None else [U.S("   ", None, bg)]
    left = [U.S("   ", None, bg), U.S("└" if last else "├", p.line, bg), U.S(" ", None, bg), U.S(pd.glyph or "·", kit.ink(icon_fg, bg, 3.0), bg), U.S(" ", None, bg)]
    room = width - U.line_cells(left, kit.cells) - U.line_cells(mark, kit.cells)
    shown = kittymux_titles.shorten(kittymux_place.clean(pd.title or pd.agent or "shell"), max(0, room), kit.cells)
    title = U.S(shown, kit.ink(p.text if lit else p.muted, bg), bg, bold=pd.active)
    return kit.fit_line(left + kit.fit_line([title], max(0, room), bg) + mark, width, bg)


def header_row(kit: U.Kit, label: str, count: int, current: bool, width: int, attn: int = 0) -> list:
    """` SESSION NAME ...... ! 2  7 `: the name (accent when it is the one you are in), how many of its tabs ask for you, how many tabs it has."""
    p = kit.p
    right = ([U.S(f"{kittymux_agents.state_glyph('waiting')} {attn}", kit.ink(p.waiting, p.bar), p.bar, bold=True), U.S("  ", None, p.bar)] if attn else [])
    right.append(U.S(f"{count}  ", kit.ink(p.faint, p.bar, 3.0), p.bar))
    rw = U.line_cells(right, kit.cells)
    if rw + 4 > width:                              # no room for the name: the count of tabs goes first, then the badge
        right = right[-1:]
        rw = U.line_cells(right, kit.cells)
    name = U.S(" " + kittymux_place.clean(label).upper(), kit.ink(p.accent if current else p.faint, p.bar, 3.0), p.bar, bold=True)
    room = width - rw
    return kit.fit_line(kit.fit_line([name], max(0, room), p.bar) + right, width, p.bar)


def summary_row(kit: U.Kit, tabs: int, waiting: int, working: int, width: int, animate: bool = True) -> list:
    """` 8 tabs   ! 2 need you   ⠋ 3 working` — the numbers a glance wants, no more."""
    p = kit.p
    out = [U.S(f" {tabs} tab{'s' if tabs != 1 else ''}", kit.ink(p.text, p.bar), p.bar, bold=True)]
    if waiting:
        out.append(U.S(f"   {kittymux_agents.state_glyph('waiting')} {waiting} need you", kit.ink(p.waiting, p.bar), p.bar, bold=True))
    if working:
        out.append(U.S(f"   {kittymux_agents.state_glyph('working', animate=animate)} {working} working", kit.ink(p.working, p.bar, 3.0), p.bar))
    return kit.fit_line(out, width, p.bar)


# ── the action bar: keycaps you can click ───────────────────────────────────

def action_bar(kit: U.Kit, pairs: list, width: int, hot: int | None = None, on: int | None = None):
    """pairs: [(key label, text, token | None[, short text])]. Returns (line, regions): regions are (x0, x1, token, index) for the pairs that were drawn whole and
    have a token. The hot one (the pointer is on it) lights up in the accent, so a button looks like a button before it is pressed.
    A pair may carry a SHORT text: when the long wording would push a button off the end, the bar uses the short one if that shows more buttons (a
    narrow panel keeps `d info` before it loses `d details` altogether); the long wording wins a tie."""
    best = None
    for use_short in (False, True) if any(len(pr) > 3 and pr[3] for pr in pairs) else (False,):
        line, regions = _bar(kit, pairs, width, hot, on, use_short)
        if best is None or len(regions) > len(best[1]):
            best = (line, regions)
    return best


def _bar(kit: U.Kit, pairs: list, width: int, hot, on, use_short: bool):
    p = kit.p
    on = p.bar if on is None else on
    out: list = []
    regions: list = []
    used = 0
    for i, pair in enumerate(pairs):
        key, label, token = pair[0], pair[1], pair[2]
        if use_short and len(pair) > 3 and pair[3]:
            label = pair[3]
        k = f" {kittymux_place.clean(str(key))} "
        lab = f" {kittymux_place.clean(str(label))} "
        need = kit.cells(k) + kit.cells(lab) + (1 if out else 0)
        if used + need > width:
            break
        if out:
            out.append(U.S(" ", None, on))
            used += 1
        is_hot = hot == i and token is not None
        x0 = used
        if is_hot:
            out += [U.S(k, p.on_accent, p.accent, bold=True), U.S(lab, p.on_accent, p.accent)]
        else:
            out += [U.S(k, kit.ink(p.text, p.card_hi), p.card_hi, bold=True), U.S(lab, kit.ink(p.muted, p.card), p.card)]
        used += kit.cells(k) + kit.cells(lab)
        if token is not None:
            regions.append((x0, used, token, i))
    return kit.fit_line(out, width, on), regions


def empty_rows(kit: U.Kit, width: int, query: str = "") -> list:
    """What the list says when it is empty: nothing matches the search (and how to get out of it), or there is no tab yet."""
    p = kit.p
    if query:
        shown = kittymux_place.clean(query)[:24]
        head, hint = f"No tab matches \u201c{shown}\u201d", "esc clears the search"
    else:
        head, hint = "No tabs yet", "open a tab and it shows up here"
    return [kit.blank(width, p.bar),
            kit.fit_line([U.S(" " + head, kit.ink(p.text, p.bar), p.bar, bold=True)], width, p.bar),
            kit.fit_line([U.S(" " + hint, kit.ink(p.muted, p.bar, 3.0), p.bar)], width, p.bar)]
