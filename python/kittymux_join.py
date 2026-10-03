# kittymux join — move a tab's panes into another tab as splits, keeping their shape.
#
# Moving windows one by one with `kitty @ detach-window --target-tab` splits the SAME pane again for each window: a three-pane tab joined into a
# two-pane one left panes of 15, 7 and 7 columns. kitty's own mouse drag-and-drop avoids that with `Tab.attach_windows(next_to=, horizontal=, after=)`,
# which this module plans for: the first incoming pane goes beside the target tab's active pane on the side you pick; every other pane goes next to
# the already-placed pane it touched in the source tab, on the same side — so a big pane plus a stack arrives as a big pane plus a stack.
#
# Pure Python, no kitty imports (python/join-kit.py does the moving).

from typing import NamedTuple

Geom = tuple[int, int, int, int]            # left, top, right, bottom — pixels, as kitty's Window.geometry reports them
_NEEDS_YOU = {"waiting", "limited"}
SIDES = ("auto", "right", "below")


class Step(NamedTuple):
    window: int
    next_to: int | None      # an already-placed incoming window; None = the target tab's active pane
    horizontal: bool         # side by side (True) or one above the other (False)
    after: bool              # to the right of / below `next_to` (True), or left of / above it


def adjacency(a: Geom, b: Geom, tol: int) -> tuple[int, bool, bool] | None:
    """How window `b` touches window `a`: (length of the shared edge, horizontal, after). `after` means b is right of / below a. `tol` is the gap
    kitty leaves between neighbours (border + padding). None when they share no edge — a corner is not an edge."""
    al, at, ar, ab = a
    bl, bt, br, bb = b
    overlap_y = min(ab, bb) - max(at, bt)
    overlap_x = min(ar, br) - max(al, bl)
    if overlap_y > 0 and abs(bl - ar) <= tol:
        return overlap_y, True, True
    if overlap_y > 0 and abs(al - br) <= tol:
        return overlap_y, True, False
    if overlap_x > 0 and abs(bt - ab) <= tol:
        return overlap_x, False, True
    if overlap_x > 0 and abs(at - bb) <= tol:
        return overlap_x, False, False
    return None


def plan(geoms: list[tuple[int, Geom]], horizontal: bool, after: bool = True, tol: int = 80) -> list[Step]:
    """The order and placement for moving windows `geoms` [(id, geometry)] so they keep their arrangement. `horizontal`/`after` say where the FIRST one
    goes relative to the target tab's active pane. Every window is placed once, always next to one already placed."""
    if not geoms:
        return []
    geom = dict(geoms)
    rest = sorted(geoms, key=lambda g: (g[1][1], g[1][0], g[0]))             # reading order: top to bottom, left to right
    first, _g = rest.pop(0)
    steps = [Step(first, None, horizontal, after)]
    placed = [first]
    while rest:
        choice = None                                                         # (index in rest, placed window, horizontal, after)
        for i, (wid, g) in enumerate(rest):
            best = None
            for pid in placed:
                adj = adjacency(geom[pid], g, tol)
                if adj and (best is None or adj[0] > best[0]):
                    best = (adj[0], pid, adj[1], adj[2])
            if best is not None:
                choice = (i, best[1], best[2], best[3])
                break
        if choice is None:                                                    # nothing left touches what is in place: alternate off the last one
            wid, _g = rest.pop(0)
            steps.append(Step(wid, placed[-1], not steps[-1].horizontal, True))
        else:
            i, pid, h, a = choice
            wid, _g = rest.pop(i)
            steps.append(Step(wid, pid, h, a))
        placed.append(wid)
    return steps


def auto_side(width: int, height: int) -> str:
    """Where the first incoming pane goes when you do not say: a wide pane is split to the right, a tall one below."""
    return "right" if width >= height else "below"


def side_flags(side: str) -> tuple[bool, bool]:
    """(horizontal, after) for a side name."""
    return {"right": (True, True), "below": (False, True), "left": (True, False), "above": (False, False)}.get(side, (True, True))


def rows(tabs: list[dict], source_tab: int) -> list[dict]:
    """The picker's rows: every tab except the one being moved, tabs that need you first. Each `tabs` entry is
    {"os": OS-window id, "id": tab id, "title", "cwd", "panes": count, "state": agent state or ""}."""
    ref_os = next((t["os"] for t in tabs if t["id"] == source_tab), tabs[0]["os"] if tabs else 0)
    out = [dict(t, other_window=t["os"] != ref_os) for t in tabs if t["id"] != source_tab]
    out.sort(key=lambda r: 0 if r.get("state") in _NEEDS_YOU else 1)          # stable: the rest keep their order
    return out


def row_budget(room: int, title: int, count: int, gap: int = 3, floor: int = 6) -> tuple[int, int, int]:
    """Cells for (title, pane count incl. its gap, folder) in a picker row `room` cells wide — 0 means leave it out. The title is who the tab is, so it is
    never dropped (it shares at most half the row when it competes); the folder needs `floor` cells to say anything; the count is the first thing to go."""
    if room < 8:
        return min(title, max(0, room)), 0, 0
    t = min(title, max(8, room // 2))
    left = room - t
    c = count + gap if left - (count + gap) - gap >= floor else 0
    f = left - c - gap
    return t, c, (f if f >= floor else 0)


def filter_rows(rows_: list[dict], query: str) -> list[dict]:
    """Rows matching every word of `query` in the title, folder or state (any order, any case)."""
    words = query.lower().split()
    if not words:
        return list(rows_)
    return [r for r in rows_ if all(w in " ".join((r.get("title", ""), r.get("cwd", ""), r.get("state", ""))).lower() for w in words)]


class Picker:
    """The picker's keyboard state, kept pure so the keys can be tested."""

    def __init__(self, n_rows: int = 0):
        self.n_rows = n_rows
        self.index = 0
        self.query = ""
        self.side = "auto"
        self.scope = "tab"

    def move(self, delta: int) -> None:
        self.index = (self.index + delta) % self.n_rows if self.n_rows > 0 else 0

    def cycle_side(self) -> None:
        self.side = SIDES[(SIDES.index(self.side) + 1) % len(SIDES)]

    def toggle_scope(self) -> None:
        self.scope = "pane" if self.scope == "tab" else "tab"

    def type(self, text: str) -> None:
        self.query += text
        self.index = 0

    def backspace(self) -> None:
        self.query = self.query[:-1]
        self.index = 0
