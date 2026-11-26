"""What a right-click on a tab offers besides a look: the peek card's action row (python/peek-kit.py). The card returns
`<action>:<tab id>` as its answer and kitty runs it here, in its own process (the kitten's handle_result), so every
action works on THAT tab, never on whatever happens to be focused.

- rename: activate the tab and open kitty's own rename prompt for it
- split: activate the tab and split its active pane to the right, in that pane's folder
- mute: mute every window of the tab, or unmute them when all are muted already (kittymux_quiet, the `kittymux mute` store)
- close: the close cross's rule (kittymux_pxbar.close_tab): a busy agent asks on its row first
"""
from __future__ import annotations

import os

ACTIONS = (("r", "rename"), ("s", "split"), ("m", "mute"), ("x", "close"))
NAMES = frozenset(name for _, name in ACTIONS)


def key_action(key: str) -> str:
    """The action a key on the card runs, or ''."""
    k = (key or "").lower()
    return next((name for ch, name in ACTIONS if ch == k), "")


def answer(action: str, tab_id: int) -> str:
    return f"{action}:{int(tab_id)}" if action in NAMES else ""


def parse(text: str) -> tuple[str, int] | None:
    """(action, tab id) from the card's answer, or None for anything else (the card closed without an action)."""
    action, _, tid = (text or "").strip().partition(":")
    if action not in NAMES or not tid.isdigit() or int(tid) <= 0:
        return None
    return action, int(tid)


def toggle_mute(window_ids, state_dir: str, kitty_pid: int) -> bool:
    """Mute every window, or unmute them all when every one is muted already. Returns the new state (True = muted)."""
    import kittymux_quiet as Q
    ids = [str(w) for w in window_ids]
    muted = Q.load_mutes(state_dir, kitty_pid)
    on = not (ids and all(w in muted for w in ids))
    for w in ids:
        Q.set_muted(state_dir, kitty_pid, w, on)
    return on


def _live_windows(boss, tab) -> list:
    """The tab's windows that are still open. The card opens over the active tab's active window, and kitty runs the kitten's
    handle_result before it takes the card's window out of the tab (it is already gone from boss.window_id_map): on the tab
    you are on, that dying window must not be muted, split or renamed."""
    known = getattr(boss, "window_id_map", None)
    return [w for w in tab if known is None or known.get(w.id) is w]


def _pane(boss, tab, target_window_id=None):
    """The pane an action on the tab means: the window the card was opened over when it is in this tab (kitty passes it),
    else its active window, or, when that is the card itself, the one you were in last."""
    live = _live_windows(boss, tab)
    target = getattr(boss, "window_id_map", {}).get(target_window_id) if target_window_id else None
    if target is not None and target in live:
        return target
    active = tab.active_window
    if active in live:
        return active
    return max(live, key=lambda w: getattr(w, "last_focused_at", 0.0), default=None)


def run(boss, text: str, state_dir: str | None = None, kitty_pid: int | None = None, target_window_id: int | None = None) -> bool:
    """Run the card's answer inside kitty. False when there was nothing to do (no action, or the tab is gone)."""
    got = parse(text)
    if got is None:
        return False
    action, tab_id = got
    tab = boss.tab_for_id(tab_id)
    if tab is None:
        return False
    if action == "close":
        import kittymux_pxbar
        # the card has closed by the time the question shows: a second x would go to the pane. The way to confirm is the way
        # you asked: open the card again and press x (within the guard's window)
        kittymux_pxbar.close_tab(boss, tab_id, again="right-click it and press x")
        return True
    if action == "mute":
        if state_dir is None:
            import kittymux_layout
            state_dir = kittymux_layout.state_dir()
        toggle_mute([w.id for w in _live_windows(boss, tab)], state_dir, os.getpid() if kitty_pid is None else kitty_pid)
        try:
            import kittymux_scan
            tm = boss.os_window_map.get(tab.os_window_id)
            if tm is not None:
                kittymux_scan.refresh_bar(tm)
        except Exception:
            pass
        return True
    tm = getattr(boss, "os_window_map", {}).get(tab.os_window_id)
    if tm is not None:                    # the tab's own OS window: boss.set_active_tab works on the focused one only
        tm.set_active_tab(tab)
    else:
        boss.set_active_tab(tab)          # the user asked for this tab: it is where the prompt or the new pane appears
    window = _pane(boss, tab, target_window_id)
    if window is None:
        return False
    if action == "rename":
        boss.combine("set_tab_title", window_for_dispatch=window)
    elif action == "split":
        boss.combine("launch --location=vsplit --cwd=current", window_for_dispatch=window)
    return True
