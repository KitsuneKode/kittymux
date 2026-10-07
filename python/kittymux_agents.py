# kittymux agent table — the one place that knows agent CLIs.
# Pure Python (no kitty imports). Glyphs live in the PUA icon font built by
# tools/build-icons.py (aider/crush/grok fall back to plain symbols).

import os
import re
from typing import Iterable, NamedTuple

import kittymux_state


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
    "agy":          Agent("\ue0ef", 0x3186ff),
    "antigravity":  Agent("\ue0ef", 0x3186ff),
    "aider":        Agent("✎", 0xa6e3a1),
    "crush":        Agent("♥", 0xf38ba8),
    "grok":         Agent("\ue0f1", 0xd0d0d0),
    "droid":        Agent("\ue0f0", 0xee6018),     # Factory
    "qwen":         Agent("\ue0f2", 0x615ced),
    "kimi":         Agent("\ue0f3", 0x1783ff),
    "goose":        Agent("\ue0f4", 0xe0a458),
    "kilo":         Agent("\ue0f5", 0xf0e442),
    "vibe":         Agent("\ue0f6", 0xfa520f),     # Mistral Vibe
    "junie":        Agent("\ue0f7", 0xfe315d),
    "auggie":       Agent("\ue0f8", 0x4fd1c5),
}
FALLBACK = Agent("⚡", 0x94e2d5)
MASCOT_GLYPH = "\ue0f9"      # the kittymux mascot (assets/icons/kittymux.svg → the icon font)


def compact_age(seconds) -> str:
    """"" under a minute, then 5m, 59m, 2h, 47h, 3d — short enough to sit beside a state glyph in a narrow bar."""
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return ""
    if s < 60:
        return ""
    return f"{int(s // 60)}m" if s < 3600 else f"{int(s // 3600)}h" if s < 172800 else f"{int(s // 86400)}d"


_AGED_STATES = ("waiting", "limited", "done", "working")


def state_age(state: str, ts_state, now: float, minimum: float = 60.0) -> str:
    """How long the tab has been in its current state, as compact text — only for states where it matters (waiting / limited / done / working) and from `minimum` seconds on (a
    reply that took 8 s is not news). `ts_state` and `now` are the same monotonic clock (the scanner runs inside the kitty that draws the bar)."""
    if state not in _AGED_STATES:
        return ""
    try:
        age = float(now) - float(ts_state)
    except (TypeError, ValueError):
        return ""
    return compact_age(age) if age >= minimum else ""


def font_fingerprint(font_path: str) -> str | None:
    """size + content hash of the icon font: what a kitty loaded is identified by WHAT the file holds, not by when it was last written."""
    import hashlib
    try:
        with open(font_path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    return f"{len(data)}:{hashlib.sha256(data).hexdigest()[:20]}"


def glyph_font_loaded(font_path: str, process_start: float, remembered: dict | None = None) -> bool:
    """Has THIS kitty loaded the current icon font? kitty reads fonts once, at start, so a glyph added by a later install draws as a box until that kitty restarts.

    Judged by content. `remembered` is a dict that lives as long as the kitty process: the first time it is asked, the file's fingerprint is stored — but only if the file is
    not newer than the process (then it IS what kitty loaded; a newer file may hold glyphs kitty never saw, so nothing is remembered and the glyph stays hidden). Later calls
    compare the file now with that fingerprint: a re-install of the SAME font (every `kittymux upgrade` used to rewrite the file and bump its timestamp, hiding the mascot in
    every running kitty) changes nothing; a font with new glyphs differs, so the new glyph is held back until a restart. Without `remembered`, the timestamp rule alone applies."""
    try:
        newer_than_process = os.stat(font_path).st_mtime > process_start + 3.0       # /proc start time is only 1 s accurate
    except OSError:
        return False
    if remembered is None:
        return not newer_than_process
    now = font_fingerprint(font_path)
    if "fp" not in remembered:
        remembered["fp"] = "" if newer_than_process else (now or "")
    return bool(now) and now == remembered["fp"]


# Short, common words: matched only as the command itself (`kilo`) or as the script a runtime/shell
# runs (`node /…/bin/kilo`), never as just any argument (`nvim vibe`, `cat goose`).
_STRICT = frozenset({"droid", "qwen", "kimi", "goose", "kilo", "vibe", "junie", "auggie"})
_RUNTIMES = frozenset({"node", "nodejs", "bun", "deno", "python", "python3", "uv", "uvx", "npx", "bunx", "sh", "bash", "zsh"})


def agent_in(cmdline_args: Iterable[str]) -> str | None:
    """The known agent CLI this command line runs, else None. Ordinary agent names match any
    argument's basename (lowercased); the short common ones in _STRICT only where a command goes."""
    args = [str(a) for a in cmdline_args]
    for i, arg in enumerate(args):
        name = os.path.basename(arg).lower()
        if name not in AGENTS:
            continue
        if name in _STRICT and not (i == 0 or (i == 1 and os.path.basename(args[0]).lower() in _RUNTIMES)):
            continue
        return name
    return None


STATES = ("working", "waiting", "limited", "done", "idle")
NEEDS_YOU = ("waiting", "limited")      # states that ask for the user (jump queue, notifications, counts)
SCAN_FRESH = 8.0                        # seconds: how old the watcher's own verdict may be and still be trusted


def resolve_status(entry: dict | None, has_agent: bool, now: float,
                   stale_after: float = 15.0) -> str:
    """Status of a pane's agent: working | waiting | limited | done | idle | "" (no agent).

    The watcher (pane-state.py + kittymux_state.py) resolves each agent pane from what is
    on its screen plus agent hooks, and stores the verdict as `state` with a `ts_scan`
    heartbeat. While that heartbeat is fresh the verdict is the answer — one source of truth
    for the tab bar, the deck, the panel and the jump queue. If the watcher is not scanning
    (older install, timer lost) we degrade gracefully: an explicit hook status, else recent
    title activity. A quiet title is NEVER read as "waiting" — silence is not evidence.
    Everything is ignored once no agent process is in the pane, so a crash can never leave
    a ghost "working" marker."""
    if not has_agent:
        return ""
    entry = entry or {}
    state = entry.get("state")
    if state in STATES and 0 <= now - float(entry.get("ts_scan") or 0) < SCAN_FRESH:
        return state
    explicit = entry.get("status")
    if explicit in STATES:
        return explicit
    ts = float(entry.get("ts_title") or 0)
    return "working" if ts and (now - ts) < 6.0 else "idle"


def fresh_verdict(entry: dict | None, now: float) -> str:
    """The scanner's verdict for a pane, or "" when it is absent, stale, or the pane has no agent."""
    entry = entry or {}
    state = entry.get("state")
    if state in STATES and 0 <= now - float(entry.get("ts_scan") or 0) < SCAN_FRESH:
        return state
    return ""


def identify(window: dict) -> tuple[str | None, str | None]:
    """(agent name, tool name) for a `kitty @ ls` window, from its foreground processes. A tool is
    only reported when no agent runs there."""
    procs = window.get("foreground_processes") or []
    for proc in procs:
        name = agent_in(proc.get("cmdline") or [])
        if name:
            return name, None
    return None, tool_in(p.get("cmdline") or [] for p in procs)


def pane_chips(panes: dict, window_ids: Iterable, now: float, limit: int = 4) -> list[tuple[str, str]]:
    """[(agent name, state)] for the agent panes of one tab, in window order — what the bar shows
    for a split tab instead of "N panes". Panes without a fresh scanner verdict (plain shells,
    unscanned) are left out."""
    out = []
    for wid in window_ids:
        entry = panes.get(str(wid)) or {}
        state = fresh_verdict(entry, now)
        if state and entry.get("agent") in AGENTS:
            out.append((entry["agent"], state))
    return out[:limit]


def tab_verdict(panes: dict, window_ids: Iterable, active_id, active_has_agent: bool, now: float,
                stale_after: float = 15.0) -> tuple[str, str]:
    """(state, window id) for a whole tab: its panes rolled up, most important state first
    (limited > waiting > working > done > idle). A split asking a question must light the tab
    even when another pane has focus. The active pane keeps its full fallback chain
    (hooks, title); the others count only on a fresh scanner verdict. Ties go to the active pane."""
    active_id = str(active_id)
    best_state, best_wid = "", ""
    for wid in [active_id] + [str(w) for w in window_ids if str(w) != active_id]:
        entry = panes.get(wid)
        if wid == active_id:
            state = resolve_status(entry, active_has_agent, now, stale_after)
        else:
            state = fresh_verdict(entry, now)
        if kittymux_state.PRIORITY.get(state, 0) > kittymux_state.PRIORITY.get(best_state, 0):
            best_state, best_wid = state, wid
    return best_state, best_wid


def merge_scan(panes: dict | None, scan: dict | None) -> dict:
    """panes-<pid>.json (hook status, title activity) + scan-<pid>.json (the scanner's verdicts)
    → one entry per window, ready for resolve_status/resolve_msg. Inputs are not modified."""
    out = {k: dict(v) for k, v in (panes or {}).items() if isinstance(v, dict)}
    for wid, v in (scan or {}).items():
        if not isinstance(v, dict):
            continue
        e = out.setdefault(str(wid), {})
        e["wid"] = str(wid)                                  # consumers that only hold the entry (the bar) can look the window up elsewhere
        for k in ("state", "reason", "agent", "ts_scan", "ts_state"):
            if k in v:
                e[k] = v[k]
    return out


def load_panes(panes_path: str) -> dict:
    """Read panes-<pid>.json and its sibling scan-<pid>.json (same directory) and merge them.
    Missing or unreadable files just contribute nothing."""
    import json

    def _read(path: str) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    head, tail = os.path.split(panes_path)
    scan_path = os.path.join(head, tail.replace("panes-", "scan-", 1)) if tail.startswith("panes-") else ""
    return merge_scan(_read(panes_path), _read(scan_path) if scan_path else {})


# Shape + colour: state must be readable without colour vision, and calm — no orbs.
#   working  an animated braille spinner
#   waiting  a bold "!"   (the only one that asks for you)
#   limited  a bold "⊘"   (usage limit / quota exhausted — nothing will happen until you act)
#   done     a dim "✓"    (finished while you were away; clears when you look)
#   unread   a faint "•"  (output arrived in a tab that has no agent)
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
# status icons agents put in front of their window title (spinners, bullets, Droid's ⛬) — most fonts
# have no glyph for them (a box in the bar), and the bar draws its own state mark and agent logo
_TITLE_PREFIX = re.compile(r"^[\s⠁-⣿✳✻✽✦•●◐◓◑◒∙·⛬.-]+")


def strip_title_prefix(title: str) -> str:
    return _TITLE_PREFIX.sub("", title or "").strip()


_NAMES = {"claude": ("claude code", "claude"), "agy": ("antigravity", "agy"), "cursor-agent": ("cursor agent", "cursor-agent", "cursor"),
          "droid": ("factory droid", "droid"), "vibe": ("mistral vibe", "vibe")}


def strip_agent_prefix(title: str, agent: str | None) -> str:
    """Drop a leading "<agent>: " from a title — the agent's logo already says it ("devin: Review PRs" →
    "Review PRs"). Left alone when nothing but the name would remain."""
    if not agent or not title:
        return title
    names = sorted(_NAMES.get(agent, (agent,)), key=len, reverse=True)
    m = re.match(r"^\s*(?:%s)\s*[:\-–—]\s*(.+)$" % "|".join(re.escape(n) for n in names), title, re.I)
    return m.group(1).strip() if m and m.group(1).strip() else title

def is_default_title(title: str, agent: str | None) -> bool:
    """True when a window title is only the agent's own product name ("Claude Code", "Codex CLI") — what a freshly resumed agent, or one that never
    names its conversation, sets. It says nothing about THIS conversation, so the bar shows the project instead."""
    if not agent or not title:
        return False
    t = re.sub(r"\s+", " ", title).strip().lower()
    for name in _NAMES.get(agent, (agent,)):
        n = name.lower()
        if t in (n, n + " code", n + " cli", n + " agent"):
            return True
    return False


STATE_GLYPH = {"working": SPINNER[0], "waiting": "!", "limited": "⊘", "done": "✓", "unread": "•"}
SPINNER_FPS = 10.0


def state_glyph(state: str, now: float | None = None, animate: bool = True) -> str:
    """Glyph for a state; `working` animates with the clock (pass `now` in tests). `animate=False` (the `motion` switch off) is one still frame."""
    if state == "working" and animate:
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
    """The one-line reason an agent needs you / finished: the hook's message, else the line the
    watcher spotted on screen (the prompt's question, the limit notice). '' otherwise."""
    if status not in ("waiting", "done", "limited"):
        return ""
    entry = entry or {}
    return sanitize_text(entry.get("msg") or (entry.get("reason") if status != "done" else "") or "")


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
