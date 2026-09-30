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


# Shape + colour: state must be readable without colour vision, and calm — no orbs.
#   working  an animated braille spinner
#   waiting  a bold "!"   (the only one that asks for you)
#   done     a dim "✓"
#   unread   a faint "•"  (output arrived in a tab that has no agent)
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
STATE_GLYPH = {"working": SPINNER[0], "waiting": "!", "done": "✓", "unread": "•"}
SPINNER_FPS = 10.0


def state_glyph(state: str, now: float | None = None) -> str:
    """Glyph for a state; `working` animates with the clock (pass `now` in tests)."""
    if state == "working":
        import time as _t
        t = _t.monotonic() if now is None else now
        return SPINNER[int(t * SPINNER_FPS) % len(SPINNER)]
    return STATE_GLYPH.get(state, "")


_CTRL = {c: " " for c in list(range(0, 32)) + [127] + list(range(0x80, 0xA0))}


def sanitize_text(text, limit: int = 120) -> str:
    """One line, control characters replaced, bounded. Text that arrives from a terminal
    user variable is drawn straight into the tab bar — never trust it."""
    return " ".join(str(text).translate(_CTRL).split())[:limit]


def resolve_msg(entry: dict | None, status: str) -> str:
    """The one-line reason an agent is waiting/done (from hooks), else ''.
    Only meaningful while the status is waiting or done."""
    if status not in ("waiting", "done"):
        return ""
    return sanitize_text((entry or {}).get("msg") or "")


# ── quiet glyphs for non-agent tools ─────────────────────────────────────────
# Agents get their brand logo; well-known tools get their real logo rendered
# quiet (kittymux icons font, BMP mirrors U+E0E1+). Tools without a logo keep a
# small muted Nerd Font glyph; a plain shell gets nothing. Order = priority:
# an editor beats the node process it spawned.
TOOLS: dict[str, str] = {}
for _glyph, _names in (
    ("\ue0e9", ("nvim", "vim", "vi", "hx", "helix", "micro", "nano", "emacs")),
    ("\ue0e8", ("git", "lazygit", "tig", "gitui")),
    ("\ue0e2", ("docker", "podman", "lazydocker")),
    ("\ue0e3", ("kubectl", "k9s", "helm")),
    ("\uf233", ("ssh", "mosh", "mosh-client")),
    ("\ue0ea", ("psql", "pgcli")),
    ("\ue76e", ("mysql", "mycli", "sqlite3", "redis-cli")),
    ("\uf080", ("htop", "btop", "top", "glances", "nvtop")),
    ("\uf02d", ("man", "less", "bat")),
    ("\ue0e4", ("cargo", "rustc")),
    ("\ue0e5", ("go",)),
    ("\ue0e6", ("python", "python3", "ipython", "uv")),
    ("\ue0e7", ("node", "npx")),
    ("\ue0e1", ("bun",)),
    ("\ue0eb", ("deno",)),
    ("\ue0ee", ("npm",)),
    ("\ue0ec", ("pnpm",)),
    ("\ue0ed", ("yarn",)),
):
    for _n in _names:
        TOOLS[_n] = _glyph
_TOOL_RANK = {name: i for i, name in enumerate(TOOLS)}
_WRAPPERS = {"env", "sudo", "doas", "command", "exec", "nohup", "time"}


def tool_in(cmdlines: Iterable[Iterable[str]]) -> str | None:
    """Best-known tool among the foreground processes' command lines, else None.

    Only the program itself counts (argv[0], or the program after a `--` wrapper
    separator or after env/sudo-style wrappers) — never arbitrary arguments, so
    `git commit -m vim` is git, not vim."""
    best: str | None = None
    for cmdline in cmdlines:
        argv = [str(a) for a in cmdline]
        if "--" in argv:                         # `trmw --profile x -- nvim file`
            argv = argv[argv.index("--") + 1:]
        while argv and os.path.basename(argv[0]).lower() in _WRAPPERS:
            argv = argv[1:]
        if not argv:
            continue
        name = os.path.basename(argv[0]).lower().lstrip("-")
        if name in TOOLS and (best is None or _TOOL_RANK[name] < _TOOL_RANK[best]):
            best = name
    return best
