"""cursor.py — Cursor plan + AI-authored-lines share.

state.vscdb holds subscription keys; ai-code-tracking.db scores commits
with composer/tab vs human line counts — an honest "today N lines · M% AI"
signal. No account-wide request quota is stored locally, so we don't fake one.
"""

import json
import sqlite3

import time

from _common import (HOME, LiveError, curl_json, fmt_wait, sqlite_ro,
                     live_failure, live_fresh, live_success, local_day)


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
        rows.append({"label": "plan", "text": f"{plan} · {status}", "plan": str(plan), "status": str(status)})
    except sqlite3.Error:
        rows.append({"label": "plan", "text": "?"})
    if tracking.is_file():
        try:
            tdb = sqlite_ro(tracking)
            now = time.time()
            _, midnight = local_day(now)
            midnight_ms = int(midnight * 1000)
            ai, _human, added = tdb.execute(
                "select coalesce(sum(composerLinesAdded+tabLinesAdded),0),"
                "       coalesce(sum(humanLinesAdded),0),"
                "       coalesce(sum(linesAdded),0)"
                " from scored_commits where scoredAt >= ? and scoredAt <= ?",
                (midnight_ms, int(now * 1000))).fetchone()
            tdb.close()
            if added:
                pct = round(ai / added * 100) if added else 0
                rows.append({"label": "today", "text": f"{added} lines · {pct}% AI", "lines": added, "ai_pct": pct})
        except sqlite3.Error:
            pass
    return {"name": "cursor", "rows": rows}


def live(cached_live: dict) -> dict:
    """Opt-in real pools via DashboardService/GetCurrentPeriodUsage — the
    same Connect-RPC the Cursor CLI uses. Bearer = CLI auth.json token.
    Returns planUsage percents + spend; cached 5min like claude's live()."""
    if live_fresh(cached_live):
        return cached_live
    auth = HOME / ".config" / "cursor" / "auth.json"
    try:
        data = json.loads(auth.read_text())
        tok = data.get("accessToken") if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return live_failure(cached_live, "credentials unavailable")
    if not isinstance(tok, str) or not tok:
        return live_failure(cached_live, "credentials unavailable")
    try:
        data = curl_json(
            "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage",
            headers=[f"Authorization: Bearer {tok}", "Content-Type: application/json",
                     "connect-protocol-version: 1", "x-cursor-client-type: cli"],
            body="{}")
    except LiveError as e:
        return live_failure(cached_live, str(e))
    plan = data.get("planUsage") or {}
    if not isinstance(plan, dict) or not plan:
        return live_failure(cached_live, "usage unavailable")
    try:
        end_ts = float(data.get("billingCycleEnd") or 0) / 1000
    except (TypeError, ValueError):
        end_ts = 0
    reset = f"resets {fmt_wait(end_ts)}" if end_ts else ""
    rem_s = end_ts - time.time() if end_ts else 0
    rows = []
    # Label convention: '5h' rows get replaced by live data upstream, so use
    # distinct pool labels; the host prepends these before local rows.
    for key, label in (("totalPercentUsed", "mo"),
                       ("autoPercentUsed", "auto"),
                       ("apiPercentUsed", "api")):
        u = plan.get(key)
        if isinstance(u, (int, float)):
            rows.append({"label": label, "pct": min(100.0, float(u)),
                         "reset": reset, "rem_s": rem_s})
    spend = plan.get("totalSpend")
    if isinstance(spend, (int, float)) and spend > 0:
        bonus = plan.get("bonusSpend") or 0
        included = plan.get("includedSpend") or 0
        note = f"${spend / 100:.0f}"
        if isinstance(bonus, (int, float)) and bonus > 0:
            note += f" (incl ${bonus / 100:.0f} bonus)"
        rows.append({"label": "spend", "text": note,
                     "stack": [v for v in (included, bonus) if isinstance(v, (int, float)) and v > 0]})
    return live_success(rows) if rows else live_failure(cached_live, "usage unavailable")
