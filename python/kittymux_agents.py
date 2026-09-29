# kittymux agent table — the one place that knows agent CLIs.
# Pure Python (no kitty imports). Glyphs live in the PUA icon font built by
# tools/build-icons.py (aider/crush/grok fall back to plain symbols).

import os
from typing import Iterable, NamedTuple


class Agent(NamedTuple):
    glyph: str
    brand: int  # plain 0xRRGGBB


AGENTS: dict[str, Agent] = {
    "claude":       Agent("", 0xd97757),
    "codex":        Agent("", 0x10a37f),
    "cursor-agent": Agent("", 0x5b8ef4),
    "cursor":       Agent("", 0x5b8ef4),
    "gemini":       Agent("", 0x4e8cff),
    "opencode":     Agent("", 0xfab283),
    "amp":          Agent("", 0xf5c2e7),
    "devin":        Agent("", 0x8b5cf6),
    "aider":        Agent("✎", 0xa6e3a1),
    "crush":        Agent("♥", 0xf38ba8),
    "grok":         Agent("✗", 0xf9e2af),
}
FALLBACK = Agent("⚡", 0x94e2d5)


def agent_in(cmdline_args: Iterable[str]) -> str | None:
    """First arg whose basename (lowercased) names a known agent CLI."""
    for arg in cmdline_args:
        name = os.path.basename(str(arg)).lower()
        if name in AGENTS:
            return name
    return None


STATES = ("working", "waiting", "done", "idle")


def resolve_status(entry: dict | None, has_agent: bool, now: float,
                   stale_after: float = 15.0) -> str:
    """Status of a pane's agent: working | waiting | done | idle | "" (no agent).

    An explicit status (set by `bin/mux-status` from agent hooks and recorded by
    pane-state.py) wins. Without one, fall back to the heuristic: an agent whose
    title has been quiet for `stale_after` seconds is probably waiting on you.
    Explicit status is ignored once no agent process is in the pane, so a crash
    can never leave a ghost "working" marker."""
    if not has_agent:
        return ""
    entry = entry or {}
    explicit = entry.get("status")
    if explicit in STATES:
        return explicit
    ts = float(entry.get("ts_title") or 0)
    return "waiting" if ts and (now - ts) > stale_after else "working"


# Shape + colour: state must be readable without colour vision.
STATE_GLYPH = {"working": "◐", "waiting": "◆", "done": "✓"}


def resolve_msg(entry: dict | None, status: str) -> str:
    """The one-line reason an agent is waiting/done (from hooks), else ''.
    Only meaningful while the status is waiting or done."""
    if status not in ("waiting", "done"):
        return ""
    return str((entry or {}).get("msg") or "")
