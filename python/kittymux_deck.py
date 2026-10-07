# kittymux deck — pure layout/grouping logic for the sidebar command deck.
# No kitty imports: unit-tested under system python3 (tests/test_deck.py).

import re
from dataclasses import dataclass
from functools import lru_cache
import kittymux_place
from typing import Callable

NO_SESSION = "other tabs"            # tabs that belong to no named session (shown only next to a named one)


MAX_PANE_ROWS = 8       # a split tab lists at most this many of its panes under the tab


@dataclass
class PaneData:
    """One pane of a split tab, shown as an indented child row."""
    win_id: int
    glyph: str = ""
    agent: str = ""
    tool: bool = False
    state: str = ""         # working | waiting | limited | done | idle | "" (not an agent)
    title: str = ""
    active: bool = False    # the tab's focused pane
    cwd: str = ""


@dataclass
class RowData:
    tab_id: int
    win_id: int
    session: str = ""
    title: str = ""         # what the row is CALLED (kittymux_titles.tidy)
    raw_title: str = ""     # the window title as the program set it: only the `/` search looks at it
    glyph: str = ""
    agent: str = ""
    tool: bool = False      # glyph is a quiet tool glyph, not an agent logo
    branch: str = ""
    cwd: str = ""
    panes: int = 1
    status: str = ""        # working | waiting | done | ""
    msg: str = ""           # what the agent is waiting for (from hooks)
    age: str = ""           # how long it has been in this state ("4m", "1h"): only from a minute on, only for states where it matters
    pr: str = ""            # "#123" for the branch's open pull request
    ports: tuple = ()       # TCP ports listening under this pane
    unread: bool = False
    current: bool = False   # the tab you are looking at right now
    index: int = 0          # 1-based position within its session (matches the tab bar)
    pane_rows: tuple = ()   # PaneData for every pane, when the tab is split (2+ panes)
    win_ids: tuple = ()     # every window of the tab (what "absorb" moves)


@dataclass
class Item:
    kind: str               # "header" | "row" | "pane" (a child line under its row)
    height: int
    label: str = ""         # header text
    count: int = 0          # header: rows in the group
    attn: int = 0           # header: rows in the group that ask for you (waiting / limited)
    row: int = -1           # row/pane: index into the flat row list (a pane's parent)
    pane: int = -1          # pane: index into the parent's pane_rows
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
    only_unnamed = len(groups) == 1 and not groups[0][0]
    for name, members in groups:
        if not only_unnamed:                       # a lone unnamed group has nothing to say: its header would only repeat "N tabs"
            items.append(Item("header", 1, label=name or NO_SESSION, count=len(members),
                              attn=sum(1 for r in members if r.status in ("waiting", "limited")), current=(name == current_session)))
        for r in members:
            items.append(Item("row", 2, row=len(flat)))
            flat.append(r)
            if len(r.pane_rows) >= 2:
                for j in range(min(len(r.pane_rows), MAX_PANE_ROWS)):
                    items.append(Item("pane", 1, row=len(flat) - 1, pane=j))
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
    end = idx                                   # the selected row's pane lines belong to it
    while end + 1 < len(items) and items[end + 1].kind == "pane":
        end += 1
    scroll = max(0, min(scroll, idx))
    while sum(it.height for it in items[scroll:end + 1]) > avail and scroll < idx:
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


def pane_at(items: list[Item], scroll: int, avail: int, y: int) -> tuple[int, int]:
    """(flat row index, pane index) of the child line under `y`, else (-1, -1)."""
    for off, it in visible(items, scroll, avail):
        if it.kind == "pane" and off <= y < off + it.height:
            return it.row, it.pane
    return -1, -1


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


# ── the layout mini-map: a split tab drawn to scale, two sub-pixels per cell each way ──────────────
_QUADRANT = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"        # index = bit mask of the cell's sub-pixels that belong to colour A (TL=1 TR=2 BL=4 BR=8)


def layout_minimap(rects: list, cols: int, rows: int) -> list:
    """A picture of a tab's pane layout. `rects`: [(pane_id, left, top, right, bottom)] in any units (pixels).
    Returns `rows` lists of `cols` cells (char, id_a, id_b): draw `char` with id_a as the foreground and id_b as the
    background colour. Every cell holds 2x2 sub-pixels, each belonging to the pane under its centre, so the grid shows
    where the splits are, to scale. A cell that straddles three or more panes shows its two most common."""
    if not rects or cols < 1 or rows < 1:
        return []
    x0, y0 = min(r[1] for r in rects), min(r[2] for r in rects)
    x1, y1 = max(r[3] for r in rects), max(r[4] for r in rects)
    w, h = max(1, x1 - x0), max(1, y1 - y0)

    def pane_at(sx: int, sy: int):
        x = x0 + (sx + 0.5) * w / (2 * cols)
        y = y0 + (sy + 0.5) * h / (2 * rows)
        best, best_d = None, None
        for pid, l, t, r, b in rects:
            if l <= x < r and t <= y < b:
                return pid
            d = max(l - x, x - r, t - y, y - b, 0)            # a gap between panes (borders): the nearest one
            if best_d is None or d < best_d:
                best, best_d = pid, d
        return best

    out = []
    for cy in range(rows):
        line = []
        for cx in range(cols):
            quad = [pane_at(2 * cx, 2 * cy), pane_at(2 * cx + 1, 2 * cy), pane_at(2 * cx, 2 * cy + 1), pane_at(2 * cx + 1, 2 * cy + 1)]
            counts: dict = {}
            for q in quad:
                counts[q] = counts.get(q, 0) + 1
            ranked = sorted(counts, key=lambda k: (-counts[k], quad.index(k)))
            a = ranked[0]
            b = ranked[1] if len(ranked) > 1 else a
            mask = sum(bit for bit, q in zip((1, 2, 4, 8), quad) if q == a)
            line.append((_QUADRANT[mask], a, b))
        out.append(line)
    return out


@lru_cache(maxsize=256)
def cached_minimap(rects: tuple, cols: int, rows: int) -> tuple:
    """Immutable, bounded geometry cache. Focus, state and palette are applied by callers."""
    return tuple(tuple(line) for line in layout_minimap(rects, cols, rows))


def complete_minimap(rects: tuple, cols: int, rows: int) -> tuple | None:
    """None instead of a misleading picture when sampling loses a tiny/stacked pane."""
    grid = cached_minimap(rects, cols, rows)
    seen = {pid for line in grid for _ch, a, b in line for pid in (a, b)}
    return grid if grid and seen == {r[0] for r in rects} else None


def wrap_detail(text: str, width: int, cells=len) -> list[str]:
    """Wrap full values without discarding their suffix; terminal controls are never drawn."""
    text = kittymux_place.clean(text)
    if width < 1:
        return []
    out, line = [], ""
    for ch in text:
        if cells(line + ch) > width:
            out.append(line)
            line = ""
        if cells(ch) <= width:
            line += ch
    return out + ([line] if line else [])


_RULE = re.compile(r"^[\s\u2500-\u257f\u2580-\u259f\-_=~*+.|]+$")                  # box drawing, block elements, ----, ====: a border, not content
_BORDER = re.compile(r"^[\u2502\u2503\u2551|]\s?|\s?[\u2502\u2503\u2551|]$")           # the vertical edges of a boxed prompt
_HINT = re.compile(
    r"(?:\?\s+for\s+shortcuts|esc(?:ape)?\s+to\s+(?:interrupt|cancel|stop|go\s+back)|ctrl\+[a-z]\s+to\s+\w+|shift\+tab\s+to\s+\w+|tab\s+to\s+(?:cycle|expand|queue)|"
    r"press\s+enter\s+to\s+continue|\bcontext\s+\d+%\s*(?:used|left)?\s*$|\(esc\s+to\s+\w+\)|bypass\s+permissions|auto-accept\s+edits|\d+\s*(?:k|m)?\s+tokens?\s*$)",
    re.I)


def tidy_preview(lines, keep: int) -> list:
    """The last `keep` lines of a pane worth reading in a small drawer: no blank lines, no box rules or box edges, no TUI hint footers ("? for shortcuts",
    "esc to interrupt"), and no line twice in a row. Never invents text; an all-chrome screen yields []."""
    out: list = []
    for raw in lines or ():
        text = kittymux_place.clean_line(str(raw)).rstrip()
        if not text.strip() or _RULE.match(text):
            continue
        text = _BORDER.sub("", text).strip()
        if not text or _RULE.match(text) or _HINT.search(text) and len(text) < 90:
            continue
        if out and out[-1] == text:
            continue
        out.append(text)
    return out[-max(0, keep):] if keep > 0 else []


def numbered_layout(rects: tuple, cols: int, rows: int, active: int = 0) -> list[str]:
    """Outline native pane rectangles and label them in kitty's window order. [] if too small."""
    if not rects or cols < 6 or rows < 3:
        return []
    x0, y0 = min(r[1] for r in rects), min(r[2] for r in rects)
    dx = max(1, max(r[3] for r in rects) - x0)
    dy = max(1, max(r[4] for r in rects) - y0)
    boxes = [(pid, round((l - x0) * (cols - 1) / dx), round((t - y0) * (rows - 1) / dy),
              round((r - x0) * (cols - 1) / dx), round((b - y0) * (rows - 1) / dy)) for pid, l, t, r, b in rects]
    labels = [f"[{i}]" if pid == active else str(i) for i, (pid, *_g) in enumerate(boxes, 1)]
    if any(r - l < len(label) + 1 or b - t < 2 for (_pid, l, t, r, b), label in zip(boxes, labels)):
        return []
    grid = [[" "] * cols for _ in range(rows)]
    for (_pid, l, t, r, b), label in zip(boxes, labels):
        for x in range(l, r + 1):
            grid[t][x] = grid[b][x] = "─"
        for y in range(t, b + 1):
            grid[y][l] = grid[y][r] = "│"
        for x, y in ((l, t), (r, t), (l, b), (r, b)):
            grid[y][x] = "┼"
    for (_pid, l, t, r, b), label in zip(boxes, labels):
        x, y = l + (r - l - len(label) + 1) // 2, (t + b) // 2
        grid[y][x:x + len(label)] = label
    return ["".join(line) for line in grid]


def matches(row: RowData, tokens: list) -> bool:
    """Every token (lower-case) appears somewhere in the row's searchable text."""
    hay = " ".join((row.title, row.raw_title, row.branch, row.cwd, row.agent, row.status, row.msg, row.session, row.pr)).lower()
    return all(t in hay for t in tokens)


def filter_groups(groups: list, query: str) -> list:
    """The deck's `/` search: keep the rows that contain every word of `query` (title, branch, folder, agent, state,
    message, session, PR); drop sessions left empty. An empty query keeps everything."""
    tokens = query.lower().split()
    if not tokens:
        return groups
    out = []
    for name, members in groups:
        kept = [r for r in members if matches(r, tokens)]
        if kept:
            out.append((name, kept))
    return out


def promote_target(rows: list[RowData], sel: int, hover_pane: tuple = (-1, -1)) -> int:
    """Window id of the pane to promote to its own tab: the pane line under the pointer, else the selected
    split tab's focused pane. 0 when the selected tab is not split (nothing to promote)."""
    if not (0 <= sel < len(rows)) or len(rows[sel].pane_rows) < 2:
        return 0
    row, pane = hover_pane
    if row == sel and 0 <= pane < len(rows[sel].pane_rows):
        return rows[sel].pane_rows[pane].win_id
    active = next((p for p in rows[sel].pane_rows if p.active), None)
    return (active or rows[sel].pane_rows[0]).win_id


def absorb_plan(rows: list[RowData], sel: int) -> tuple[list[int], int]:
    """([window ids], target tab id): pull the selected tab's panes into the tab you are looking at
    (they become splits there). Nothing to do when the selection IS the current tab or none is current."""
    if not (0 <= sel < len(rows)):
        return [], 0
    here = next((r for r in rows if r.current), None)
    row = rows[sel]
    if here is None or row.tab_id == here.tab_id or not row.win_ids:
        return [], 0
    return list(row.win_ids), here.tab_id


def hint(width: int) -> str:
    for cand in ("j/k move · J/K session · ⏎ go · / find · a absorb · t tab · q quit",
                 "j/k move · ⏎ go · / find · a absorb · t tab · q quit",
                 "j/k move · ⏎ go · / find · q quit",
                 "j/k move · ⏎ go · a absorb · q quit",
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


class LatestWorker:
    """One active operation plus one replaceable pending request.

    Submission never waits for work or completion callbacks. Generations identify
    requests (including A→B→A); consumers must check them on their event thread.
    Closing discards pending reads, or drains the last write without joining.
    """

    def __init__(self, work: Callable, complete: Callable, *, coalesce: Callable | None = None, daemon: bool = True):
        import threading
        self._lock = threading.Lock()
        self._work, self._complete = work, complete
        self._coalesce, self._daemon = coalesce, daemon
        self._generation = 0
        self._pending = None
        self._running = False
        self._closed = False

    def submit(self, value):
        import threading
        with self._lock:
            if self._closed:
                return None
            self._generation += 1
            generation = self._generation
            if self._pending is not None and self._coalesce is not None:
                value = self._coalesce(self._pending[1], value)
            self._pending = (generation, value)
            if not self._running:
                self._running = True
                try:
                    threading.Thread(target=self._run, daemon=self._daemon).start()
                except Exception:
                    self._running = False
                    self._pending = None
                    raise
            return generation

    def is_current(self, generation: int) -> bool:
        with self._lock:
            return not self._closed and generation == self._generation

    def invalidate(self) -> None:
        with self._lock:
            self._generation += 1
            self._pending = None

    def close(self, drain: bool = False) -> None:
        with self._lock:
            self._closed = True
            self._generation += 1
            if not drain:
                self._pending = None

    def _run(self) -> None:
        while True:
            with self._lock:
                request, self._pending = self._pending, None
                if request is None:
                    self._running = False
                    return
            generation, value = request
            try:
                result = self._work(value)
            except Exception:
                result = None
            try:
                self._complete(generation, result)
            except Exception:
                pass


def target_owner(data: list, parent_of: dict, kitty_pids: set) -> int:
    """Verify one kitty owner from ls pane child PIDs, never OS-window IDs or socket names."""
    parents = {parent_of[w["pid"]]
               for osw in data for tab in osw.get("tabs", [])
               for w in tab.get("windows", []) if w.get("pid") in parent_of}
    if len(parents) == 1:
        pid = next(iter(parents))
        if pid in kitty_pids:
            return pid
    return 0


def target_pid(data: list) -> int:
    """Linux owner verification for a remote ls response; unavailable evidence fails closed."""
    import os
    from pathlib import Path
    parents, kitties = {}, set()
    try:
        for osw in data:
            for tab in osw.get("tabs", []):
                for w in tab.get("windows", []):
                    pid = w.get("pid")
                    if not isinstance(pid, int) or pid <= 0:
                        continue
                    try:
                        stat = Path(f"/proc/{pid}/stat").read_text()
                        parent = int(stat.rsplit(")", 1)[1].split()[1])
                        parents[pid] = parent
                        if Path(os.readlink(f"/proc/{parent}/exe")).name == "kitty":
                            kitties.add(parent)
                    except (OSError, ValueError, IndexError):
                        pass
        return target_owner(data, parents, kitties)
    except (TypeError, AttributeError):
        return 0


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
