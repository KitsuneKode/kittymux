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
import subprocess
import sys
import threading
import time
from pathlib import Path

from kittens.tui.handler import Handler, kitten_ui, result_handler
from kittens.tui.loop import Loop
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
import kittymux_theme  # noqa: E402

_STATE_DIR = Path(os.environ["KITTYMUX_STATE"]) if os.environ.get("KITTYMUX_STATE") else \
    Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "kittymux"
_ERR_LOG = _STATE_DIR / "sidebar-kit-err.log"

_ICON_BRANCH = ""
_ICON_FOLDER = ""
_RAIL = "▌"
_DOT = "●"
_STALE_AFTER = 15.0
_GIT_TTL = 5.0
_REFRESH_EVERY = 1.5


def _C(rgb: int) -> Color:
    return Color(rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255)


def _cells(s: str) -> int:
    return max(0, wcswidth(s))


def _rc(*args: str) -> str:
    """Synchronous remote control over the kitten's fd channel."""
    p = main.remote_control(list(args), capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def _panes_state() -> dict:
    try:
        return json.loads((_STATE_DIR / f"panes-{os.getppid()}.json").read_text())
    except Exception:
        return {}


def _short_home(p: str) -> str:
    home = os.path.expanduser("~")
    return "~" + p[len(home):] if p.startswith(home) else p


class Snapshot:
    __slots__ = ("rows", "items", "current_session")

    def __init__(self, rows: list, current_session: str):
        groups = deck.group_rows(rows, current_session)
        self.items, self.rows = deck.flatten(groups, current_session)
        self.current_session = current_session


class Collector:
    """Builds a Snapshot from `kitty @ ls`. Runs on a worker thread only."""

    def __init__(self):
        self._git: dict[str, tuple[float, str]] = {}

    def branch(self, cwd: str) -> str:
        now = time.monotonic()
        hit = self._git.get(cwd)
        if hit and now - hit[0] < _GIT_TTL:
            return hit[1]
        b = ""
        try:
            p = subprocess.run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
                               capture_output=True, text=True, timeout=0.4)
            b = p.stdout.strip() if p.returncode == 0 else ""
            b = "" if b == "HEAD" else b
        except Exception:
            pass
        self._git[cwd] = (now, b)
        return b

    def collect(self) -> Snapshot | None:
        try:
            data = json.loads(_rc("ls"))
        except Exception:
            return None
        panes = _panes_state()
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
                name = None
                for proc in aw.get("foreground_processes") or []:
                    name = kittymux_agents.agent_in(proc.get("cmdline") or [])
                    if name:
                        break
                agent = kittymux_agents.AGENTS.get(name) if name else None
                st = panes.get(str(aw["id"])) or {}
                ts = float(st.get("ts_title") or 0)
                quiet = bool(ts) and (time.monotonic() - ts) > _STALE_AFTER
                unread = bool(tab.get("needs_attention") or aw.get("needs_attention")
                              or aw.get("has_activity_since_last_focus"))
                status = ("waiting" if quiet else "working") if agent else ("done" if unread else "")
                current = bool(osw.get("is_focused") and tab.get("is_active"))
                session = aw.get("session_name", "") or ""
                if current:
                    current_session = session
                rows.append(deck.RowData(
                    tab_id=tab["id"], win_id=aw["id"], session=session,
                    title=tab.get("title") or "", glyph=agent.glyph if agent else "",
                    agent=name or "", branch=self.branch(cwd) if cwd else "", cwd=cwd,
                    panes=len(wins), status=status, unread=unread, current=current))
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

    def _request_preview(self, force: bool = False) -> None:
        if not self.snap.rows:
            self.preview = []
            return
        wid = self.snap.rows[self.sel].win_id
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
        return cols, rows, bar_w

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
        icon = (r.glyph or " ",
                glyph_fg if selected or r.current else kittymux_theme.blend(glyph_fg, p.bg, 0.6), False)
        state_fg = {"waiting": p.waiting, "working": p.working, "done": p.done}.get(r.status)
        title_fg = p.text if (selected or r.current) else p.muted
        title = deck.pad(r.title or "—", bar_w - 3 - 2, _cells)
        dot = (_DOT, state_fg, False) if state_fg is not None else (" ", p.text, False)
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
        if r.panes > 1:
            parts.append((f"{r.panes} panes", p.faint))
        tail = [(r.status, state_fg)] if r.status in ("working", "waiting") else []
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

    @Handler.atomic_update
    def draw_screen(self) -> None:
        cols, rows_n, bar_w = self._geom()
        p = self.pal
        w = self.write
        snap = self.snap
        # header: counts + hint
        waiting = sum(1 for r in snap.rows if r.status == "waiting")
        head = [(f" {len(snap.rows)} tabs", p.text, True)]
        if waiting:
            head.append((f"  ! {waiting} waiting", p.waiting, True))
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
        self.flush()

    # ---- events -----------------------------------------------------------
    def on_key_event(self, key_event, in_bracketed_paste: bool = False) -> None:
        if key_event.type == EventType.RELEASE:   # press+release both arrive; act once
            return
        k = (key_event.key or "").upper()
        if k in ("Q", "ESCAPE"):
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
        self._clamp()
        self._request_preview()
        self.draw_screen()

    def _row_at(self, y: int) -> int:
        return deck.row_at(self.snap.items, self.scroll, self._avail(), y - 2)

    def on_mouse_move(self, mouse_event) -> None:
        idx = self._row_at(mouse_event.cell_y)
        if idx >= 0 and idx != self.sel and mouse_event.cell_x < self._geom()[2]:
            self.sel = idx
            self._request_preview()
            self.draw_screen()

    def on_click(self, mouse_event) -> None:
        if mouse_event.cell_x < self._geom()[2] and self._row_at(mouse_event.cell_y) == self.sel:
            self._jump()

    def on_resize(self, new_size) -> None:
        self.screen_size = new_size
        self._clamp()
        self.draw_screen()

    def _jump(self) -> None:
        if not self.snap.rows:
            return
        r = self.snap.rows[self.sel]
        _rc("focus-tab", "--match", f"id:{r.tab_id}")
        if r.win_id:
            _rc("focus-window", "--match", f"id:{r.win_id}")
        self.quit_loop()


def _log_error() -> None:
    import traceback
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(_ERR_LOG, "a") as f:
            f.write(traceback.format_exc())
    except Exception:
        pass


@kitten_ui(allow_remote_control=True)
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
