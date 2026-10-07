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
AGE_REFRESH = 20.0            # tabs that show "waiting 5m" / "done 2m" are redrawn this often, so the minutes tick (a working tab already redraws with its spinner)
NOTIFY_EVERY = 10.0
NOTIFY_DONE_MIN = 15.0        # a completion the AGENT announced (hook / its own notification) pops up after this much work: a quick reply is not news
NOTIFY_DONE_LOW_MIN = 60.0    # …one inferred from the screen alone only after this much (it is shown in the inbox and the bar either way)
DONE_SETTLE = 5.0             # ...and only once it has STAYED finished this long: a screen that blinks (a repaint, a popup,
                              # a status line that changes wording) is not a completion
_PRIVATE = ("marker", "marker_ts", "seen_working", "unseen", "ack_ts", "work_ts", "handled_wait_ts",
            "hook_turn", "hook_turn_ts", "completed", "unseen_cause", "why", "done_source", "agent_done_ts")

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


# ── decision log (kittymux explain) ──────────────────────────────────────────
# Every state change and every notification decision (sent, or why it was not) is recorded: in memory (a bounded deque that survives config
# reloads in _RT) and appended to decisions-<pid>.jsonl (0600, rotated at DECISION_FILE_MAX). Events are rare — a state change, a
# notification — so this is a handful of tiny writes a minute at most, no per-tick work, nothing unbounded. A false "finished" can then be
# diagnosed after the fact instead of guessed at.
DECISION_KEEP = 300             # events kept in memory
DECISION_FILE_MAX = 192 * 1024  # rotate the file past this many bytes…
DECISION_FILE_KEEP = 400        # …keeping this many of the newest lines


def decisions_path() -> str:
    return os.path.join(state_dir(), f"decisions-{os.getpid()}.jsonl")


def _record(kind: str, wid: str, agent: str, **fields) -> None:
    """Remember one decision. Never raises."""
    try:
        import collections
        ev = {"t": round(time.time(), 1), "kind": kind, "w": wid, "agent": agent or "", **fields}
        vars(_RT).setdefault("decisions", collections.deque(maxlen=DECISION_KEEP)).append(ev)
        _append_decision(decisions_path(), json.dumps(ev, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _append_decision(path: str, line: str) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        size = os.fstat(fd).st_size
    finally:
        os.close(fd)
    if size > DECISION_FILE_MAX:
        _rotate_decisions(path)


def _rotate_decisions(path: str) -> None:
    """Keep the newest DECISION_FILE_KEEP lines (atomic replace; a concurrent append lands in the old file at worst)."""
    with open(path, "rb") as f:
        lines = f.read().splitlines(keepends=True)[-DECISION_FILE_KEEP:]
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.writelines(lines)
    os.replace(tmp, path)


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
    adt = view.get("agent_done_ts")
    if adt and adt > float(view.get("ts_status") or 0):
        view["status"], view["ts_status"] = "done", adt        # the agent's own "finished" notification counts like its Stop hook
    new = st.resolve(view, agent, marker, now, focused)
    if new != prev.get("state", "") or wid not in _journal_rt()["keys"]:
        _journal_note(window, new)
    for k in _PRIVATE:
        if k in view:
            book[k] = view[k]
        else:
            book.pop(k, None)
    reason = _clean(line) if marker in ("waiting", "limited") else ""
    old_state = prev.get("state", "")
    changed = new != old_state or reason != prev.get("reason", "") or agent != prev.get("agent", agent)
    why = view.get("why", "")
    _RT.verdicts[wid] = {"state": new, "reason": reason, "agent": agent, "why": why,
                         "ts_state": now if changed else prev.get("ts_state", now), "ts_scan": now}
    if new != old_state:
        _record("state", wid, agent, frm=old_state, to=new, why=why)
        if new == "working" and old_state in ("idle", "done"):
            _checkpoint(window, "start", now)
        elif old_state == "working" and new in ("waiting", "limited", "done", "idle"):
            _checkpoint(window, "finish", now)
    if new == "working" and old_state != "working":
        book["work_ts"] = now                      # when this run of work began (completion threshold)
    if changed and old_state and new in agents.NEEDS_YOU and old_state not in agents.NEEDS_YOU:
        text = entry.get("msg") or reason
        if new == "limited":
            kind = "limit"
        else:
            kind = _inbox().classify_text("", text)[0]
            kind = kind if kind in ("permission", "question") else "permission"
        reset = _inbox().parse_reset(text, time.time(), float(time.localtime().tm_gmtoff or 0)) if kind == "limit" else None
        source = "hook" if "hook" in why else "screen"
        _record("notify", wid, agent, state=new, source=source,
                outcome=_announce(window, kind, agent, source, text, confidence="high" if source == "hook" else "low", reset_at=reset))
        _record("attention", wid, agent, outcome=_alert(window))
    elif changed and not old_state and new in agents.NEEDS_YOU:
        _record("notify", wid, agent, state=new, outcome="suppressed: first sight of this window (a scanner restart must not replay old events)")
    if new == "done":
        if old_state and old_state != "done":
            # first sight of a window (no previous verdict) never notifies: after a scanner restart every
            # old unseen completion would fire at once
            book["done_since"] = now
            book["done_worked"] = (now - book["work_ts"]) if book.get("work_ts") else None
            book["done_conf"] = "high" if view.get("done_source") == "agent" else "low"
        since = book.get("done_since")
        if since is not None and now - since >= DONE_SETTLE:
            book.pop("done_since", None)           # settled: decide once
            worked = book.pop("done_worked", None)
            conf = book.pop("done_conf", "low")
            outcome = _announce(window, "done", agent, "agent" if conf == "high" else "screen", "", confidence=conf, worked=worked)
            _record("notify", wid, agent, state="done", worked=None if worked is None else round(worked), confidence=conf, outcome=outcome)
    else:
        book.pop("done_since", None)               # it blinked back to work: that was no completion
        book.pop("done_worked", None)
        book.pop("done_conf", None)
    unread = vars(_RT).get("unread")
    if focused and unread and wid in unread:       # you are looking at it: whatever it reported is seen
        unread.discard(wid)
        _inbox().ack(state_dir(), time.time(), window=wid, pid=os.getpid())
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
        live, bars, n_agents, dirty = set(), {}, 0, False
        age_due = now - vars(_RT).get("age_refresh", 0.0) >= AGE_REFRESH
        for w in list(boss.all_windows):
            live.add(str(w.id))
            try:
                changed = scan_window(w, now)
                dirty = dirty or changed
                if changed:
                    try:
                        tab = w.tabref()
                        update = getattr(w, "update_title_bar", None)
                        if update is not None:
                            update(is_active=bool(tab and tab.active_window is w))
                    except Exception:
                        pass
                state = (_RT.verdicts.get(str(w.id)) or {}).get("state")
                if state:
                    n_agents += 1
                if changed or (age_due and state in ("waiting", "limited", "done")):
                    tm = _tab_manager(w)
                    if tm is not None:
                        bars[id(tm)] = tm
            except Exception:
                _debug()
        for wid in [k for k in _RT.verdicts if k not in live]:      # closed windows
            _RT.verdicts.pop(wid, None)
            _RT.book.pop(wid, None)
            dirty = True
        if age_due:
            vars(_RT)["age_refresh"] = now
        _maybe_autosave(now, live)
        _journal_tick(boss, live, time.time())
        for table in (_RT.notified, vars(_RT).get("alerted", {})):
            for wid in [k for k in table if k not in live]:
                table.pop(wid, None)
        for tm in bars.values():
            try:
                refresh_bar(tm)
            except Exception:
                pass
        _flush(now, force=bool(bars), dirty=dirty)
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
def _flush(now: float, force: bool = False, dirty: bool = True) -> None:
    """Write scan-<pid>.json when the verdicts changed (or every HEARTBEAT seconds, so readers
    can see the scanner is alive). The heartbeat field itself is not part of the change test. `dirty=False` (no window's verdict
    changed this tick) skips even serialising the verdicts to compare them — that was the bulk of an idle tick."""
    if not force and not dirty and now - _RT.last_write < HEARTBEAT:
        return
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
        tms = _working_tms() if _motion_on() else []         # switched off while a spinner ran: the timer ends with its next beat
        _trace(f"spin_tick tms={len(tms)}")
        if not tms:
            _stop_spinner()
            return
        n = vars(_RT).get("spin_n", 0) + 1                  # (an _RT made by an older version lacks it)
        _RT.spin_n = n
        try:
            from kitty.fast_data_types import current_focused_os_window_id
            focused = current_focused_os_window_id()
        except Exception:
            focused = 0
        for tm in tms:
            # a window nobody is typing in animates at half rate: same information, half the redraws (a full bar redraw is the
            # costliest thing this module does, and a kitty parked on another workspace used to pay it 10×/s for nothing)
            if focused and tm.os_window_id != focused and n & 1:         # focus unknown (0) = full rate
                continue
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


def _motion_on() -> bool:
    """The `motion` switch (env > flag file > default). Off: nothing here redraws a bar just to turn a spinner."""
    try:
        import kittymux_features
        return kittymux_features.enabled("motion", state_dir())
    except Exception:
        return True


def _sync_spinner() -> None:
    try:
        working = any(v.get("state") == "working" for v in _RT.verdicts.values()) and _motion_on()
        if working and _RT.spin_timer is None:
            from kitty.fast_data_types import add_timer
            _RT.spin_timer = add_timer(_spin_tick, SPIN_INTERVAL, True)
        elif not working:
            _stop_spinner()
    except Exception:
        _debug()


# ── autosave: the last state of things ───────────────────────────────────────
# So a crash, a reboot or "I closed kitty" never loses the layout or the agents' conversations: when the set of windows changes (and has been stable for
# AUTOSAVE_SETTLE), and at least every AUTOSAVE_PERIOD, `kittymux sessions autosave` saves this kitty with kitty's own save_as_session and rewrites agent
# windows to `--resume <id>`. It is a detached subprocess (a couple of times an hour at most); the scanner only compares a tuple of window ids per tick.
# Restore with `kittymux sessions restore last`. Off: KITTYMUX_AUTOSAVE=0 or the file `autosave-off`.
AUTOSAVE_SETTLE = 20.0
AUTOSAVE_MIN_GAP = 60.0
AUTOSAVE_PERIOD = 900.0


def _autosave_enabled() -> bool:
    return os.environ.get("KITTYMUX_AUTOSAVE") != "0" and not os.path.exists(os.path.join(state_dir(), "autosave-off"))


def _quit_capture(boss, window, data) -> None:
    """Capture before teardown; the detached writer never needs the closing socket."""
    if not data.get("confirmed") or not _autosave_enabled() or os.environ.get("KITTYMUX_PANEL") == "1":
        return
    if getattr(_RT, "exit_captured", False) or not callable(getattr(boss, "serialize_state_as_session", None)):
        return
    originals = []
    outcome = "exit capture failed"
    try:
        import tempfile
        from kitty.session import default_save_as_session_opts
        _, R = _journal_mod()
        agents = _journal_agents(R)
        for w in list(boss.all_windows):
            original = dict(w.user_vars)
            originals.append((w, original))
            for key in ("kittymux_agent", "kittymux_resume", "kittymux_sid"):
                w.user_vars.pop(key, None)
            fg = [{"pid": p.get("pid"), "cmdline": p.get("cmdline") or []}
                  for p in getattr(w.child, "foreground_processes", [])]
            ident = R.identify(agents, fg, os.environ.get("KITTYMUX_CLAUDE_HOME") or os.path.expanduser("~/.claude"))
            if ident and ident.get("sid"):
                w.user_vars.update(kittymux_agent=ident["agent"], kittymux_resume="exact", kittymux_sid=ident["sid"])
        opts = default_save_as_session_opts()
        opts.use_foreground_process = True
        opts.match = ""
        captured_ns = time.time_ns()
        chunks, size = [], 0
        for line in boss.serialize_state_as_session(ser_opts=opts):
            raw = (line + "\n").encode("utf-8")
            size += len(raw)
            if size > 8 * 1024 * 1024:
                raise ValueError("capture too large")
            chunks.append(raw)
        os.makedirs(state_dir(), mode=0o700, exist_ok=True)
        # TemporaryFile is unlinked; no partially captured restore candidate exists.
        with tempfile.TemporaryFile(dir=state_dir()) as f:
            f.write(b"".join(chunks))
            f.seek(0)
            cli = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin", "kittymux")
            subprocess.Popen([cli, "sessions", "finalize", str(f.fileno()), str(os.getpid()), str(captured_ns)],
                             pass_fds=(f.fileno(),), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        _RT.exit_captured = True
        outcome = "exit capture handed to offline writer"
    except Exception:
        _debug()
    finally:
        for w, original in originals:
            w.user_vars.clear()
            w.user_vars.update(original)
        _record("autosave", "", "", outcome=outcome)


def _install_quit_capture() -> None:
    """Replace our callback on reload without touching other global watchers."""
    try:
        from kitty.window import global_watchers
        callbacks = global_watchers().on_quit
        old = getattr(_RT, "quit_callback", None)
        if old in callbacks:
            callbacks.remove(old)
        callbacks.append(_quit_capture)
        _RT.quit_callback = _quit_capture
    except Exception:
        pass


def _maybe_autosave(now: float, window_ids) -> str:
    """Decide (and, when due, start) an autosave. Returns what it did (for tests/debugging)."""
    st = vars(_RT).setdefault("autosave", {"sig": None, "since": 0.0, "last": now, "pending": False})
    sig = hash(tuple(sorted(window_ids)))
    if st["sig"] is None:
        st["sig"], st["last"] = sig, now                       # first look: a baseline, nothing has changed yet
        return "baseline"
    if sig != st["sig"]:
        st["sig"], st["since"], st["pending"] = sig, now, True
    due = (st["pending"] and now - st["since"] >= AUTOSAVE_SETTLE and now - st["last"] >= AUTOSAVE_MIN_GAP) or now - st["last"] >= AUTOSAVE_PERIOD
    if not due or not window_ids or not _autosave_enabled():
        return "idle"
    st["last"], st["pending"] = now, False
    try:
        from kitty.fast_data_types import get_boss
        sock = getattr(get_boss(), "listening_on", "") or ""
        if not sock.startswith("unix:"):
            return "no socket"
        env = dict(os.environ, KITTYMUX_TARGET=sock)
        subprocess.Popen([os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin", "kittymux"), "sessions", "autosave"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, env=env)
        return "started"
    except Exception:
        return "error"


# ── what did it change? (kittymux_changes) ───────────────────────────────────
# A run starting (idle/done → working) takes a baseline snapshot of the repository around the window's directory; a run ending (working → waiting/limited/done/idle) takes the
# summary. Both are done by a detached, low-priority `kittymux checkpoint` — git is never run on kitty's main thread. First sight of a window never starts one (we did not see the
# run begin; the summary then compares with HEAD), at most CHANGES_MAX helpers run at once, and the same (window, kind) is not repeated within CHANGES_GAP seconds.
CHANGES_MAX, CHANGES_GAP = 2, 3.0


def _changes_enabled() -> bool:
    return os.environ.get("KITTYMUX_CHANGES") != "0" and not os.path.exists(os.path.join(state_dir(), "changes-off"))


def _checkpoint(window, kind: str, now: float) -> str:
    """Start the detached helper for one transition. Returns what it did (tests / decision log). Never raises."""
    try:
        if not _changes_enabled():
            return "off"
        cwd = getattr(window, "cwd_of_child", "") or ""
        if not cwd:
            return "no directory"
        rt = vars(_RT).setdefault("changes", {"procs": [], "last": {}})
        rt["procs"] = [p for p in rt["procs"] if p.poll() is None]
        wid = str(window.id)
        if len(rt["procs"]) >= CHANGES_MAX:
            return "busy"
        if now - rt["last"].get((wid, kind), -1e9) < CHANGES_GAP:
            return "too soon"
        rt["last"][(wid, kind)] = now
        if len(rt["last"]) > 512:
            rt["last"].clear()
        exe = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin", "kittymux")
        argv = [exe, "checkpoint", kind, "--pid", str(os.getpid()), "--window", wid, "--cwd", cwd]
        if shutil.which("nice"):
            argv = ["nice", "-n", "10", *argv]
        rt["procs"].append(subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True))
        return "started " + kind
    except Exception:
        return "error"


# ── the journal: every agent session, recorded as it runs ────────────────────
# kittymux_journal keeps one record per agent session (which agent, where, what command, last state, runs, working time) in agent-sessions.json. The scanner
# feeds it from here: an observation on every state change (cheap: the identity — session id, command — is read only then) and one per HEARTBEAT_S for every
# agent window, so a session id that appears late, a `cd`, or a renamed tab is picked up. Writes are coalesced (FLUSH_GAP) and never block (see journal.flush).
JOURNAL_FLUSH_GAP = 5.0


def _journal_rt() -> dict:
    return vars(_RT).setdefault("journal", {"recs": {}, "keys": {}, "dirty": False, "flushed": 0.0, "beat": 0.0})


def _journal_enabled() -> bool:
    return os.environ.get("KITTYMUX_JOURNAL") != "0" and not os.path.exists(os.path.join(state_dir(), "journal-off"))


def _journal_mod():
    _ensure_path()
    import kittymux_journal
    import kittymux_resume
    return kittymux_journal, kittymux_resume


def _journal_agents(R) -> dict:
    """The resume definitions (shipped + the user's override), loaded once per scanner life: they only tell the journal which commands are agents."""
    rt = _journal_rt()
    if "agents" not in rt:
        here = globals().get("__file__")
        shipped = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(here))), "assets", "resume-agents.json") if here else ""
        user = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "kittymux", "resume.json")
        rt["agents"] = R.load_agents(shipped, user)
    return rt["agents"]


def _journal_note(window, state: str, wall: float | None = None) -> None:
    """One observation of an agent window. Never raises: the journal must not be able to hurt the scanner."""
    rt = _journal_rt()
    wid = str(window.id)
    try:
        if not _journal_enabled():
            rt["keys"].setdefault(wid, None)
            return
        J, R = _journal_mod()
        wall = wall if wall is not None else time.time()
        agents = _journal_agents(R)
        fg = [{"pid": p.get("pid"), "cmdline": p.get("cmdline") or []} for p in getattr(window.child, "foreground_processes", [])]
        ident = R.identify(agents, fg, os.environ.get("KITTYMUX_CLAUDE_HOME") or os.path.expanduser("~/.claude"))
        if ident is None:
            return
        tab = getattr(window, "tabref", lambda: None)()
        obs = {"agent": ident["agent"], "sid": ident["sid"], "argv": ident["argv"], "state": state, "kitty_pid": os.getpid(), "wid": window.id,
               "cwd": getattr(window, "cwd_of_child", "") or "", "tab": getattr(tab, "effective_title", "") if tab is not None else ""}
        key = J.key_for(obs["agent"], obs["sid"], obs["kitty_pid"], obs["wid"])
        old = rt["keys"].get(wid)
        if J.observe(rt["recs"], obs, wall) or old != key:
            rt["dirty"] = True
        rt["keys"][wid] = key
    except Exception:
        _debug()


def _journal_tick(boss, live, wall: float) -> None:
    """Heartbeat (re-observe every agent window), close what vanished, and write when something changed."""
    rt = _journal_rt()
    try:
        if not _journal_enabled():
            return
        J, _ = _journal_mod()
        if wall - rt["beat"] >= J.HEARTBEAT_S:
            rt["beat"] = wall
            for w in list(boss.all_windows):
                v = _RT.verdicts.get(str(w.id)) or {}
                if v.get("agent"):
                    _journal_note(w, v.get("state", ""), wall)
                    rt["dirty"] = True              # `last seen` moves on every beat: write it (once a minute at most), or a crash would lose how recent it was
        gone = [k for k in rt["keys"] if k not in live or not (_RT.verdicts.get(k) or {}).get("agent")]
        for k in gone:
            rt["keys"].pop(k, None)
        running = {v for v in rt["keys"].values() if v}
        if J.close_missing(rt["recs"], os.getpid(), running, wall) or gone:
            rt["dirty"] = True
        if rt["dirty"] and wall - rt["flushed"] >= JOURNAL_FLUSH_GAP:
            rt["flushed"] = wall
            if J.flush(state_dir(), rt["recs"], wall):
                rt["dirty"] = False
    except Exception:
        _debug()


# ── typed events: the inbox ──────────────────────────────────────────────────
# Every needs-you, limit and completion is a typed event in the shared inbox (kittymux_inbox: docs/inbox.md). `_announce` is the ONE place that
# decides whether it also pops up: the inbox says whether this occurrence was already reported (by the agent's own notification, a hook or the
# screen scan — a popup per occurrence, not per source), and the confidence of a completion decides whether a screen-only guess may interrupt you.
def _inbox():
    _ensure_path()
    import kittymux_inbox
    return kittymux_inbox


def _announce(window, kind: str, agent: str, source: str, detail: str, *, confidence: str = "high", worked=None, reset_at=None) -> str:
    """Record the event and, if it is new and the policy allows, show the popup. Returns the outcome for the decision log. Never raises."""
    try:
        agents = _mods()[0]
        inbox = _inbox()
        wid = str(window.id)
        tab = agents.strip_agent_prefix(agents.strip_title_prefix(window.title or ""), agent) or agent
        ev = inbox.make_event(kind, agent, wid, source, time.time(), pid=os.getpid(), tab=tab, title=f"{agent or 'agent'} {_TEXT_BY_KIND.get(kind, kind)}",
                              body=detail, confidence=confidence, reset_at=reset_at, private=_private())
        is_new, _ = inbox.add(state_dir(), ev)
        if is_new:
            vars(_RT).setdefault("unread", set()).add(wid)
        if not is_new:
            return "merged into an earlier report of the same thing: no second popup"
        if kind in ("permission", "question"):
            return _notify(window, "waiting", detail, agent)
        if kind == "limit":
            return _notify(window, "limited", detail, agent)
        if kind == "done":
            if confidence == "high":
                if worked is not None and worked < NOTIFY_DONE_MIN:
                    return f"inbox only: the agent said it finished, but it worked only {round(worked)} s (< {int(NOTIFY_DONE_MIN)} s)"
                return _notify(window, "done", "", agent)
            if worked is not None and worked >= NOTIFY_DONE_LOW_MIN:
                return _notify(window, "done", "", agent)
            return ("inbox only: finish judged from the screen alone and the run was short (< %d s)" % int(NOTIFY_DONE_LOW_MIN)
                    if worked is not None else "inbox only: finish judged from the screen alone and the duration is unknown")
        return "inbox only"
    except Exception:
        return "error: could not record the event"


_TEXT_BY_KIND = {"permission": "needs permission", "question": "asks a question", "limit": "hit a usage limit", "done": "finished",
                 "error": "reported an error", "info": "says"}


def _on_agent_notification(cmd) -> None:
    """The agent announced something itself (an OSC 9/99/777 notification — kitty hands it to NotificationManager). This is the most authoritative
    thing we ever learn about an agent's state: classify what it SAID, record it, and (for a completion) let the resolver treat it like a Stop hook.
    Notifications from windows that are not agent windows are left alone."""
    wid = str(getattr(cmd, "channel_id", 0))
    agent = (_RT.verdicts.get(wid) or {}).get("agent") or ""
    if not agent:
        return
    from kitty.fast_data_types import get_boss
    window = get_boss().window_id_map.get(int(wid))
    if window is None:
        return
    inbox = _inbox()
    title, body = inbox.clean(cmd.title, 200), inbox.clean(cmd.body, 400)
    kind, tag = inbox.classify_text(title, body)
    detail = body or title
    now = time.time()
    if tag == "idle-notice":                      # the agent has been idle since it finished: not a new event, but worth keeping in the inbox
        inbox.add(state_dir(), inbox.make_event("info", agent, wid, "agent", now, pid=os.getpid(), tab=window.title or "", title=title, body=detail,
                                                private=_private(), tag=tag))
        _record("agent-notification", wid, agent, what="info", tag=tag, outcome="inbox only: its idle notice (it finished earlier)")
        return
    reset = inbox.parse_reset(f"{title} {body}", now, float(time.localtime().tm_gmtoff or 0)) if kind == "limit" else None
    if kind == "done":
        _RT.book.setdefault(wid, {})["agent_done_ts"] = time.monotonic()    # the resolver treats this like its Stop hook (scan_window)
    outcome = _announce(window, kind, agent, "agent", detail, confidence="high", reset_at=reset)
    _record("agent-notification", wid, agent, what=kind, outcome=outcome)


def _install_notification_tap() -> None:
    """Observe every notification kitty is about to filter/show, once per process: wrap NotificationManager.is_notification_filtered (it receives
    the finalised notification, with the window it came from, before our filter_notification rule drops the agents' own popups — we show our own).
    The wrapper only delegates to this module's function by name, so a reload's new code applies without re-wrapping, and it never raises."""
    try:
        from kitty.notifications import NotificationManager
        if getattr(NotificationManager.is_notification_filtered, "_kittymux_wrapped", False):
            return
        original = NotificationManager.is_notification_filtered

        def is_notification_filtered(self, cmd):
            try:
                _on_agent_notification(cmd)
            except Exception:
                _debug()
            return original(self, cmd)

        is_notification_filtered._kittymux_wrapped = True                      # type: ignore[attr-defined]
        NotificationManager.is_notification_filtered = is_notification_filtered  # type: ignore[method-assign]
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


def _quiet_reason(window=None, wall: float | None = None) -> str | None:
    """Why popups and bells are held back right now (`kittymux notify mute`, `kittymux snooze`), or None — see kittymux_quiet. Events still go to the inbox either way."""
    try:
        _ensure_path()
        import kittymux_quiet
        return kittymux_quiet.quiet_reason(state_dir(), os.getpid(), getattr(window, "id", ""), wall)
    except Exception:
        return None


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


def _attention_allowed() -> tuple[bool, str]:
    """(allowed, why not): may we ask the window manager for attention? Checked at most once a minute. Not when the compositor would answer
    the request by FOCUSING the window (Hyprland `misc:focus_on_activate`) — see kittymux_layout.attention_allowed."""
    now = time.monotonic()
    cached = vars(_RT).get("attention")
    if cached is None or now - cached[0] > 60.0:
        _ensure_path()
        import kittymux_layout
        steals = kittymux_layout.hypr_focus_on_activate()
        ok = kittymux_layout.attention_allowed(state_dir(), steals)
        cached = _RT.attention = (now, ok, "" if ok else "your compositor focuses windows that request attention (Hyprland misc:focus_on_activate): it would steal focus")
    return cached[1], cached[2]


def _alert(window) -> str:
    """Ask the window manager for attention (taskbar flash / urgent border) when an agent you are not looking at needs you. This is kitty's own
    bell path (`screen.bell()`), so it obeys the user's `window_alert_on_bell` / `enable_audio_bell`. Only for needs-you. Off with KITTYMUX_BELL=0
    or the file `bell-off`; skipped when it would steal focus. Returns what it did, for the decision log."""
    try:
        if getattr(window, "is_focused", False):
            return "skipped: you are looking at it"
        if os.environ.get("KITTYMUX_BELL") == "0" or os.path.exists(os.path.join(state_dir(), "bell-off")):
            return "skipped: switched off (bell-off)"
        quiet = _quiet_reason(window)
        if quiet:
            return "skipped: " + quiet.split(": ", 1)[1]
        allowed, why = _attention_allowed()
        if not allowed:
            return "skipped: " + why
        now = time.monotonic()
        alerted = vars(_RT).setdefault("alerted", {})      # (an _RT made by an older version lacks it)
        wid = str(window.id)
        if now - alerted.get(wid, -1e9) < NOTIFY_EVERY:
            return "skipped: this window rang less than %d s ago" % int(NOTIFY_EVERY)
        alerted[wid] = now
        window.screen.bell()
        return "rang"
    except Exception:
        return "error"


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


def _notify(window, state: str, detail: str, agent: str = "") -> str:
    """Desktop notification when an agent you are not looking at starts needing you or finishes.
    bin/mux-notify shows it and, if you invoke its action, jumps to this window. Returns "sent" or why not (for the decision log)."""
    try:
        kind = "done" if state == "done" else "needs"
        if getattr(window, "is_focused", False):
            return "suppressed: you are looking at it"
        if not _notify_enabled(kind):
            return "suppressed: notifications are switched off"
        quiet = _quiet_reason(window)
        if quiet:
            return quiet
        if not shutil.which("notify-send"):
            return "suppressed: notify-send is not installed"
        now = time.monotonic()
        wid = str(window.id)
        if now - _RT.notified.get(wid, -1e9) < NOTIFY_EVERY:
            return f"suppressed: this window was notified less than {int(NOTIFY_EVERY)} s ago"
        if not _within_budget(now):
            return "suppressed: global notification rate limit"
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
        return "sent"
    except Exception:
        return "error: could not start the notifier"


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
    _install_notification_tap()
    _retime(SCAN_FAST)
    return _RT.scan_timer is not None


def restart() -> None:
    """Drop the timers and start fresh — used after this file was reloaded so the timer runs the
    NEW code rather than the function objects of the previous version."""
    stop()
    _install_quit_capture()
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
