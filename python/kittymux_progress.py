"""Progress a program reports with OSC 9;4 (kitty ≥ 0.42 keeps it per window), as the vertical bar draws it.

The tab's card fills from the left like a progress bar (Rex's tab progress): a soft tint of the accent while it runs,
the waiting colour when paused, the alert colour on an error, a faint full tint when the amount is unknown. The
percent takes the tab number's place. Pure: the bar hands in the tab and a window lookup.

    printf '\\e]9;4;1;42\\e\\\\'     # 42 %          (0 clears, 2 error, 3 indeterminate, 4 paused)
"""

# Tint strength of the fill over the card, per state.
TINT = {"set": 0.24, "paused": 0.24, "error": 0.28, "indeterminate": 0.12}


def of_window(window) -> tuple[str, int] | None:
    """(state, percent) for one pane's OSC 9;4 progress, else None."""
    progress = getattr(window, "progress", None)
    if progress is None:
        return None
    state = getattr(getattr(progress, "state", None), "name", "unset")
    if state not in TINT:
        return None
    if state == "indeterminate":
        return state, 0
    pct = int(getattr(progress, "percent", 0) or 0)
    return state, max(0, min(100, pct))


def of_tab(tab, windows) -> tuple[str, int] | None:
    """(state, percent) for a tab with progress, else None. `windows` maps a window id to kitty's Window. With
    several windows reporting, the percent is their mean (kitty's own total) and the state the last focused one's."""
    n = getattr(tab, "num_of_windows_with_progress", 0) or 0
    wid = getattr(tab, "last_focused_window_with_progress_id", 0) or 0
    # kitty counts only set/paused windows in `n` (Tab.update_progress), yet makes an error or indeterminate window the
    # last focused one with progress: decide by that window, and use `n` only to average the amount
    if not wid:
        return None
    progress = getattr(windows.get(wid), "progress", None)
    state = getattr(getattr(progress, "state", None), "name", "unset")
    if state not in TINT:
        return None
    if n > 1 or (n == 1 and state not in ("set", "paused")):
        pct = int((getattr(tab, "total_progress", 0) or 0) / n)
    else:
        pct = int(getattr(progress, "percent", 0) or 0)
    return state, max(0, min(100, pct))


def fill_cells(width: int, state: str, pct: int) -> int:
    """How many of `width` cells the fill covers: all of them when the amount is unknown, at least one once started."""
    if width <= 0:
        return 0
    if state == "indeterminate":
        return width
    if state == "error":
        return width
    if pct <= 0:
        return 0
    return max(1, min(width, round(width * pct / 100)))


def label(state: str, pct: int) -> str:
    """The short text in the tab number's place."""
    if state == "error":
        return "failed"
    if state == "indeterminate":
        return "…"
    return f"{pct}%"
