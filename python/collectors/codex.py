"""codex.py — Codex rate-limit snapshots from rollout journals.

Newest rollout-*.jsonl carries a rate_limits object with real
used_percent + resets_at for the primary (5h) and secondary (week)
windows, plus plan_type. Best data of the bunch — fully offline.
"""

import json
import os
import time
from datetime import datetime

from _common import HOME, fmt_wait

WINDOWS = {"primary": 5 * 3600, "secondary": 7 * 86400}     # seconds each rate-limit window lasts when the event does not say
LABELS = {"primary": "5h", "secondary": "wk"}
TAIL_BYTES = 512 * 1024                                       # a rollout is read from its end: limit events are frequent, the head is never newer
FILES = 6                                                     # newest-modified rollouts looked at


def _epoch(iso) -> float | None:
    """The event's own clock ("2026-10-07T06:16:33.038Z"), as epoch seconds; None when absent or unreadable."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _newest_in(path) -> tuple | None:
    """(event time or None, rate_limits) of the LAST limit event in one rollout; reads only the tail."""
    try:
        with path.open("rb") as fh:
            size = os.fstat(fh.fileno()).st_size
            fh.seek(max(0, size - TAIL_BYTES))
            raw = fh.read(TAIL_BYTES)
    except OSError:
        return None
    lines = raw.decode("utf-8", errors="replace").splitlines()
    if size > TAIL_BYTES and lines:
        lines = lines[1:]                                     # the first line of a tail is usually cut in half
    best = None
    for line in lines:
        if '"rate_limits"' not in line:
            continue
        try:
            event = json.loads(line)
            rl = event.get("payload", {}).get("rate_limits")
        except (json.JSONDecodeError, AttributeError):
            continue
        if isinstance(rl, dict) and (rl.get("primary") or rl.get("secondary")):
            ts = _epoch(event.get("timestamp"))
            if best is None or ts is None or best[0] is None or ts >= best[0]:
                best = (ts, rl)
    return best


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf") else None


def collect() -> dict:
    sessions = HOME / ".codex" / "sessions"
    if not sessions.is_dir():
        return {"name": "codex", "rows": [], "note": "not installed"}
    stamped = []
    for p in sessions.rglob("rollout-*.jsonl"):
        try:
            stamped.append((p.stat().st_mtime, p))
        except OSError:
            continue                                          # a rollout that vanished mid-scan is not a failure
    best = None                                               # (event time or file mtime, event time, rate_limits)
    for mtime, f in sorted(stamped, key=lambda t: t[0], reverse=True)[:FILES]:
        found = _newest_in(f)
        if found is None:
            continue
        ts, rl = found
        key = ts if ts is not None else mtime
        if best is None or key > best[0]:
            best = (key, ts, rl)
    if best is None:
        return {"name": "codex", "rows": [], "note": "no usage data"}
    _key, sample_ts, snap = best
    now = time.time()
    rows = []
    for key, label in LABELS.items():
        w = snap.get(key)
        if not isinstance(w, dict) or _num(w.get("used_percent")) is None:
            continue
        minutes = _num(w.get("window_minutes"))
        window_s = minutes * 60 if minutes and 0 < minutes <= 60 * 24 * 31 else WINDOWS[key]
        resets_at = _num(w.get("resets_at"))
        if resets_at is not None and resets_at <= now:
            # the window this sample describes has ended: its percentage says nothing about the window that is open now
            rows.append({"label": label, "text": "window reset · no newer sample", "state": "closed"})
            continue
        row = {"label": label, "pct": w["used_percent"], "reset": f"resets {fmt_wait(resets_at)}" if resets_at else "", "window_s": window_s}
        if resets_at is not None:
            row["rem_s"] = max(0.0, resets_at - now)
        rows.append(row)
    out = {"name": "codex", "rows": rows, "note": snap.get("plan_type") or ""}
    if sample_ts is not None:
        out["sample_ts"] = sample_ts                          # when Codex last reported these numbers (the view says how old they are)
    return out
