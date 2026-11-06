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


def _quiet(raw, row) -> str:
    """A row's state for a space's roll-up: a muted question counts as nothing (it never asks for you)."""
    state = _state(raw)
    return "idle" if getattr(row, "muted", False) and state in ("waiting", "limited") else state


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


def facts(row) -> str:
    """The quiet facts after a tab's state word: its open pull request and the first ports it listens on."""
    out = []
    pr = getattr(row, "pr", "") or ""
    if pr:
        out.append(str(pr))
    ports = [int(p) for p in (getattr(row, "ports", ()) or ()) if str(p).isdigit()][:2]
    if ports:
        out.append(" ".join(f":{p}" for p in ports))
    return " \u00b7 ".join(out)


def first_waiting(model):
    """(row, pane) of the first tab or pane that asks for you, for the header's Needs-you chip; (-1, -1) when none."""
    for agent in model.agents:
        if agent.state in ("waiting", "limited") and not agent.muted:
            return agent.row, -1
        for child in agent.children:
            if child.state in ("waiting", "limited") and not child.muted:
                return child.row, child.pane
    return -1, -1


def _space_name(project: str) -> str:
    return "Home" if project == "~" else project


def to_model(snap, sel: int, hover, host: str, session: str, project_of=None):
    """Machine → Space → Agents. A space is a named session; with none, a repo (`project_of(cwd)`) heads the run of tabs
    that sit in it, in tab order (never re-sorted, so j/k still walk the list top to bottom). Closed splits stay one row:
    hover never opens them."""
    dp = _px()
    by_project = project_of is not None and not any(it.kind == "header" for it in snap.items)
    by_state = bool(getattr(snap, "by_state", False))
    hover_row, hover_pane = _hover_pair(hover)
    spaces, agents = [], []
    space = None
    members: list = []

    def close_space() -> None:
        if space is None:
            return
        current = next((r.branch for r in members if r.current and r.branch), "")
        first = next((r.branch for r in members if r.branch), "")
        space.branch = "" if by_state else (current or first)     # a state group spans repos: a branch would say nothing
        states = [_quiet(r.status, r) for r in members]
        for r in members:
            states.extend(_quiet(pd.state, pd) for pd in r.pane_rows if pd.state and pd.state != _state(r.status))
        space.state = _loudest(states) if members else ""
        space.counts = dp.state_counts(_quiet(r.status, r) for r in members)

    for it in snap.items:
        if it.kind == "header":
            close_space()
            space = dp.Space(it.label, current=bool(it.current))
            spaces.append(space)
            members = []
        elif it.kind == "row":
            row = snap.rows[it.row]
            if by_project:
                try:
                    name = _space_name(project_of(getattr(row, "cwd", "") or "") or "")
                except Exception:
                    name = ""
                if name and (space is None or space.name != name):
                    close_space()
                    space = dp.Space(name)
                    spaces.append(space)
                    members = []
                if name and row.current:
                    space.current = True
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
                progress_state=pst, can_open=len(row.pane_rows) >= 2, opened=False, row=it.row,
                meta=facts(row), panes=max(1, int(getattr(row, "panes", 1) or 1)), muted=bool(getattr(row, "muted", False))))
        elif it.kind == "pane" and agents:
            parent = agents[-1]
            parent.opened = True
            pane = snap.rows[it.row].pane_rows[it.pane]
            picked = hover_row == it.row and hover_pane == it.pane
            parent.children.append(dp.Agent(
                pane.title or "pane", pane.agent or "shell", _brand(pane.agent), parent.space,
                state=_state(pane.state), active=picked, selected=picked, row=it.row, pane=it.pane,
                muted=bool(getattr(pane, "muted", False))))
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
