#!/usr/bin/env python3
"""A synthetic world for the panel's Usage and Inbox views: a fake HOME the real collectors read, a week of usage history, inbox events.

    python3 tools/demo_world.py OUT_DIR            writes OUT_DIR/home and OUT_DIR/state

Run the panel with KITTYMUX_USAGE_HOME=OUT_DIR/home KITTYMUX_STATE=OUT_DIR/state and it draws what the author's own panel looked like (Codex at 99 % of its 5 hour
window, Claude with a closed window and a cap hit a week ago, Cursor on a plan, Devin with five sessions) without a byte of anyone's real data. `kittymux demo` and
`tests/shot_panel.sh` use it. Every number here is made up; nothing is credential-shaped."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))      # tools/ sits next to python/
import kittymux_inbox as I  # noqa: E402


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def write(path: Path, text: str, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def codex(home: Path, now: float) -> None:
    line = {"payload": {"rate_limits": {"primary": {"used_percent": 99.0, "resets_at": now + 3 * 3600 + 50 * 60},
                                        "secondary": {"used_percent": 63.0, "resets_at": now + 4 * 86400 + 19 * 3600}, "plan_type": "plus"}}}
    write(home / ".codex/sessions/2026/10/rollout-2026-10-07T00-00-00-0a1b2c3d-0000-4000-8000-000000000001.jsonl", json.dumps(line) + "\n", now)


def claude(home: Path, now: float) -> None:
    """Twelve sessions this week (about 109M fresh tokens, 6.0G cached), the last one eight hours ago (its 5h window is closed), and a cap hit a week ago."""
    root = home / ".claude/projects/demo"
    for i in range(12):
        ts = now - (8 * 3600 if i == 0 else (i * 13 + 6) * 3600)
        event = {"type": "assistant", "timestamp": iso(ts),
                 "message": {"usage": {"input_tokens": 3_000_000, "output_tokens": 6_083_333, "cache_creation_input_tokens": 0,
                                       "cache_read_input_tokens": 500_000_000}}}
        text = json.dumps(event) + "\n"
        if i == 11:
            cap = {"timestamp": iso(now - 6 * 86400 - 20 * 3600), "quotaLimits": {"rateLimitType": "five_hour", "status": "rejected",
                                                                                 "resetsAt": now - 6 * 86400 - 15 * 3600}}
            text = json.dumps(cap) + "\n" + text
        write(root / f"0a1b2c3d-0000-4000-8000-0000000000{i:02d}.jsonl", text, now)


def cursor(home: Path, now: float) -> None:
    db = home / ".config/Cursor/User/globalStorage/state.vscdb"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("create table ItemTable (key text primary key, value text)")
    con.executemany("insert into ItemTable values (?, ?)", [("cursorAuth/stripeMembershipType", "pro"), ("cursorAuth/stripeSubscriptionStatus", "active")])
    con.commit()
    con.close()
    tracking = home / ".cursor/ai-tracking/ai-code-tracking.db"
    tracking.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(tracking)
    con.execute("create table scored_commits (composerLinesAdded int, tabLinesAdded int, humanLinesAdded int, linesAdded int, scoredAt int)")
    con.execute("insert into scored_commits values (120, 40, 252, 412, ?)", (int((now - 600) * 1000),))
    con.commit()
    con.close()


def devin(home: Path, now: float) -> None:
    for i in range(5):
        doc = {"final_metrics": {"total_prompt_tokens": 6_000_000, "total_completion_tokens": 1_520_000}, "agent": {"model_name": "SWE-2 Max"}}
        write(home / f".local/share/devin/cli/transcripts/session-{i}.json", json.dumps(doc), now - 60 * i)


def history(state: Path, now: float) -> None:
    claude_days = [18_000_000, 6_000_000, 31_000_000, 9_000_000, 27_000_000, 14_000_000, 4_000_000]
    devin_days = [0, 8_000_000, 3_000_000, 0, 12_000_000, 21_000_000, 9_000_000]
    hist = {}
    for back in range(6, -1, -1):
        day = (datetime.fromtimestamp(now) - timedelta(days=back)).strftime("%Y-%m-%d")
        c, d = claude_days[6 - back], devin_days[6 - back]
        hist[day] = {"_daily_version": 2, "claude_fresh": c, "devin_tok": d, "burn": c + d}
    write(state / "agent-usage-history.json", json.dumps(hist))


def inbox(state: Path, now: float) -> None:
    rows = [("permission", "claude", "api", "Claude needs your permission to use Bash", "rm -rf node_modules", 180, {}),
            ("question", "claude", "web", "Which migration approach should I use?", "", 60, {}),
            ("limit", "codex", "api", "5h usage limit reached", "", 540, {"reset_at": now + 3 * 3600 + 50 * 60}),
            ("done", "claude", "docs", "Finished in 4m 12s", "", 250, {}),
            ("info", "claude", "notes", "Session started", "", 900, {})]
    for kind, agent, tab, title, body, age, extra in rows:
        ev = I.make_event(kind, agent, 7, "screen", now - age, pid=424242, tab=tab, title=title, body=body, **extra)
        I.add(str(state), ev)
    I.ack(str(state), now, ids=[e["id"] for e in I.load(str(state)) if e["kind"] == "info"])      # the last one has been read


def build(out: Path, now: float | None = None) -> None:
    now = time.time() if now is None else now
    home, state = out / "home", out / "state"
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    for fn in (codex, claude, cursor, devin):
        fn(home, now)
    history(state, now)
    inbox(state, now)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(Path(sys.argv[1]))
    print(f"wrote {sys.argv[1]}/home and {sys.argv[1]}/state")
