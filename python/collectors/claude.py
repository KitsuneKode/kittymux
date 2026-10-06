"""claude.py — Claude usage reconstructed from transcripts.

Transcripts only record quotaLimits on limit *hits*, so local truth is:
the reconstructed 5h billing window (message-triggered, expires 5h after
the first message), burn inside the live window, weekly fresh-vs-cached
tokens, and the last recorded cap. Optional live() adds real utilization
via the OAuth usage endpoint — opt-in only (KITTYMUX_USAGE_LIVE=1).
"""

import json

import time

from _common import (HOME, LiveError, curl_json, fmt_ago, fmt_tokens, fmt_wait,
                     iso_ts, live_failure, live_fresh, live_success, local_day, safe_mtime)


def collect() -> dict:
    root = HOME / ".claude" / "projects"
    if not root.is_dir():
        return {"name": "claude", "rows": [], "note": "not installed"}
    now = time.time()
    day, midnight = local_day(now)
    daily_fresh = 0
    week_cut, scan_cut = now - 7 * 86400, now - 12 * 3600

    files = sorted(root.rglob("*.jsonl"), key=safe_mtime,
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
                    if not ts or ts > now:
                        continue
                    fresh = (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0) \
                        + (u.get("cache_creation_input_tokens") or 0)
                    cached = u.get("cache_read_input_tokens") or 0
                    if ts >= midnight:
                        daily_fresh += fresh
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
            if ts >= wstart + 5 * 3600:
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
    return {"name": "claude", "rows": rows,
            "daily": {"day": day, "claude_fresh": daily_fresh}}


def live(cached_live: dict) -> dict:
    """Opt-in real quota via the OAuth usage endpoint (same data as the
    agent SDK's get_usage). Cached 5min so a keypress never hammers it."""
    if live_fresh(cached_live):
        return cached_live
    cred = HOME / ".claude" / ".credentials.json"
    try:
        data = json.loads(cred.read_text())
        oauth = data.get("claudeAiOauth") if isinstance(data, dict) else None
        tok = oauth.get("accessToken") if isinstance(oauth, dict) else None
    except (OSError, json.JSONDecodeError):
        return live_failure(cached_live, "credentials unavailable")
    if not isinstance(tok, str) or not tok:
        return live_failure(cached_live, "credentials unavailable")
    try:
        data = curl_json("https://api.anthropic.com/api/oauth/usage",
                         headers=[f"Authorization: Bearer {tok}",
                                  "anthropic-beta: oauth-2025-04-20"], max_time=3)
    except LiveError as e:
        return live_failure(cached_live, str(e))
    rows = []
    for key, label in (("five_hour", "5h"), ("seven_day", "wk"),
                       ("seven_day_opus", "wk·opus"),
                       ("seven_day_sonnet", "wk·sonnet"),
                       ("seven_day_cowork", "wk·cowork"),
                       ("seven_day_oauth_apps", "wk·apps")):
        w = data.get(key) or {}
        if not isinstance(w, dict):
            continue
        u = w.get("utilization")

        if not isinstance(u, (int, float)):
            continue
        rem_s = (iso_ts(w.get("resets_at") or "") - time.time()
                 if w.get("resets_at") else 0)
        rows.append({"label": label, "pct": min(100.0, float(u)),
                     "reset": f"resets {fmt_wait(iso_ts(w.get('resets_at') or ''))}"
                              if w.get("resets_at") else "",
                     "rem_s": rem_s})
    return live_success(rows) if rows else live_failure(cached_live, "usage unavailable")
