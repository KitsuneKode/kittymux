"""_common.py — shared helpers for kittymux usage collectors.

Collector contract — every collectors/*.py module defines:

    def collect() -> dict:
        return {
            "name": "codex",                 # provider id, lowercase
            "rows": [                        # rendered top-to-bottom
                {"label": "5h", "pct": 62.0, "reset": "resets in 1h 53m"},
                {"label": "win", "text": "8.2M tok · 23 turns"},
                {"label": "5h", "pct": 14.0, "reset": "...", "clock": True},
            ],
            "note": "plus",                  # optional dim suffix on the row
            "daily": {"day": "2026-03-09", "claude_fresh": 1234},
            # Optional exact daily counters for history, never formatted text.
        }

    # Optional — called only when KITTYMUX_USAGE_LIVE is enabled:
    def live(cached: dict) -> dict:
        # Return {"ts": last_success, "attempt_ts": last_attempt, "rows": [...]},
        # retaining cached rows plus a safe "error" on failure. Both successes
        # and failures respect LIVE_TTL. The caller persists all attempts.

Row keys:
    label  str   — left column tag ("5h", "week", "plan", ...)
    pct    float — renders a quota bar (green→red); "clock": True renders
             the elapsed-time variant (mauve) instead
    reset  str   — dim suffix after the bar
    text   str   — plain text row when no pct is present

Collectors must be pure local-file reads — no provider CLI spawns, no
network unless implementing live(). Be honest: show "unavailable" rather
than a fabricated percentage.
"""

import json
import math
import os
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

# KITTYMUX_USAGE_HOME points the collectors at another home (the demo and the panel screenshots read tools/demo_world.py's synthetic one); unset, it is yours.
HOME = Path(os.environ["KITTYMUX_USAGE_HOME"]) if os.environ.get("KITTYMUX_USAGE_HOME") else Path.home()
# KITTYMUX_STATE is the state dir itself; otherwise derive under XDG state.
STATE_DIR = Path(os.environ["KITTYMUX_STATE"]) \
    if os.environ.get("KITTYMUX_STATE") else \
    Path(os.environ.get("XDG_STATE_HOME", HOME / ".local" / "state")) / "kittymux"
CACHE = STATE_DIR / "agent-usage.json"
HIST = STATE_DIR / "agent-usage-history.json"
TTL = 60.0
LIVE_TTL = 300.0  # live quota fetch is opt-in and polite: 5min minimum cadence
LIVE = os.environ.get("KITTYMUX_USAGE_LIVE", os.environ.get("KITTY_USAGE_LIVE", "")) \
    not in ("", "0", "no")


class LiveError(Exception):
    """Safe diagnostic: never includes credentials or curl stderr."""


def curl_json(url: str, *, headers: list[str], body: str | None = None,
              max_time: int = 4) -> dict:
    """Keep secrets off argv/disk while retaining curl's proxy/TLS defaults."""
    if any("\r" in h or "\n" in h or "\0" in h for h in headers):
        raise LiveError("invalid credential header")

    def quote(value: str) -> str:
        # curl config supports these quoted-string escapes, not JSON's \u escapes.
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace(
            "\t", "\\t").replace("\n", "\\n").replace("\r", "\\r") + '"'

    config = "".join("header = " + quote(h) + "\n" for h in headers)
    if body is not None:
        config += "data = " + quote(body) + "\n"
    args = ["curl", "-fsS", "--max-time", str(max_time), "--config", "-"]
    if body is not None:
        args += ["-X", "POST"]
    args.append(url)
    try:
        out = subprocess.run(args, input=config, capture_output=True,
                             text=True, timeout=max_time + 2)
    except subprocess.TimeoutExpired:
        raise LiveError("request timed out") from None
    except OSError:
        raise LiveError("curl unavailable") from None
    if out.returncode:
        raise LiveError(f"curl failed (exit {out.returncode})")
    try:
        data = json.loads(out.stdout)
    except (ValueError, TypeError):
        raise LiveError("invalid JSON response") from None
    if not isinstance(data, dict):
        raise LiveError("invalid response shape")
    return data


def live_fresh(cached: dict) -> bool:
    """Legacy ts is last success; attempt_ts also throttles unsuccessful fetches."""
    if not isinstance(cached, dict) or not cached:
        return False
    timestamp = cached.get("attempt_ts", cached.get("ts", 0))
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
        return False
    return 0 <= time.time() - timestamp < LIVE_TTL


def live_failure(cached: dict, error: str) -> dict:
    return dict(cached, ts=cached.get("ts", 0), rows=cached.get("rows", []),
                attempt_ts=time.time(), error=error)


def live_success(rows: list) -> dict:
    now = time.time()
    return {"ts": now, "attempt_ts": now, "rows": rows}


def local_day(now: float) -> tuple[str, float]:
    """Calendar date and local midnight, including DST's 23/25-hour days."""
    dt = datetime.fromtimestamp(now)
    return dt.strftime("%Y-%m-%d"), dt.replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()


def fmt_wait(ts: float) -> str:
    """Epoch → 'in 2d 3h' / 'in 5h 12m' / 'in 9m', or 'now' if past."""
    m = int((ts - time.time()) / 60)
    if m <= 0:
        return "now"
    d, rem = divmod(m, 24 * 60)
    h, mm = divmod(rem, 60)
    if d:
        return f"in {d}d {h}h" if h else f"in {d}d"
    if h:
        return f"in {h}h {mm}m" if mm else f"in {h}h"
    return f"in {m}m"


def fmt_ago(ts: float) -> str:
    m = int((time.time() - ts) / 60)
    if m < 60:
        return f"{max(m, 1)}m ago"
    h = m // 60
    if h < 24:
        return f"{h}h ago"
    return f"{h // 24}d ago"


def fmt_tokens(n: int | float) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}G"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(int(n))


def iso_ts(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, AttributeError):
        return 0.0


def sqlite_ro(path: Path):
    """Open a sqlite database strictly read-only."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def write_private(path: Path, payload: str) -> None:
    tmp = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(tmp, path)
    except OSError:
        pass
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass


def safe_mtime(path) -> float:
    """A disappearing transcript sorts last; collection can still use the surviving files."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
