"""The pixel tab bar's grouping (plan 015, direction A). Pure: no kitty imports.

Tabs are grouped by project. Groups come in the order their first tab appears and rows keep kitty's order, so nothing
moves under the pointer when a state changes; what needs you shows through the row itself and the header count.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_BRANCHES = frozenset({"main", "master"})
COLLAPSE_AFTER = 6                 # a group of only settled tabs larger than this shows just its header and a count
SETTLED = frozenset({"", "idle"})


@dataclass(frozen=True)
class Row:
    """One tab as the bar shows it. `mark` is an assets/icons basename ("" draws the shell prompt); `tint` the brand
    colour for an agent's tile (None: a neutral tile)."""
    tab_id: int
    title: str
    project: str
    branch: str = ""
    state: str = ""                # working | waiting | done | limited | error | idle | ""
    active: bool = False
    mark: str = ""
    tint: int | None = None
    meta: str = ""                 # the second line: the question, what failed, the branch and diff; "" for none
    meta_tone: str = ""            # "" | "waiting" | "alert" | "working"
    age: str = ""
    path: str = ""                 # a plain shell's folder, shown faint after its name
    progress: tuple | None = None  # (state, percent) from OSC 9;4
    muted: bool = False
    stack: tuple = ()              # the marks of the other agents in this tab's splits, most important first
    phase: int = 0                 # the working loader's frame (steps with kittymux_agents.SPINNER_FPS; 0 when motion is off)


@dataclass(frozen=True)
class Group:
    project: str
    branch: str
    rows: tuple = field(default_factory=tuple)
    hidden: int = 0                # rows folded away (the header says how many)


def settled(r: Row) -> bool:
    return r.state in SETTLED


def reporting(r: Row) -> bool:
    """The tab shows OSC 9;4 progress: something is running there even with no agent, so its group stays open."""
    return r.progress is not None


def group(rows, *, collapse_after: int = COLLAPSE_AFTER, expanded: frozenset = frozenset()) -> list[Group]:
    order: list[str] = []
    members: dict[str, list[Row]] = {}
    for r in rows:
        if r.project not in members:
            order.append(r.project)
            members[r.project] = []
        members[r.project].append(r)
    out = []
    for project in order:
        rs = members[project]
        branches = {r.branch for r in rs}
        branch = next(iter(branches)) if len(branches) == 1 else ""
        if branch in DEFAULT_BRANCHES:
            branch = ""
        fold = (len(rs) > collapse_after and project not in expanded
                and all(settled(r) for r in rs) and not any(r.active or reporting(r) for r in rs))
        out.append(Group(project, branch, () if fold else tuple(rs), len(rs) if fold else 0))
    return out


def step(groups, active_tab_id: int, direction: int):
    """The tab ctrl+tab (direction 1) or ctrl+shift+tab (-1) goes to: the next row the bar DRAWS, wrapping, never one folded
    away (a folded group has no rows). An active tab that is not drawn steps to the first or the last row. None when there is
    nowhere else to go."""
    ids = [r.tab_id for g in groups for r in g.rows]
    if not ids or ids == [active_tab_id]:
        return None
    if active_tab_id not in ids:
        return ids[0] if direction > 0 else ids[-1]
    return ids[(ids.index(active_tab_id) + (1 if direction > 0 else -1)) % len(ids)]


def needs_you(groups) -> int:
    return sum(1 for g in groups for r in g.rows if r.state == "waiting" and not r.muted)
