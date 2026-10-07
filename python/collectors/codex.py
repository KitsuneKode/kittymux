"""codex.py — Codex rate-limit snapshots from rollout journals.

Newest rollout-*.jsonl carries a rate_limits object with real
used_percent + resets_at for the primary (5h) and secondary (week)
windows, plus plan_type. Best data of the bunch — fully offline.
"""

import json
import time

from _common import HOME, fmt_wait

WINDOWS = {"primary": 5 * 3600, "secondary": 7 * 86400}     # seconds each rate-limit window lasts


def collect() -> dict:
    sessions = HOME / ".codex" / "sessions"
    if not sessions.is_dir():
        return {"name": "codex", "rows": [], "note": "not installed"}
    files = sorted(sessions.rglob("rollout-*.jsonl"), key=lambda p: p.name)[-3:]
    snap, plan = None, ""
    for f in reversed(files):
        try:
            with f.open(errors="replace") as fh:
                for line in fh:
                    if '"rate_limits"' not in line:
                        continue
                    try:
                        rl = json.loads(line).get("payload", {}).get("rate_limits")
                    except json.JSONDecodeError:
                        continue
                    if rl and (rl.get("primary") or rl.get("secondary")):
                        snap, plan = rl, rl.get("plan_type") or ""
            if snap:
                break
        except OSError:
            continue
    if not snap:
        return {"name": "codex", "rows": [], "note": "no usage data"}
    rows = []
    for key, label in (("primary", "5h"), ("secondary", "wk")):
        w = snap.get(key)
        if w and isinstance(w.get("used_percent"), (int, float)):
            rows.append({"label": label, "pct": w["used_percent"],
                         "reset": f"resets {fmt_wait(w['resets_at'])}"
                                  if w.get("resets_at") else "",
                         "window_s": WINDOWS[key]})
            if isinstance(w.get("resets_at"), (int, float)) and not isinstance(w.get("resets_at"), bool):
                rows[-1]["rem_s"] = max(0.0, w["resets_at"] - time.time())
    return {"name": "codex", "rows": rows, "note": plan}
