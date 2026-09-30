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
    tool: bool = False      # glyph is a quiet tool glyph, not an agent logo
    branch: str = ""
    cwd: str = ""
    panes: int = 1
    status: str = ""        # working | waiting | done | ""
    msg: str = ""           # what the agent is waiting for (from hooks)
    pr: str = ""            # "#123" for the branch's open pull request
    ports: tuple = ()       # TCP ports listening under this pane
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


# ── listening ports under a pane ────────────────────────────────────────────
def children_map(ppid_of: dict) -> dict:
    """{pid: ppid} → {ppid: [pid, …]}"""
    out: dict = {}
    for pid, ppid in ppid_of.items():
        out.setdefault(ppid, []).append(pid)
    return out


def descendants(root: int, children: dict) -> set:
    """root and every process below it."""
    seen, stack = set(), [root]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(children.get(pid, ()))
    return seen


def parse_ss(text: str) -> list:
    """`ss -H -ltnp` output → [(port, pid)]. Lines without a pid are skipped."""
    import re
    out = []
    for line in text.splitlines():
        cols = line.split()
        if len(cols) < 5:
            continue
        m = re.search(r":(\d+)$", cols[3])
        pids = re.findall(r"pid=(\d+)", line)
        if m:
            for pid in pids:
                out.append((int(m.group(1)), int(pid)))
    return out


def ports_for(root: int, children: dict, listeners: list) -> tuple:
    """Sorted unique listening ports owned by root's process tree."""
    tree = descendants(root, children)
    return tuple(sorted({port for port, pid in listeners if pid in tree}))


# ── docked-panel edge drag ───────────────────────────────────────────────────
PANEL_MIN_COLS, PANEL_MAX_COLS = 16, 80


def in_grab_zone(cell_x: int, cols: int, zone: int = 2) -> bool:
    """Pointer over the resize handle of a LEFT-docked panel (its inner, right edge)."""
    return cols > 0 and cell_x >= cols - zone


def drag_columns(cell_x: int) -> int:
    """New panel width for a left-docked panel while the handle is dragged to `cell_x`
    (the panel is anchored at the screen edge, so the width is the pointer's column + 1)."""
    return max(PANEL_MIN_COLS, min(PANEL_MAX_COLS, cell_x + 1))


class DragThrottle:
    """Send resize requests at most every `interval` seconds and only when the target
    actually changes; `final` always goes through (release must land on the exact width)."""

    def __init__(self, interval: float = 0.06):
        self.interval = interval
        self.last_sent = -1e9
        self.last_cols = -1

    def should_send(self, now: float, cols: int, final: bool = False) -> bool:
        if cols == self.last_cols and not final:
            return False
        if not final and now - self.last_sent < self.interval:
            return False
        self.last_sent, self.last_cols = now, cols
        return True
