"""Progress a program reports with OSC 9;4 (kitty ≥ 0.42 keeps it per window), as the vertical bar draws it.

A hairline under the tab's last line runs from the left as far as the work has got: the accent while it runs, the
waiting colour when paused, the alert colour (whole width) on an error, the whole width when the amount is unknown.
The percent takes the tab number's place. Pure: the bar hands in the tab and a window lookup.

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


def from_ls(tab: dict, windows: list) -> tuple[str, int] | None:
    """The same answer as `of_tab`, from a `kitty @ ls` tab and its windows.

    A window may carry `progress: {state, percent}`. When the tab omits the counters, they are derived the way kitty
    does: only `set` and `paused` windows count toward the average. No last-focused window means no progress."""
    from types import SimpleNamespace
    by_id = {}
    derived_n, derived_total = 0, 0
    for w in windows or []:
        if not isinstance(w, dict):
            continue
        prog = w.get("progress") if isinstance(w.get("progress"), dict) else None
        if prog and prog.get("state"):
            state, pct = str(prog.get("state")), int(prog.get("percent") or 0)
            by_id[w.get("id")] = SimpleNamespace(progress=SimpleNamespace(state=SimpleNamespace(name=state), percent=pct))
            if state in ("set", "paused"):
                derived_n += 1
                derived_total += pct
        else:
            by_id[w.get("id")] = SimpleNamespace(progress=None)
    wid = int(tab.get("last_focused_window_with_progress_id") or 0)
    if not wid:
        return None
    n = tab.get("num_of_windows_with_progress")
    total = tab.get("total_progress")
    if n is None:
        n, total = derived_n, derived_total
    stub = SimpleNamespace(num_of_windows_with_progress=n or 0, total_progress=total or 0,
                           last_focused_window_with_progress_id=wid)
    return of_tab(stub, by_id)


def save_reports(path, reports) -> None:
    """Write `{tab id: [state, percent]}` for states the bar draws. Atomic replace, mode 0600, directory 0700."""
    import json
    import os
    from pathlib import Path
    clean = {}
    for key, value in (reports or {}).items():
        try:
            tid = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, (tuple, list)) and len(value) == 2 and value[0] in TINT:
            clean[str(tid)] = [value[0], int(value[1])]
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = dest.with_name(dest.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(clean).encode())
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, dest)


def load_reports(path) -> dict:
    """`{tab id: (state, percent)}`. A missing or unreadable file is no progress, not an error."""
    import json
    from pathlib import Path
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        try:
            tid = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] in TINT:
            out[tid] = (value[0], int(value[1]))
    return out


def label(state: str, pct: int) -> str:
    """The short text in the tab number's place."""
    if state == "error":
        return "failed"
    if state == "indeterminate":
        return "…"
    return f"{pct}%"
