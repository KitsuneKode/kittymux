"""Zoom the focused pane so it fills the tab, on both axes.

kitty's plain `layout_action maximize` is horizontal only (`args or ('horizontal',)` in the splits
layout). A second call with `vertical` covers a top/bottom split. Pressing the same chord again
toggles each axis back.

The stack layout shows only the active pane, so it already fills the tab. Its `layout_action`
returns nothing, and kitty rings the bell for that. Zoom therefore sends no action on stack.
"""
from __future__ import annotations

import sys

ZOOM = (("layout_action", "maximize", "horizontal"), ("layout_action", "maximize", "vertical"))


def focused_os(ls) -> dict | None:
    """The OS window zoom should read. The focused one, else the last-focused one (what an unmatched
    kitty action would hit), else the first listed."""
    rows = [o for o in (ls or []) if isinstance(o, dict)]
    focused = [o for o in rows if o.get("is_focused")]
    if focused:
        return focused[0]
    last = [o for o in rows if o.get("last_focused")]
    return (last or rows or [None])[0]


def active_tab(osw) -> dict | None:
    for tab in (osw or {}).get("tabs") or []:
        if isinstance(tab, dict) and tab.get("is_active"):
            return tab
    return None


def active_layout(ls) -> str:
    """Layout name of the focused OS window's active tab, else ""."""
    return str((active_tab(focused_os(ls)) or {}).get("layout") or "")


def focused_window_id(ls) -> int | None:
    """The window the layout was read from, so the actions can be matched to it."""
    tab = active_tab(focused_os(ls))
    wins = [w for w in (tab or {}).get("windows") or [] if isinstance(w, dict)]
    for w in wins:
        if w.get("is_focused") or w.get("is_active"):
            wid = w.get("id")
            return wid if isinstance(wid, int) else None
    if wins and isinstance(wins[0].get("id"), int):
        return wins[0]["id"]
    return None


def maximized_axes(tab, window_id: int | None) -> set[str]:
    """Axes kitty already has maximized for this window's group (`layout_state.maximized`, kitty 0.49.2).

    The id there is the window-group id (`splits.py` keys `_maximized_biases` by `active_group.id`)."""
    if window_id is None or not isinstance(tab, dict):
        return set()
    group = window_id
    for g in tab.get("groups") or []:
        if isinstance(g, dict) and window_id in (g.get("windows") or []):
            gid = g.get("id")
            if isinstance(gid, int):
                group = gid
            break
    axes = set()
    state = tab.get("layout_state") if isinstance(tab.get("layout_state"), dict) else {}
    for entry in state.get("maximized") or []:
        if isinstance(entry, dict) and entry.get("window_id") == group:
            axes.add("horizontal" if entry.get("is_horizontal") else "vertical")
    return axes


def zoom_actions(layout: str | None, maximized=()) -> tuple[tuple[str, str, str], ...]:
    """Remote-control actions for this layout. Empty on stack (the pane already fills the tab).

    kitty toggles each axis on its own (`splits.py` `layout_action` maximize). An axis that is
    already maximized is left alone, so a half-zoomed pane reaches a full zoom instead of swapping
    which axis is maximized. Both axes already maximized: toggle both off (press again to restore)."""
    name = (layout or "").split(":", 1)[0].strip().lower()
    if name == "stack":
        return ()
    have = {a for a in maximized if a in ("horizontal", "vertical")}
    if have == {"horizontal", "vertical"}:
        return ZOOM
    missing = tuple(a for a in ("horizontal", "vertical") if a not in have)
    return tuple(("layout_action", "maximize", a) for a in missing)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["layout"]:
        import json
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError:
            return 0
        sys.stdout.write(active_layout(data))
        return 0
    if args[:1] == ["actions"]:
        layout = args[1] if len(args) > 1 else ""
        for row in zoom_actions(layout):
            sys.stdout.write("\t".join(row) + "\n")
        return 0
    if args[:1] == ["plan"]:
        import json
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError:
            return 0
        tab = active_tab(focused_os(data))
        wid = focused_window_id(data)
        sys.stdout.write(("" if wid is None else str(wid)) + "\n")
        for row in zoom_actions(active_layout(data), maximized_axes(tab, wid)):
            sys.stdout.write("\t".join(row) + "\n")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
