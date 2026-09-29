"""claude.py — Claude usage reconstructed from transcripts.

Transcripts only record quotaLimits on limit *hits*, so local truth is:
the reconstructed 5h billing window (message-triggered, expires 5h after
the first message), burn inside the live window, weekly fresh-vs-cached
tokens, and the last recorded cap. Optional live() adds real utilization
via the OAuth usage endpoint — opt-in only (KITTYMUX_USAGE_LIVE=1).
"""

import json
import subprocess
import time

from _common import HOME, LIVE_TTL, fmt_ago, fmt_tokens, fmt_wait, iso_ts


def collect() -> dict:
    root = HOME / ".claude" / "projects"
    if not root.is_dir():
        return {"name": "claude", "rows": [], "note": "not installed"}
    now = time.time()
    week_cut, scan_cut = now - 7 * 86400, now - 12 * 3600

    files = sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime,
                   reverse=True)
    events: list[tuple[float, int, int]] = []  # (ts, fresh, cached)
    week_fresh, week_cached, week_sess = 0, 0, set()
    hit = None  # (resetsAt, hit_ts)

    for f in files:
        try:
            if f.stat().st_mtime < week_cut:
                break
        except OSError:
            continue
        try:
            with f.open(errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line and '"quotaLimits"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    q = d.get("quotaLimits") or {}
                    if q.get("rateLimitType") == "five_hour" \
                            and q.get("status") == "rejected":
                        hit = (q.get("resetsAt") or 0, iso_ts(d.get("timestamp", "")))
                    u = (d.get("message") or {}).get("usage")
                    if not u or d.get("type") != "assistant":
                        continue
                    ts = iso_ts(d.get("timestamp", ""))
                    if not ts:
                        continue
                    fresh = (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0) \
                        + (u.get("cache_creation_input_tokens") or 0)
                    cached = u.get("cache_read_input_tokens") or 0
                    if ts >= week_cut:
                        week_fresh += fresh
                        week_cached += cached
                        week_sess.add(f.stem)
                    if ts >= scan_cut:
                        events.append((ts, fresh, cached))
        except OSError:
            continue

    rows: list[dict] = []
    # Walk events forward: an event landing after the window expires opens a
    # new one. Only the final window can still be live (it's ≤5h old).
    if events:
        events.sort()
        wstart, wfresh, wcached, wturns = events[0][0], 0, 0, 0
        for ts, fresh, cached in events:
            if ts > wstart + 5 * 3600:
                wstart, wfresh, wcached, wturns = ts, 0, 0, 0
            wfresh += fresh
            wcached += cached
            wturns += 1
        wend = wstart + 5 * 3600
        if wend > now:
            elapsed = min(100.0, (now - wstart) / (5 * 3600) * 100)
            rows.append({"label": "5h", "pct": elapsed, "clock": True,
                         "reset": f"resets {fmt_wait(wend)}"})
            cache_note = f" (+{fmt_tokens(wcached)} cached)" if wcached else ""
            rows.append({"label": "win",
                         "text": f"{fmt_tokens(wfresh)} tok{cache_note} · {wturns} turns"})
        else:
            rows.append({"label": "5h", "text": "window closed · next msg opens new"})
    else:
        rows.append({"label": "5h", "text": "idle"})
    if week_fresh:
        cache_note = f" (+{fmt_tokens(week_cached)} cached)" if week_cached else ""
        rows.append({"label": "week",
                     "text": f"{fmt_tokens(week_fresh)} tok{cache_note} · {len(week_sess)} sess"})
    if hit:
        resets, hit_ts = hit
        if resets > now:
            rows.append({"label": "cap", "pct": 100.0,
                         "reset": f"hit · resets {fmt_wait(resets)}"})
        elif hit_ts:
            rows.append({"label": "cap", "text": f"limit hit {fmt_ago(hit_ts)}"})
    return {"name": "claude", "rows": rows}


def live(cached_live: dict) -> dict:
    """Opt-in real quota via the OAuth usage endpoint (same data as the
    agent SDK's get_usage). Cached 5min so a keypress never hammers it."""
    if cached_live and time.time() - cached_live.get("ts", 0) < LIVE_TTL:
        return cached_live
    cred = HOME / ".claude" / ".credentials.json"
    try:
        tok = (json.loads(cred.read_text()).get("claudeAiOauth") or {}).get("accessToken")
    except (OSError, json.JSONDecodeError):
        return cached_live
    if not tok:
        return cached_live
    try:
        out = subprocess.run(
            ["curl", "-fsS", "--max-time", "3",
             "-H", f"Authorization: Bearer {tok}",
             "-H", "anthropic-beta: oauth-2025-04-20",
             "https://api.anthropic.com/api/oauth/usage"],
            capture_output=True, text=True, timeout=5)
        data = json.loads(out.stdout) if out.returncode == 0 else {}
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return cached_live
    rows = []
    for key, label in (("five_hour", "5h"), ("seven_day", "wk")):
        w = data.get(key) or {}
        u = w.get("utilization")
        if isinstance(u, (int, float)) and u <= 1.0:
            u = u * 100  # fraction form
        if not isinstance(u, (int, float)):
            continue
        rem_s = (iso_ts(w.get("resets_at") or "") - time.time()
                 if w.get("resets_at") else 0)
        rows.append({"label": label, "pct": min(100.0, float(u)),
                     "reset": f"resets {fmt_wait(iso_ts(w.get('resets_at') or ''))}"
                              if w.get("resets_at") else "",
                     "rem_s": rem_s})
    return {"ts": time.time(), "rows": rows} if rows else cached_live
