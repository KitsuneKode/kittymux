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
# variable, set by bin/mux-status from agent hooks (see README). It is one INPUT to the
# resolver in kittymux_scan.py / kittymux_state.py, which combines it with what is actually
# on the pane's screen and publishes the verdict in scan-<pid>.json for every consumer.

import json
import os
import re
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
        os.makedirs(os.path.dirname(STATE_FILE), mode=0o700, exist_ok=True)
        # window titles and agent messages are private: 0600 from the first byte
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_state, f)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


# ── hygiene ──────────────────────────────────────────────────────────────────
_CTRL_MAP = {c: " " for c in list(range(0, 32)) + [127] + list(range(0x80, 0xA0))}


def _clean(text, limit: int = 120) -> str:
    """One line, no control characters (anything running in a pane can set user vars, and
    this text is drawn into the tab bar and shown in notifications), bounded length."""
    return " ".join(str(text).translate(_CTRL_MAP).split())[:limit]


def _cleanup_stale() -> None:
    """Delete stale state only when the process filesystem can establish liveness."""
    if not os.path.isdir("/proc"):
        return
    try:
        for name in os.listdir(_STATE_DIR):
            m = re.fullmatch(r"(?:panes|scan|changes)-(\d+)\.json(?:\.tmp)?|decisions-(\d+)\.jsonl(?:\.tmp)?", name)
            pid = (m.group(1) or m.group(2)) if m else None
            if m and int(pid) != os.getpid() and not os.path.exists(f"/proc/{pid}"):
                try:
                    os.unlink(os.path.join(_STATE_DIR, name))
                except OSError:
                    pass
    except OSError:
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


def _install_bar_drag() -> None:
    """Make the vertical tab bar's inner edge draggable (see kittymux_barsize)."""
    try:
        import sys
        here = globals().get("__file__")
        for d in (os.environ.get("KITTY_CONFIG_DIRECTORY") or os.path.expanduser("~/.config/kitty"),
                  (os.path.dirname(os.path.realpath(here)) if here else "")):   # own dir inserted LAST → searched FIRST
            if d and d not in sys.path:
                sys.path.insert(0, d)
        import kittymux_barsize
        kittymux_barsize.install()
    except Exception:
        pass


def on_load(boss, data) -> None:
    _cleanup_stale()
    _install_bar_drag()
    ks = _scan()
    if ks is not None:
        ks.ensure_started()
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


# Scanning, the spinner clock and notifications live in kittymux_scan.py — a helper module the
# tab bar also (re)starts on every config load. kitty caches watcher modules for the life of the
# process, so anything that must pick up an upgrade without a restart cannot live in this file.
def _scan():
    """kittymux_scan, imported from the config dir; None if it cannot be loaded."""
    try:
        import sys
        here = globals().get("__file__")
        for d in (os.environ.get("KITTY_CONFIG_DIRECTORY") or os.path.expanduser("~/.config/kitty"),
                  (os.path.dirname(os.path.realpath(here)) if here else "")):   # own dir inserted LAST → searched FIRST
            if d and d not in sys.path:
                sys.path.insert(0, d)
        import kittymux_scan
        return kittymux_scan
    except Exception:
        return None


def _poke(window) -> None:
    ks = _scan()
    if ks is not None:
        ks.poke(window)


def on_set_user_var(boss, window, data) -> None:
    try:
        key, value = data.get("key"), str(data.get("value") or "")
        if key not in ("kittymux_status", "kittymux_msg"):
            return
        e = _entry(window)
        now = time.monotonic()
        if key == "kittymux_msg":
            e["msg"] = _clean(value)
        else:
            e["status"] = value
            e["ts_status"] = now
        _flush(now, force=True)
        _mark_tab_bar_dirty(window)
        _poke(window)                       # resolve the pane NOW, not at the next scan tick
    except Exception:
        pass


def on_focus_change(boss, window, data) -> None:
    e = _entry(window)
    e["focused"] = bool(data.get("focused"))
    if e["focused"] and e.get("status") == "done":
        e["status"] = "idle"   # you looked at it: no longer unread
        _mark_tab_bar_dirty(window)
    _flush(time.monotonic(), force=True)
    _poke(window)              # focusing clears an unseen completion immediately


def on_close(boss, window, data) -> None:
    _state.pop(window.id, None)
    _flush(time.monotonic(), force=True)
