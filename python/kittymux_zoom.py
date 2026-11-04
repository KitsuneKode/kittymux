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


def active_layout(ls) -> str:
    """Layout name of the focused OS window's active tab, else ""."""
    rows = list(ls or [])
    focused = [o for o in rows if o.get("is_focused")]
    for ow in focused or rows:
        for tab in ow.get("tabs") or []:
            if tab.get("is_active"):
                return str(tab.get("layout") or "")
    return ""


def zoom_actions(layout: str | None) -> tuple[tuple[str, str, str], ...]:
    """Remote-control actions for this layout. Empty on stack (the pane already fills the tab)."""
    name = (layout or "").split(":", 1)[0].strip().lower()
    if name == "stack":
        return ()
    return ZOOM


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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
