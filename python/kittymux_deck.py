# kittymux deck — pure layout/grouping logic for the sidebar command deck.
# No kitty imports: unit-tested under system python3 (tests/test_deck.py).

from dataclasses import dataclass
from typing import Callable

NO_SESSION = "(no session)"


@dataclass
class RowData:
    tab_id: int
    win_id: int
    session: str = ""
    title: str = ""
    glyph: str = ""
    agent: str = ""
    branch: str = ""
    cwd: str = ""
    panes: int = 1
    status: str = ""        # working | waiting | done | ""
    unread: bool = False
    current: bool = False   # the tab you are looking at right now
    index: int = 0          # 1-based position within its session (matches the tab bar)


@dataclass
class Item:
    kind: str               # "header" | "row"
    height: int
    label: str = ""         # header text
    count: int = 0          # header: rows in the group
    row: int = -1           # row: index into the flat row list
    current: bool = False   # header: this is the current session


def group_rows(rows: list[RowData], current_session: str) -> list[tuple[str, list[RowData]]]:
    """Group by session: current session first, then alphabetical, '' last.
    Rows keep their original order inside a group and get 1-based indices."""
    groups: dict[str, list[RowData]] = {}
    for r in rows:
        groups.setdefault(r.session, []).append(r)
    for members in groups.values():
        for i, r in enumerate(members, 1):
            r.index = i

    def key(name: str):
        return (name != current_session, name == "", name.lower())

    return [(name, groups[name]) for name in sorted(groups, key=key)]


def flatten(groups: list[tuple[str, list[RowData]]], current_session: str) -> tuple[list[Item], list[RowData]]:
    """Items (headers + 2-line rows) and the flat row list they index into."""
    items: list[Item] = []
    flat: list[RowData] = []
    for name, members in groups:
        items.append(Item("header", 1, label=name or NO_SESSION, count=len(members),
                          current=(name == current_session)))
        for r in members:
            items.append(Item("row", 2, row=len(flat)))
            flat.append(r)
    return items, flat


def item_of_row(items: list[Item], row: int) -> int:
    for i, it in enumerate(items):
        if it.kind == "row" and it.row == row:
            return i
    return 0


def ensure_visible(items: list[Item], scroll: int, sel_row: int, avail: int) -> int:
    """Smallest scroll (item index) that keeps the selected row fully visible.
    Prefers showing the session header above the first visible row."""
    if not items:
        return 0
    idx = item_of_row(items, sel_row)
    scroll = max(0, min(scroll, idx))
    while sum(it.height for it in items[scroll:idx + 1]) > avail and scroll < idx:
        scroll += 1
    if scroll == idx and idx > 0 and items[idx - 1].kind == "header" \
            and items[idx - 1].height + items[idx].height <= avail:
        scroll = idx - 1
    return scroll


def visible(items: list[Item], scroll: int, avail: int) -> list[tuple[int, Item]]:
    """[(y_offset, item)] that fit entirely in `avail` lines from `scroll`."""
    out, y = [], 0
    for it in items[scroll:]:
        if y + it.height > avail:
            break
        out.append((y, it))
        y += it.height
    return out


def row_at(items: list[Item], scroll: int, avail: int, y: int) -> int:
    """Flat row index under line `y` (relative to the list's first line), else -1."""
    for off, it in visible(items, scroll, avail):
        if it.kind == "row" and off <= y < off + it.height:
            return it.row
    return -1


def step_row(cur: int, delta: int, n: int) -> int:
    return max(0, min(n - 1, cur + delta)) if n else 0


def step_group(flat: list[RowData], cur: int, delta: int) -> int:
    """Jump to the first row of the next/previous session group."""
    if not flat:
        return 0
    sessions: list[str] = []
    firsts: dict[str, int] = {}
    for i, r in enumerate(flat):
        if r.session not in firsts:
            firsts[r.session] = i
            sessions.append(r.session)
    here = sessions.index(flat[cur].session)
    there = max(0, min(len(sessions) - 1, here + delta))
    return firsts[sessions[there]]


def hint(width: int) -> str:
    for cand in ("j/k move · J/K session · ⏎ go · click · q quit",
                 "j/k move · ⏎ go · click · q quit",
                 "j/k · ⏎ go · q quit",
                 "⏎ go · q quit",
                 "q quit"):
        if len(cand) <= width:
            return cand
    return ""


def fit(text: str, width: int, cells: Callable[[str], int] = len) -> str:
    """Truncate to `width` cells with a trailing … (cells: width function)."""
    if width <= 0:
        return ""
    if cells(text) <= width:
        return text
    out, used = "", 0
    for ch in text:
        w = cells(ch)
        if used + w > width - 1:
            break
        out += ch
        used += w
    return out + "…"


def pad(text: str, width: int, cells: Callable[[str], int] = len) -> str:
    """fit() then right-pad with spaces to exactly `width` cells."""
    t = fit(text, width, cells)
    return t + " " * max(0, width - cells(t))
