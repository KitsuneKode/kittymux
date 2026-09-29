# kittymux sidebar — a cmux-style command deck for kitty.
# Bound as: map ctrl+alt+b kitten <this file>
# Real mouse hover + click via kittens.tui (MouseTracking.full); tab/pane data
# and jumps go through the kitten's fd-based remote-control channel.

import json
import os
import subprocess
import time
from pathlib import Path

from kittens.tui.handler import Handler, kitten_ui, result_handler
from kittens.tui.loop import Loop
from kittens.tui.operations import (
    MouseTracking, repeat, set_cursor_position, styled,
)
from kitty.rgb import Color
from kitty.typing_compat import BossType


def _C(rgb: int) -> Color:
    return Color(rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255)

_CONFIG_DIR = os.environ.get("KITTY_CONFIG_DIRECTORY", str(Path.home() / ".config" / "kitty"))
_STATE_DIR = Path(os.environ["KITTYMUX_STATE"]) if os.environ.get("KITTYMUX_STATE") else \
    Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "kittymux"

# Brand palette shared with tab_bar.py's provider table.
_GLYPHS = {
    "claude": "\ue0d8", "codex": "\ue0d9", "cursor-agent": "\ue0da",
    "cursor": "\ue0da", "gemini": "\ue0db", "opencode": "\ue0dc",
    "amp": "\ue0dd", "devin": "\ue0de", "aider": "\U0001f4dd",
    "crush": "\u2764", "grok": "\u2573",
}
_BRANDS = {
    "claude": _C(0xd97757), "codex": _C(0x10a37f), "cursor-agent": _C(0x5b8ef4),
    "cursor": _C(0x5b8ef4), "gemini": _C(0x4e8cff), "opencode": _C(0xfab283),
    "amp": _C(0xf5c2e7), "devin": _C(0x8b5cf6), "aider": _C(0xa6e3a1),
    "crush": _C(0xf38ba8), "grok": _C(0xf9e2af),
}

_MAUVE = _C(0xcba6f7)      # active text
_TEXT = _C(0xcdd6f4)
_DIM = _C(0x9399b2)        # subtitle / preview
_FAINT = _C(0x6c7086)
_ROW_BG = _C(0x313244)     # selected row fill
_EDGE = _C(0x45475a)
_SKY = _C(0x89dceb)        # working
_INDIGO = _C(0xb4befe)     # waiting / input needed
_EMERALD = _C(0xa6e3a1)    # unread output
_GIT = "\uf126"         # nerd-font git-branch
_STALE_AFTER = 15.0
_GENERIC = {"kitty", "zsh", "bash", "fish", "sh"}


def _rc(*args: str) -> str:
    """Synchronous remote control over the kitten's fd channel."""
    p = main.remote_control(list(args), capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def _panes_state() -> dict:
    try:
        return json.loads((_STATE_DIR / f"panes-{os.getppid()}.json").read_text())
    except Exception:
        return {}


def _git_branch(cwd: str) -> str:
    try:
        p = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=0.4)
        b = p.stdout.strip()
        return "" if b == "HEAD" else b
    except Exception:
        return ""


def _agent_of(fg_procs: list) -> tuple[str, str] | None:
    for proc in fg_procs or []:
        for arg in proc.get("cmdline") or []:
            name = os.path.basename(arg).lower()
            if name in _GLYPHS:
                return _GLYPHS[name], name
    return None


def _short_home(p: str) -> str:
    return "~" + p[len(os.path.expanduser("~")):] if p.startswith(os.path.expanduser("~")) else p


class Row:
    __slots__ = ("tab_id", "win_id", "title", "glyph", "agent", "branch",
                 "panes", "status", "unread", "focused", "cwd")

    def __init__(self, tab: dict, panes_state: dict):
        self.tab_id = tab["id"]
        self.title = tab.get("title") or ""
        # Overlay/kitten windows (kitty +runpy cmdline) are chrome, not content —
        # exclude them from pane counts and preview targets.
        wins = [w for w in tab.get("windows") or []
                if "kittens.runner" not in str(w.get("cmdline"))]
        hist = [i for i in tab.get("active_window_history") or []
                if any(w["id"] == i for w in wins)]
        aw_id = hist[0] if hist else (wins[0]["id"] if wins else 0)
        aw = next((w for w in wins if w["id"] == aw_id), wins[0] if wins else {})
        self.win_id = aw.get("id", 0)
        self.panes = len(wins)
        self.cwd = aw.get("cwd", "")
        agent = _agent_of(aw.get("foreground_processes"))
        self.glyph, self.agent = agent if agent else ("", "")
        self.branch = _git_branch(self.cwd) if self.cwd else ""
        st = panes_state.get(str(self.win_id)) or {}
        ts = float(st.get("ts_title") or 0)
        quiet = bool(ts) and (time.monotonic() - ts) > _STALE_AFTER
        self.focused = bool(aw.get("is_focused"))
        self.unread = bool(tab.get("needs_attention") or aw.get("has_activity"))
        self.status = "waiting" if (self.agent and quiet) else ("working" if self.agent else "")


class Sidebar(Handler):
    mouse_tracking = MouseTracking.full

    def initialize(self) -> None:
        self.rows: list[Row] = []
        self.sel = 0
        self.offset = 0
        self.preview: list[str] = []
        self.preview_for = 0
        self._alive = True
        self._panes_state: dict = {}
        self.refresh_data(select_active=True)
        self.draw_screen()
        self._schedule()

    def finalize(self) -> None:
        self._alive = False

    # ---- data -------------------------------------------------------------
    def refresh_data(self, select_active: bool = False) -> None:
        try:
            data = json.loads(_rc("ls"))
        except Exception:
            return
        tabs = [t for w in data for t in w.get("tabs", [])]
        self._panes_state = _panes_state()
        keep = self.rows[self.sel].tab_id if self.rows else None
        self.rows = [Row(t, self._panes_state) for t in tabs]
        if not self.rows:
            return
        if select_active:
            self.sel = next((i for i, r in enumerate(self.rows) if r.focused), 0)
        elif keep is not None:
            self.sel = next((i for i, r in enumerate(self.rows) if r.tab_id == keep),
                            min(self.sel, len(self.rows) - 1))
        self._clamp()
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if not self.rows:
            self.preview = []
            return
        wid = self.rows[self.sel].win_id
        if wid == self.preview_for and self.preview:
            return
        self.preview_for = wid
        txt = _rc("get-text", "--extent", "screen", "--match", f"id:{wid}")
        lines = txt.splitlines()
        self.preview = lines[-max(4, self.screen_size.rows - 4):] if lines else ["(empty pane)"]

    def _schedule(self) -> None:
        if self._alive:
            self.asyncio_loop.call_later(1.5, self._tick)

    def _tick(self) -> None:
        if not self._alive:
            return
        keep_wid = self.rows[self.sel].win_id if self.rows else 0
        self.refresh_data()
        # Periodic refresh may keep the same row — refresh preview anyway so
        # the pane tail feels live.
        self.preview_for = 0
        self._refresh_preview()
        self.draw_screen()
        self._schedule()

    def _clamp(self) -> None:
        self.sel = max(0, min(self.sel, len(self.rows) - 1))
        per = max(1, (self.screen_size.rows - 2) // 2)
        if self.sel < self.offset:
            self.offset = self.sel
        elif self.sel >= self.offset + per:
            self.offset = self.sel - per + 1

    # ---- layout ------------------------------------------------------------
    def _geom(self):
        cols, rows = self.screen_size.cols, self.screen_size.rows
        bar_w = 36 if cols >= 64 else cols
        return cols, rows, bar_w

    # ---- drawing -----------------------------------------------------------
    @Handler.atomic_update
    def draw_screen(self) -> None:
        cols, rows_n, bar_w = self._geom()
        w = self.write
        w(set_cursor_position(0, 0))
        # Header
        waiting = sum(1 for r in self.rows if r.status == "waiting")
        head = f" tabs · {len(self.rows)}"
        if waiting:
            head += styled(f"  ! {waiting} waiting", fg=_INDIGO, bold=True)
        w(styled(head.ljust(bar_w)[:bar_w], fg=_MAUVE, bold=True))
        w(set_cursor_position(0, 1))
        w(styled(" j/k move · ⏎ jump · click to go · q quit".ljust(bar_w)[:bar_w],
                 fg=_FAINT, dim=True))
        # Rows
        per = max(1, (rows_n - 2) // 2)
        vis = self.rows[self.offset:self.offset + per]
        y = 2
        for i, r in enumerate(vis):
            idx = self.offset + i
            selected = idx == self.sel
            bg = _ROW_BG if selected else None
            w(set_cursor_position(0, y))
            edge = styled("▌", fg=_MAUVE) if r.focused else styled(" ", bg=bg)
            icon = styled(r.glyph or " ", fg=_BRANDS.get(r.agent, _DIM) if r.glyph else None)
            title = f" {idx + 1}:{r.title}"
            title_w = bar_w - 6 - (3 if r.status == "waiting" else 0)
            mark = styled("●", fg=_EMERALD) if r.unread else " "
            wait = styled(" !", fg=_INDIGO, bold=True) if r.status == "waiting" else ""
            line = edge + icon + styled(f"{title:<{title_w}.{title_w}s}",
                                        fg=_TEXT if selected else _DIM,
                                        bold=selected or r.focused, bg=bg) + mark + wait
            w(line + (styled(repeat(" ", bar_w), bg=bg) if bg else ""))
            w(set_cursor_position(0, y + 1))
            sub = ""
            if r.branch:
                sub = f"{_GIT} {r.branch}"
            if r.panes > 1:
                sub += ("  " if sub else "") + f"{r.panes} panes"
            if r.status:
                sub += ("  " if sub else "") + r.status
            st_fg = _INDIGO if r.status == "waiting" else (_SKY if r.status == "working" else _FAINT)
            w(styled(f"    {sub:<{bar_w - 4}.{bar_w - 4}s}", fg=st_fg, dim=not selected, bg=bg))
            y += 2
        if self.offset + per < len(self.rows):
            w(set_cursor_position(0, rows_n - 1))
            w(styled(f" +{len(self.rows) - self.offset - per} more", fg=_FAINT, dim=True))
        # Preview pane
        if cols >= 64:
            px = bar_w + 1
            pw = cols - px - 1
            for y2 in range(rows_n):
                w(set_cursor_position(px - 1, y2))
                w(styled("│", fg=_EDGE))
            r = self.rows[self.sel] if self.rows else None
            if r:
                w(set_cursor_position(px, 0))
                w(styled(f" {r.agent or 'pane'} · {_short_home(r.cwd)}",
                         fg=_FAINT, dim=True))
                for j, ln in enumerate(self.preview[:rows_n - 2]):
                    w(set_cursor_position(px, j + 2))
                    w(styled(ln[:pw], fg=_DIM))
        self.flush()

    # ---- events -------------------------------------------------------------
    def on_key_event(self, key_event, in_bracketed_paste: bool = False) -> None:
        k = (key_event.key or "").upper()
        if k in ("Q", "ESCAPE"):
            self.quit_loop()
            return
        shifted = bool(key_event.mods & 1)
        if k in ("J", "DOWN", "TAB"):
            self.sel = min(self.sel + 1, len(self.rows) - 1)
        elif k in ("K", "UP"):
            self.sel = max(self.sel - 1, 0)
        elif k == "G" and not shifted:
            self.sel = 0
        elif k == "G" and shifted:
            self.sel = len(self.rows) - 1
        elif k == "ENTER":
            self._jump()
            return
        else:
            return
        self._clamp()
        self._refresh_preview()
        self.draw_screen()

    def _row_at(self, y: int) -> int:
        if y < 2:
            return -1
        idx = self.offset + (y - 2) // 2
        return idx if 0 <= idx < len(self.rows) else -1

    def on_mouse_move(self, mouse_event) -> None:
        idx = self._row_at(mouse_event.cell_y)
        if idx >= 0 and idx != self.sel and mouse_event.cell_x < self._geom()[2]:
            self.sel = idx
            self._refresh_preview()
            self.draw_screen()

    def on_click(self, mouse_event) -> None:
        if mouse_event.cell_x < self._geom()[2] and self._row_at(mouse_event.cell_y) == self.sel:
            self._jump()

    def on_resize(self, new_size) -> None:
        self.screen_size = new_size
        self.draw_screen()

    def _jump(self) -> None:
        if not self.rows:
            return
        r = self.rows[self.sel]
        _rc("focus-tab", "--match", f"id:{r.tab_id}")
        if r.win_id:
            _rc("focus-window", "--match", f"id:{r.win_id}")
        self.quit_loop()


@kitten_ui(allow_remote_control=True)
def main(args: list[str]) -> str:
    loop = Loop()
    handler = Sidebar()
    try:
        loop.loop(handler)
    except Exception:
        import traceback
        with open("/tmp/sidebar-kit-err.log", "a") as f:
            f.write(traceback.format_exc())
        raise
    return ""


@result_handler()
def handle_result(args: list[str], answer: str, target_window_id: int, boss: BossType) -> None:
    pass
