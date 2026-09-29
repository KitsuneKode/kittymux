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
        }

    # Optional — called only when KITTYMUX_USAGE_LIVE is enabled:
    def live(cached: dict) -> dict:
        # Return {"ts": epoch, "rows": [...]}, or `cached` when the fetch
        # is unavailable. Must be cheap, cached by the caller, and opt-in.

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
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

HOME = Path.home()
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
    try:
        STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(payload)
        path.chmod(0o600)
    except OSError:
        pass
