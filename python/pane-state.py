# kittymux pane-state watcher — per-window activity for the agent picker.
#
# Loaded via `watcher` in the rendered keys conf. Runs inside the kitty
# process; callbacks receive (boss, window, data) with the real Window.
#
# Writes $KITTYMUX_STATE/panes-<pid>.json:
#   { "<wid>": {title, ts_title, ts_cmd, cmd, running, focused, at_prompt} }

import json
import os
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
             "running": False, "focused": False, "at_prompt": False}
        _state[window.id] = e
    return e


def _attach(window) -> None:
    # Windows created before this watcher loaded hold a copy of the watcher
    # lists taken at construction. Register ourselves on those too, once.
    ws = getattr(window, "watchers", None)
    if ws is None:
        return
    for lst, fn in ((ws.on_title_change, on_title_change),
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


def on_focus_change(boss, window, data) -> None:
    e = _entry(window)
    e["focused"] = bool(data.get("focused"))
    _flush(time.monotonic(), force=True)


def on_close(boss, window, data) -> None:
    _state.pop(window.id, None)
    _flush(time.monotonic(), force=True)
