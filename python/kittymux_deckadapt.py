# kittymux deckadapt — the panel's snapshot as a pixel-deck model.
# Pure: no kitty imports. The pixel modules load only when a model is built, so a machine without cairo still runs the cell panel.

import kittymux_agents
import kittymux_progress
import kittymux_state

_STATES = ("working", "waiting", "done", "idle", "limited", "error")


def _px():
    import kittymux_deckpx as deckpx
    return deckpx


def _state(raw) -> str:
    return raw if raw in _STATES else "idle"


def _loudest(states) -> str:
    best = "idle"
    for state in states:
        if kittymux_state.PRIORITY.get(state, 0) > kittymux_state.PRIORITY.get(best, 0):
            best = state
    return best


def progress_mark(report):
    """(fraction 0..1 or None, state). 0% and an unknown report draw no hairline; error and indeterminate fill it."""
    if not report or not isinstance(report, (tuple, list)) or len(report) != 2:
        return None, ""
    state, pct = report
    if state not in kittymux_progress.TINT:
        return None, ""
    filled = kittymux_progress.fill_cells(100, state, int(pct))
    if filled <= 0:
        return None, str(state)
    return filled / 100.0, str(state)


def _hover_pair(hover) -> tuple[int, int]:
    try:
        row, pane = hover
        return int(row), int(pane)
    except (TypeError, ValueError):
        return -1, -1


def _brand(name: str) -> int:
    agent = kittymux_agents.AGENTS.get(name or "")
    return agent.brand if agent else 0


def to_model(snap, sel: int, hover, host: str, session: str):
    """Spaces, agents and their open panes. Closed splits stay one row: hover never opens them."""
    dp = _px()
    hover_row, hover_pane = _hover_pair(hover)
    spaces, agents = [], []
    space = None
    members: list = []

    def close_space() -> None:
        if space is None:
            return
        current = next((r.branch for r in members if r.current and r.branch), "")
        first = next((r.branch for r in members if r.branch), "")
        space.branch = current or first
        space.state = _loudest(_state(r.status) for r in members) if members else ""

    for it in snap.items:
        if it.kind == "header":
            close_space()
            space = dp.Space(it.label, current=bool(it.current))
            spaces.append(space)
            members = []
        elif it.kind == "row":
            row = snap.rows[it.row]
            if space is not None:
                members.append(row)
                if it.row == sel:
                    space.active = True
            frac, pst = progress_mark(getattr(row, "progress", None))
            on_pane = hover_row == it.row and hover_pane >= 0
            picked = it.row == sel and not on_pane
            agents.append(dp.Agent(
                row.title or row.raw_title or "tab", row.agent or "shell", _brand(row.agent),
                space.name if space is not None else "", age=row.age or "", state=_state(row.status),
                progress=frac, active=picked, current=bool(row.current), selected=picked,
                progress_state=pst, can_open=len(row.pane_rows) >= 2, opened=False, row=it.row))
        elif it.kind == "pane" and agents:
            parent = agents[-1]
            parent.opened = True
            pane = snap.rows[it.row].pane_rows[it.pane]
            picked = hover_row == it.row and hover_pane == it.pane
            parent.children.append(dp.Agent(
                pane.title or "pane", pane.agent or "shell", _brand(pane.agent), parent.space,
                state=_state(pane.state), active=picked, selected=picked, row=it.row, pane=it.pane))
    close_space()
    for agent in agents:
        if any(child.selected for child in agent.children):
            agent.selected = agent.active = False
        elif agent.row == sel and not agent.children:
            agent.selected = agent.active = True
    query = getattr(snap, "query", "") or ""
    empty = empty_hint = ""
    if not agents:
        if query:
            empty, empty_hint = f"No tab matches \u201c{query[:24]}\u201d", "esc clears the search"
        else:
            empty, empty_hint = "No tabs yet", "open a tab and it shows up here"
    return dp.Model(session or "kitty", host or "this machine", spaces, agents, empty, empty_hint)


def hit_target(model, kind: str, index: int):
    """(row, pane) for a hit. A pane is -1 on an agent or its chevron."""
    if kind in ("agent", "toggle"):
        if 0 <= index < len(model.agents):
            return model.agents[index].row, -1
        return -1, -1
    if kind == "pane":
        flat = 0
        for agent in model.agents:
            for child in agent.children:
                if flat == index:
                    return agent.row, child.pane
                flat += 1
    return -1, -1


def selected_target(model):
    """('agent', index) or ('pane', flat index) for the keyboard ring, else None."""
    found = None
    flat = 0
    for i, agent in enumerate(model.agents):
        if agent.selected:
            found = ("agent", i)
        for child in agent.children:
            if child.selected:
                found = ("pane", flat)
            flat += 1
    return found


def graphics_verdict(reply, timed_out: bool) -> str:
    """'ok' when kitty answers the probe, 'no' on a refusal or a timeout, 'wait' for anything else. Never blocks."""
    text = reply.decode("ascii", "replace") if isinstance(reply, (bytes, bytearray)) else str(reply or "")
    if text.startswith("G"):
        text = text[1:]
    if "i=999" in text:
        return "ok" if text.rstrip().endswith("OK") else "no"
    if timed_out:
        return "no"
    return "wait"
