"""kittymux quiet — mute and snooze (pure: no kitty imports; unit-tested).

`kittymux notify mute 1h` is one file (`notify-mute-until`: the end time). `kittymux snooze 2h` quiets ONE window and is stored in `snoozes-<kitty pid>.json` in the private
state dir — deliberately NOT a window user variable: any program in a window can set its own user variables with an escape sequence, so an agent (or a file you `cat`) could
silence the very popup that tells you it wants something. Both only hold back the interruption (popup, bell); every event still reaches the inbox.
"""

from __future__ import annotations

import json
import os
import time

MAX_SPAN_S = 30 * 86400


def mute_path(state_dir: str) -> str:
    return os.path.join(state_dir, "notify-mute-until")


def snooze_path(state_dir: str, kitty_pid: int) -> str:
    return os.path.join(state_dir, f"snoozes-{int(kitty_pid)}.json")


def _atomic_private(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _valid_until(value, now: float) -> float | None:
    """An end time in the future and within MAX_SPAN_S, else None (a corrupt or absurd value never silences anything for good)."""
    try:
        until = float(value)
    except (TypeError, ValueError):
        return None
    return until if now < until <= now + MAX_SPAN_S + 60 else None


def mute_until(state_dir: str, now: float | None = None) -> float | None:
    now = time.time() if now is None else now
    try:
        with open(mute_path(state_dir), encoding="utf-8") as f:
            return _valid_until(f.read().strip(), now)
    except OSError:
        return None


def set_mute(state_dir: str, span_s: float, now: float | None = None) -> float:
    now = time.time() if now is None else now
    until = now + min(max(span_s, 1.0), MAX_SPAN_S)
    _atomic_private(mute_path(state_dir), str(until))
    return until


def clear_mute(state_dir: str) -> None:
    try:
        os.unlink(mute_path(state_dir))
    except OSError:
        pass


def load_snoozes(state_dir: str, kitty_pid: int, now: float | None = None) -> dict:
    """{window id (str): end time} of the snoozes still running for this kitty."""
    now = time.time() if now is None else now
    try:
        with open(snooze_path(state_dir, kitty_pid), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): u for k, v in data.items() if str(k).isdigit() and (u := _valid_until(v, now)) is not None}


def set_snooze(state_dir: str, kitty_pid: int, window_id, span_s: float, now: float | None = None) -> float:
    now = time.time() if now is None else now
    snoozes = load_snoozes(state_dir, kitty_pid, now)
    until = now + min(max(span_s, 1.0), MAX_SPAN_S)
    snoozes[str(int(window_id))] = until
    _atomic_private(snooze_path(state_dir, kitty_pid), json.dumps(snoozes))
    return until


def clear_snooze(state_dir: str, kitty_pid: int, window_id, now: float | None = None) -> None:
    snoozes = load_snoozes(state_dir, kitty_pid, now)
    snoozes.pop(str(int(window_id)), None)
    _atomic_private(snooze_path(state_dir, kitty_pid), json.dumps(snoozes))


# ── mute: one agent, until you unmute it ─────────────────────────────────────
# `kittymux mute`, `m` or a right-click in the panel. A muted agent keeps running and stays listed (with a quiet bell-slash), but it sends no
# popup or bell and never counts as "needs you". Kept in the private state dir per kitty (window ids are only unique within one kitty), for the
# same reason as a snooze: a window variable could be set by the program in the window itself.

def mutes_path(state_dir: str, kitty_pid: int) -> str:
    return os.path.join(state_dir, f"mutes-{int(kitty_pid)}.json")


def load_mutes(state_dir: str, kitty_pid: int) -> set:
    """The window ids (str) muted in this kitty. A missing or bad file mutes nothing."""
    try:
        with open(mutes_path(state_dir, kitty_pid), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return set()
    if not isinstance(data, list):
        return set()
    return {str(w) for w in data if str(w).isdigit()}


def _save_mutes(state_dir: str, kitty_pid: int, ids: set) -> None:
    _atomic_private(mutes_path(state_dir, kitty_pid), json.dumps(sorted(ids, key=int)))


def set_muted(state_dir: str, kitty_pid: int, window_id, on: bool) -> bool:
    """Mute or unmute one window. True when that changed anything."""
    ids = load_mutes(state_dir, kitty_pid)
    wid = str(int(window_id))
    if (wid in ids) == bool(on):
        return False
    (ids.add if on else ids.discard)(wid)
    _save_mutes(state_dir, kitty_pid, ids)
    return True


def is_muted(state_dir: str, kitty_pid: int, window_id) -> bool:
    return str(window_id) in load_mutes(state_dir, kitty_pid)


def prune_mutes(state_dir: str, kitty_pid: int, live) -> None:
    """Forget the mutes of windows that are gone (a new window may reuse nothing, but the file should not grow)."""
    ids = load_mutes(state_dir, kitty_pid)
    keep = ids & {str(w) for w in live}
    if keep != ids:
        _save_mutes(state_dir, kitty_pid, keep)


def tab_windows(ls: list, spec: str, here=None):
    """(tab title, [window ids]) for `kittymux mute [TAB]`, from `kitty @ ls`. TAB: empty = the tab holding window `here` (where the command
    runs); a number = that tab of the focused OS window (1-based, as the bar counts one session); `id:N` = kitty's tab id; else the first
    tab whose title contains it. The windows are the tab's agent windows, or all of them when none runs an agent. None when nothing matches."""
    import kittymux_agents
    spec = (spec or "").strip()
    tabs = [(osw, t) for osw in (ls or []) for t in (osw.get("tabs") or [])]
    found = None
    if not spec:
        if here is not None:
            found = next((t for _o, t in tabs if any(str(w.get("id")) == str(here) for w in t.get("windows") or [])), None)
    elif spec.isdigit():
        osw = next((o for o in ls or [] if o.get("is_focused")), None) or next((o for o in ls or [] if o.get("last_focused")), None)
        own = (osw or {}).get("tabs") or []
        n = int(spec)
        found = own[n - 1] if 1 <= n <= len(own) else None
    elif spec.startswith("id:") and spec[3:].isdigit():
        found = next((t for _o, t in tabs if str(t.get("id")) == spec[3:]), None)
    else:
        low = spec.lower()
        found = next((t for _o, t in tabs if low in str(t.get("title") or "").lower()), None)
    if found is None:
        return None
    wins = found.get("windows") or []
    agents = [int(w["id"]) for w in wins if kittymux_agents.identify(w)[0]]
    return str(found.get("title") or ""), agents or [int(w["id"]) for w in wins]


def quiet_reason(state_dir: str, kitty_pid: int, window_id, now: float | None = None) -> str | None:
    """Why popups and bells are held back for this window right now, or None. Static text (no clocks): it is published in decision logs."""
    now = time.time() if now is None else now
    if mute_until(state_dir, now) is not None:
        return "suppressed: muted (kittymux notify unmute); the event is in the inbox"
    if str(window_id) in load_mutes(state_dir, kitty_pid):
        return "suppressed: this agent is muted (kittymux unmute); the event is in the inbox"
    if str(window_id) in load_snoozes(state_dir, kitty_pid, now):
        return "suppressed: this window is snoozed (kittymux snooze --clear); the event is in the inbox"
    return None
