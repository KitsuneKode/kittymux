"""tabs.json — every tab of every running kitty, for a client drawn outside kitty (the kittymux client, kuwai's Agents tab).

agents.json lists agents; a client that draws the tab strip also needs the tabs nobody's agent runs in, which tab is active, and how
many panes each has. The scanner (one pass per kitty) calls `publish` with that kitty's OS windows. The file is shared like
agents.json: this process replaces only its own entries and keeps entries whose kitty is still alive; mode 0600; atomic; and a
write is skipped when nothing but `t` would change, so a client that watches the file wakes only for real changes. Schema version
1 is docs/inbox.md. Pure: no kitty imports.
"""
from __future__ import annotations

import json
import os
import re

import kittymux_agents
import kittymux_agentsnap as snap
import kittymux_git
import kittymux_palette
import kittymux_place
import kittymux_theme

VERSION = 1
NAME = "tabs.json"
# Which pane speaks for the tab: what asks for you first, then trouble, then work, then the rest. A muted agent speaks only
# when nothing else in the tab does.
LEAD = ("waiting", "limited", "error", "working", "done", "idle")
_AGENT = re.compile(r"[a-z][a-z0-9-]{0,30}")
_CLASS = re.compile(r"[A-Za-z0-9._-]{1,64}")
_PALETTE = ("bg", "fg", "bar", "muted", "faint", "accent", "working", "waiting", "done", "alert")
_TAB_FIELDS = ("tab_id", "index", "active", "title", "cwd", "project", "branch", "hue", "panes", "agent", "agent_window", "brand", "state", "since",
               "progress", "question", "limit_reset", "muted", "needs_you", "action")


def path_for(state_dir: str) -> str:
    return os.path.join(state_dir, NAME)


def _lead(windows: list) -> dict | None:
    """The pane whose agent speaks for the tab, or None when no pane runs an agent."""
    best, best_key = None, None
    for w in windows:
        state, agent = w.get("state"), str(w.get("agent") or "").strip().lower()
        if state not in LEAD or not _AGENT.fullmatch(agent):
            continue
        key = (bool(w.get("muted")), LEAD.index(state), 0 if w.get("active") else 1)
        if best_key is None or key < best_key:
            best, best_key = w, key
    return best


def palette_of(colors: dict) -> dict:
    """The kitty theme's tokens a client draws with (kittymux_theme.from_colors), as #rrggbb. {} when `colors` is empty."""
    if not colors:
        return {}
    try:
        pal = kittymux_theme.from_colors(colors)
    except Exception:
        return {}
    return {k: kittymux_theme._hex(getattr(pal, k)) for k in _PALETTE}


def _hue(project: str, colors: dict) -> str:
    """The project's own colour, the one the bar gives its space (kittymux_theme.project_hue), or ""."""
    if not project or not colors:
        return ""
    try:
        pal = kittymux_theme.from_colors(colors)
        return kittymux_theme._hex(kittymux_theme.project_hue(project, pal.accent, pal.surface_hi,
                                                                 avoid=(pal.waiting, pal.alert, pal.working, pal.done)))
    except Exception:
        return ""


def _tab(kitty_pid: int, index: int, spec: dict, home: str, previous: dict, now: float, colors: dict | None = None) -> dict | None:
    tid = snap._wid(spec.get("tab_id"))
    windows = [w for w in (spec.get("windows") or []) if isinstance(w, dict) and snap._wid(w.get("window_id")) is not None]
    if tid is None or not windows:
        return None
    active = next((w for w in windows if w.get("active")), windows[0])
    action = kittymux_palette.validate_action({"op": "jump", "pid": kitty_pid, "w": str(snap._wid(active.get("window_id")))})
    if action is None:
        return None
    cwd_raw = str(active.get("cwd") or spec.get("cwd") or "")
    project = branch = ""
    if cwd_raw:
        try:
            info = kittymux_git.info(cwd_raw)
            facts = kittymux_place.facts(cwd_raw, info, home)
            project, branch = snap._text(facts.project, 80), snap._text(facts.branch, 80)
        except Exception:
            pass
    lead = _lead(windows)
    state = lead.get("state") if lead else ""
    agent = str(lead.get("agent") or "").strip().lower() if lead else ""
    muted = bool(lead.get("muted")) if lead else False
    reason = snap._text(lead.get("reason") or "", 160) if lead else ""
    row = {
        "tab_id": tid,
        "index": index,
        "active": bool(spec.get("active")),
        "title": snap._text(spec.get("title") or "", 80),
        "cwd": snap._text(snap._short_cwd(cwd_raw, home), 240),
        "project": project,
        "branch": branch,
        "hue": _hue(project, colors or {}),
        "panes": len(windows),
        "agent": agent,
        "agent_window": snap._wid(lead.get("window_id")) if lead else None,      # what `kittymux mute --pid P --window W` mutes
        "brand": kittymux_agents.brand_of(agent) if agent else "",
        "state": state,
        "since": None,
        "progress": snap._progress(lead.get("progress")) if lead else None,
        "question": reason if state == "waiting" and reason else None,
        "limit_reset": snap._epoch(lead.get("limit_reset")) if state == "limited" else None,
        "muted": muted,
        "needs_you": state in kittymux_agents.NEEDS_YOU and not muted,
        "action": action,
    }
    old = previous.get(tid)
    since = old.get("since") if isinstance(old, dict) and old.get("state") == state else None
    row["since"] = since if isinstance(since, (int, float)) and not isinstance(since, bool) else (round(float(now), 1) if state else None)
    return {k: row[k] for k in _TAB_FIELDS}


def _window(kitty_pid: int, spec: dict, home: str, previous: dict, now: float) -> dict | None:
    if not isinstance(spec, dict):
        return None
    osw = snap._wid(spec.get("os_window_id"))
    if osw is None:
        return None
    wm_class = str(spec.get("wm_class") or "kitty")
    colors = spec.get("colors") if isinstance(spec.get("colors"), dict) else {}
    tabs = []
    for spec_tab in spec.get("tabs") or []:
        if isinstance(spec_tab, dict):
            row = _tab(kitty_pid, len(tabs) + 1, spec_tab, home, previous, now, colors)
            if row is not None:
                tabs.append(row)
    return {"key": f"o{kitty_pid}.{osw}", "kitty_pid": kitty_pid, "os_window_id": osw,
            "wm_class": wm_class if _CLASS.fullmatch(wm_class) else "kitty", "focused": bool(spec.get("focused")),
            "session": snap._text(spec.get("session") or "", 80), "title": snap._text(spec.get("title") or "", 200),
            "geometry": geometry_of(spec.get("geometry")), "palette": palette_of(colors), "tabs": tabs}


def _num(value, lo: float, hi: float):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and lo <= value <= hi else None


def bar_reserves_space(bar, central) -> bool:
    """The terminal has stepped aside for this bar. A zero bar, or one that overlaps the terminal, is not on screen:
    a client must not cover the shell. No central rectangle means we cannot check, so the bar is kept."""
    if not (isinstance(bar, (list, tuple)) and len(bar) == 4 and all(_num(v, 0, 1 << 16) is not None for v in bar)):
        return False
    left, top, right, bottom = (int(v) for v in bar)
    if right - left < 8 or bottom - top < 8:
        return False
    if not (isinstance(central, (list, tuple)) and len(central) == 4 and all(_num(v, 0, 1 << 16) is not None for v in central)):
        return True
    cl, ct, cr, cb = (int(v) for v in central)
    if left <= 1 and cl + 1 >= right - 1:
        return True
    if cr <= left + 1 < right:
        return True
    if top <= 1 and ct + 1 >= bottom - 1:
        return True
    if cb <= top + 1 < bottom:
        return True
    return False


def geometry_of(spec) -> dict | None:
    """The OS window's bar, for a client that draws over it: framebuffer size (`vw`, `vh`), logical size (`width`, `height`), `scale`
    (framebuffer pixels per logical pixel), the bar's `edge` (left/right/top/bottom) and `bar` [left, top, right, bottom] in framebuffer
    pixels, the `cell` size and the background `opacity`. None when kitty gave nothing usable; `bar` None when the bar is hidden."""
    if not isinstance(spec, dict):
        return None
    vw, vh = _num(spec.get("vw"), 1, 1 << 16), _num(spec.get("vh"), 1, 1 << 16)
    w, h = _num(spec.get("width"), 1, 1 << 16), _num(spec.get("height"), 1, 1 << 16)
    if not (vw and vh and w and h):
        return None
    out = {"vw": int(vw), "vh": int(vh), "width": int(w), "height": int(h), "scale": round(vw / w, 4), "edge": "", "bar": None,
           "cell": None, "opacity": None}
    cell = spec.get("cell")
    if isinstance(cell, (list, tuple)) and len(cell) == 2 and all(_num(c, 1, 4096) for c in cell):
        out["cell"] = [int(c) for c in cell]
    op = _num(spec.get("opacity"), 0, 1)
    out["opacity"] = round(float(op), 3) if op is not None else None
    bar = spec.get("bar")
    if isinstance(bar, (list, tuple)) and len(bar) == 4 and all(_num(v, 0, 1 << 16) is not None for v in bar):
        l, t, r, b = (int(v) for v in bar)
        if r > l and b > t:
            out["bar"] = [l, t, r, b]
            if b - t >= vh - 1 and r - l < vw:
                out["edge"] = "left" if l == 0 else "right"
            else:
                out["edge"] = "top" if t == 0 else "bottom"
        if not bar_reserves_space(out["bar"], spec.get("central")):
            out["bar"] = None
            out["edge"] = ""
    return out


def _read(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError, UnicodeError):
        return []
    rows = doc.get("windows") if isinstance(doc, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def publish(state_dir: str, kitty_pid: int, specs, now: float, alive=None, home: str | None = None) -> bool:
    """Replace this kitty's OS windows in tabs.json. True only when the file was replaced. Never raises."""
    try:
        pid = snap._pid(kitty_pid)
        if pid is None:
            return False
        home = home if home is not None else os.path.expanduser("~")
        check = alive or snap._alive
        import fcntl
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        lock = os.open(os.path.join(state_dir, "tabs.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            dest = path_for(state_dir)
            old = _read(dest)
            previous = {t.get("tab_id"): t for w in old if w.get("kitty_pid") == pid for t in (w.get("tabs") or []) if isinstance(t, dict)}
            fresh = [w for w in (_window(pid, s, home, previous, now) for s in (specs or [])) if w is not None]
            rows = [w for w in old if snap._keep(w, pid, check)] + fresh
            rows.sort(key=lambda w: (str(w.get("key") or "")))
            tabs = [t for w in rows for t in (w.get("tabs") or []) if isinstance(t, dict)]
            doc = {"version": VERSION, "t": round(float(now), 1), "windows": rows,
                   "needs_you": sum(1 for t in tabs if t.get("needs_you"))}
            if os.path.isfile(dest):
                try:
                    with open(dest, encoding="utf-8") as handle:
                        current = json.load(handle)
                    if isinstance(current, dict) and snap._signature(current) == snap._signature(doc):
                        return False
                except (OSError, ValueError, UnicodeError):
                    pass
            snap._write(dest, json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
            return True
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)
    except Exception:
        return False
