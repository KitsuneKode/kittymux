"""kittymux inbox — typed events for everything that deserves your attention, one shared store (pure: no kitty imports; unit-tested).

Where events come from (most authoritative first): what the AGENT itself announced (its own OSC 9/99 notification, captured natively from
kitty's notification pipeline), the agent's hooks, then what we read off its screen. All of them become the same typed event:

    kind      permission | question | limit | done | error | info
    severity  needs-you | warn | info            (derived from kind)
    source    agent | hook | screen              (who said so; `sources` lists every one that agreed)
    confidence  high | low                        (a "done" read only off a screen is low: shown in the inbox and the bar, never a popup on its own)

The store is `inbox.jsonl` in the state dir (0600): append-only operations — {"op":"add",…} / {"op":"ack",…} / {"op":"clear"} — so several kitty
processes can write it with O_APPEND and nobody rewrites anyone's data; readers fold it. `inbox-snapshot.json` is the folded newest-first view,
rewritten atomically after every change: the single file a shell widget (Quickshell, eww, waybar) watches. See docs/inbox.md for the contract.
"""

from __future__ import annotations

import json
import os
import re
import time

KINDS = ("permission", "question", "limit", "done", "error", "info")
SEVERITY = {"permission": "needs-you", "question": "needs-you", "limit": "warn", "error": "warn", "done": "info", "info": "info"}
STATUSES = ("unread", "read", "dismissed")

STORE_MAX_BYTES = 256 * 1024     # compact the log past this size
KEEP_EVENTS = 200                # events kept after compaction (and in the snapshot's backing view)
SNAPSHOT_EVENTS = 60             # events in inbox-snapshot.json
MERGE_WINDOW_S = 45.0            # the same thing reported again inside this window (by another source, or twice) is one event
BODY_MAX = 160
TITLE_MAX = 80

_I = re.IGNORECASE
_CTRL = {c: " " for c in list(range(0, 32)) + [127] + list(range(0x80, 0xA0))}


def clean(text, limit: int) -> str:
    """One line, no control characters, bounded (what an agent sends is untrusted text)."""
    return " ".join(str(text or "").translate(_CTRL).split())[:limit]


# ── classification of what an agent said ──────────────────────────────────────
_LIMIT = re.compile(r"(?:usage|rate|weekly|daily|monthly|5-?hour|session)\s+limit|quota|out\s+of\s+(?:credits|acus?)|credits?\s+(?:exhausted|depleted)"
                    r"|resource\s+has\s+been\s+exhausted|too\s+many\s+requests", _I)
_PERMISSION = re.compile(r"permission|approv|authori[sz]|\ballow\b|confirm|\bproceed\b|\(y/n\)|\bapply\b|\boverwrite\b|make\s+this\s+edit|\brun\s+(?:this|the\s+following)", _I)
_QUESTION = re.compile(r"\?\s*$|\bquestion\b|asks?\s+you|needs?\s+your\s+(?:input|answer|attention|decision|response)|"
                       r"(?:waiting|waits)\s+for\s+(?:your\s+)?(?:answer|response|decision|reply)", _I)
_ERROR = re.compile(r"\b(?:error|failed|failure|crash(?:ed)?|exception|could\s+not|cannot|unable\s+to)\b", _I)
_DONE = re.compile(r"\b(?:turn|task|run|job|agent|session)\s+(?:is\s+)?(?:complete|completed|finished|done)\b|\bfinished\b|\bcompleted\b|\bdone\b"
                   r"|ready\s+for\s+(?:your\s+)?(?:next|review)", _I)
_IDLE = re.compile(r"waiting\s+for\s+your\s+input|is\s+idle|awaiting\s+(?:your\s+)?(?:next\s+)?(?:prompt|input)", _I)


def classify_text(title: str, body: str = "", urgency: int | None = None) -> tuple[str, str]:
    """(kind, tag) for a notification an agent sent. Conservative: only specific, documented-looking phrasings are anything but "info" —
    an unrecognised message is recorded as info, never guessed into a completion. `tag` is a short machine label ("idle-notice", …).
    Order: limit > permission > question > error > done > info. `urgency` is kitty's (0 low, 1 normal, 2 critical)."""
    text = f"{title or ''} {body or ''}"
    if _LIMIT.search(text):
        return "limit", ""
    if _IDLE.search(text):
        return "info", "idle-notice"          # "waiting for your input": the agent has been idle since it finished — not a new completion
    if _PERMISSION.search(text):
        return "permission", ""
    if _QUESTION.search(text):
        return "question", ""
    if _ERROR.search(text):
        return "error", ""
    if _DONE.search(text):
        return "done", ""
    return "info", ""


_RESET_IN = re.compile(r"(?:resets?|available|try\s+again)\s+in\s+((?:\d+\s*[dhms]\s*)+)", _I)
_RESET_AT = re.compile(r"(?:resets?|available|try\s+again)\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", _I)
_UNIT = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_reset(text: str, now: float, tz_offset_s: float = 0.0) -> float | None:
    """When a usage limit lifts, as epoch seconds, from phrasings like "resets in 10h 50m" or "resets at 5pm"; None if there is no such hint.
    Best effort by design: the result only labels the inbox entry and de-duplicates repeats, nothing depends on it being exact."""
    m = _RESET_IN.search(text or "")
    if m:
        total = sum(int(n) * _UNIT[u.lower()] for n, u in re.findall(r"(\d+)\s*([dhms])", m.group(1), _I))
        return now + total if total > 0 else None
    m = _RESET_AT.search(text or "")
    if m:
        hour = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
        minute = int(m.group(2) or 0)
        if hour > 23 or minute > 59:
            return None
        local = now + tz_offset_s
        midnight = local - (local % 86400)
        target = midnight + hour * 3600 + minute * 60
        if target <= local:
            target += 86400
        return target - tz_offset_s
    return None


# ── events ────────────────────────────────────────────────────────────────────
_SEQ = [0]


def make_event(kind: str, agent: str, window: int | str, source: str, now: float, *, pid: int = 0, tab: str = "", title: str = "",
               body: str = "", confidence: str = "high", reset_at: float | None = None, private: bool = False, tag: str = "") -> dict:
    """A new event dict. `private` drops the body (the agent's own words may contain a command or a path)."""
    if kind not in KINDS:
        kind = "info"
    _SEQ[0] += 1
    ev = {"op": "add", "id": f"{int(now * 1000):x}-{pid}-{_SEQ[0]}", "t": round(now, 1), "pid": pid, "w": str(window), "kind": kind,
          "severity": SEVERITY[kind], "agent": clean(agent, 24), "tab": clean(tab, TITLE_MAX), "title": clean(title, TITLE_MAX),
          "body": "" if private else clean(body, BODY_MAX), "sources": [source], "confidence": confidence, "status": "unread", "count": 1}
    if tag:
        ev["tag"] = clean(tag, 24)
    if reset_at:
        ev["reset_at"] = round(reset_at)
    return ev


def merge_key(ev: dict) -> tuple:
    """Two events with the same key inside MERGE_WINDOW_S are the same occurrence reported twice (by the agent's own notification AND the
    screen scan, say). A limit is one occurrence per agent per reset, whichever window noticed it."""
    if ev.get("kind") == "limit":
        return ("limit", ev.get("pid"), ev.get("agent"), ev.get("reset_at", 0) // 3600)
    return (ev.get("kind"), ev.get("pid"), ev.get("w"))


def fold(ops: list[dict]) -> list[dict]:
    """Replay the append-only log into the current events, oldest first. Unknown/damaged operations are ignored."""
    events: dict[str, dict] = {}
    order: list[str] = []
    recent: dict[tuple, str] = {}                 # merge key -> id of the newest event with it
    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        if kind == "add" and isinstance(op.get("id"), str) and op.get("kind") in KINDS:
            key = merge_key(op)
            prev = events.get(recent.get(key, ""))
            # the window is symmetric: a report appended out of order (two kitty processes, a skewed clock) must not merge into an event it is hours away from
            if prev is not None and abs(op.get("t", 0) - prev.get("t", 0)) <= MERGE_WINDOW_S and prev.get("status") == "unread":
                prev["count"] = prev.get("count", 1) + 1
                prev["t0"] = min(prev.get("t0", prev.get("t", 0)), op.get("t", 0))
                prev["t"] = max(prev.get("t", 0), op.get("t", 0))             # the newest report; it never moves backwards
                prev["sources"] = sorted(set(prev.get("sources", [])) | set(op.get("sources", [])))
                if op.get("confidence") == "high":
                    prev["confidence"] = "high"                      # any authoritative source upgrades it
                for field in ("body", "title", "tab", "reset_at", "tag"):
                    if op.get(field):
                        prev[field] = op[field]
                continue
            ev = {k: v for k, v in op.items() if k != "op"}
            ev.setdefault("t0", ev.get("t", 0))                      # when it FIRST appeared (`t` moves to the newest report of a merged event)
            events[ev["id"]] = ev
            order.append(ev["id"])
            recent[key] = ev["id"]
        elif kind == "ack":
            targets = op.get("ids") or []
            for eid in order:
                ev = events[eid]
                if eid in targets or (op.get("w") is not None and str(op["w"]) == ev.get("w") and str(op.get("pid", ev.get("pid"))) == str(ev.get("pid"))):
                    if ev.get("status") == "unread":
                        ev["status"] = op.get("status") if op.get("status") in STATUSES else "read"
                        ev["ack_t"] = op.get("t", 0)                    # when you first looked at it (focused its window, read or dismissed it)
        elif kind == "restore":                                    # an undone dismissal: the event is unread again, as if it had never been looked at
            ids = op.get("ids")
            for eid in ids if isinstance(ids, list) else []:
                ev = events.get(eid) if isinstance(eid, str) else None
                if ev is not None and ev.get("status") == "dismissed":
                    ev["status"] = "unread"
                    ev.pop("ack_t", None)
        elif kind == "clear":
            for ev in events.values():
                if ev.get("status") == "unread" or op.get("all"):
                    if ev.get("status") == "unread":
                        ev["ack_t"] = op.get("t", 0)
                    ev["status"] = "dismissed"
    return [events[i] for i in order]


def is_duplicate(existing: list[dict], ev: dict) -> bool:
    """Would adding `ev` merge into a still-unread event? (The caller then skips the popup: it was already shown.)"""
    key = merge_key(ev)
    for old in reversed(existing):
        if merge_key(old) == key and old.get("status") == "unread" and abs(ev.get("t", 0) - old.get("t", 0)) <= MERGE_WINDOW_S:
            return True
    return False


def snapshot(events: list[dict], now: float, limit: int = SNAPSHOT_EVENTS) -> dict:
    """What a shell widget reads: counts plus the newest events first. Schema version 1."""
    newest = list(reversed(events))[:limit]
    unread = [e for e in events if e.get("status") == "unread"]
    return {"version": 1, "updated": round(now, 1), "unread": len(unread),
            "needs_you": sum(1 for e in unread if e.get("severity") == "needs-you"), "events": newest}


def compact(events: list[dict]) -> list[dict]:
    """The operations that rebuild `events` (newest KEEP_EVENTS) as a fresh log: adds with their current status, nothing else."""
    out = []
    for ev in events[-KEEP_EVENTS:]:
        op = dict(ev)
        op["op"] = "add"
        out.append(op)
    return out


# ── the store (files) ─────────────────────────────────────────────────────────
def store_path(state_dir: str) -> str:
    return os.path.join(state_dir, "inbox.jsonl")


def snapshot_path(state_dir: str) -> str:
    return os.path.join(state_dir, "inbox-snapshot.json")


def read_ops(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _append(path: str, op: dict) -> int:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(op, separators=(",", ":")) + "\n").encode("utf-8"))
        return os.fstat(fd).st_size
    finally:
        os.close(fd)


def _write_atomic(path: str, data: str) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)


def _locked(state_dir: str):
    import fcntl
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(state_dir, "inbox.lock"), os.O_WRONLY | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _refresh(state_dir: str, now: float) -> list[dict]:
    """Fold the log, compact it if it grew past STORE_MAX_BYTES, rewrite the snapshot. Caller holds the lock."""
    path = store_path(state_dir)
    events = fold(read_ops(path))
    try:
        if os.path.getsize(path) > STORE_MAX_BYTES:
            _write_atomic(path, "".join(json.dumps(op, separators=(",", ":")) + "\n" for op in compact(events)))
            events = fold(read_ops(path))
    except OSError:
        pass
    _write_atomic(snapshot_path(state_dir), json.dumps(snapshot(events, now), separators=(",", ":")))
    return events


def add(state_dir: str, ev: dict) -> tuple[bool, dict]:
    """Record an event. Returns (is_new, event): is_new is False when it merged into an unread event from the last MERGE_WINDOW_S (nothing to
    announce again). Never raises."""
    try:
        fd = _locked(state_dir)
        try:
            existing = fold(read_ops(store_path(state_dir)))
            dup = is_duplicate(existing, ev)
            _append(store_path(state_dir), ev)
            _refresh(state_dir, ev["t"])
            return (not dup), ev
        finally:
            os.close(fd)
    except Exception:
        return True, ev


def ack(state_dir: str, now: float, *, ids: list | None = None, window: str | int | None = None, pid: int | None = None,
        status: str = "read") -> None:
    """Mark events read (or dismissed): by id, or everything of one window (when you focus it)."""
    try:
        op = {"op": "ack", "t": round(now, 1), "status": status}
        if ids:
            op["ids"] = list(ids)
        if window is not None:
            op["w"] = str(window)
            if pid is not None:
                op["pid"] = pid
        fd = _locked(state_dir)
        try:
            _append(store_path(state_dir), op)
            _refresh(state_dir, now)
        finally:
            os.close(fd)
    except Exception:
        pass


def restore(state_dir: str, now: float, ids: list) -> None:
    """Undo a dismissal (only events that are still dismissed come back; anything else is left alone)."""
    try:
        fd = _locked(state_dir)
        try:
            _append(store_path(state_dir), {"op": "restore", "t": round(now, 1), "ids": [i for i in ids if isinstance(i, str)]})
            _refresh(state_dir, now)
        finally:
            os.close(fd)
    except Exception:
        pass


def clear(state_dir: str, now: float, everything: bool = False) -> None:
    try:
        fd = _locked(state_dir)
        try:
            _append(store_path(state_dir), {"op": "clear", "t": round(now, 1), "all": bool(everything)})
            _refresh(state_dir, now)
        finally:
            os.close(fd)
    except Exception:
        pass


def load(state_dir: str) -> list[dict]:
    """The current events, oldest first."""
    return fold(read_ops(store_path(state_dir)))
