"""kittymux launcher — the rows of the "get me there instantly" picker, how an agent is spawned, and which agents run without approvals (pure: no kitty imports;
unit-tested). `kittymux pick` feeds the rows to rofi / fuzzel / fzf and runs the chosen action; `kittymux spawn` builds a `kitty @ launch` from `launch_args`.

Rows, most pressing first:  needs you (longest-waiting first) → finished-unseen → running agents → conversations that were running and are not (reopen) → new agent.
Every row carries an `action` (jump / reopen / spawn) — the picker never parses its own text back.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata

# the order agents are offered to spawn, and the names people type
SPAWN_ORDER = ["claude", "codex", "devin", "cursor-agent", "opencode", "agy", "grok", "droid", "gemini", "amp"]
ALIASES = {"cursor": "cursor-agent", "antigravity": "agy", "c": "claude", "x": "codex", "d": "devin", "u": "cursor-agent", "o": "opencode", "a": "agy", "g": "grok"}
_AGENT_NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
STATE_GLYPH = {"limited": "⊘", "waiting": "◆", "working": "◐", "done": "✓", "idle": "·", "": "·"}
STATE_RANK = {"limited": 0, "waiting": 1, "done": 2, "working": 3, "idle": 4, "": 5}


# What the bar's header shows while a keyboard mode is armed (kitty names the mode; the keys are ours).
MODE_HINTS = {"leader": ["hjkl cnp saw g ?", "hjkl cnp g ?", "? help"],
              "spawn": ["c x d u o a g  ⇧ split", "c x d u o a g ⇧", "cxduoag"]}


def mode_hint(mode: str, room: int | None = None) -> str:
    """The key reminder for an armed mode: the longest variant that fits in `room` cells ('' when none does, or the mode has none)."""
    for hint in MODE_HINTS.get((mode or "").lower(), []):
        if room is None or len(hint) <= room:
            return hint
    return ""


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
                extra: list[str] | None = None, tab_title: str | None = None) -> list[str]:
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
    if tab_title:
        args += ["--tab-title", clean_text(tab_title, 60)]
    args += [f"--cwd={cwd}" if cwd else "--cwd=current"]
    if source_window and str(source_window).isdigit():
        args += ["--source-window", f"id:{source_window}"]
    args += ["--title", agent, f"--var=kittymux_agent={agent}", "--", exe, *(extra or [])]
    return args


# ── giving an agent its first prompt (fan-out) ────────────────────────────────
PROMPT_MAX = 8000


def load_prompt_forms(builtin_path: str, user_path: str | None = None) -> dict:
    out: dict = {}
    for path in (builtin_path, user_path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(data, dict):
            out.update({k: v for k, v in data.items() if isinstance(v, dict) and not k.startswith("_") and v.get("form") in ("positional", "dashdash", "flag")})
    return out


def validate_prompt(text) -> str | None:
    """The prompt, or None when it is unusable: empty, too long, containing NUL, or starting with `-` (a positional prompt would be read as an option). It is passed as ONE argv
    element — never through a shell — so quotes and `$()` in it are just text."""
    if not isinstance(text, str):
        return None
    t = text.strip()
    if not t or len(t) > PROMPT_MAX or "\0" in t or t.startswith("-"):
        return None
    return t


def prompt_args(forms: dict, agent: str, prompt: str) -> list[str] | None:
    """The arguments that hand `prompt` to `agent` as its first message, or None if we do not know how (an agent without a verified form is never guessed at)."""
    d = forms.get(agent)
    if not d or validate_prompt(prompt) is None:
        return None
    if d["form"] == "positional":
        return [prompt]
    if d["form"] == "dashdash":
        return ["--", prompt]
    flag = d.get("flag", "")
    return [flag, prompt] if re.fullmatch(r"--[a-z][a-z-]{0,30}", flag) else None


# ── the rows ──────────────────────────────────────────────────────────────────
def clean_text(value, limit: int = 120) -> str:
    """Text from a terminal (a window title, an agent's message, a path) made safe to put in ONE line of a menu. Any program can set a window title with an escape
    sequence, so everything shown comes through here: control characters (newline, NUL, ESC), format characters (bidi overrides that reorder what you read, zero-width
    joiners), line separators, private-use and unassigned code points all become a space; whitespace is collapsed; the length is bounded."""
    out = [" " if _unsafe_char(ch) else ch for ch in str(value if value is not None else "")]
    return " ".join("".join(out).split())[:limit]


def _unsafe_char(ch: str) -> bool:
    return unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp") or (ch.isspace() and ch != " ")


def _short(path: str, home: str, width: int = 28) -> str:
    path = clean_text(path, 400)
    p = path.replace(home, "~", 1) if home and path.startswith(home) else path
    return p if len(p) <= width else "…" + p[-(width - 1):]


def _age(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s}s" if s < 90 else f"{s // 60}m" if s < 5400 else f"{s // 3600}h" if s < 172800 else f"{s // 86400}d"


def build_rows(events: list[dict], windows: list[dict], closed: list[dict], installed: list[str], now: float, home: str = "", cwd: str = "",
               risk: dict | None = None, max_closed: int = 8, include_settled: bool = False) -> list[dict]:
    """events: unread inbox events; windows: live agent windows [{pid, w, agent, state, tab, cwd, argv}]; closed: journal entries that are not running
    ([{key, agent, tab, cwd, last, turns, sid, argv, pinned, settled, lifecycle}]; lifecycle is pinned | recent | settled); installed: agent names on PATH. Pinned conversations come first
    and always show; settled ones are folded behind one "show settled" row unless `include_settled`. Returns rows [{kind, text, action, jkey, pinned, settled}]."""
    risk = risk or {}
    rows: list[dict] = []
    evented: set = set()

    def flag(agent: str, argv: list) -> str:
        return "  ⚠ no approvals" if risk_of(risk, agent, argv) else ""

    def delta(w: dict) -> str:                       # what the agent changed in its last/current run (cached by `kittymux checkpoint`; digits only, so safe to print)
        txt = clean_text(w.get("changes", ""), 40)
        return f"   Δ {txt}" if txt and txt != "no changes" else ""

    live = {(str(w.get("pid")), str(w.get("w"))): w for w in windows}
    needs = sorted((e for e in events if e.get("severity") == "needs-you"), key=lambda e: float(e.get("t", now)))        # longest-waiting first
    rest = sorted((e for e in events if e.get("severity") != "needs-you"), key=lambda e: -float(e.get("t", 0)))
    for e in needs + rest:
        key = (str(e.get("pid")), str(e.get("w")))
        w = live.get(key, {})
        evented.add(key)
        glyph = "◆" if e.get("severity") == "needs-you" else "✓"
        body = clean_text(e.get("body") or e.get("title") or "", 70)
        rows.append({"kind": "event", "agent": e.get("agent", ""), "tone": "urgent" if e.get("severity") == "needs-you" else "",
                     "event": e.get("id"), "action": {"op": "jump", "pid": e.get("pid"), "w": e.get("w"), "ack": e.get("id")},
                     "text": f"{glyph}  {clean_text(e.get('agent', 'agent'), 24)}  {clean_text(w.get('tab') or e.get('tab') or '', 60)} — {body}   {_age(now - float(e.get('t', now)))}"
                             + delta(w) + flag(e.get("agent", ""), w.get("argv", []))})
    for w in sorted(windows, key=lambda w: (not w.get("pinned"), STATE_RANK.get(w.get("state", ""), 9), w.get("tab", ""))):
        key = (str(w.get("pid")), str(w.get("w")))
        if key in evented:
            continue
        st = w.get("state", "")
        rows.append({"kind": "running", "agent": w.get("agent", ""), "tone": "active" if st == "working" else "urgent" if st in ("waiting", "limited") else "",
                     "jkey": w.get("jkey"), "pinned": bool(w.get("pinned")), "settled": False,
                     "action": {"op": "jump", "pid": w.get("pid"), "w": w.get("w")},
                     "text": f"{'★' if w.get('pinned') else STATE_GLYPH.get(st, '·')}  {clean_text(w.get('agent', 'agent'), 24)}  {clean_text(w.get('tab', ''), 60)}   {_short(w.get('cwd', ''), home)}"
                             + (f"   {clean_text(st, 12)}" if st and st != "idle" else "") + delta(w) + flag(w.get("agent", ""), w.get("argv", []))})
    seen_closed: set = set()
    shown_closed, hidden_settled = 0, 0
    for c in sorted(closed, key=lambda c: (c.get("lifecycle") != "pinned", -float(c.get("last", 0)))):          # pinned first, then newest
        ident = (c.get("agent"), c.get("cwd"), c.get("tab"))
        if ident in seen_closed:
            continue
        seen_closed.add(ident)
        life = c.get("lifecycle") or ("pinned" if c.get("pinned") else "settled" if c.get("settled") else "recent")
        if life == "settled" and not include_settled:
            hidden_settled += 1
            continue
        if life != "pinned":
            shown_closed += 1                                   # the cap counts recent ones only: a pin never takes a slot from them
            if shown_closed > max_closed:
                continue
        bits = [f"closed {_age(now - float(c.get('last', now)))} ago"]
        if c.get("turns"):
            bits.append(f"{c['turns']} runs")
        rows.append({"kind": "closed", "agent": c.get("agent", ""), "tone": "", "jkey": c.get("key"), "pinned": life == "pinned", "settled": life == "settled",
                     "action": {"op": "reopen", "key": c.get("key")},
                     "text": f"{'★' if life == 'pinned' else '↺'}  {clean_text(c.get('agent', 'agent'), 24)}  {clean_text(c.get('tab') or '', 60)}   {_short(c.get('cwd', ''), home)}   {' · '.join(bits)}"
                             + flag(c.get("agent", ""), c.get("argv", []))})
    if hidden_settled:
        rows.append({"kind": "more", "agent": "", "tone": "", "jkey": None, "pinned": False, "settled": False, "action": {"op": "all"},
                     "text": f"⋯  {hidden_settled} settled conversation{'s' if hidden_settled != 1 else ''} (older than a few days, or settled by you) — show"})
    here = _short(cwd, home) if cwd else "here"          # (clean_text'd inside _short)
    for name in [a for a in SPAWN_ORDER if a in installed]:
        rows.append({"kind": "new", "agent": name, "tone": "", "action": {"op": "spawn", "agent": name, "where": "tab"}, "text": f"+  new {name}   tab · {here}"})
        rows.append({"kind": "new", "agent": name, "tone": "", "action": {"op": "spawn", "agent": name, "where": "vsplit"}, "text": f"+  new {name}   split right · {here}"})
    seen: dict = {}
    for r in rows:                                               # menus that return the text (fuzzel) need it unique
        n = seen.get(r["text"], 0)
        seen[r["text"]] = n + 1
        if n:
            r["text"] += f"  ({n + 1})"
    return rows


# ── look: icons and a rofi theme derived from the live kitty theme ────────────
def needs_you_target(rows: list[dict], pid) -> str | None:
    """The window of kitty `pid` that needs you most, from `build_rows` output (event rows first, longest-waiting first, then agents that are waiting or limited), as a
    window-id string; None when nothing in that kitty does. The peek card can only show windows of the kitty it runs in, hence the pid."""
    for r in rows:
        if r.get("tone") != "urgent":
            continue
        a = r.get("action") or {}
        w = str(a.get("w", ""))
        if a.get("op") == "jump" and str(a.get("pid")) == str(pid) and w.isdigit():
            return w
    return None


def icon_for(agent: str, notify_dir: str, fallback: str) -> str:
    """Path of the agent's mark (assets/notify/<agent>.png, which carries the mascot badge) — chosen from OUR directory by a validated name, never from output — else `fallback`."""
    name = ALIASES.get((agent or "").lower(), (agent or "").lower())
    if _AGENT_NAME.match(name):
        path = os.path.join(notify_dir, name + ".png")
        if os.path.isfile(path):
            return path
    return fallback


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def rofi_theme(colors: dict, mascot: str, title: str = "kittymux", subtitle: str = "agents · needs you first") -> str:
    """A rofi theme in kittymux's look: the mascot and name in a header, a search bar, rows with their agent's icon and an accent rail on the selected one (the same `▎` the tab bar
    uses), needs-you rows in the waiting colour, working rows in the working colour. Every colour comes from `colors` ({name: "#rrggbb"}, derived from the LIVE kitty theme by the
    caller — nothing here is a palette of ours). Returns "" when a colour is missing or malformed: the caller then leaves the user's own rofi theme alone."""
    need = ("bg", "bar", "surface", "surface_hi", "text", "muted", "faint", "accent", "waiting", "working", "alert")
    if any(not _HEX.match(str(colors.get(k, ""))) for k in need) or not mascot or any(c in mascot for c in '"\\\n'):
        return ""
    c = {k: colors[k] for k in need}
    return f"""* {{
    bg: {c['bg']}f4; bar: {c['bar']}; surface: {c['surface']}; surface-hi: {c['surface_hi']};
    fg: {c['text']}; muted: {c['muted']}; faint: {c['faint']}; accent: {c['accent']};
    waiting: {c['waiting']}; working: {c['working']}; alert: {c['alert']};
    background-color: transparent; text-color: @fg;
}}
window {{ transparency: "real"; location: center; anchor: center; width: 720px; padding: 0; border: 2px; border-color: @accent; border-radius: 14px; background-color: @bg; }}
mainbox {{ children: [ header, inputbar, message, listview ]; spacing: 0; padding: 0; background-color: transparent; }}
header, inputbar, message {{ expand: false; }}
header {{ orientation: horizontal; children: [ icon-mascot, titles ]; spacing: 16px; padding: 14px 20px; background-color: @bar; border-radius: 12px 12px 0 0; }}
icon-mascot {{ expand: false; filename: "{mascot}"; size: 56px; vertical-align: 0.5; }}
titles {{ orientation: vertical; children: [ textbox-title, textbox-subtitle ]; spacing: 2px; vertical-align: 0.5; expand: true; background-color: transparent; }}
textbox-title, textbox-subtitle {{ expand: false; }}
textbox-title {{ content: "{title}"; text-color: @accent; }}
textbox-subtitle {{ content: "{subtitle}"; text-color: @faint; }}
inputbar {{ children: [ prompt, entry ]; spacing: 10px; padding: 12px 20px; background-color: @surface; }}
prompt {{ text-color: @accent; }}
entry {{ placeholder: "type to find an agent, a conversation or a new one…"; placeholder-color: @faint; text-color: @fg; }}
message {{ padding: 8px 20px 0 20px; background-color: transparent; }}
textbox {{ text-color: @muted; background-color: transparent; }}
listview {{ lines: 10; columns: 1; scrollbar: false; spacing: 3px; padding: 10px 12px 12px 12px; fixed-height: false; expand: true; background-color: transparent; }}
element {{ padding: 9px 12px; spacing: 14px; border-radius: 8px; border: 0 0 0 3px; border-color: transparent; background-color: transparent; text-color: @fg; }}
element-icon {{ size: 28px; background-color: transparent; }}
element-text {{ vertical-align: 0.5; background-color: transparent; text-color: inherit; }}
element normal.urgent, element alternate.urgent {{ text-color: @waiting; }}
element normal.active, element alternate.active {{ text-color: @working; }}
element selected.normal, element selected.active {{ background-color: @surface-hi; border-color: @accent; text-color: @fg; }}
element selected.urgent {{ background-color: @surface-hi; border-color: @waiting; text-color: @waiting; }}
"""


# ── a status-bar module (waybar custom module: {"text", "tooltip", "class"}) ─────────────
def waybar_status(events: list[dict], now: float) -> dict:
    """What a waybar `custom` module shows: `◆ 2` when agents need you (class `needs-you`), `✓ 1` for finished-unseen (class `unread`), hidden when there is nothing. The tooltip lists
    the most pressing few (longest-waiting first). All text goes through clean_text: it comes from terminals."""
    unread = [e for e in events if e.get("status", "unread") == "unread"]
    needs = sorted((e for e in unread if e.get("severity") == "needs-you"), key=lambda e: float(e.get("t", now)))
    rest = [e for e in unread if e.get("severity") != "needs-you"]
    if not unread:
        return {"text": "", "tooltip": "", "class": "idle"}
    lines = [f"{'◆' if e.get('severity') == 'needs-you' else '✓'} {clean_text(e.get('agent', 'agent'), 20)} {clean_text(e.get('tab') or '', 30)} — "
             f"{clean_text(e.get('body') or e.get('title') or '', 50)} ({_age(now - float(e.get('t', now)))})" for e in (needs + rest)[:8]]
    text = f"◆ {len(needs)}" if needs else f"✓ {len(rest)}"
    return {"text": text, "tooltip": "\n".join(lines), "class": "needs-you" if needs else "unread"}


# ── menus ─────────────────────────────────────────────────────────────────────
def menu_command(menu: str, rows: list[dict], message: str = "", theme_path: str | None = None, notify_dir: str | None = None,
                 mascot: str | None = None) -> tuple[list[str], str]:
    """(argv, stdin text) for a dmenu-style picker. rofi and fzf answer with an index; fuzzel answers with the text (rows are unique). For rofi, `theme_path` applies our theme and
    `notify_dir` + `mascot` give each row its agent's icon (and mark needs-you / working rows) through rofi's row options — appended AFTER the text was checked, from our own table."""
    texts = [r["text"] for r in rows]
    if any(_unsafe_char(ch) for t in texts for ch in t):          # defence in depth: one row = one clean line, or the indexes the menu answers with no longer match the rows
        raise ValueError("a menu row contains control characters")
    if menu == "rofi":
        argv = ["rofi", "-dmenu", "-i", "-no-custom", "-format", "i", "-p", "kittymux ›", "-kb-custom-1", "alt+a", "-kb-custom-2", "alt+p", "-kb-custom-3", "alt+s"]
        if theme_path:
            argv += ["-theme", theme_path]
        if message:
            argv += ["-mesg", clean_text(message, 120)]
        if notify_dir and mascot:
            argv += ["-show-icons"]
            lines = []
            for r in rows:
                opts = ["icon", icon_for(r.get("agent", ""), notify_dir, mascot)]
                if r.get("tone") in ("urgent", "active"):
                    opts += [r["tone"], "true"]
                lines.append(r["text"] + "\0" + "\x1f".join(opts))
            return argv, "\n".join(lines) + "\n"
        return argv, "\n".join(texts) + "\n"
    if menu == "fuzzel":
        return ["fuzzel", "--dmenu", "--prompt", "kittymux  "], "\n".join(texts) + "\n"
    if menu == "fzf":
        return (["fzf", "--delimiter", "\t", "--with-nth", "2..", "--prompt", "kittymux> ", "--no-sort", "--layout=reverse", "--expect", "alt-a,alt-p,alt-s"],
                "\n".join(f"{i}\t{t}" for i, t in enumerate(texts)) + "\n")
    raise ValueError(menu)


def parse_choice(menu: str, rows: list[dict], returncode: int, stdout: str) -> tuple[dict, str] | None:
    """(row, "open" | "ack" | "pin" | "settle") the picker chose, or None (cancelled, empty, out of range). Never raises on odd output."""
    out = (stdout or "").rstrip("\n")
    try:
        if menu == "rofi":
            how = {0: "open", 10: "ack", 11: "pin", 12: "settle"}.get(returncode)
            if how is None or not out.strip().isdigit():
                return None
            i = int(out.strip())
            return (rows[i], how) if 0 <= i < len(rows) else None
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
            if lines and lines[0] in ("alt-a", "alt-p", "alt-s", ""):
                key = {"alt-a": "ack", "alt-p": "pin", "alt-s": "settle"}.get(lines[0], "open")
                lines = lines[1:]
            if not lines or not lines[0]:
                return None
            i = int(lines[0].split("\t", 1)[0])
            return (rows[i], key) if 0 <= i < len(rows) else None
    except (ValueError, IndexError):
        return None
    return None
