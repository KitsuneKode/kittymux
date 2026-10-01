# kittymux scan — the in-kitty side of agent status: scanner, spinner clock, notifier.
#
# Runs inside the kitty process. Twice a second (2 s when no pane runs an agent) it looks at
# every window whose foreground process is a known agent CLI, reads the bottom of its visible
# screen, combines that with hook status from panes-<pid>.json, and stores the verdict from
# kittymux_state.resolve() in scan-<pid>.json. The tab bar, deck, panel and jump queue all read
# that verdict (kittymux_agents.merge_scan), so they can never disagree.
#
# Lifecycle — the part that is easy to get wrong in a long-lived process:
#   * All runtime state lives in `_RT`, parked in sys.modules, so re-executing / reloading this
#     file (every config reload does) NEVER forgets a timer id. ensure_started() is idempotent:
#     it re-uses a live timer instead of stacking another.
#   * Timers are removed the moment their job is gone (spinner: nothing working; scanner: kitty
#     has no windows). Nothing here grows without bound: verdicts for closed windows are dropped
#     each scan, the notify map is pruned, and files are rewritten only when something changed
#     (plus a 3 s heartbeat so consumers can tell the scanner is alive).
#   * Everything is wrapped: an exception here must never reach kitty's event loop.
#
# Privacy: only a matched marker and one short line (the prompt's question / the limit notice,
# control characters stripped, <= 100 chars) are stored, in a 0600 file inside the 0700 state dir.

import json
import os
import re
import shutil
import subprocess
import sys
import time
import types

_RT = sys.modules.setdefault("_kittymux_scan_rt", types.SimpleNamespace(
    scan_timer=None, spin_timer=None, interval=0.0,
    book={},                      # wid -> private resolver bookkeeping (kittymux_state.resolve)
    verdicts={},                  # wid -> {state, reason, ts_state, ts_scan}
    last_sig="", last_write=0.0,
    notified={},                  # wid -> monotonic time of last notification
    panes=(0.0, {}),              # (mtime, parsed panes-<pid>.json)
))

SCAN_FAST, SCAN_IDLE = 0.5, 2.0
SPIN_INTERVAL = 0.1
HEARTBEAT = 3.0
NOTIFY_EVERY = 10.0
NOTIFY_DONE_MIN = 15.0        # a completion only notifies after this much work: a quick reply is not news
DONE_SETTLE = 5.0             # ...and only once it has STAYED finished this long: a screen that blinks (a repaint, a popup,
                              # a status line that changes wording) is not a completion
_PRIVATE = ("marker", "marker_ts", "seen_working", "unseen", "ack_ts", "work_ts", "handled_wait_ts",
            "hook_turn", "hook_turn_ts", "completed")

_helper_dirs_done = False


def _ensure_path() -> None:
    global _helper_dirs_done
    if _helper_dirs_done:
        return
    here = globals().get("__file__")
    for d in (os.environ.get("KITTY_CONFIG_DIRECTORY") or os.path.expanduser("~/.config/kitty"),
              (os.path.dirname(os.path.realpath(here)) if here else "")):   # own dir inserted LAST → searched FIRST
        if d and d not in sys.path:
            sys.path.insert(0, d)
    _helper_dirs_done = True


def state_dir() -> str:
    return os.environ.get("KITTYMUX_STATE") or os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "kittymux")


def scan_path() -> str:
    return os.path.join(state_dir(), f"scan-{os.getpid()}.json")


def _panes_path() -> str:
    return os.path.join(state_dir(), f"panes-{os.getpid()}.json")


def _debug() -> None:
    """KITTYMUX_DEBUG=1: record the traceback of an exception that would otherwise be swallowed
    (nothing here may ever raise into kitty's event loop, so failures are silent by default)."""
    if not os.environ.get("KITTYMUX_DEBUG"):
        return
    try:
        import traceback
        os.makedirs(state_dir(), mode=0o700, exist_ok=True)
        with open(os.path.join(state_dir(), "scan-debug.log"), "a") as f:
            f.write(traceback.format_exc() + "\n")
    except Exception:
        pass


def _mods():
    _ensure_path()
    import kittymux_agents
    import kittymux_state
    return kittymux_agents, kittymux_state


# ── reading hook state ───────────────────────────────────────────────────────
def _panes() -> dict:
    """panes-<pid>.json (hook status, title activity), re-parsed only when it changes."""
    try:
        mtime = os.stat(_panes_path()).st_mtime
    except OSError:
        return _RT.panes[1]
    if mtime != _RT.panes[0]:
        try:
            with open(_panes_path(), encoding="utf-8") as f:
                _RT.panes = (mtime, json.load(f))
        except Exception:
            pass
    return _RT.panes[1]


# ── scanning ─────────────────────────────────────────────────────────────────
_CTRL = {c: " " for c in list(range(0, 32)) + [127] + list(range(0x80, 0xA0))}


def _clean(text, limit: int = 100) -> str:
    return " ".join(str(text).translate(_CTRL).split())[:limit]


def agent_of(window):
    """Agent CLI in the pty's foreground process group (two cheap syscalls), else None."""
    agents, _ = _mods()
    fd = getattr(window.child, "child_fd", None)
    if fd is None:
        return None
    pgrp = os.tcgetpgrp(fd)
    if pgrp <= 0:
        return None
    with open(f"/proc/{pgrp}/cmdline", "rb") as f:
        args = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
    return agents.agent_in(args)


def scan_window(window, now: float) -> bool:
    """Re-resolve one window. True if its verdict changed (so its tab bar needs a redraw)."""
    agents, st = _mods()
    try:
        agent = agent_of(window)
    except Exception:
        agent = None
    wid = str(window.id)
    prev = _RT.verdicts.get(wid) or {}
    if agent is None:
        if prev.get("state"):
            _RT.verdicts[wid] = {"state": "", "reason": "", "ts_state": now, "ts_scan": now}
            _RT.book.pop(wid, None)
            return True
        _RT.verdicts.pop(wid, None)
        return False

    marker, line = "", ""
    if agent in st.SCREEN_AGENTS:
        try:
            marker, line = st.classify_screen(window.as_text())
        except Exception:
            marker, line = "", ""
    entry = dict(_panes().get(wid) or {})
    book = _RT.book.setdefault(wid, {})
    view = {**entry, **book}
    focused = bool(getattr(window, "is_focused", False))
    new = st.resolve(view, agent, marker, now, focused)
    for k in _PRIVATE:
        if k in view:
            book[k] = view[k]
        else:
            book.pop(k, None)
    reason = _clean(line) if marker in ("waiting", "limited") else ""
    old_state = prev.get("state", "")
    changed = new != old_state or reason != prev.get("reason", "")
    _RT.verdicts[wid] = {"state": new, "reason": reason, "agent": agent,
                         "ts_state": now if changed else prev.get("ts_state", now), "ts_scan": now}
    if new == "working" and old_state != "working":
        book["work_ts"] = now                      # when this run of work began (completion threshold)
    if changed and old_state and new in agents.NEEDS_YOU and old_state not in agents.NEEDS_YOU:
        _notify(window, new, entry.get("msg") or reason, agent)
        _alert(window)
    if new == "done":
        if old_state and old_state != "done":
            # first sight of a window (no previous verdict) never notifies: after a scanner restart every
            # old unseen completion would fire at once
            book["done_since"] = now
            book["done_worked"] = (now - book["work_ts"]) if book.get("work_ts") else None
        since = book.get("done_since")
        if since is not None and now - since >= DONE_SETTLE:
            book.pop("done_since", None)           # settled: decide once
            worked = book.pop("done_worked", None)
            if worked is not None and worked >= NOTIFY_DONE_MIN:   # unknown duration = cannot prove it was news
                _notify(window, "done", "", agent)
    else:
        book.pop("done_since", None)               # it blinked back to work: that was no completion
        book.pop("done_worked", None)
    return changed


def _tab_manager(window):
    try:
        tab = window.tabref()
        return tab.tab_manager_ref() if tab is not None else None
    except Exception:
        return None


def refresh_bar(tm) -> None:
    """Redraw a TabManager's bar NOW: re-run the draw, flag the tab bar dirty, then flag the OS
    window itself and wake kitty's main loop. Without the last two, kitty updates the bar's cells
    but does not render until something else asks for a frame (cursor blink, output), so a
    spinner advanced ~1 frame per second on an idle window instead of 10."""
    tm.update_tab_bar_data()
    tm.mark_tab_bar_dirty()
    try:
        from kitty.fast_data_types import mark_os_window_dirty, wakeup_main_loop
        mark_os_window_dirty(tm.os_window_id)
        wakeup_main_loop()
    except Exception:
        pass


def scan_all(timer_id=None) -> None:
    try:
        from kitty.fast_data_types import get_boss
        boss = get_boss()
        now = time.monotonic()
        live, bars, n_agents = set(), {}, 0
        for w in list(boss.all_windows):
            live.add(str(w.id))
            try:
                changed = scan_window(w, now)
                if (_RT.verdicts.get(str(w.id)) or {}).get("state"):
                    n_agents += 1
                if changed:
                    tm = _tab_manager(w)
                    if tm is not None:
                        bars[id(tm)] = tm
            except Exception:
                _debug()
        for wid in [k for k in _RT.verdicts if k not in live]:      # closed windows
            _RT.verdicts.pop(wid, None)
            _RT.book.pop(wid, None)
        for table in (_RT.notified, vars(_RT).get("alerted", {})):
            for wid in [k for k in table if k not in live]:
                table.pop(wid, None)
        for tm in bars.values():
            try:
                refresh_bar(tm)
            except Exception:
                pass
        _flush(now, force=bool(bars))
        _sync_spinner()
        _retime(SCAN_FAST if n_agents else SCAN_IDLE)
    except Exception:
        _debug()


def poke(window) -> None:
    """Something changed in this window right now (a hook fired): resolve it immediately
    instead of waiting for the next tick."""
    try:
        now = time.monotonic()
        if scan_window(window, now):
            tm = _tab_manager(window)
            if tm is not None:
                refresh_bar(tm)
            _flush(now, force=True)
            _sync_spinner()
    except Exception:
        pass


# ── persistence ──────────────────────────────────────────────────────────────
def _flush(now: float, force: bool = False) -> None:
    """Write scan-<pid>.json when the verdicts changed (or every HEARTBEAT seconds, so readers
    can see the scanner is alive). The heartbeat field itself is not part of the change test."""
    sig = json.dumps({w: {k: v for k, v in e.items() if k != "ts_scan"} for w, e in _RT.verdicts.items()},
                     sort_keys=True)
    if not force and sig == _RT.last_sig and now - _RT.last_write < HEARTBEAT:
        return
    _RT.last_sig, _RT.last_write = sig, now
    path = scan_path()
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_RT.verdicts, f)
        os.replace(tmp, path)
    except Exception:
        pass


# ── spinner clock ────────────────────────────────────────────────────────────
# The tab bar only redraws on kitty events, so a silently working agent would freeze the
# spinner on one frame. While — and only while — some window's verdict is `working`, a
# timer marks those tabs' bars dirty at the spinner's frame rate.
def _working_tms() -> list:
    from kitty.fast_data_types import get_boss
    boss = get_boss()
    seen, out = set(), []
    for wid, v in _RT.verdicts.items():
        if v.get("state") != "working":
            continue
        w = boss.window_id_map.get(int(wid))
        tm = _tab_manager(w) if w is not None else None
        if tm is not None and id(tm) not in seen:                  # once per OS window per tick
            seen.add(id(tm))
            out.append(tm)
    return out


def _trace(msg: str) -> None:
    """KITTYMUX_DEBUG=trace: one line per event (timer cadence debugging)."""
    if os.environ.get("KITTYMUX_DEBUG") != "trace":
        return
    try:
        with open(os.path.join(state_dir(), "scan-trace.log"), "a") as f:
            f.write(f"{time.monotonic():.3f} {msg}\n")
    except Exception:
        pass


def _spin_tick(timer_id) -> None:
    try:
        tms = _working_tms()
        _trace(f"spin_tick tms={len(tms)}")
        if not tms:
            _stop_spinner()
            return
        for tm in tms:
            refresh_bar(tm)
    except Exception:
        _debug()
        _stop_spinner()


def _stop_spinner() -> None:
    _trace("stop_spinner")
    if _RT.spin_timer is not None:
        try:
            from kitty.fast_data_types import remove_timer
            remove_timer(_RT.spin_timer)
        except Exception:
            pass
        _RT.spin_timer = None


def _sync_spinner() -> None:
    try:
        working = any(v.get("state") == "working" for v in _RT.verdicts.values())
        if working and _RT.spin_timer is None:
            from kitty.fast_data_types import add_timer
            _RT.spin_timer = add_timer(_spin_tick, SPIN_INTERVAL, True)
        elif not working:
            _stop_spinner()
    except Exception:
        _debug()


# ── notifications ────────────────────────────────────────────────────────────
def _notify_enabled(kind: str = "needs") -> bool:
    """Off switches: KITTYMUX_NOTIFY=0 or the file `notify-off` silence everything;
    KITTYMUX_NOTIFY_DONE=0 or the file `notify-done-off` silence only "finished" notifications."""
    if os.environ.get("KITTYMUX_NOTIFY") == "0" or os.path.exists(os.path.join(state_dir(), "notify-off")):
        return False
    if kind == "done":
        return os.environ.get("KITTYMUX_NOTIFY_DONE") != "0" and \
            not os.path.exists(os.path.join(state_dir(), "notify-done-off"))
    return True


def _plain(text, limit: int) -> str:
    """Notification text: cleaned, and markup-escaped (many daemons render Pango markup)."""
    return _clean(text, limit).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _helper() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin", "mux-notify")


_TEXT = {   # state -> (title suffix, default body, urgency, category)
    "waiting": ("needs you", "Waiting for your input", "normal", "kittymux.attention"),
    "limited": ("hit a limit", "Usage limit reached", "normal", "kittymux.attention"),
    "done": ("finished", "Ready for your next prompt", "low", "kittymux.done"),
}


def _alert(window) -> None:
    """Ask the window manager for attention (taskbar flash / urgent border) when an agent you are not
    looking at needs you. This is kitty's own bell path (`screen.bell()`), so it obeys the user's
    `window_alert_on_bell` / `enable_audio_bell`. Only for needs-you: a bell per completion would
    flash constantly. Off with KITTYMUX_BELL=0 or the file `bell-off`."""
    try:
        if getattr(window, "is_focused", False) or os.environ.get("KITTYMUX_BELL") == "0" \
                or os.path.exists(os.path.join(state_dir(), "bell-off")):
            return
        now = time.monotonic()
        alerted = vars(_RT).setdefault("alerted", {})      # (an _RT made by an older version lacks it)
        wid = str(window.id)
        if now - alerted.get(wid, -1e9) < NOTIFY_EVERY:
            return
        alerted[wid] = now
        window.screen.bell()
    except Exception:
        pass


NOTIFY_BURST, NOTIFY_WINDOW = 5, 10.0        # at most this many notifications per this many seconds, in total


def _icon(agent: str) -> str:
    """The notification icon: the agent's own mark (assets/notify/<agent>.png, see tools/build-notify-icons.py),
    else kittymux's, else the kitty icon from the icon theme. Always chosen from OUR table, never from output."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "assets", "notify")
    for name in (agent, "kittymux"):
        path = os.path.join(root, f"{name}.png")
        if name and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", name) and os.path.isfile(path):
            return path
    return "kitty"


def _private() -> bool:
    """Notifications hold text from the agent's screen; in private mode they carry only "<agent> needs you"."""
    return os.environ.get("KITTYMUX_NOTIFY_PRIVATE") == "1" or os.path.exists(os.path.join(state_dir(), "notify-private"))


def _within_budget(now: float) -> bool:
    """A global cap on top of the per-window one: output that flips many windows' states cannot flood the desktop."""
    log = vars(_RT).setdefault("notify_log", [])
    log[:] = [t for t in log if now - t < NOTIFY_WINDOW]
    if len(log) >= NOTIFY_BURST:
        return False
    log.append(now)
    return True


def _notify(window, state: str, detail: str, agent: str = "") -> None:
    """Desktop notification when an agent you are not looking at starts needing you or finishes.
    bin/mux-notify shows it and, if you invoke its action, jumps to this window."""
    try:
        kind = "done" if state == "done" else "needs"
        if getattr(window, "is_focused", False) or not _notify_enabled(kind) or not shutil.which("notify-send"):
            return
        now = time.monotonic()
        wid = str(window.id)
        if now - _RT.notified.get(wid, -1e9) < NOTIFY_EVERY:
            return
        if not _within_budget(now):
            return
        _RT.notified[wid] = now
        suffix, default_body, urgency, category = _TEXT[state]
        private = _private()
        agents = _mods()[0]
        shown = agents.strip_agent_prefix(agents.strip_title_prefix(window.title or ""), agent) or agent or "agent"
        title = _plain(agent if private and agent else shown, 60)
        body = _plain(default_body if private else (detail or default_body), 120)
        try:
            from kitty.fast_data_types import get_boss
            socket = getattr(get_boss(), "listening_on", "") or ""
        except Exception:
            socket = ""
        subprocess.Popen(
            [_helper(), socket, wid, str(os.getpid()), urgency, category, _icon(agent), f"{title} {suffix}", body],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
    except Exception:
        pass


# ── lifecycle ────────────────────────────────────────────────────────────────
def _retime(interval: float) -> None:
    if _RT.scan_timer is not None and interval == _RT.interval:
        return
    try:
        from kitty.fast_data_types import add_timer, remove_timer
        if _RT.scan_timer is not None:
            remove_timer(_RT.scan_timer)
        _RT.scan_timer = add_timer(scan_all, interval, True)
        _RT.interval = interval
    except Exception:
        _RT.scan_timer = None


def ensure_started() -> bool:
    """Start the scanner if it is not running. Idempotent and cheap — the tab bar calls it on
    every draw, so a freshly (re)loaded kitty config brings it up without a restart."""
    if _RT.scan_timer is not None:
        return True
    try:
        from kitty.fast_data_types import get_boss
        if get_boss() is None:
            return False
    except Exception:
        return False
    _retime(SCAN_FAST)
    return _RT.scan_timer is not None


def restart() -> None:
    """Drop the timers and start fresh — used after this file was reloaded so the timer runs the
    NEW code rather than the function objects of the previous version."""
    stop()
    ensure_started()


def stop() -> None:
    """Remove both timers (tests, shutdown)."""
    try:
        from kitty.fast_data_types import remove_timer
        if _RT.scan_timer is not None:
            remove_timer(_RT.scan_timer)
    except Exception:
        pass
    _RT.scan_timer = None
    _RT.interval = 0.0
    _stop_spinner()
