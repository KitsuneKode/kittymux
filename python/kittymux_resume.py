"""kittymux resume — save a kitty session so that agents come back WITH their conversation (pure: no kitty imports; unit-tested).

kitty's own `save_as_session --use-foreground-process` saves layout, tabs, titles, cwd and the foreground command of every window — an agent window
comes back as a plain `claude`/`codex`, a NEW conversation. This module knows each agent's real resume syntax and where to find its session id, and
rewrites the saved `launch` lines so the same window restarts as `claude --resume <id>` (keeping the flags you started it with).

Session ids, most exact first:  1. the agent's own per-process registry (Claude: ~/.claude/sessions/<pid>.json),  2. a session file the process holds
open (Codex: rollout-…-<uuid>.jsonl),  3. "continue the latest session in this directory" — only when that directory is unambiguous (one window of that
agent), because two windows would both reopen the same conversation.  Anything else is left as saved. Nothing here guesses a flag: definitions are
data (assets/resume-agents.json, overridable in ~/.config/kittymux/resume.json) and `kittymux sessions check` probes the installed CLI's --help.
"""

from __future__ import annotations

import json
import os
import re
import shlex

UNSERIALIZE = "kitty-unserialize-data="
VAR_PREFIX = "--var=kittymux_"
STALE_VARS = ("kittymux_status", "kittymux_msg")           # hook state belongs to the process that is gone: never restore it
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")            # never starts with "-": an id is a value, not an option


# ── agent definitions (data, not code) ────────────────────────────────────────
def load_agents(builtin_path: str, user_path: str | None = None) -> dict:
    """Agent resume definitions: the shipped file, then the user's (same shape; a user entry replaces the shipped one). Bad files are ignored."""
    out: dict = {}
    for path in (builtin_path, user_path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(data, dict):
            for name, d in data.items():
                if isinstance(d, dict) and not name.startswith("_"):
                    out[name] = d
    return out


def _strip(argv: list[str], d: dict) -> list[str]:
    """argv without any existing resume/continue/session flags (and their values)."""
    with_value, plain = set(d.get("strip_with_value", [])), set(d.get("strip", []))
    out, i = [], 0
    while i < len(argv):
        tok = argv[i]
        flag = tok.split("=", 1)[0]
        if flag in with_value:
            i += 1
            if "=" not in tok and i < len(argv) and not argv[i].startswith("-"):
                i += 1                                    # its value
            continue
        if flag in plain:
            i += 1
            continue
        out.append(tok)
        i += 1
    return out


_RUNTIMES = {"node", "nodejs", "bun", "deno", "python", "python3", "uv", "npx", "bunx", "env"}


def resume_argv(d: dict, argv: list[str], session_id: str | None, mode: str, idx: int = 0) -> list[str] | None:
    """The command that reopens this agent's conversation, or None when we cannot do it safely. `mode`: "exact" (needs session_id) or "latest".
    Flags the agent was started with are kept; a subcommand-style agent (codex resume …) is only rewritten when it was started with flags alone."""
    if not argv or mode not in ("exact", "latest"):
        return None
    template = d.get(mode)
    if not template:
        return None
    if mode == "exact":
        if not session_id or not _SAFE_ID.match(session_id):
            return None
        template = [session_id if t == "{id}" else t for t in template]
    head, rest = argv[:idx + 1], argv[idx + 1:]                 # `node /path/claude --flag`: the runtime and the script stay as they were
    if d.get("form") == "subcommand":
        if any(not t.startswith("-") for t in rest):           # `codex exec …`, `codex some prompt`: not an interactive start we may rewrite
            return None
        return [*head, *rest, *template]
    return [*head, *_strip(rest, d), *template]


# ── finding session ids ───────────────────────────────────────────────────────
def proc_start(pid: int, proc: str = "/proc") -> str | None:
    """Field 22 of /proc/<pid>/stat (start time in ticks): with the pid it identifies one process, so a registry file cannot belong to a reused pid."""
    try:
        with open(f"{proc}/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def claude_session(home: str, pid: int, proc: str = "/proc") -> dict | None:
    """Claude Code's own record of the live session of process `pid`: {"id", "cwd", "status", "name"} or None. The file is Claude's, not ours, so
    everything about it is optional and checked (a format change must degrade to "unknown", never to a wrong id)."""
    try:
        with open(os.path.join(home, "sessions", f"{pid}.json"), encoding="utf-8") as f:
            d = json.load(f)
        sid = d["sessionId"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(sid, str) or not _UUID.fullmatch(sid) or d.get("pid") != pid:
        return None
    started = proc_start(pid, proc)
    if started is not None and d.get("procStart") is not None and str(d["procStart"]) != started:
        return None                                        # same pid, different process
    return {"id": sid, "cwd": d.get("cwd", ""), "status": d.get("status", ""), "name": d.get("name", "")}


def open_session_ids(pids: list[int], pattern: str, proc: str = "/proc") -> list[str]:
    """Distinct uuids found in the NAMES of files these processes hold open, matching `pattern` (a regex with the uuid in group 1)
    — Codex keeps its rollout-<time>-<uuid>.jsonl open. Newest-opened first is not knowable here, so callers use it only when it is unique."""
    rx = re.compile(pattern)
    seen: list[str] = []
    for pid in pids:
        try:
            fds = os.listdir(f"{proc}/{pid}/fd")
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(f"{proc}/{pid}/fd/{fd}")
            except OSError:
                continue
            m = rx.search(target)
            if m and m.group(1) not in seen:
                seen.append(m.group(1))
    return seen


# ── the plan: what each agent window should come back as ──────────────────────
def agent_of(agents: dict, argv: list[str]) -> tuple[str, int] | None:
    """(agent, index of its token in argv) for the agent this command line runs, else None. An agent's name (or one of its `names`) is matched on the
    basename of argv[0], or of argv[1] when argv[0] is a runtime (`node /path/to/claude`). A helper process of the same agent (`devin acp`,
    `codex app-server …`: the agent's `helpers` subcommands) is not the interactive agent and is skipped."""
    if not argv:
        return None
    for i in (0, 1):
        if i >= len(argv) or (i == 1 and os.path.basename(argv[0]).lower() not in _RUNTIMES):
            continue
        base = os.path.basename(argv[i]).lower()
        for name, d in agents.items():
            if base == name or base in d.get("names", []):
                rest = [t for t in argv[i + 1:] if not t.startswith("-")]
                if rest and rest[0] in d.get("helpers", []):
                    return None
                return name, i
    return None


def build_plan(windows: list[dict], agents: dict, home_claude: str, proc: str = "/proc", enabled=lambda name: True) -> list[dict]:
    """`windows`: [{"id", "cwd", "fg": [{"pid", "cmdline"}, …]}] (from `kitty @ ls`). Returns one entry per agent window:
    {"id", "agent", "cwd", "argv", "session_id", "mode", "resume", "why"} — `resume` is the new argv, or None with `why` explaining."""
    found = []
    for w in windows:
        hit = next(((p, agent_of(agents, p.get("cmdline") or [])) for p in w.get("fg", []) if agent_of(agents, p.get("cmdline") or [])), None)
        if hit is None:
            continue
        proc_entry, (name, idx) = hit
        found.append({"id": w["id"], "agent": name, "idx": idx, "cwd": w.get("cwd", ""), "argv": proc_entry["cmdline"], "pid": proc_entry.get("pid"),
                      "pids": [p.get("pid") for p in w.get("fg", []) if p.get("pid")]})
    per_dir: dict = {}
    per_agent: dict = {}
    for e in found:
        per_dir.setdefault((e["agent"], e["cwd"]), []).append(e)
        per_agent.setdefault(e["agent"], []).append(e)
    for e in found:
        d = agents[e["agent"]]
        e["session_id"], e["mode"], e["resume"] = None, "none", None
        if not enabled(e["agent"]):
            e["why"] = "no resume flag verified for this agent on this machine (run `kittymux sessions check`)"
            continue
        sid = None
        if d.get("locator") == "claude-registry" and e["pid"]:
            info = claude_session(home_claude, e["pid"], proc)
            sid = info["id"] if info else None
        elif d.get("locator") == "open-file" and d.get("open_file_pattern"):
            ids = open_session_ids(e["pids"], d["open_file_pattern"], proc)
            sid = ids[0] if len(ids) == 1 else None
        if sid:
            e["session_id"], e["mode"] = sid, "exact"
            e["resume"] = resume_argv(d, e["argv"], sid, "exact", e["idx"])
            e["why"] = "the agent's own session id" if e["resume"] else "could not build the command"
        elif d.get("latest_scope") == "directory" and len(per_dir[(e["agent"], e["cwd"])]) == 1:
            e["mode"] = "latest"
            e["resume"] = resume_argv(d, e["argv"], None, "latest", e["idx"])
            e["why"] = ("continues the latest session in this directory (it is the only %s window here)" % e["agent"]) if e["resume"] else "no latest-session form"
        elif d.get("latest_scope") != "directory" and len(per_agent[e["agent"]]) == 1:
            e["mode"] = "latest"
            e["resume"] = resume_argv(d, e["argv"], None, "latest", e["idx"])
            e["why"] = ("continues %s's most recent session (its help does not say whether that is limited to this directory; it is the only %s window, so the "
                        "likeliest one)" % (e["agent"], e["agent"])) if e["resume"] else "no latest-session form"
        elif d.get("latest_scope") != "directory":
            e["why"] = ("%s's `latest` is not documented as per-directory and there are %d %s windows, so it could open the wrong conversation: restoring as saved"
                        % (e["agent"], len(per_agent[e["agent"]]), e["agent"]))
        else:
            e["why"] = "several %s windows share this directory and none exposes its session id: restoring as saved (a new conversation) rather than opening one conversation twice" % e["agent"]
    return found


# ── rewriting a saved session file ────────────────────────────────────────────
def _window_id(tokens: list[str]) -> int | None:
    for t in tokens:
        if t.startswith(UNSERIALIZE):
            try:
                return int(json.loads(t[len(UNSERIALIZE):])["id"])
            except (ValueError, KeyError, TypeError):
                return None
    return None


def _command_start(tokens: list[str]) -> int:
    """Index of the first token of the command in a `launch …` line: kitty writes every option as one `--opt=value` token."""
    for i, t in enumerate(tokens[1:], 1):
        if not t.startswith("--") and not t.startswith(UNSERIALIZE):
            return i
    return len(tokens)


def rewrite_with_plan(text: str, plan: list[dict]) -> tuple[str, list[str]]:
    """Return (new text, report lines). Only `launch` lines of agent windows that have a resume command change (their command part); every line
    loses the restored hook-state variables. The line is matched to its window by the id kitty serialised into it AND the agent name, so a stale file
    can never rewrite the wrong window."""
    by_id = {e["id"]: e for e in plan if e.get("resume")}
    out, report = [], []
    for line in text.splitlines():
        if not line.startswith("launch"):
            out.append(line)
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            out.append(line)
            continue
        tokens = [t for t in tokens if not any(t.startswith(f"--var={v}=") for v in STALE_VARS)]
        wid = _window_id(tokens)
        entry = by_id.get(wid)
        start = _command_start(tokens)
        if entry is not None and start < len(tokens) and os.path.basename(tokens[start]) == os.path.basename(entry["argv"][0]):          # same program as saved
            tokens = tokens[:start] + entry["resume"]
            report.append("window %s: %s → %s" % (wid, entry["agent"], shlex.join(entry["resume"])))
        out.append(shlex.join(tokens))
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), report


def _vars(tokens: list[str]) -> dict:
    """`--var=kittymux_<name>=<value>` options of a launch line → {name: value} (empty values dropped)."""
    out = {}
    for t in tokens:
        if t.startswith(VAR_PREFIX):
            key, _, val = t[len("--var="):].partition("=")
            if val:
                out[key[len("kittymux_"):]] = val
    return out


def rewrite_session(text: str, agents: dict, enabled=lambda name: True) -> tuple[str, list[str]]:
    """Rewrite a saved session file using only what is IN it: each window kitty serialised carries the `--var=kittymux_sid=<id>` and
    `--var=kittymux_resume=exact|latest` we set on it just before saving (see `kittymux sessions prepare`), and its foreground command. No live kitty,
    no window ids to match — so a file can be rewritten any time, anywhere. Restored hook state is stripped from every line."""
    out, report = [], []
    for line in text.splitlines():
        if not line.startswith("launch"):
            out.append(line)
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            out.append(line)
            continue
        tokens = [t for t in tokens if not any(t.startswith(f"--var={v}=") for v in STALE_VARS)]
        start = _command_start(tokens)
        command = tokens[start:]
        hit = agent_of(agents, command)
        meta = _vars(tokens)
        mode = meta.get("resume", "")
        if hit and mode in ("exact", "latest") and enabled(hit[0]):
            new = resume_argv(agents[hit[0]], command, meta.get("sid"), mode, hit[1])
            if new:
                tokens = tokens[:start] + new
                report.append("%s → %s" % (hit[0], shlex.join(new)))
        out.append(shlex.join(tokens))
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), report


# ── templates ─────────────────────────────────────────────────────────────────
def render_template(text: str, values: dict) -> str:
    """Fill @NAME@ placeholders. Values are shell-quoted when they go into a launch/cd line, so a path with spaces or quotes stays one token."""
    def sub(m):
        key = m.group(1)
        if key not in values:
            return m.group(0)
        return shlex.quote(str(values[key])) if m.group(0).startswith("@Q:") else str(values[key])
    return re.sub(r"@(?:Q:)?([A-Z0-9_]+)@", sub, text)
