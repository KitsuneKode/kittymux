"""tabs.json — the vertical bar's tabs, for a shell that draws them in real pixels.

The bar already decides each tab's title, place line, state, age and progress. This module is that
decision as data: `display_title` and `show_program` are what the bar draws, `build_tab` turns one
tab into a row, and `publish` merges rows across kitty processes the way agents.json does. A kitty
replaces only its own windows and drops a pid that is gone. The file is mode 0600, written by
rename, and skipped when nothing but `t` changed.

Writes are coalesced by `Gate` / `submit`: at most one per 250 ms, and the last update in that
window is kept for a trailing write. The timer itself lives in the bar (`kittymux_timers`), not here.
Pure: no kitty imports. Schema version 1 is docs/inbox.md.
"""
from __future__ import annotations

import json
import os

import kittymux_agents
import kittymux_git
import kittymux_palette
import kittymux_place
import kittymux_progress

VERSION = 1
NAME = "tabs.json"
GAP = 0.25
PLACE_WIDTH = 240
_LEGACY_CWD = 24
_WIN_FIELDS = ("kitty_pid", "os_window_id", "wm_class", "focused", "session", "tabs")
_TAB_FIELDS = ("tab_id", "index", "active", "title", "subtitle", "project", "hue", "branch", "cwd",
               "agent", "brand", "state", "age", "progress", "panes", "needs_you", "action")


def path_for(state_dir: str) -> str:
    return os.path.join(state_dir, NAME)


def display_title(title: str) -> str:
    """The title the bar draws for a tidied string. A bare `~` (the home folder) is Home."""
    return "Home" if (title or "").strip() == "~" else (title or "")


def show_program(has_agent: bool, has_place: bool, home_only: bool, place_is_folder: bool) -> bool:
    """True when the bar draws the program instead of the folder line.

    No agent, and either there is no place line, or the line is only the home folder (it would
    repeat `~`). An agent keeps its place line. A legacy branch/path line is not the home folder.
    """
    if has_agent:
        return False
    if not has_place:
        return True
    return bool(home_only and place_is_folder)


def hue_hex(rgb) -> str | None:
    """`#rrggbb` for a project hue, or None. The bar's `project_hue` int, not a second palette."""
    if isinstance(rgb, bool) or not isinstance(rgb, int) or not 0 <= rgb <= 0xFFFFFF:
        return None
    return f"#{rgb:06x}"


def progress_obj(value) -> dict | None:
    """The bar's `(state, percent)` as `{state, pct}`, or None when nothing was reported."""
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    state, pct = value[0], value[1]
    if state not in kittymux_progress.TINT:
        return None
    if isinstance(pct, bool) or not isinstance(pct, (int, float)):
        return None
    return {"state": state, "pct": max(0, min(100, int(pct)))}


def place_plain(facts, hide_project: bool, hide_worktree: bool, width: int = PLACE_WIDTH) -> str:
    """The place line's words at `width` cells: project, path and branch. No icons, no colour."""
    if facts is None:
        return ""
    runs = kittymux_place.layout(facts, width, icon="", branch_icon="", hide_project=hide_project,
                                 hide_worktree=hide_worktree, cells=len)
    return kittymux_place.clean_line("".join(text for text, _role in runs)).strip()


def _pid(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2 ** 40:
        return None
    return value


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


def _contract_state(state: str) -> str:
    return state if state in kittymux_agents.STATES else "idle"


class Gate:
    """At most one write per `gap` seconds, with the newest item kept for the trailing write.

    `push` returns `("write", item)`, `("arm", delay)` or `("hold", None)`. The caller arms a timer
    on `"arm"` and calls `fire` when it runs. No timer lives here.
    """

    def __init__(self, gap: float = GAP):
        self.gap = gap
        self.last: float | None = None
        self.armed = False
        self.pending = None

    def push(self, item, now: float) -> tuple[str, object]:
        self.pending = item
        if self.armed:
            return "hold", None
        if self.last is None or now - self.last >= self.gap:
            item = self.pending
            self.pending = None
            self.last = now
            return "write", item
        return "arm", self.gap - (now - self.last)

    def arm(self) -> None:
        self.armed = True

    def fire(self, now: float):
        """The trailing timer ran. The item to write, or None when nothing is waiting."""
        self.armed = False
        if self.pending is None:
            return None
        item = self.pending
        self.pending = None
        self.last = now
        return item


def submit(gate: Gate, item, now: float, write, arm) -> str:
    """Run one `push`. `arm(delay)` is true when a trailing timer was scheduled.

    When a timer cannot be scheduled the pending item is written now, so the last update is not
    dropped. Returns `write`, `arm`, `hold` or `write-now`.
    """
    action, payload = gate.push(item, now)
    if action == "write":
        write(payload)
        return "write"
    if action == "arm":
        gate.arm()
        if arm(float(payload)):
            return "arm"
        gate.armed = False
        pending = gate.fire(now)
        if pending is not None:
            write(pending)
        return "write-now"
    return "hold"


def build_tab(*, tab_id: int, index: int, active: bool, title: str, program: str, has_agent: bool,
              agent: str, facts, folder: bool, cwd: str, home: str, hue, state: str, ts_state,
              now: float, panes: int, window_id: int, kitty_pid: int, progress=None, reset_at=None,
              wall=None, home_only: bool | None = None, hide_project: bool | None = None,
              hide_worktree: bool | None = None, title_key: str | None = None,
              raw_title: str | None = None) -> dict | None:
    """One tab row. `title` is the bar's tidied title, before the Home substitution. None when the
    jump action would not validate."""
    pid = _pid(kitty_pid)
    tid = _pid(tab_id)
    wid = _pid(window_id)
    if pid is None or tid is None or wid is None or isinstance(index, bool) or not isinstance(index, int) or index < 1:
        return None
    action = kittymux_palette.validate_action({"op": "jump", "pid": pid, "w": str(wid)})
    if action is None:
        return None
    shown = display_title(_text(title, 400))
    key = title if title_key is None else title_key
    if facts is not None:
        if hide_project is None:
            hide_project = kittymux_place.redundant(key, facts)
        if hide_worktree is None:
            hide_worktree = kittymux_place.worktree_named(key, facts)
    else:
        hide_project, hide_worktree = False, False
    if home_only is None:
        home_only = kittymux_place.clean(title if raw_title is None else raw_title).strip() == "~"
    if folder and cwd and facts is not None:
        place, has_place, place_is_folder = place_plain(facts, hide_project, hide_worktree), True, True
    elif cwd and not folder:
        if facts is not None and facts.branch:
            place = facts.branch
        else:
            place = kittymux_git.short_path(cwd, home, _LEGACY_CWD)
        has_place, place_is_folder = bool(place), False
    else:
        place, has_place, place_is_folder = "", False, False
    if show_program(bool(has_agent), has_place, bool(home_only), place_is_folder):
        subtitle = _text(program, 80)
    else:
        # keep the place line's spacing (project, two spaces, branch); only controls go
        subtitle = kittymux_place.clean_line(place).strip()[:240]
    name = str(agent or "").strip().lower()
    if not has_agent or not kittymux_agents.agent_in([name]):
        name = ""
    contract = _contract_state(state)
    try:
        n_panes = int(panes)
    except (TypeError, ValueError):
        n_panes = 0
    if isinstance(panes, bool) or n_panes < 0:
        n_panes = 0
    row = {
        "tab_id": tid,
        "index": index,
        "active": bool(active),
        "title": shown,
        "subtitle": subtitle,
        "project": _text(getattr(facts, "project", "") or "", 80),
        "hue": hue_hex(hue),
        "branch": _text(getattr(facts, "branch", "") or "", 80),
        "cwd": _text(_short_cwd(cwd, home), 240),
        "agent": name,
        "brand": kittymux_agents.brand_of(name),
        "state": contract,
        "age": kittymux_agents.state_age(contract, ts_state, now, reset_at=reset_at, wall=wall) or "",
        "progress": progress_obj(progress),
        "panes": n_panes,
        "needs_you": contract in kittymux_agents.NEEDS_YOU,
        "action": action,
    }
    return {k: row[k] for k in _TAB_FIELDS}


def _signature(doc: dict) -> str:
    body = {k: v for k, v in doc.items() if k != "t"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _read(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return []
    rows = doc.get("windows") if isinstance(doc, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _alive(pid: int) -> bool:
    return os.path.isdir(f"/proc/{pid}")


def _keep(window: dict, kitty_pid: int, alive) -> bool:
    other = _pid(window.get("kitty_pid"))
    if other is None or other == kitty_pid:
        return False
    try:
        return bool(alive(other))
    except Exception:
        return False


def _window(raw: dict, kitty_pid: int) -> dict | None:
    osw = _pid(raw.get("os_window_id"))
    if osw is None or not isinstance(raw.get("tabs"), list):
        return None
    tabs = [t for t in raw["tabs"] if isinstance(t, dict)]
    return {
        "kitty_pid": kitty_pid,
        "os_window_id": osw,
        "wm_class": _text(raw.get("wm_class") or "kitty", 64) or "kitty",
        "focused": bool(raw.get("focused")),
        "session": _text(raw.get("session") or "", 80),
        "tabs": tabs,
    }


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


def publish(state_dir: str, kitty_pid: int, windows, now: float, alive=None) -> bool:
    """Replace this kitty's windows. True only when the file was replaced. Never raises."""
    try:
        pid = _pid(kitty_pid)
        if pid is None:
            return False
        fresh = []
        for raw in windows or []:
            if isinstance(raw, dict):
                window = _window(raw, pid)
                if window is not None:
                    fresh.append(window)
        check = alive or _alive
        import fcntl
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        lock = os.open(os.path.join(state_dir, "tabs.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            dest = path_for(state_dir)
            old = _read(dest)
            rows = [r for r in old if _keep(r, pid, check)] + fresh
            rows.sort(key=lambda r: (_pid(r.get("kitty_pid")) or 0, _pid(r.get("os_window_id")) or 0))
            doc = {"version": VERSION, "t": round(float(now), 1), "windows": rows}
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
