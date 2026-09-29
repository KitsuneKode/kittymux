"""cursor.py — Cursor plan + AI-authored-lines share.

state.vscdb holds subscription keys; ai-code-tracking.db scores commits
with composer/tab vs human line counts — an honest "today N lines · M% AI"
signal. No account-wide request quota is stored locally, so we don't fake one.
"""

import json
import sqlite3
import subprocess
import time

from _common import HOME, LIVE_TTL, fmt_wait, sqlite_ro


def collect() -> dict:
    db_path = HOME / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb"
    tracking = HOME / ".cursor" / "ai-tracking" / "ai-code-tracking.db"
    if not db_path.is_file():
        return {"name": "cursor", "rows": [], "note": "not installed"}
    rows = []
    try:
        db = sqlite_ro(db_path)
        get = lambda k: (db.execute(
            "select value from ItemTable where key=?", (k,)).fetchone() or [None])[0]
        plan = get("cursorAuth/stripeMembershipType") or "?"
        status = get("cursorAuth/stripeSubscriptionStatus") or "?"
        db.close()
        rows.append({"label": "plan", "text": f"{plan} · {status}"})
    except sqlite3.Error:
        rows.append({"label": "plan", "text": "?"})
    if tracking.is_file():
        try:
            tdb = sqlite_ro(tracking)
            midnight_ms = int(time.mktime(
                time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d")) * 1000)
            ai, _human, added = tdb.execute(
                "select coalesce(sum(composerLinesAdded+tabLinesAdded),0),"
                "       coalesce(sum(humanLinesAdded),0),"
                "       coalesce(sum(linesAdded),0)"
                " from scored_commits where scoredAt >= ?", (midnight_ms,)).fetchone()
            tdb.close()
            if added:
                pct = round(ai / added * 100) if added else 0
                rows.append({"label": "today", "text": f"{added} lines · {pct}% AI"})
        except sqlite3.Error:
            pass
    return {"name": "cursor", "rows": rows}


def live(cached_live: dict) -> dict:
    """Opt-in real pools via DashboardService/GetCurrentPeriodUsage — the
    same Connect-RPC the Cursor CLI uses. Bearer = CLI auth.json token.
    Returns planUsage percents + spend; cached 5min like claude's live()."""
    if cached_live and time.time() - cached_live.get("ts", 0) < LIVE_TTL:
        return cached_live
    auth = HOME / ".config" / "cursor" / "auth.json"
    try:
        tok = json.loads(auth.read_text()).get("accessToken")
    except (OSError, json.JSONDecodeError):
        return cached_live
    if not tok:
        return cached_live
    try:
        out = subprocess.run(
            ["curl", "-fsS", "--max-time", "4", "-X", "POST",
             "-H", f"Authorization: Bearer {tok}",
             "-H", "Content-Type: application/json",
             "-H", "connect-protocol-version: 1",
             "-H", "x-cursor-client-type: cli",
             "-d", "{}",
             "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage"],
            capture_output=True, text=True, timeout=6)
        data = json.loads(out.stdout) if out.returncode == 0 else {}
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return cached_live
    plan = data.get("planUsage") or {}
    if not plan:
        return cached_live
    try:
        end_ts = float(data.get("billingCycleEnd") or 0) / 1000
    except (TypeError, ValueError):
        end_ts = 0
    reset = f"resets {fmt_wait(end_ts)}" if end_ts else ""
    rows = []
    # Label convention: '5h' rows get replaced by live data upstream, so use
    # distinct pool labels; the host prepends these before local rows.
    for key, label in (("totalPercentUsed", "mo"),
                       ("autoPercentUsed", "auto"),
                       ("apiPercentUsed", "api")):
        u = plan.get(key)
        if isinstance(u, (int, float)):
            rows.append({"label": label, "pct": min(100.0, float(u)),
                         "reset": reset})
    spend = plan.get("totalSpend")
    if isinstance(spend, (int, float)) and spend > 0:
        bonus = plan.get("bonusSpend") or 0
        note = f"${spend / 100:.0f} spend"
        if isinstance(bonus, (int, float)) and bonus > 0:
            note += f" (incl ${bonus / 100:.0f} bonus)"
        rows.append({"label": "spend", "text": note})
    return {"ts": time.time(), "rows": rows} if rows else cached_live
