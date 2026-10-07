# kittymux command palette (ctrl+alt+shift+space): one searchable list of what needs you, every tab, agents you can reopen or start, and a few actions.
#
#   kitten palette-kit.py
#
# Type to filter · ↑ ↓ (ctrl+n / ctrl+p, Page Up / Page Down) choose · Enter does it · a click does it · Esc clears the filter, then closes.
#
# This kitten only CHOOSES. It hands the chosen action to `kittymux act` (handle_result, after the overlay is gone, so a focus change is not undone by the
# overlay closing), which validates it again and does it: focus a tab, jump to an agent, reopen a conversation, start an agent, or run one of a few fixed commands.
# The list is drawn by the shared kit (kittymux_ui) from the live theme; what to list and how to rank it is kittymux_palette (pure, tested).

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from kittens.tui.handler import Handler, kitten_ui, result_handler
from kittens.tui.loop import Loop, MouseButton
from kittens.tui.operations import MouseTracking, set_cursor_position, styled
from kitty.fast_data_types import wcswidth
from kitty.key_encoding import EventType
from kitty.rgb import Color
from kitty.typing_compat import BossType

_CONFIG_DIR = os.environ.get("KITTY_CONFIG_DIRECTORY", str(Path.home() / ".config" / "kitty"))
for _d in (_CONFIG_DIR, os.path.dirname(os.path.realpath(sys.argv[0])) if sys.argv and sys.argv[0] else ""):
    if _d and _d not in sys.path:
        sys.path.insert(0, _d)
import kittymux_agents  # noqa: E402
import kittymux_deck  # noqa: E402
import kittymux_palette as P  # noqa: E402
import kittymux_theme  # noqa: E402
import kittymux_ui as U  # noqa: E402

_STATE_DIR = Path(os.environ["KITTYMUX_STATE"]) if os.environ.get("KITTYMUX_STATE") else \
    Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "kittymux"
_STALE_AFTER = 15.0
_WIDTH_MAX = 84
_TOP = 3                          # rows above the list: padding, the search field, a gap
_BOTTOM = P.PREVIEW_ROWS + 2      # rows under the list: the preview, a rule, the keycaps


def _C(rgb: int) -> Color:
    return Color(rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255)


def _cells(s: str) -> int:
    return max(0, wcswidth(s))


def _rc(*args: str) -> str:
    p = main.remote_control(list(args), capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def _own_window_id() -> int:
    try:
        return int(os.environ.get("KITTY_WINDOW_ID", "0"))
    except ValueError:
        return 0


def _root() -> Path:
    """The checkout (or install) the modules came from: kittens are exec'd, so anchor on a module that WAS imported."""
    return Path(os.path.realpath(kittymux_deck.__file__)).parent.parent


def collect_tabs() -> list:
    try:
        data = json.loads(_rc("ls"))
    except Exception:
        return []
    panes = kittymux_agents.load_panes(str(_STATE_DIR / f"panes-{os.getppid()}.json"))
    return P.tabs_from_ls(data, panes, _own_window_id(), time.monotonic(), _STALE_AFTER)


def collect_rows() -> list:
    """`kittymux pick --json`: the rows `pick` would show (events, closed conversations, new agents), computed by the one place that knows how."""
    try:
        r = subprocess.run([str(_root() / "bin" / "kittymux"), "pick", "--json"], capture_output=True, text=True, timeout=8, stdin=subprocess.DEVNULL)
        rows = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
    except (OSError, ValueError, subprocess.SubprocessError):
        rows = []
    return rows if isinstance(rows, list) else []


class Palette(Handler):
    mouse_tracking = MouseTracking.full                 # hover moves the pick, a left click does it

    def __init__(self):
        super().__init__()
        self.cur = P.Cursor()
        self.tabs: list = []
        self.rows: list = []
        self.items: list = []
        self.shown: list = []
        self.hits: list = []
        self.scroll = 0
        self.result = ""
        self._alive = True
        self._loading = 2

    def initialize(self) -> None:
        self.pal = kittymux_theme.from_colors(kittymux_theme.parse_kitty_colors(_rc("get-colors", "--configured")))
        self.kit = U.Kit(self.pal, cells=_cells)
        self._rebuild()

        def fetch(fn, apply) -> None:
            data = fn()
            try:
                self.asyncio_loop.call_soon_threadsafe(apply, data)
            except Exception:
                pass
        threading.Thread(target=fetch, args=(collect_tabs, self._got_tabs), daemon=True).start()
        threading.Thread(target=fetch, args=(collect_rows, self._got_rows), daemon=True).start()
        self.draw_screen()

    def finalize(self) -> None:
        self._alive = False

    def _got_tabs(self, tabs) -> None:
        if self._alive:
            self.tabs, self._loading = tabs, self._loading - 1
            self._rebuild()

    def _got_rows(self, rows) -> None:
        if self._alive:
            self.rows, self._loading = rows, self._loading - 1
            self._rebuild()

    def _rebuild(self) -> None:
        self.items = P.build(self.tabs, self.rows)
        self.shown = P.filter_items(self.items, self.cur.query)
        self.cur.count = len(self.shown)
        self.cur.index = min(self.cur.index, max(0, len(self.shown) - 1))
        self.draw_screen()

    # ---- drawing ------------------------------------------------------------
    def _ansi(self, line) -> str:
        return "".join(styled(s.text, fg=_C(s.fg) if s.fg is not None else None, bg=_C(s.bg) if s.bg is not None else None, bold=s.bold, dim=s.dim) for s in line)

    @Handler.atomic_update
    def draw_screen(self) -> None:
        cols, rows_h = self.screen_size.cols, self.screen_size.rows
        p, kit, w = self.pal, self.kit, self.write
        width = min(cols, _WIDTH_MAX)
        x0 = (cols - width) // 2
        blank = self._ansi(kit.blank(cols, p.bar))
        for y in range(rows_h):
            w(set_cursor_position(0, y) + blank)
        field_bg = p.card
        query = self.cur.query
        count = f"{len(self.shown)} " if (query or self._loading <= 0) else "… "
        field = [U.S("  ⌕  ", kit.ink(p.accent, field_bg), field_bg, bold=True),
                 U.S(query if query else "search tabs, agents and actions", kit.ink(p.text if query else p.faint, field_bg, 3.0), field_bg),
                 U.S("▏" if query else "", kit.ink(p.accent, field_bg), field_bg)]
        right = [U.S(count, kit.ink(p.muted, field_bg), field_bg)]
        for i, line in enumerate(kit.card([self._row(field, right, width - 4, field_bg)], width, on=p.bar)):
            w(set_cursor_position(x0, i) + self._ansi(line))
        room = max(1, rows_h - _TOP - _BOTTOM)
        v = P.view(self.items, query, self.cur.index, self.scroll, width, room, kit)
        self.scroll, self.hits = v.scroll, v.hits
        for y, line in enumerate(v.lines):
            w(set_cursor_position(x0, _TOP + y) + self._ansi(line))
        top = rows_h - _BOTTOM + 1
        w(set_cursor_position(x0, top - 1) + self._ansi(kit.rule(width, p.bar)))
        for y, line in enumerate(v.preview):
            w(set_cursor_position(x0, top + y) + self._ansi(line))
        keys = [("⏎", "go"), ("↑↓", "choose"), ("esc", "clear / close")]
        w(set_cursor_position(x0, rows_h - 1) + self._ansi(kit.keycaps(keys, width)))
        self.flush()

    def _row(self, left, right, width, bg):
        lw, rw = U.line_cells(left, _cells), U.line_cells(right, _cells)
        return self.kit.fit_line(left + [U.S(" " * max(0, width - lw - rw), None, bg)] + right, width, bg)

    # ---- events --------------------------------------------------------------
    def _choose(self, index: int | None = None) -> None:
        i = self.cur.index if index is None else index
        if 0 <= i < len(self.shown) and self.shown[i].get("action"):
            self.result = json.dumps(self.shown[i]["action"])
            self.quit_loop()

    def _typed(self) -> None:
        self.shown = P.filter_items(self.items, self.cur.query)
        self.cur.count = len(self.shown)
        self.scroll = 0
        self.draw_screen()

    def on_text(self, text: str, in_bracketed_paste: bool = False) -> None:
        if text and text.isprintable():
            self.cur.type(text)
            self._typed()

    def on_key_event(self, key_event, in_bracketed_paste: bool = False) -> None:
        if key_event.type == EventType.RELEASE:
            return
        k = (key_event.key or "").upper()
        mods = key_event.mods or 0
        ctrl = bool(mods & 4)
        if k == "ESCAPE":
            if self.cur.query:
                self.cur.clear()
                self._typed()
            else:
                self.quit_loop()
        elif k == "ENTER":
            self._choose()
        elif k == "DOWN" or (ctrl and k == "N") or (ctrl and k == "J"):
            self.cur.move(1)
            self.draw_screen()
        elif k == "UP" or (ctrl and k == "P") or (ctrl and k == "K"):
            self.cur.move(-1)
            self.draw_screen()
        elif k == "PAGE_DOWN":
            self.cur.move(8)
            self.draw_screen()
        elif k == "PAGE_UP":
            self.cur.move(-8)
            self.draw_screen()
        elif ctrl and k == "U":
            self.cur.clear()
            self._typed()
        elif ctrl and k == "C":
            self.quit_loop()
        elif k == "BACKSPACE":
            self.cur.backspace()
            self._typed()
        elif not ctrl and (key_event.text or (len(key_event.key or "") == 1 and not (mods & ~1))):
            self.on_text(key_event.text or key_event.key)

    def _row_at(self, mouse_event) -> int:
        x0 = (self.screen_size.cols - min(self.screen_size.cols, _WIDTH_MAX)) // 2
        y = mouse_event.cell_y - _TOP
        if mouse_event.cell_x < x0 or mouse_event.cell_x >= x0 + min(self.screen_size.cols, _WIDTH_MAX):
            return -1
        return next((i for hy, i in self.hits if hy == y), -1)

    def on_mouse_move(self, mouse_event) -> None:
        i = self._row_at(mouse_event)
        if i >= 0 and i != self.cur.index:
            self.cur.index = i
            self.draw_screen()

    def on_click(self, mouse_event) -> None:
        if mouse_event.buttons & MouseButton.LEFT:       # a right or middle click does nothing
            i = self._row_at(mouse_event)
            if i >= 0:
                self._choose(i)

    def on_resize(self, new_size) -> None:
        self.screen_size = new_size
        self.draw_screen()


@kitten_ui(allow_remote_control=True)
def main(args: list[str]) -> str:
    ui = Palette()
    Loop().loop(ui)
    return ui.result


@result_handler()
def handle_result(args: list[str], answer: str, target_window_id: int, boss: BossType) -> None:
    """Runs in kitty after the overlay is gone. `kittymux act` re-validates the action; it is started FROM kitty (a background process whose parent is kitty), which is how
    the CLI knows which kitty it belongs to, and with the window the palette was open over, which `join` needs."""
    try:
        action = json.loads(answer) if answer else None
    except ValueError:
        action = None
    if not isinstance(action, dict):
        return
    cmd = [str(Path(os.path.realpath(kittymux_deck.__file__)).parent.parent / "bin" / "kittymux"), "act", json.dumps(action)]
    try:
        boss.run_background_process(cmd, env={"KITTY_WINDOW_ID": str(target_window_id)})
    except Exception:
        import traceback
        traceback.print_exc()
