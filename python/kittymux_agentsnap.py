"""agents.json — one live list of every agent, for a shell that must not parse menu text.

The scanner (one pass per kitty) calls `publish` with that kitty's windows. The file is shared:
this process replaces only its own rows and keeps rows whose kitty is still alive. A write is the
whole document, mode 0600, and it is skipped when nothing but `t` would change. Schema version 1
is docs/inbox.md. Pure: no kitty imports.
"""
from __future__ import annotations

import json
import os
import re

import kittymux_agents
import kittymux_git
import kittymux_palette
import kittymux_place
import kittymux_titles

VERSION = 1
NAME = "agents.json"
# Contract order, most important first. `limited` is the status-contract name (an older note said `limit`).
RANK = ("limited", "waiting", "error", "working", "done", "idle")
COUNTS = ("working", "waiting", "done", "idle", "limited", "error")
_AGENT = re.compile(r"[a-z][a-z0-9-]{0,30}")
_FIELDS = ("key", "kitty_pid", "window_id", "agent", "brand", "source", "state", "since",
           "title", "tab_title", "cwd", "project", "session", "question", "progress",
           "limit_reset", "error", "action", "muted")


def path_for(state_dir: str) -> str:
    return os.path.join(state_dir, NAME)


def _pid(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2 ** 40:
        return None
    return value


def _wid(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _text(value, limit: int) -> str:
    return kittymux_place.clean(str(value or ""))[:limit]


def _short_cwd(cwd: str, home: str) -> str:
    if not cwd:
        return ""
    path = os.path.abspath(cwd)
    root = os.path.abspath(home) if home else ""
    if root and (path == root or path.startswith(root + os.sep)):
        return "~" + path[len(root):]
    return path


def _progress(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number < 0 or number > 1:
        return None
    return round(number, 4)


def _epoch(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = int(value)
    if number <= 0 or number >= 2 ** 40:
        return None
    return number


def _alive(pid: int) -> bool:
    return os.path.isdir(f"/proc/{pid}")


def _row(kitty_pid: int, spec: dict, home: str) -> dict | None:
    if not isinstance(spec, dict):
        return None
    wid = _wid(spec.get("window_id"))
    agent = str(spec.get("agent") or "").strip().lower()
    state = spec.get("state")
    if wid is None or not _AGENT.fullmatch(agent) or state not in kittymux_agents.STATES:
        return None
    action = kittymux_palette.validate_action({"op": "jump", "pid": kitty_pid, "w": str(wid)})
    if action is None:
        return None
    cwd_raw = str(spec.get("cwd") or "")
    cwd = _text(_short_cwd(cwd_raw, home), 240)
    try:
        info = kittymux_git.info(cwd_raw) if cwd_raw else None
    except Exception:
        info = None
    project = ""
    if cwd_raw:
        try:
            project = _text(kittymux_place.facts(cwd_raw, info, home).project, 80)
        except Exception:
            project = ""
    title = _text(kittymux_titles.tidy(spec.get("title") or "", agent, project).text, 200)
    reason = _text(spec.get("reason") or "", 160)
    waiting = state == "waiting" and bool(reason)
    failed = state == "error" and bool(reason)
    row = {
        "key": f"w{kitty_pid}.{wid}",
        "kitty_pid": kitty_pid,
        "window_id": wid,
        "agent": agent,
        "brand": kittymux_agents.brand_of(agent),
        "source": "agent",
        "state": state,
        "since": None,
        "title": title,
        "tab_title": _text(spec.get("tab_title") or "", 80),
        "cwd": cwd,
        "project": project,
        "session": _text(spec.get("session") or "", 80),
        "question": reason if waiting else None,
        "progress": _progress(spec.get("progress")),
        "limit_reset": _epoch(spec.get("limit_reset")) if state == "limited" else None,
        "error": reason if failed else None,
        "action": action,
        "muted": bool(spec.get("muted")),     # `kittymux mute`: still listed, never "needs you", no popup or bell
    }
    return {k: row[k] for k in _FIELDS}


def _signature(doc: dict) -> str:
    body = {k: v for k, v in doc.items() if k != "t"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _read(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError, UnicodeError):
        return []
    rows = doc.get("agents") if isinstance(doc, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _keep(row: dict, kitty_pid: int, alive) -> bool:
    other = _pid(row.get("kitty_pid"))
    if other is None or other == kitty_pid:
        return False
    try:
        return bool(alive(other))
    except Exception:
        return False


def _apply_since(row: dict, previous: dict, now: float) -> None:
    old = previous.get(row["key"])
    since = old.get("since") if isinstance(old, dict) and old.get("state") == row["state"] else None
    if isinstance(since, (int, float)) and not isinstance(since, bool):
        row["since"] = since
    else:
        row["since"] = round(float(now), 1)


def _counts(rows: list) -> dict:
    counts = {name: 0 for name in COUNTS}
    for row in rows:
        state = row.get("state")
        if state in counts:
            counts[state] += 1
    return counts


def _write(path: str, text: str) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def publish(state_dir: str, kitty_pid: int, specs, now: float, alive=None, home: str | None = None) -> bool:
    """Replace this kitty's rows. True only when the file was replaced. Never raises."""
    try:
        pid = _pid(kitty_pid)
        if pid is None:
            return False
        home = home if home is not None else os.path.expanduser("~")
        fresh = []
        for spec in specs or []:
            row = _row(pid, spec, home)
            if row is not None:
                fresh.append(row)
        check = alive or _alive
        import fcntl
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        lock = os.open(os.path.join(state_dir, "agents.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            dest = path_for(state_dir)
            old = _read(dest)
            previous = {r.get("key"): r for r in old if r.get("kitty_pid") == pid}
            for row in fresh:
                _apply_since(row, previous, now)
            rows = [r for r in old if _keep(r, pid, check)] + fresh
            rows.sort(key=lambda r: (RANK.index(r["state"]) if r.get("state") in RANK else len(RANK), str(r.get("key") or "")))
            doc = {"version": VERSION, "t": round(float(now), 1), "agents": rows, "counts": _counts(rows),
                   "needs_you": sum(1 for r in rows if r.get("state") in kittymux_agents.NEEDS_YOU and not r.get("muted"))}
            if os.path.isfile(dest):
                try:
                    with open(dest, encoding="utf-8") as handle:
                        current = json.load(handle)
                    if isinstance(current, dict) and _signature(current) == _signature(doc):
                        return False
                except (OSError, ValueError, UnicodeError):
                    pass
            _write(dest, json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
            return True
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)
    except Exception:
        return False
