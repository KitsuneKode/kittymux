"""kittymux journal — a continuous record of every agent session you run, so nothing is lost between saves and the history is queryable (pure: no kitty
imports; unit-tested).

One record per agent session (`claude:<uuid>`; `agent:w<kitty pid>.<window>` while no session id is exposed): which agent, where (cwd), what the tab was called, the
command it was started with (flags and all), when it was first/last seen, its last state, how many runs it finished and how long it spent working. It is updated
by the scanner on state changes and at most once a minute otherwise — not per tick — and stored in `agent-sessions.json` (0600), bounded to RECORD_MAX records /
MAX_AGE_S, merged under a lock so several kitty processes can share it. `kittymux sessions history` reads it; `kittymux sessions recover` rebuilds a session from it
after a crash; the resume prompt uses it to say when a conversation was last active.
"""

from __future__ import annotations

import json
import os
import re
import time

RECORD_MAX = 300
MAX_AGE_S = 90 * 86400
HEARTBEAT_S = 60.0
SETTLE_AFTER_S = 3 * 86400          # a closed conversation untouched this long drops out of the default picker ("settled"); pinned ones never do
FLAG_FIELDS = ("pinned", "settled", "flags_ts")          # set by the user (pin / settle), not by the scanner: merged by their OWN timestamp


def key_for(agent: str, sid: str | None, kitty_pid: int, window: int | str) -> str:
    return f"{agent}:{sid}" if sid else f"{agent}:w{kitty_pid}.{window}"


def observe(records: dict, obs: dict, now: float) -> bool:
    """Fold one observation of a live agent window into `records`. `obs`: agent, sid, cwd, tab, argv, state, kitty_pid, wid, mode (all strings/ints; sid may be
    None). Returns True when something worth writing changed (a heartbeat alone is not: the caller decides when to write `last`)."""
    agent, sid = obs["agent"], obs.get("sid") or None
    key = key_for(agent, sid, obs["kitty_pid"], obs["wid"])
    rec = records.get(key)
    changed = False
    if rec is None:
        # a window-bound record becomes the session's record once its id is known: carry the history over
        old_key = key_for(agent, None, obs["kitty_pid"], obs["wid"])
        rec = records.pop(old_key, None) if sid and old_key in records else None
        if rec is None:
            rec = {"agent": agent, "first": round(now), "turns": 0, "work_s": 0, "state": "", "work_since": 0}
        records[key] = rec
        changed = True
    state = obs.get("state") or ""
    prev = rec.get("state", "")
    if state != prev:
        if prev == "working" and rec.get("work_since"):
            rec["work_s"] = int(rec.get("work_s", 0) + max(0, now - rec["work_since"]))
            rec["work_since"] = 0
        if state == "working":
            rec["work_since"] = round(now)
        if state == "done":
            rec["turns"] = rec.get("turns", 0) + 1
        rec["state"] = state
        changed = True
    for field in ("cwd", "tab", "argv", "mode", "sid"):
        value = obs.get(field)
        if value and rec.get(field) != value:
            rec[field] = value
            changed = True
    if rec.get("kitty_pid") != obs["kitty_pid"] or rec.get("wid") != obs["wid"]:
        rec["kitty_pid"], rec["wid"] = obs["kitty_pid"], obs["wid"]
        changed = True
    rec["last"] = round(now)
    rec["open"] = True
    return changed


def close_missing(records: dict, kitty_pid: int, running_keys: set, now: float) -> bool:
    """Records this kitty owned whose window is gone: finalise their working time and mark them closed."""
    changed = False
    for key, rec in records.items():
        if rec.get("kitty_pid") == kitty_pid and rec.get("open") and key not in running_keys:
            if rec.get("work_since"):
                rec["work_s"] = int(rec.get("work_s", 0) + max(0, now - rec["work_since"]))
                rec["work_since"] = 0
            rec["open"], rec["state"] = False, ""
            changed = True
    return changed


def prune(records: dict, now: float) -> None:
    """Age and size limits. A PINNED record is exempt from both: pinning means "keep this"."""
    for key in [k for k, r in records.items() if now - r.get("last", 0) > MAX_AGE_S and not r.get("pinned")]:
        del records[key]
    unpinned = [(k, r) for k, r in records.items() if not r.get("pinned")]
    if len(unpinned) > RECORD_MAX:
        for key, _ in sorted(unpinned, key=lambda kv: kv[1].get("last", 0))[: len(unpinned) - RECORD_MAX]:
            del records[key]


# ── the file ──────────────────────────────────────────────────────────────────
def path_for(state_dir: str) -> str:
    return os.path.join(state_dir, "agent-sessions.json")


def load(state_dir: str) -> dict:
    try:
        with open(path_for(state_dir), encoding="utf-8") as f:
            data = json.load(f)
        recs = data.get("records", {})
        return {k: v for k, v in recs.items() if isinstance(v, dict) and v.get("agent")} if isinstance(recs, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _lock(state_dir: str, wait: float):
    """An exclusive lock on the journal (a file descriptor to pass to os.close), or None if it stayed busy for `wait` seconds. Never blocks longer: the scanner calls this from kitty's
    main thread."""
    import fcntl
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(state_dir, "agent-sessions.lock"), os.O_WRONLY | os.O_CREAT, 0o600)
    deadline = time.monotonic() + wait
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                return None
            time.sleep(0.01)


def _write(state_dir: str, records: dict) -> None:
    path = path_for(state_dir)
    tmp = f"{path}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "records": records}, f, separators=(",", ":"))
    os.replace(tmp, path)


def flush(state_dir: str, mine: dict, now: float, wait: float = 0.25) -> bool:
    """Merge `mine` into the shared file (a record from another process wins when it is newer; pin/settle flags win by their own timestamp), prune, write atomically 0600.
    Never raises, never waits longer than `wait`."""
    try:
        lock = _lock(state_dir, wait)
        if lock is None:
            return False
        try:
            merged = load(state_dir)
            for key, rec in mine.items():
                other = merged.get(key)
                if other is None or rec.get("last", 0) >= other.get("last", 0):
                    merged[key] = dict(rec)
                    newer_flags = other if other is not None and other.get("flags_ts", 0) > rec.get("flags_ts", 0) else None
                else:
                    merged[key] = other
                    newer_flags = rec if rec.get("flags_ts", 0) > other.get("flags_ts", 0) else None
                if newer_flags is not None:                      # a pin / settle made elsewhere (the CLI) must not be undone by a stale copy of the record
                    for f in FLAG_FIELDS:
                        if f in newer_flags:
                            merged[key][f] = newer_flags[f]
            prune(merged, now)
            _write(state_dir, merged)
            return True
        finally:
            os.close(lock)
    except Exception:
        return False


def set_flag(state_dir: str, key: str, field: str, value: bool, now: float | None = None, wait: float = 1.0) -> bool:
    """Set `pinned` / `settled` on the record `key` (False when there is no such record or the lock stayed busy). Under the same lock as flush; stamped with `flags_ts` so the
    scanner's own, staler copy of the record cannot undo it on its next write."""
    if field not in ("pinned", "settled"):
        raise ValueError(field)
    now = time.time() if now is None else now
    try:
        lock = _lock(state_dir, wait)
        if lock is None:
            return False
        try:
            records = load(state_dir)
            if key not in records:
                return False
            records[key][field] = bool(value)
            if field == "pinned" and value:
                records[key]["settled"] = False                      # pinning brings a settled conversation back
            records[key]["flags_ts"] = now
            _write(state_dir, records)
            return True
        finally:
            os.close(lock)
    except Exception:
        return False


def lifecycle(entry: dict, now: float, settle_after: float = SETTLE_AFTER_S) -> str:
    """pinned | running | recent | settled. A pinned conversation is always shown; a running one is live; a closed one is `settled` when you settled it or it has not been touched for
    `settle_after` (3 days by default) — settled ones leave the default picker but stay reachable (`pick --all`) and are never deleted by this."""
    if entry.get("pinned"):
        return "pinned"
    if entry.get("running"):
        return "running"
    if entry.get("settled") or now - entry.get("last", now) > settle_after:
        return "settled"
    return "recent"


def key_for_window(records: dict, kitty_pid: int, window_id) -> str | None:
    """The record of the agent session running in that window (the newest one the scanner bound to it), or None."""
    best = None
    for key, rec in records.items():
        if rec.get("kitty_pid") == kitty_pid and str(rec.get("wid")) == str(window_id) and rec.get("open"):
            if best is None or rec.get("last", 0) > records[best].get("last", 0):
                best = key
    return best


# ── reading it back ───────────────────────────────────────────────────────────
def _alive(pid: int, proc: str = "/proc") -> bool:
    return isinstance(pid, int) and pid > 0 and (not os.path.isdir(proc) or os.path.isdir(f"{proc}/{pid}"))


def is_running(rec: dict, proc: str = "/proc") -> bool:
    return bool(rec.get("open")) and _alive(rec.get("kitty_pid", 0), proc)


def parse_span(text: str, default: float) -> float:
    """"90m", "6h", "7d" → seconds (default when unparseable)."""
    try:
        return float(text[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[text[-1].lower()]
    except (ValueError, KeyError, IndexError):
        return default


def entries(records: dict, now: float, since_s: float, proc: str = "/proc") -> list[dict]:
    """Records seen within `since_s`, newest first, each with `key` and `running`."""
    out = []
    for key, rec in records.items():
        if now - rec.get("last", 0) <= since_s:
            e = dict(rec)
            e["key"], e["running"] = key, is_running(rec, proc)
            out.append(e)
    return sorted(out, key=lambda e: e.get("last", 0), reverse=True)


def insights(recs: list[dict]) -> dict:
    """Totals for a list of entries: sessions, running now, runs finished, time worked, by agent."""
    by_agent: dict = {}
    for e in recs:
        a = by_agent.setdefault(e["agent"], {"sessions": 0, "turns": 0, "work_s": 0})
        a["sessions"] += 1
        a["turns"] += e.get("turns", 0)
        a["work_s"] += e.get("work_s", 0)
    return {"sessions": len(recs), "running": sum(1 for e in recs if e["running"]), "turns": sum(e.get("turns", 0) for e in recs),
            "work_s": sum(e.get("work_s", 0) for e in recs), "by_agent": by_agent}


_SECRET_FLAG = ("token", "key", "secret", "password", "passwd", "auth", "credential", "bearer")
_SECRET_VALUE = re.compile(r"(?:sk|pk|rk|sbp|ghp|gho|ghu|ghs|github_pat|xox[abprs]|AKIA|AIza|ya29|eyJ)[A-Za-z0-9_\-.]{12,}|[A-Za-z0-9+/_-]{40,}={0,2}")


def redact_argv(argv: list) -> list:
    """A command line safe to print or paste: the value of a secret-looking flag (`--api-key X`, `--token=X`) and anything shaped like a credential become `<redacted>`.
    The stored journal keeps the real command (0600, like a session file) so recovery can restart it; this is for output that leaves the machine."""
    out, hide_next = [], False
    for tok in argv:
        tok = str(tok)
        if hide_next:
            out.append("<redacted>")
            hide_next = False
            continue
        flag, eq, val = tok.partition("=") if tok.startswith("-") else (tok, "", "")
        if tok.startswith("-") and any(w in flag.lower() for w in _SECRET_FLAG):
            if eq:
                out.append(f"{flag}=<redacted>")
            else:
                out.append(tok)
                hide_next = True
            continue
        out.append("<redacted>" if _SECRET_VALUE.fullmatch(tok) else tok)
    return out


def human_span(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{seconds // 60}m"
    if seconds < 86400 * 2:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
    return f"{seconds // 86400}d"


def recoverable(recs: list[dict]) -> list[dict]:
    """Entries that were open work and are no longer running: what a crash or a closed kitty left behind. Needs a command to restart."""
    return [e for e in recs if not e["running"] and e.get("argv") and e.get("cwd")]
