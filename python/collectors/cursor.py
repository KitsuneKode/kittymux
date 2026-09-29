"""cursor.py — Cursor plan + AI-authored-lines share.

state.vscdb holds subscription keys; ai-code-tracking.db scores commits
with composer/tab vs human line counts — an honest "today N lines · M% AI"
signal. No account-wide request quota is stored locally, so we don't fake one.
"""

import sqlite3
import time

from _common import HOME, sqlite_ro


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
