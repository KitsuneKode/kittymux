# kittymux sidebar — a cmux-style command deck for kitty.
# Bound as: map ctrl+alt+b kitten <this file>
# Real mouse hover + click via kittens.tui (MouseTracking.full); tab/pane data
# and jumps go through the kitten's fd-based remote-control channel.
#
# Tabs are grouped by session. All colours derive from the live kitty theme
# (kittymux_theme). Data collection (kitty @ ls, git, get-text) runs in a
# worker thread so keys and mouse never wait on a subprocess.

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from kittens.tui.handler import Handler, kitten_ui, result_handler
from kittens.tui.loop import EventType as MouseEventType, Loop, MouseButton  # noqa: E402
from kittens.tui.operations import MouseTracking, set_cursor_position, styled
from kitty.fast_data_types import wcswidth
from kitty.key_encoding import EventType
from kitty.rgb import Color
from kitty.typing_compat import BossType

# Kittens are exec'd (no __file__): find the shared modules via the config dir
# (the installer links them there) or next to this script if we can tell.
_CONFIG_DIR = os.environ.get("KITTY_CONFIG_DIRECTORY", str(Path.home() / ".config" / "kitty"))
for _d in (_CONFIG_DIR, os.path.dirname(os.path.realpath(sys.argv[0])) if sys.argv and sys.argv[0] else ""):
    if _d and _d not in sys.path:
        sys.path.insert(0, _d)
import kittymux_agents  # noqa: E402
import kittymux_deck as deck  # noqa: E402
import kittymux_git  # noqa: E402
import kittymux_theme  # noqa: E402

_STATE_DIR = Path(os.environ["KITTYMUX_STATE"]) if os.environ.get("KITTYMUX_STATE") else \
    Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "kittymux"
_ERR_LOG = _STATE_DIR / "sidebar-kit-err.log"

_ICON_BRANCH = ""
_ICON_FOLDER = ""
_RAIL = "▌"
_STALE_AFTER = 15.0
_PR_TTL = 120.0
_REFRESH_EVERY = 1.5


def _C(rgb: int) -> Color:
    return Color(rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255)


def _cells(s: str) -> int:
    return max(0, wcswidth(s))


# Panel mode (bin/mux-panel): the deck lives in its own docked kitty instance and
# talks to a *target* kitty over its socket; it stays open after a jump.
_TARGET = os.environ.get("KITTYMUX_TARGET", "")
_PANEL = os.environ.get("KITTYMUX_PANEL") == "1"
_PANEL_SOCK = os.environ.get("KITTYMUX_PANEL_SOCK", "")       # the panel's own RC socket (for drag-resize)
_PANEL_EDGE = os.environ.get("KITTYMUX_PANEL_EDGE", "left")


def _rc(*args: str) -> str:
    """Synchronous remote control: over --to $KITTYMUX_TARGET in panel mode, else the
    kitten's own fd channel."""
    if _TARGET:
        try:
            p = subprocess.run(["kitty", "@", "--to", _TARGET, *args],
                               capture_output=True, text=True, timeout=4)
        except Exception:
            return ""
        return p.stdout if p.returncode == 0 else ""
    p = main.remote_control(list(args), capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def _panes_state() -> dict:
    try:
        return kittymux_agents.load_panes(str(_STATE_DIR / f"panes-{os.getppid()}.json"))
    except Exception:
        return {}


def _short_home(p: str) -> str:
    home = os.path.expanduser("~")
    return "~" + p[len(home):] if p.startswith(home) else p


class PrCache:
    """Open-PR number per (cwd, branch) via `gh`, refreshed in the background so a
    slow network never stalls a snapshot. Disabled with KITTYMUX_PR=0 or no gh."""

    def __init__(self):
        self._cache: dict[tuple[str, str], tuple[float, str]] = {}
        self._inflight: set = set()
        self._lock = threading.Lock()
        self.enabled = os.environ.get("KITTYMUX_PR") != "0" and bool(shutil.which("gh"))

    def get(self, cwd: str, branch: str) -> str:
        if not self.enabled or not cwd or not branch or branch in ("main", "master", "detached"):
            return ""
        key = (cwd, branch)
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            stale = hit is None or now - hit[0] > _PR_TTL
            if stale and key not in self._inflight:
                self._inflight.add(key)
                threading.Thread(target=self._fetch, args=(key,), daemon=True).start()
            return hit[1] if hit else ""

    def _fetch(self, key) -> None:
        cwd, branch = key
        pr = ""
        try:
            p = subprocess.run(["gh", "pr", "view", branch, "--json", "number,state", "-q",
                                r'select(.state=="OPEN") | "#\(.number)"'],
                               cwd=cwd, capture_output=True, text=True, timeout=6)
            pr = p.stdout.strip() if p.returncode == 0 else ""
        except Exception:
            pass
        with self._lock:
            self._cache[key] = (time.monotonic(), pr)
            self._inflight.discard(key)
            if len(self._cache) > 200:                       # bounded: drop the oldest half
                for k in sorted(self._cache, key=lambda k: self._cache[k][0])[:100]:
                    del self._cache[k]


def _proc_ppids() -> dict:
    out = {}
    try:
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                with open(f"/proc/{name}/stat") as f:
                    stat = f.read()
                out[int(name)] = int(stat.rsplit(")", 1)[1].split()[1])
            except Exception:
                continue
    except Exception:
        pass
    return out


def _listeners() -> list:
    try:
        p = subprocess.run(["ss", "-H", "-ltnp"], capture_output=True, text=True, timeout=1.5)
        return deck.parse_ss(p.stdout) if p.returncode == 0 else []
    except Exception:
        return []


class Snapshot:
    __slots__ = ("rows", "items", "current_session")

    def __init__(self, rows: list, current_session: str):
        groups = deck.group_rows(rows, current_session)
        self.items, self.rows = deck.flatten(groups, current_session)
        self.current_session = current_session


class Collector:
    """Builds a Snapshot from `kitty @ ls`. Runs on a worker thread only."""

    def __init__(self):
        self._pr = PrCache()

    def branch(self, cwd: str) -> str:
        gi = kittymux_git.info(cwd)                 # reads .git/HEAD; no subprocess
        return "" if gi is None or gi.branch == "detached" else gi.branch

    @staticmethod
    def _identify(w: dict) -> tuple:
        """(agent name | None, tool name | None) for a `kitty @ ls` window."""
        procs = w.get("foreground_processes") or []
        name = None
        for proc in procs:
            name = kittymux_agents.agent_in(proc.get("cmdline") or [])
            if name:
                break
        tool = None if name else kittymux_agents.tool_in(p.get("cmdline") or [] for p in procs)
        return name, tool

    def _pane(self, w: dict, active_id: int, panes: dict, now: float) -> deck.PaneData:
        name, tool = self._identify(w)
        agent = kittymux_agents.AGENTS.get(name) if name else None
        if w["id"] == active_id:
            state = kittymux_agents.resolve_status(panes.get(str(w["id"])), agent is not None, now, _STALE_AFTER)
        else:
            state = kittymux_agents.fresh_verdict(panes.get(str(w["id"])), now)
        title = (w.get("title") or "").strip() or _short_home(w.get("cwd", ""))
        return deck.PaneData(win_id=w["id"], glyph=agent.glyph if agent else kittymux_agents.TOOLS.get(tool, ""),
                             agent=name or "", tool=bool(tool and not agent), state=state,
                             title=kittymux_agents.strip_title_prefix(title), active=w["id"] == active_id)

    def collect(self) -> Snapshot | None:
        try:
            data = json.loads(_rc("ls"))
        except Exception:
            return None
        panes = _panes_state()
        children = deck.children_map(_proc_ppids())
        listeners = _listeners()
        rows, current_session = [], ""
        for osw in data:
            for tab in osw.get("tabs", []):
                # Overlay/kitten windows are chrome, not content.
                wins = [w for w in tab.get("windows") or []
                        if "kittens.runner" not in str(w.get("cmdline"))]
                if not wins:
                    continue
                hist = [i for i in tab.get("active_window_history") or []
                        if any(w["id"] == i for w in wins)]
                aw_id = hist[0] if hist else wins[0]["id"]
                aw = next((w for w in wins if w["id"] == aw_id), wins[0])
                cwd = aw.get("cwd", "")
                now = time.monotonic()
                name, tool_name = self._identify(aw)
                agent = kittymux_agents.AGENTS.get(name) if name else None
                # every pane of the tab counts: a question in a split you are not in must show here too
                st, deciding = kittymux_agents.tab_verdict(
                    panes, [w["id"] for w in wins], aw["id"], agent is not None, now, _STALE_AFTER)
                unread = bool(tab.get("needs_attention") or aw.get("needs_attention")
                              or aw.get("has_activity_since_last_focus"))
                status = ("" if st == "idle" else st) if st else ("unread" if unread else "")
                jump_to = int(deciding) if deciding and st in kittymux_agents.NEEDS_YOU else aw["id"]
                pane_rows = tuple(self._pane(w, aw["id"], panes, now) for w in wins) if len(wins) >= 2 else ()
                current = bool((osw.get("is_focused") or (_PANEL and osw.get("last_focused"))) and tab.get("is_active"))
                session = aw.get("session_name", "") or ""
                if current:
                    current_session = session
                branch = self.branch(cwd) if cwd else ""
                pids = [w.get("pid") for w in wins if w.get("pid")]
                ports = tuple(sorted({p for pid in pids
                                      for p in deck.ports_for(int(pid), children, listeners)}))
                rows.append(deck.RowData(
                    tab_id=tab["id"], win_id=jump_to, session=session,
                    title=tab.get("title") or "",
                    glyph=agent.glyph if agent else kittymux_agents.TOOLS.get(tool_name, ""),
                    tool=bool(tool_name and not agent),
                    agent=name or "", branch=branch, cwd=cwd,
                    panes=len(wins), status=status, unread=unread, current=current,
                    msg=kittymux_agents.resolve_msg(panes.get(str(deciding or aw["id"])), st) if st else "",
                    pr=self._pr.get(cwd, branch), ports=ports, pane_rows=pane_rows))
        return Snapshot(rows, current_session)


class Sidebar(Handler):
    mouse_tracking = MouseTracking.full

    def initialize(self) -> None:
        self.pal = kittymux_theme.from_colors(
            kittymux_theme.parse_kitty_colors(_rc("get-colors", "--configured")))
        self.snap = Snapshot([], "")
        self.sel = 0
        self.scroll = 0
        self.preview: list[str] = []
        self.preview_for = 0
        self._hover_pane = (-1, -1)             # (row, pane) of the child line under the pointer
        self._alive = True
        self._collecting = False
        self._collector = Collector()
        self._first = True
        self._request_refresh()
        self.draw_screen()
        self._schedule()

    def finalize(self) -> None:
        self._alive = False

    # ---- data (worker threads → event loop) -------------------------------
    def _request_refresh(self) -> None:
        if self._collecting or not self._alive:
            return
        self._collecting = True

        def work() -> None:
            snap = None
            try:
                snap = self._collector.collect()
            except Exception:
                _log_error()
            finally:
                self._post(self._apply, snap)

        threading.Thread(target=work, daemon=True).start()

    def _post(self, fn, *args) -> None:
        try:
            self.asyncio_loop.call_soon_threadsafe(fn, *args)
        except Exception:
            pass

    def _apply(self, snap) -> None:
        self._collecting = False
        if not self._alive or snap is None:
            return
        keep = self.snap.rows[self.sel].tab_id if self.snap.rows else None
        self.snap = snap
        self._hover_pane = (-1, -1)             # row indices changed under it
        if not snap.rows:
            self.draw_screen()
            return
        if self._first:
            self._first = False
            self.sel = next((i for i, r in enumerate(snap.rows) if r.current), 0)
        elif keep is not None:
            self.sel = next((i for i, r in enumerate(snap.rows) if r.tab_id == keep),
                            min(self.sel, len(snap.rows) - 1))
        self._clamp()
        self._request_preview(force=True)
        self.draw_screen()
        self._schedule_spin()

    # ---- spinner: redraw at frame rate only while something is working ----
    def _schedule_spin(self) -> None:
        if getattr(self, "_spin_pending", False) or not self._alive:
            return
        if any(r.status == "working" for r in self.snap.rows):
            self._spin_pending = True
            self.asyncio_loop.call_later(0.1, self._spin)

    def _spin(self) -> None:
        self._spin_pending = False
        if self._alive and any(r.status == "working" for r in self.snap.rows):
            self.draw_screen()
            self._schedule_spin()

    def _request_preview(self, force: bool = False) -> None:
        if not self.snap.rows:
            self.preview = []
            return
        r = self.snap.rows[self.sel]
        row, pane = self._hover_pane
        wid = r.pane_rows[pane].win_id if row == self.sel and 0 <= pane < len(r.pane_rows) else r.win_id
        if wid == self.preview_for and self.preview and not force:
            return
        self.preview_for = wid
        rows_n = self.screen_size.rows

        def work() -> None:
            try:
                txt = _rc("get-text", "--extent", "screen", "--match", f"id:{wid}")
            except Exception:
                txt = ""
            lines = txt.rstrip().splitlines()
            self._post(self._apply_preview, wid,
                       lines[-max(4, rows_n - 4):] if lines else ["(empty pane)"])

        threading.Thread(target=work, daemon=True).start()

    def _apply_preview(self, wid: int, lines: list) -> None:
        if self._alive and wid == self.preview_for:
            self.preview = lines
            self.draw_screen()

    def _schedule(self) -> None:
        if self._alive:
            self.asyncio_loop.call_later(_REFRESH_EVERY, self._tick)

    def _tick(self) -> None:
        if not self._alive:
            return
        self._request_refresh()
        self._schedule()

    # ---- layout -----------------------------------------------------------
    def _geom(self):
        cols, rows = self.screen_size.cols, self.screen_size.rows
        bar_w = 36 if cols >= 64 else cols
        if self._can_drag():
            bar_w = min(bar_w, cols - 1)          # the last column is the resize handle
        return cols, rows, bar_w

    def _can_drag(self) -> bool:
        return _PANEL and bool(_PANEL_SOCK) and _PANEL_EDGE == "left"

    def _avail(self) -> int:
        return max(1, self.screen_size.rows - 3)   # 2 header lines + 1 footer line

    def _clamp(self) -> None:
        n = len(self.snap.rows)
        self.sel = max(0, min(self.sel, n - 1)) if n else 0
        self.scroll = deck.ensure_visible(self.snap.items, self.scroll, self.sel, self._avail())

    # ---- drawing ----------------------------------------------------------
    def _seg(self, text, fg=None, bg=None, bold=False, dim=False) -> str:
        return styled(text, fg=_C(fg) if fg is not None else None,
                      bg=_C(bg) if bg is not None else None, bold=bold, dim=dim)

    def _line(self, parts: list, width: int, bg: int) -> str:
        """parts: [(text, fg, bold)] → exactly `width` cells with row bg."""
        out, used = "", 0
        for text, fg, bold in parts:
            room = width - used
            if room <= 0:
                break
            t = deck.fit(text, room, _cells)
            out += self._seg(t, fg=fg, bg=bg, bold=bold)
            used += _cells(t)
        if used < width:
            out += self._seg(" " * (width - used), bg=bg)
        return out

    def _row_lines(self, r, selected: bool, bar_w: int) -> tuple[str, str]:
        p = self.pal
        bg = p.surface_hi if selected else p.bar
        rail = (_RAIL, p.accent, False) if r.current else (" ", p.text, False)
        glyph_fg = kittymux_agents.AGENTS[r.agent].brand if r.agent in kittymux_agents.AGENTS else p.muted
        if r.tool:                                   # quiet tool glyph, not a brand mark
            icon = (r.glyph, p.muted if selected or r.current else p.faint, False)
        else:
            icon = (r.glyph or " ",
                    glyph_fg if selected or r.current else kittymux_theme.blend(glyph_fg, p.bg, 0.6), False)
        state_fg = {"waiting": p.waiting, "working": p.working, "limited": p.alert,
                    "done": kittymux_theme.blend(p.done, p.bg, 0.65), "unread": p.faint}.get(r.status)
        title_fg = p.text if (selected or r.current) else p.muted
        title = deck.pad(r.title or "—", bar_w - 3 - 2, _cells)
        dot = (kittymux_agents.state_glyph(r.status), state_fg, r.status in kittymux_agents.NEEDS_YOU) if state_fg is not None else (" ", p.text, False)
        line1 = self._line([rail, icon, (" ", p.text, False),
                            (title, title_fg, selected or r.current), dot, (" ", p.text, False)], bar_w, bg)

        idx = str(r.index)
        room = bar_w - 3 - 1 - len(idx) - 1
        sub_fg = p.muted if (selected or r.current) else p.faint
        parts = []
        if r.branch:
            parts.append((f"{_ICON_BRANCH} {r.branch}", sub_fg))
        elif r.cwd:
            parts.append((f"{_ICON_FOLDER} {_short_home(r.cwd)}", sub_fg))
        if r.pr:
            parts.append((r.pr, p.info))
        if r.ports:
            parts.append((" ".join(f":{n}" for n in r.ports[:3]), p.info))
        if r.panes > 1:
            parts.append((f"{r.panes} panes", p.faint))
        tail = [(r.status, state_fg)] if r.status in kittymux_agents.NEEDS_YOU else []
        if r.msg:                                   # what it is waiting for beats everything
            parts, tail = [(r.msg, state_fg)], []
        reserve = sum(_cells(t) + 2 for t, _ in tail)
        cells, used = [], 0
        for i, (text, fg) in enumerate(parts):
            sep = "  " if i else ""
            avail = room - used - reserve - _cells(sep)
            if avail <= 1:
                break
            piece = sep + deck.fit(text, avail, _cells)
            cells.append((piece, fg, False))
            used += _cells(piece)
        for text, fg in tail:
            sep = "  " if used else ""
            if room - used >= _cells(sep + text):
                cells.append((sep + text, fg, False))
                used += _cells(sep + text)
        lead = [rail if r.current else (" ", p.text, False), (" ", p.text, False), (" ", p.text, False)]
        body = self._line(lead + cells, bar_w - 1 - len(idx), bg)
        line2 = body + self._seg(idx, fg=p.faint, bg=bg) + self._seg(" ", bg=bg)
        return line1, line2

    def _pane_line(self, r, j: int, bar_w: int, hovered: bool) -> str:
        """`   ├ ◆ title ........ ⠋` — one child line of a split tab (└ on the last)."""
        p = self.pal
        pd = r.pane_rows[j]
        last = j == min(len(r.pane_rows), deck.MAX_PANE_ROWS) - 1
        bg = p.surface if hovered else p.bar
        brand = kittymux_agents.AGENTS[pd.agent].brand if pd.agent in kittymux_agents.AGENTS else p.muted
        lit = pd.active or hovered
        icon_fg = (brand if lit else kittymux_theme.blend(brand, p.bg, 0.6)) if pd.agent else (p.muted if lit else p.faint)
        state_fg = {"waiting": p.waiting, "working": p.working, "limited": p.alert,
                    "done": kittymux_theme.blend(p.done, p.bg, 0.65)}.get(pd.state)
        mark = (kittymux_agents.state_glyph(pd.state), state_fg, pd.state in kittymux_agents.NEEDS_YOU) \
            if state_fg is not None else (" ", p.text, False)
        title = deck.pad(pd.title or pd.agent or "shell", bar_w - 7 - 3, _cells)
        return self._line([("   ", p.text, False), ("└" if last else "├", p.line, False), (" ", p.text, False),
                           (pd.glyph or "·", icon_fg, False), (" ", p.text, False),
                           (title, p.text if lit else p.muted, pd.active), mark, (" ", p.text, False)], bar_w, bg)

    @Handler.atomic_update
    def draw_screen(self) -> None:
        cols, rows_n, bar_w = self._geom()
        p = self.pal
        w = self.write
        snap = self.snap
        # header: counts + hint
        waiting = sum(1 for r in snap.rows if r.status in kittymux_agents.NEEDS_YOU)
        head = [(f" {len(snap.rows)} tabs", p.text, True)]
        if waiting:
            head.append((f"  {kittymux_agents.state_glyph('waiting')} {waiting} waiting", p.waiting, True))
        w(set_cursor_position(0, 0) + self._line(head, bar_w, p.bar))
        w(set_cursor_position(0, 1) + self._line([(" " + deck.hint(bar_w - 1), p.faint, False)], bar_w, p.bar))
        # list
        avail = self._avail()
        y = 2
        blank = self._seg(" " * bar_w, bg=p.bar)
        drawn = 0
        for off, it in deck.visible(snap.items, self.scroll, avail):
            if it.kind == "header":
                col = p.accent if it.current else p.faint
                cnt = f"{it.count}  "
                w(set_cursor_position(0, y + off) + self._line(
                    [(" " + it.label.upper(), col, True)], bar_w - len(cnt), p.bar)
                    + self._seg(cnt, fg=p.faint, bg=p.bar))
                drawn = off + 1
            elif it.kind == "pane":
                w(set_cursor_position(0, y + off) + self._pane_line(
                    snap.rows[it.row], it.pane, bar_w, (it.row, it.pane) == self._hover_pane))
                drawn = off + 1
            else:
                l1, l2 = self._row_lines(snap.rows[it.row], it.row == self.sel, bar_w)
                w(set_cursor_position(0, y + off) + l1)
                w(set_cursor_position(0, y + off + 1) + l2)
                drawn = off + 2
        for yy in range(y + drawn, rows_n):
            w(set_cursor_position(0, yy) + blank)
        shown = sum(1 for _o, it in deck.visible(snap.items, self.scroll, avail) if it.kind == "row")
        hidden = sum(1 for it in snap.items[self.scroll:] if it.kind == "row") - shown
        if hidden > 0:
            w(set_cursor_position(0, rows_n - 1) + self._line(
                [(f" +{hidden} more", p.faint, False)], bar_w, p.bar))
        if not snap.rows:
            w(set_cursor_position(0, 2) + self._line([(" no tabs", p.faint, False)], bar_w, p.bar))
        # separator + preview
        if cols >= 64:
            px = bar_w + 2
            pw = cols - px - 1
            for y2 in range(rows_n):
                w(set_cursor_position(bar_w, y2) + self._seg("▕", fg=p.line, bg=p.bar))
                w(set_cursor_position(bar_w + 1, y2) + " " * (cols - bar_w - 1))
            if snap.rows:
                r = snap.rows[self.sel]
                w(set_cursor_position(px, 0) + self._seg(
                    deck.fit(f"{r.agent or 'pane'} · {_short_home(r.cwd)}", pw, _cells), fg=p.faint))
                for j, ln in enumerate(self.preview[:rows_n - 2]):
                    w(set_cursor_position(px, j + 2) + self._seg(deck.fit(ln, pw, _cells), fg=p.muted))
        if self._can_drag():                      # the drag handle: lights up on hover / while dragging
            hot = getattr(self, "_drag", False) or getattr(self, "_handle_hot", False)
            for y2 in range(rows_n):
                w(set_cursor_position(cols - 1, y2) + self._seg("▕", fg=p.accent if hot else p.line, bg=p.bar))
        self.flush()

    # ---- events -----------------------------------------------------------
    def on_key_event(self, key_event, in_bracketed_paste: bool = False) -> None:
        if key_event.type == EventType.RELEASE:   # press+release both arrive; act once
            return
        k = (key_event.key or "").upper()
        if k in ("Q", "ESCAPE"):
            if not _PANEL or k == "Q":
                self.quit_loop()
            return
        shifted = bool(key_event.mods & 1)
        n = len(self.snap.rows)
        if k in ("J", "DOWN", "TAB") and not (k == "J" and shifted):
            self.sel = deck.step_row(self.sel, 1, n)
        elif k in ("K", "UP") and not (k == "K" and shifted):
            self.sel = deck.step_row(self.sel, -1, n)
        elif k == "J" and shifted:
            self.sel = deck.step_group(self.snap.rows, self.sel, 1) if n else 0
        elif k == "K" and shifted:
            self.sel = deck.step_group(self.snap.rows, self.sel, -1) if n else 0
        elif k == "G" and not shifted:
            self.sel = 0
        elif k == "G" and shifted:
            self.sel = max(0, n - 1)
        elif k == "ENTER":
            self._jump()
            return
        else:
            return
        self._hover_pane = (-1, -1)
        self._clamp()
        self._request_preview()
        self.draw_screen()

    # ---- drag the panel's inner edge to resize it ------------------------------
    def on_mouse_event(self, mouse_event) -> None:
        if self._can_drag():
            cols = self.screen_size.cols
            over = deck.in_grab_zone(mouse_event.pixel_x // max(1, self.screen_size.cell_width), cols)
            if getattr(self, "_drag", False):
                # cell_x is clamped to the panel's own surface, so it can never say "wider";
                # the raw pixel position can (Wayland keeps delivering it during a drag)
                col = mouse_event.pixel_x // max(1, self.screen_size.cell_width)
                if mouse_event.type is MouseEventType.MOVE:
                    self._resize_panel(col)
                elif mouse_event.type is MouseEventType.RELEASE:
                    self._resize_panel(col, final=True)
                    self._drag = False
                    self.draw_screen()
                return
            if mouse_event.type is MouseEventType.PRESS and (mouse_event.buttons & MouseButton.LEFT) and over:
                self._drag = True
                self._throttle = deck.DragThrottle()
                self.draw_screen()
                return
            if mouse_event.type is MouseEventType.MOVE and over != getattr(self, "_handle_hot", False):
                self._handle_hot = over
                self.draw_screen()
        super().on_mouse_event(mouse_event)

    def _resize_panel(self, cell_x: int, final: bool = False) -> None:
        cols = deck.drag_columns(cell_x)
        if not self._throttle.should_send(time.monotonic(), cols, final):
            return
        lock = self.__dict__.setdefault("_rz_lock", threading.Lock())
        if not lock.acquire(blocking=final):          # a request is in flight: drop non-final ones
            return

        def work() -> None:
            try:
                r = subprocess.run(["kitten", "@", "--to", f"unix:{_PANEL_SOCK}", "resize-os-window",
                                    "--action=os-panel", "--incremental", f"columns={cols}"],
                                   capture_output=True, text=True, timeout=3)
                if r.returncode != 0 or os.environ.get("KITTYMUX_DEBUG"):
                    _log_line(f"panel resize to {cols} rc={r.returncode} final={final} "
                              f"out={r.stdout.strip()[:100]!r} err={r.stderr.strip()[:200]!r}")
                if final:
                    try:
                        _STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
                        (_STATE_DIR / "panel-columns").write_text(str(cols))
                    except OSError:
                        pass
            except Exception:
                _log_error()
            finally:
                lock.release()

        threading.Thread(target=work, daemon=True).start()

    def _row_at(self, y: int) -> int:
        return deck.row_at(self.snap.items, self.scroll, self._avail(), y - 2)

    def _pane_at(self, y: int) -> tuple:
        return deck.pane_at(self.snap.items, self.scroll, self._avail(), y - 2)

    def on_mouse_move(self, mouse_event) -> None:
        if mouse_event.cell_x >= self._geom()[2]:
            return
        idx = self._row_at(mouse_event.cell_y)
        hover = self._pane_at(mouse_event.cell_y) if idx < 0 else (-1, -1)
        if hover[0] >= 0:                                    # a child line: select its tab, preview THAT pane
            idx = hover[0]
        if idx >= 0 and (idx != self.sel or hover != self._hover_pane):
            self.sel, self._hover_pane = idx, hover
            self._request_preview()
            self.draw_screen()

    def on_click(self, mouse_event) -> None:
        if mouse_event.cell_x >= self._geom()[2]:
            return
        row, pane = self._pane_at(mouse_event.cell_y)
        if row >= 0:
            self._jump(row, pane)
        elif self._row_at(mouse_event.cell_y) == self.sel:
            self._jump()

    def on_resize(self, new_size) -> None:
        self.screen_size = new_size
        self._clamp()
        self.draw_screen()

    def _jump(self, row: int = -1, pane: int = -1) -> None:
        if not self.snap.rows:
            return
        r = self.snap.rows[self.sel if row < 0 else row]
        win = r.pane_rows[pane].win_id if 0 <= pane < len(r.pane_rows) else r.win_id
        _rc("focus-tab", "--match", f"id:{r.tab_id}")
        if win:
            _rc("focus-window", "--match", f"id:{win}")
        if not _PANEL:
            self.quit_loop()
        else:
            self._request_refresh()


def _append_log(text: str) -> None:
    """Append to the error log, never letting it grow past 64 KB."""
    _STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    if _ERR_LOG.exists() and _ERR_LOG.stat().st_size > 64 * 1024:
        _ERR_LOG.write_text("")
    fd = os.open(_ERR_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(text)


def _log_line(text: str) -> None:
    try:
        _append_log(text + "\n")
    except Exception:
        pass


def _log_error() -> None:
    import traceback
    try:
        _append_log(traceback.format_exc())
    except Exception:
        pass


@kitten_ui(allow_remote_control=not _PANEL)   # panel mode talks to _TARGET over its socket
def main(args: list[str]) -> str:
    loop = Loop()
    handler = Sidebar()
    try:
        loop.loop(handler)
    except Exception:
        _log_error()
        raise
    return ""


@result_handler()
def handle_result(args: list[str], answer: str, target_window_id: int, boss: BossType) -> None:
    pass
