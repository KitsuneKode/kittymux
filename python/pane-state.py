# kittymux pane-state watcher — per-window activity for the agent picker.
#
# Loaded via `watcher` in the rendered keys conf. Runs inside the kitty
# process; callbacks receive (boss, window, data) with the real Window.
#
# Writes $KITTYMUX_STATE/panes-<pid>.json:
#   { "<wid>": {title, ts_title, ts_cmd, cmd, running, focused, at_prompt,
#                status, ts_status, msg} }
#
# `status` (working|waiting|done|idle) comes from the `kittymux_status` window user
# variable, set by bin/mux-status from agent hooks (see README). It outranks the
# "title went quiet" heuristic. `done` clears to `idle` once the window is focused.

import json
import os
import shutil
import subprocess
import time

_STATE_DIR = os.environ.get("KITTYMUX_STATE") or os.path.join(
    os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
    "kittymux")
# Window ids are per kitty process — namespace by pid so multiple
# --single-instance groups don't collide (socket: /tmp/mykitty-<pid>).
STATE_FILE = os.path.join(_STATE_DIR, f"panes-{os.getpid()}.json")

_state = {}
_last_flush = 0.0
_FLUSH_EVERY = 0.75


def _flush(now: float, force: bool = False) -> None:
    global _last_flush
    if not force and now - _last_flush < _FLUSH_EVERY:
        return
    _last_flush = now
    tmp = STATE_FILE + ".tmp"
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


def _entry(window) -> dict:
    e = _state.get(window.id)
    if e is None:
        e = {"title": "", "ts_title": 0.0, "ts_cmd": 0.0, "cmd": "",
             "running": False, "focused": False, "at_prompt": False,
             "status": "", "ts_status": 0.0, "msg": ""}
        _state[window.id] = e
    return e


def _attach(window) -> None:
    # Windows created before this watcher loaded hold a copy of the watcher
    # lists taken at construction. Register ourselves on those too, once.
    ws = getattr(window, "watchers", None)
    if ws is None:
        return
    for lst, fn in ((ws.on_title_change, on_title_change),
                    (ws.on_set_user_var, on_set_user_var),
                    (ws.on_cmd_startstop, on_cmd_startstop),
                    (ws.on_focus_change, on_focus_change),
                    (ws.on_close, on_close)):
        if fn not in lst:
            lst.append(fn)


def on_load(boss, data) -> None:
    now = time.monotonic()
    for w in getattr(boss, "all_windows", []):
        try:
            _attach(w)
            e = _entry(w)
            e["focused"] = bool(getattr(w, "is_focused", False))
            e["at_prompt"] = bool(getattr(w, "at_prompt", False))
            e["title"] = w.title or ""
            e["ts_title"] = now  # grace: treat pre-existing panes as fresh
        except Exception:
            pass
    _flush(now, force=True)


def on_title_change(boss, window, data) -> None:
    e = _entry(window)
    e["title"] = data.get("title") or ""
    e["ts_title"] = time.monotonic()
    e["at_prompt"] = bool(getattr(window, "at_prompt", False))
    _flush(e["ts_title"])


def on_cmd_startstop(boss, window, data) -> None:
    e = _entry(window)
    e["running"] = bool(data.get("is_start"))
    e["cmd"] = data.get("cmdline") or ""
    e["ts_cmd"] = time.monotonic()
    _flush(e["ts_cmd"], force=True)


def _refresh_bar(tm) -> None:
    """Redraw a TabManager's bar now. Kitty's own refresh_active_tab_bar does both:
    re-run the draw (update_tab_bar_data) AND flag the OS window dirty — a bare dirty
    flag waits for some unrelated event to repaint."""
    tm.update_tab_bar_data()
    tm.mark_tab_bar_dirty()


def _mark_tab_bar_dirty(window) -> None:
    # Redraw the tab bar now instead of waiting for some other event to.
    try:
        _refresh_bar(window.tabref().tab_manager_ref())
    except Exception:
        pass


# ── spinner ticks ────────────────────────────────────────────────────────────
# The tab bar only redraws on kitty events, so an agent that works silently (no title
# churn) would freeze the spinner on one frame. While — and only while — some window
# has an explicit `working` status, a timer marks those tabs' bars dirty at the spinner's
# frame rate; it stops itself the moment nothing is working.
_SPIN_INTERVAL = 0.1
_spin_timer = None


def _working_windows() -> list:
    return [wid for wid, e in _state.items() if e.get("status") == "working"]


def _spin_tick(timer_id) -> None:
    global _spin_timer
    try:
        from kitty.fast_data_types import get_boss
        boss = get_boss()
        wids = _working_windows()
        if not wids:
            _stop_spinner()
            return
        seen = set()
        for wid in wids:
            w = boss.window_id_map.get(wid)
            tab = w.tabref() if w is not None else None
            tm = tab.tab_manager_ref() if tab is not None else None
            if tm is not None and id(tm) not in seen:   # once per OS window per tick
                seen.add(id(tm))
                _refresh_bar(tm)
    except Exception:
        _stop_spinner()


def _stop_spinner() -> None:
    global _spin_timer
    if _spin_timer is not None:
        try:
            from kitty.fast_data_types import remove_timer
            remove_timer(_spin_timer)
        except Exception:
            pass
        _spin_timer = None


def _sync_spinner() -> None:
    """Start the timer when something is working, stop it when nothing is."""
    global _spin_timer
    try:
        if _working_windows():
            if _spin_timer is None:
                from kitty.fast_data_types import add_timer
                _spin_timer = add_timer(_spin_tick, _SPIN_INTERVAL, True)
        else:
            _stop_spinner()
    except Exception:
        pass


_NOTIFY_EVERY = 10.0     # seconds, per window
_last_notify: dict = {}


def _notify_enabled() -> bool:
    if os.environ.get("KITTYMUX_NOTIFY") == "0":
        return False
    return not os.path.exists(os.path.join(_STATE_DIR, "notify-off"))


def _notify_waiting(window, e: dict) -> None:
    """Desktop notification when an agent you are not looking at starts waiting."""
    try:
        if e.get("focused") or not _notify_enabled() or not shutil.which("notify-send"):
            return
        now = time.monotonic()
        if now - _last_notify.get(window.id, -1e9) < _NOTIFY_EVERY:
            return
        _last_notify[window.id] = now
        title = " ".join((window.title or "agent").split())[:60]
        subprocess.Popen(
            ["notify-send", "-a", "kittymux", "-i", "utilities-terminal",
             f"{title} needs you", e.get("msg") or "Waiting for your input"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
    except Exception:
        pass


def on_set_user_var(boss, window, data) -> None:
    try:
        key, value = data.get("key"), str(data.get("value") or "")
        if key not in ("kittymux_status", "kittymux_msg"):
            return
        e = _entry(window)
        now = time.monotonic()
        if key == "kittymux_msg":
            e["msg"] = value
        else:
            prev = e.get("status")
            e["status"] = value
            e["ts_status"] = now
            if value == "waiting" and prev != "waiting":
                _notify_waiting(window, e)
        _flush(now, force=True)
        _mark_tab_bar_dirty(window)
        _sync_spinner()
    except Exception:
        pass


def on_focus_change(boss, window, data) -> None:
    e = _entry(window)
    e["focused"] = bool(data.get("focused"))
    if e["focused"] and e.get("status") == "done":
        e["status"] = "idle"   # you looked at it: no longer unread
        _mark_tab_bar_dirty(window)
    _flush(time.monotonic(), force=True)


def on_close(boss, window, data) -> None:
    _state.pop(window.id, None)
    _last_notify.pop(window.id, None)
    _sync_spinner()
    _flush(time.monotonic(), force=True)
