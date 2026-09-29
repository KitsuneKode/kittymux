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
