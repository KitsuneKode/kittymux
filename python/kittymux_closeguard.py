"""kittymux closeguard — ask before closing an agent that is busy (Rex adoption). Pure: no kitty imports; unit-tested.

kitty's close keys are bound to `python/close-kit.py` (a no-UI kitten that runs inside kitty). Closing a pane or a tab whose agent is Working or
Needs you does not close it at once: the pane's own title bar turns into a one-line question ("Close Claude Code? It is working · ctrl+shift+w
again") and the SAME key pressed again within CONFIRM_S closes it. Anything else lets the question lapse. No dialog, no overlay, no focus change,
and no Escape to dismiss (Escape belongs to the agent: it interrupts Claude). A pane with nothing busy closes the way kitty always did.
"""

from __future__ import annotations

import sys
import time
import types

BUSY = ("working", "waiting", "limited")        # Working, or Needs you (a question, a permission, a usage limit)
CONFIRM_S = 4.0                                  # how long the question stands; a second press inside it closes
_RT_NAME = "_kittymux_close_rt"                 # one record per kitty process, kept across reloads of this module


def _rt():
    rt = sys.modules.get(_RT_NAME)
    if rt is None:
        rt = types.ModuleType(_RT_NAME)
        rt.pending = None                        # (what, target id, until (monotonic), (window ids that ask))
        rt.text = ""                             # the question the title bars show
        sys.modules[_RT_NAME] = rt
    return rt


def window_states(windows) -> dict:
    """{window id (str): (fresh verdict, agent)} for kitty windows, from the scanner's runtime record (no kitty imports).
    One copy of this rule: close-kit's keys and the pixel bar's close cross both ask it."""
    import kittymux_agents
    rt = sys.modules.get("_kittymux_scan_rt")
    hooks = (getattr(rt, "panes", (None, {}))[1] or {}) if rt is not None else {}
    verdicts = getattr(rt, "verdicts", {}) if rt is not None else {}
    now = time.monotonic()
    out = {}
    for w in windows:
        key = str(w.id)
        entry = kittymux_agents.merge_scan({key: hooks.get(key) or {}}, {key: verdicts.get(key) or {}}).get(key) or {}
        out[key] = (kittymux_agents.fresh_verdict(entry, now), entry.get("agent") or "")
    return out


def busy_windows(states: dict, window_ids) -> list:
    """The windows among `window_ids` whose agent is busy, in order. `states` maps a window id (str) to a state."""
    return [w for w in window_ids if (states.get(str(w)) or "") in BUSY]


def decide(what: str, target: int, busy: list, now: float | None = None) -> str:
    """'close' or 'ask' for a press of the close key on `target` (a window id for what='window', a tab id for 'tab')."""
    now = time.monotonic() if now is None else now
    rt = _rt()
    if not busy:
        rt.pending = None
        return "close"
    p = rt.pending
    if p and p[0] == what and p[1] == target and now < p[2]:
        rt.pending = None
        return "close"
    rt.pending = (what, int(target), now + CONFIRM_S, tuple(int(w) for w in busy))
    return "ask"


def asking(window_id, now: float | None = None) -> bool:
    """Is this window's title bar showing the close question right now?"""
    now = time.monotonic() if now is None else now
    p = _rt().pending
    return bool(p and now < p[2] and int(window_id) in p[3])


def clear() -> None:
    _rt().pending = None


def set_text(text: str, short: str = "") -> None:
    """The question in full (a pane title bar) and short (the tab's row in the bar, ~20 cells)."""
    _rt().text = str(text or "")
    _rt().short = str(short or "")


def text() -> str:
    """The standing question, for the pane title bar ('' when none)."""
    return getattr(_rt(), "text", "") if _rt().pending else ""


def short_for(window_ids, now: float | None = None) -> str:
    """The short question for a tab's row in the bar when any of its windows is asking, else ''."""
    if not any(asking(w, now) for w in window_ids):
        return ""
    return getattr(_rt(), "short", "") or getattr(_rt(), "text", "")


def short(chord: str = "") -> str:
    """The question where only ~20 cells fit (a bar row, a narrow pane). You just pressed the key, so it need not be named again."""
    return "Close? Press again"


def refresh(boss, ids) -> None:
    """Redraw what shows the question: each window's title bar and its tab bar."""
    for wid in ids:
        w = boss.window_id_map.get(int(wid))
        if w is None:
            continue
        try:
            tab = w.tabref()
            w.update_title_bar(is_active=bool(tab and tab.active_window is w))
            tm = tab.tab_manager_ref() if tab is not None else None
            if tm is not None:
                tm.mark_tab_bar_dirty()
        except Exception:
            pass


def lapse(timer_id=None) -> None:
    """The kitty timer at the end of CONFIRM_S (kittymux_timers.add): redraw the title bars that showed the question, so it goes away."""
    p = _rt().pending
    ids = p[3] if p else getattr(_rt(), "last_ids", ())
    if p and time.monotonic() >= p[2]:
        _rt().pending = None
    try:
        from kitty.fast_data_types import get_boss
        refresh(get_boss(), ids)
    except Exception:
        pass


def question(agent_label: str, state: str, chord: str, what: str = "window", others: int = 0) -> str:
    """The one line the title bar shows: "Close Claude Code? It is working · ctrl+shift+w again"."""
    doing = {"working": "it is working", "waiting": "it needs you", "limited": "it hit a limit"}.get(state, "it is busy")
    who = agent_label or "this agent"
    noun = "this tab" if what == "tab" else who
    more = f" (+{others} more)" if others else ""
    lead = f"Close {noun}? {who}{more}: {doing}" if what == "tab" else f"Close {who}? {doing[0].upper() + doing[1:]}"
    return f"{lead} · {chord} again"
