"""Panel keyboard focus: summoned (exclusive) or docked (on-demand). Pure; no kitty imports.

A docked layer-shell panel takes keys only after a click (`on-demand`). Summoning it from a chord must
work at once, so it asks the compositor for an exclusive keyboard grab, and gives the grab back as soon as the
user is done (Esc, a jump, Q) — and unconditionally after IDLE_DOCK_S without a keypress, so a forgotten
summon can never trap typing.
"""
from __future__ import annotations

SUMMONED = "summoned"      # focus_policy=exclusive: every key goes to the panel
DOCKED = "docked"          # focus_policy=on-demand: visible, keys only after a click

POLICY = {SUMMONED: "exclusive", DOCKED: "on-demand"}
IDLE_DOCK_S = 12.0


def idle_limit(env: str | None) -> float:
    """`KITTYMUX_PANEL_IDLE_S`, clamped to 3..300 s; anything unreadable is the default. (Short limits exist for tests.)"""
    try:
        v = float(env) if env else IDLE_DOCK_S
    except (TypeError, ValueError):
        return IDLE_DOCK_S
    return IDLE_DOCK_S if v != v else min(300.0, max(3.0, v))     # NaN is not a number of seconds


def parse_mode(text: str | None) -> str:
    """What a `panel-mode` file says; anything else (missing, garbage) is docked — the safe state."""
    return SUMMONED if (text or "").strip() == SUMMONED else DOCKED


def toggle_action(running, mode: str) -> str:
    """`start-summoned` | `summon` | `stop`: what the toggle chord does. `running` may be a bool or the shell's "1"/"true"."""
    if isinstance(running, str):
        running = running.strip().lower() in ("1", "true", "yes")
    if not running:
        return "start-summoned"
    return "stop" if mode == SUMMONED else "summon"


def should_dock(mode: str, last_key_t: float, now: float, limit: float = IDLE_DOCK_S) -> bool:
    """True when a summoned panel has had no key for `limit` seconds (or its clock went backwards)."""
    if mode != SUMMONED:
        return False
    return now < last_key_t or now - last_key_t >= limit


def release_on(key: str, has_query: bool) -> bool:
    """Whether this key ends a summon: Esc with no search to clear, or Q."""
    k = (key or "").upper()
    return k == "Q" or (k == "ESCAPE" and not has_query)
