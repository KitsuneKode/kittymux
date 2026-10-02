"""kittymux launcher — the rows of the "get me there instantly" picker, how an agent is spawned, and which agents run without approvals (pure: no kitty imports;
unit-tested). `kittymux pick` feeds the rows to rofi / fuzzel / fzf and runs the chosen action; `kittymux spawn` builds a `kitty @ launch` from `launch_args`.

Rows, most pressing first:  needs you (longest-waiting first) → finished-unseen → running agents → conversations that were running and are not (reopen) → new agent.
Every row carries an `action` (jump / reopen / spawn) — the picker never parses its own text back.
"""

from __future__ import annotations

import json
import os
import re

# the order agents are offered to spawn, and the names people type
SPAWN_ORDER = ["claude", "codex", "devin", "cursor-agent", "opencode", "agy", "grok", "droid", "gemini", "amp"]
ALIASES = {"cursor": "cursor-agent", "antigravity": "agy", "c": "claude", "x": "codex", "d": "devin", "u": "cursor-agent", "o": "opencode", "a": "agy", "g": "grok"}
_AGENT_NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
STATE_GLYPH = {"limited": "⊘", "waiting": "◆", "working": "◐", "done": "✓", "idle": "·", "": "·"}
STATE_RANK = {"limited": 0, "waiting": 1, "done": 2, "working": 3, "idle": 4, "": 5}


# ── risk: agents running with their approvals off ─────────────────────────────
def load_risk(builtin_path: str, user_path: str | None = None) -> dict:
    out: dict = {}
    for path in (builtin_path, user_path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(data, dict):
            out.update({k: v for k, v in data.items() if isinstance(v, dict) and not k.startswith("_")})
    return out


def risk_of(table: dict, agent: str, argv: list) -> str:
    """"no-approvals" when the command line carries one of the agent's documented approval-bypass flags (`--flag`, `--flag=value` or `--flag value`), else ""."""
    d = table.get(agent) or {}
    toks = [str(t) for t in (argv or [])]
    flags = set(d.get("flags", []))
    if any(t.split("=", 1)[0] in flags for t in toks):
        return "no-approvals"
    for flag, value in d.get("pairs", []):
        for i, t in enumerate(toks):
            if t == f"{flag}={value}" or (t == flag and i + 1 < len(toks) and toks[i + 1] == value):
                return "no-approvals"
    return ""


# ── spawning ──────────────────────────────────────────────────────────────────
def resolve_agent(name: str) -> str | None:
    """A typed name or one-letter alias → a known agent, else None. Only names that look like a command name are ever accepted (never a path or an option)."""
    name = ALIASES.get((name or "").strip().lower(), (name or "").strip().lower())
    return name if _AGENT_NAME.match(name) and name in SPAWN_ORDER else None


def launch_args(agent: str, exe: str, where: str, cwd: str | None = None, source_window: str | None = None, before_scratch: bool = False,
                extra: list[str] | None = None) -> list[str]:
    """The arguments after `kitty @ --to SOCK launch` that start `exe` as a tab (`tab`), or as a split (`hsplit`/`vsplit`). The working directory is the source window's
    (`--cwd=current`) unless `cwd` is given. `before_scratch` puts a new tab before the `!scratch` tab so the scratch tab stays last (same rule as mux-newtab)."""
    if where not in ("tab", "hsplit", "vsplit"):
        raise ValueError(where)
    args: list[str] = []
    if where == "tab":
        args += ["--type=tab"]
        if before_scratch:
            args += ["--match", "title:^!scratch and state:focused_os_window", "--location=before"]
    else:
        args += ["--type=window", f"--location={where}"]
    args += [f"--cwd={cwd}" if cwd else "--cwd=current"]
    if source_window and str(source_window).isdigit():
        args += ["--source-window", f"id:{source_window}"]
    args += ["--title", agent, f"--var=kittymux_agent={agent}", "--", exe, *(extra or [])]
    return args


# ── the rows ──────────────────────────────────────────────────────────────────
def _short(path: str, home: str, width: int = 28) -> str:
    p = (path or "").replace(home, "~", 1) if home and (path or "").startswith(home) else (path or "")
    return p if len(p) <= width else "…" + p[-(width - 1):]


def _age(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s}s" if s < 90 else f"{s // 60}m" if s < 5400 else f"{s // 3600}h" if s < 172800 else f"{s // 86400}d"


def build_rows(events: list[dict], windows: list[dict], closed: list[dict], installed: list[str], now: float, home: str = "", cwd: str = "",
               risk: dict | None = None, max_closed: int = 8) -> list[dict]:
    """events: unread inbox events; windows: live agent windows [{pid, w, agent, state, tab, cwd, argv}]; closed: journal entries that are not running
    ([{key, agent, tab, cwd, last, turns, sid, argv}]); installed: agent names on PATH. Returns rows [{kind, text, action}]."""
    risk = risk or {}
    rows: list[dict] = []
    evented: set = set()

    def flag(agent: str, argv: list) -> str:
        return "  ⚠ no approvals" if risk_of(risk, agent, argv) else ""

    live = {(str(w.get("pid")), str(w.get("w"))): w for w in windows}
    needs = sorted((e for e in events if e.get("severity") == "needs-you"), key=lambda e: float(e.get("t", now)))        # longest-waiting first
    rest = sorted((e for e in events if e.get("severity") != "needs-you"), key=lambda e: -float(e.get("t", 0)))
    for e in needs + rest:
        key = (str(e.get("pid")), str(e.get("w")))
        w = live.get(key, {})
        evented.add(key)
        glyph = "◆" if e.get("severity") == "needs-you" else "✓"
        body = (e.get("body") or e.get("title") or "").replace("\n", " ")[:70]
        rows.append({"kind": "event", "event": e.get("id"), "action": {"op": "jump", "pid": e.get("pid"), "w": e.get("w"), "ack": e.get("id")},
                     "text": f"{glyph}  {e.get('agent', 'agent')}  {w.get('tab') or e.get('tab') or ''} — {body}   {_age(now - float(e.get('t', now)))}" + flag(e.get("agent", ""), w.get("argv", []))})
    for w in sorted(windows, key=lambda w: (STATE_RANK.get(w.get("state", ""), 9), w.get("tab", ""))):
        key = (str(w.get("pid")), str(w.get("w")))
        if key in evented:
            continue
        st = w.get("state", "")
        rows.append({"kind": "running", "action": {"op": "jump", "pid": w.get("pid"), "w": w.get("w")},
                     "text": f"{STATE_GLYPH.get(st, '·')}  {w.get('agent', 'agent')}  {w.get('tab', '')}   {_short(w.get('cwd', ''), home)}" + (f"   {st}" if st and st != "idle" else "")
                             + flag(w.get("agent", ""), w.get("argv", []))})
    for c in closed[:max_closed]:
        bits = [f"closed {_age(now - float(c.get('last', now)))} ago"]
        if c.get("turns"):
            bits.append(f"{c['turns']} runs")
        rows.append({"kind": "closed", "action": {"op": "reopen", "key": c.get("key")},
                     "text": f"↺  {c.get('agent', 'agent')}  {c.get('tab') or ''}   {_short(c.get('cwd', ''), home)}   {' · '.join(bits)}" + flag(c.get("agent", ""), c.get("argv", []))})
    here = _short(cwd, home) if cwd else "here"
    for name in [a for a in SPAWN_ORDER if a in installed]:
        rows.append({"kind": "new", "action": {"op": "spawn", "agent": name, "where": "tab"}, "text": f"+  new {name}   tab · {here}"})
        rows.append({"kind": "new", "action": {"op": "spawn", "agent": name, "where": "vsplit"}, "text": f"+  new {name}   split right · {here}"})
    seen: dict = {}
    for r in rows:                                               # menus that return the text (fuzzel) need it unique
        n = seen.get(r["text"], 0)
        seen[r["text"]] = n + 1
        if n:
            r["text"] += f"  ({n + 1})"
    return rows


# ── menus ─────────────────────────────────────────────────────────────────────
def menu_command(menu: str, rows: list[dict], message: str = "") -> tuple[list[str], str]:
    """(argv, stdin text) for a dmenu-style picker. rofi and fzf answer with an index; fuzzel answers with the text (rows are unique)."""
    texts = [r["text"] for r in rows]
    if menu == "rofi":
        argv = ["rofi", "-dmenu", "-i", "-no-custom", "-format", "i", "-p", "kittymux", "-kb-custom-1", "alt+a"]
        if message:
            argv += ["-mesg", message]
        return argv, "\n".join(texts) + "\n"
    if menu == "fuzzel":
        return ["fuzzel", "--dmenu", "--prompt", "kittymux  "], "\n".join(texts) + "\n"
    if menu == "fzf":
        return (["fzf", "--delimiter", "\t", "--with-nth", "2..", "--prompt", "kittymux> ", "--no-sort", "--layout=reverse", "--expect", "alt-a"],
                "\n".join(f"{i}\t{t}" for i, t in enumerate(texts)) + "\n")
    raise ValueError(menu)


def parse_choice(menu: str, rows: list[dict], returncode: int, stdout: str) -> tuple[dict, str] | None:
    """(row, "open" | "ack") the picker chose, or None (cancelled, empty, out of range). Never raises on odd output."""
    out = (stdout or "").rstrip("\n")
    try:
        if menu == "rofi":
            if returncode not in (0, 10) or not out.strip().isdigit():
                return None
            i = int(out.strip())
            return (rows[i], "ack" if returncode == 10 else "open") if 0 <= i < len(rows) else None
        if menu == "fuzzel":
            if returncode != 0 or not out:
                return None
            for r in rows:
                if r["text"] == out:
                    return r, "open"
            return None
        if menu == "fzf":
            lines = out.split("\n")
            key = "open"
            if lines and lines[0] in ("alt-a", ""):
                key = "ack" if lines[0] == "alt-a" else "open"
                lines = lines[1:]
            if not lines or not lines[0]:
                return None
            i = int(lines[0].split("\t", 1)[0])
            return (rows[i], key) if 0 <= i < len(rows) else None
    except (ValueError, IndexError):
        return None
    return None
