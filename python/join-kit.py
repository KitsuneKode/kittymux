# kittymux join — move this tab's panes into another tab as splits (ctrl+alt+shift+j), keeping their shape.
#
#   kitten join-kit.py                       pick the target tab in a list
#   kitten join-kit.py --to TAB [--side right|below|left|above|auto] [--pane]        no UI: for scripts and tests (`kittymux join`)
#
# In the picker: type to filter · ↑ ↓ (ctrl+n / ctrl+p) choose · Enter joins · Tab cycles where the first pane goes (auto → right → below) ·
# ctrl+t toggles "the whole tab" / "only this pane" · a click joins that row · Esc clears the filter, then closes.
#
# The picking runs in this kitten's own process; the MOVING runs in kitty (handle_result): the placement is planned by kittymux_join, and each
# window goes through kitty's own Tab.detach_window → Tab.attach_windows(next_to=, horizontal=, after=) — the calls its drag-and-drop uses.

import json
import os
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
import kittymux_git  # noqa: E402
import kittymux_join as J  # noqa: E402
import kittymux_place  # noqa: E402
import kittymux_theme  # noqa: E402

_STATE_DIR = Path(os.environ["KITTYMUX_STATE"]) if os.environ.get("KITTYMUX_STATE") else \
    Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "kittymux"
_STALE_AFTER = 15.0
_ICON_FOLDER = ""
_ICON_BRANCH = ""
_LIST_ROWS_RESERVED = 6          # header, rule, rule, footer, blank lines


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


def collect() -> tuple[list[dict], dict | None]:
    """(every tab of this kitty as picker rows' raw data, the tab being moved or None). The kitten's own overlay is not counted as a pane."""
    try:
        data = json.loads(_rc("ls"))
    except Exception:
        return [], None
    me = _own_window_id()
    panes = kittymux_agents.load_panes(str(_STATE_DIR / f"panes-{os.getppid()}.json"))
    now = time.monotonic()
    tabs, source = [], None
    for os_window in data:
        for tab in os_window.get("tabs", []):
            wins = [w for w in tab.get("windows") or [] if "kittens.runner" not in str(w.get("cmdline"))]
            is_source = any(w["id"] == me for w in tab.get("windows") or [])
            if not wins:
                continue
            hist = [i for i in tab.get("active_window_history") or [] if any(w["id"] == i for w in wins)]
            aw = next((w for w in wins if w["id"] == (hist[0] if hist else wins[0]["id"])), wins[0])
            name, _tool = kittymux_agents.identify(aw)
            state, _why = kittymux_agents.tab_verdict(panes, [w["id"] for w in wins], aw["id"], name is not None, now, _STALE_AFTER)
            title = kittymux_place.clean(kittymux_agents.strip_title_prefix(tab.get("title") or aw.get("title") or ""))
            row = {"os": os_window["id"], "id": tab["id"], "title": title or "—", "cwd": aw.get("cwd", ""), "panes": len(wins),
                   "state": state if state in kittymux_agents.NEEDS_YOU or state in ("working", "done") else ""}
            tabs.append(row)
            if is_source:
                source = row
    return tabs, source


def parse_args(args: list[str]) -> dict:
    out = {"to": None, "side": "auto", "scope": "tab"}
    it = iter(args)
    for a in it:
        if a == "--to":
            try:
                out["to"] = int(next(it))
            except (StopIteration, ValueError):
                out["to"] = -1
        elif a == "--side":
            out["side"] = next(it, "auto")
        elif a == "--pane":
            out["scope"] = "pane"
    return out


class Join(Handler):
    mouse_tracking = MouseTracking.full                 # hover moves the selection, a left click joins

    def __init__(self):
        super().__init__()
        self.pick = J.Picker()
        self.all_rows: list[dict] = []
        self.rows: list[dict] = []
        self.source: dict | None = None
        self.loaded = False
        self.result = ""
        self.scroll = 0
        self._alive = True

    def initialize(self) -> None:
        self.pal = kittymux_theme.from_colors(kittymux_theme.parse_kitty_colors(_rc("get-colors", "--configured")))

        def work() -> None:
            tabs, source = collect()
            try:
                self.asyncio_loop.call_soon_threadsafe(self._apply, tabs, source)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()
        self.draw_screen()

    def finalize(self) -> None:
        self._alive = False

    def _apply(self, tabs: list[dict], source: dict | None) -> None:
        if not self._alive:
            return
        self.source = source
        self.all_rows = J.rows(tabs, source["id"] if source else -1)
        self.loaded = True
        self._refilter()

    def _refilter(self) -> None:
        self.rows = J.filter_rows(self.all_rows, self.pick.query)
        self.pick.n_rows = len(self.rows)
        self.pick.index = min(self.pick.index, max(0, len(self.rows) - 1))
        self.draw_screen()

    # ---- drawing ------------------------------------------------------------
    def _seg(self, text, fg=None, bg=None, bold=False) -> str:
        return styled(text, fg=_C(fg) if fg is not None else None, bg=_C(bg) if bg is not None else None, bold=bold)

    def _line(self, parts: list, width: int, bg: int) -> str:
        out, used = "", 0
        for text, fg, bold in parts:
            room = width - used
            if room <= 0 or (room < 6 and _cells(text) > room):          # a sliver of a label says nothing: leave it out
                break
            if _cells(text) > room:
                text = kittymux_place.mid_ellipsis(text, room, _cells)
            out += self._seg(text, fg=fg, bg=bg, bold=bold)
            used += _cells(text)
        return out + (self._seg(" " * (width - used), bg=bg) if used < width else "")

    def _row_parts(self, r: dict, selected: bool, width: int) -> list:
        p = self.pal
        state_fg = {"waiting": p.waiting, "limited": p.alert, "working": p.working,
                    "done": kittymux_theme.blend(p.done, p.bg, 0.65)}.get(r["state"])
        count = f"{r['panes']} pane{'s' if r['panes'] != 1 else ''}" + (" · other window" if r["other_window"] else "")
        mark = kittymux_agents.state_glyph(r["state"]) if state_fg is not None else " "
        title_w, count_w, folder_w = J.row_budget(width - 6, _cells(r["title"]), _cells(count))
        title = kittymux_place.mid_ellipsis(r["title"], title_w, _cells)
        parts = [("  " + ("▸ " if selected else "  "), p.accent, True), (mark + " ", state_fg if state_fg is not None else p.text, True),
                 (title, p.text if selected else p.muted, selected)]
        if folder_w:
            facts = kittymux_place.facts(r["cwd"], kittymux_git.info(r["cwd"]) if r["cwd"] else None)
            folder = "".join(t for t, _role in kittymux_place.layout(facts, folder_w, icon=_ICON_FOLDER, branch_icon=_ICON_BRANCH, cells=_cells))
            if folder:
                parts.append(("   " + folder, p.faint, False))
        if count_w:
            parts.append(("   " + count, p.faint, False))
        return parts

    @Handler.atomic_update
    def draw_screen(self) -> None:
        cols, rows_h = self.screen_size.cols, self.screen_size.rows
        p, w = self.pal, self.write
        width = min(cols, 100)
        bg = p.bar
        w(set_cursor_position(0, 0) + "\x1b[2J")
        src = self.source
        if self.pick.scope == "pane":
            who, tail = "this pane", ""
        elif src:
            who, tail = f"“{src['title']}”", f" ({src['panes']} pane{'s' if src['panes'] != 1 else ''})"
        else:
            who, tail = "this tab", ""
        room = width - _cells(" Join ") - _cells(" into…")                   # the name gives way first, then the pane count — never the verb
        if room < _cells(who) + _cells(tail):
            tail = ""
        who = kittymux_place.mid_ellipsis(who, max(room, 4), _cells)
        w(set_cursor_position(0, 0) + self._line([(" Join ", p.muted, False), (who, p.text, True), (tail, p.faint, False), (" into…", p.muted, False)], width, bg))
        side = {"auto": "auto side", "right": "to the right", "below": "below"}[self.pick.side]
        w(set_cursor_position(0, 1) + self._line([(" " + (("⌕ " + self.pick.query + "▏") if self.pick.query else "type to filter"), p.accent if self.pick.query else p.faint, False),
                                                  ("    " + side, p.faint, False)], width, bg))
        w(set_cursor_position(0, 2) + self._line([("─" * width, p.line, False)], width, bg))
        room = max(1, rows_h - _LIST_ROWS_RESERVED + 1)
        if self.pick.index < self.scroll:
            self.scroll = self.pick.index
        elif self.pick.index >= self.scroll + room:
            self.scroll = self.pick.index - room + 1
        y = 3
        if not self.loaded:
            w(set_cursor_position(0, y) + self._line([("  loading…", p.faint, False)], width, bg))
        elif not self.rows:
            msg = "  no tab matches" if self.pick.query else "  there is no other tab to join into"
            w(set_cursor_position(0, y) + self._line([(msg, p.faint, False)], width, bg))
        for i, r in enumerate(self.rows[self.scroll:self.scroll + room]):
            sel = (self.scroll + i) == self.pick.index
            w(set_cursor_position(0, y + i) + self._line(self._row_parts(r, sel, width), width, p.surface_hi if sel else bg))
        foot = "⏎ join · tab side · ctrl+t whole tab / this pane · esc"
        w(set_cursor_position(0, max(y + 1, rows_h - 2)) + self._line([("─" * width, p.line, False)], width, bg))
        w(set_cursor_position(0, rows_h - 1) + self._line([(" " + foot, p.faint, False)], width, bg))
        self.flush()

    # ---- events --------------------------------------------------------------
    def _choose(self, index: int | None = None) -> None:
        i = self.pick.index if index is None else index
        if 0 <= i < len(self.rows):
            self.result = json.dumps({"to": self.rows[i]["id"], "side": self.pick.side, "scope": self.pick.scope})
            self.quit_loop()

    def on_text(self, text: str, in_bracketed_paste: bool = False) -> None:
        if text and text.isprintable():
            self.pick.type(text)
            self._refilter()

    def on_key_event(self, key_event, in_bracketed_paste: bool = False) -> None:
        if key_event.type == EventType.RELEASE:
            return
        k = (key_event.key or "").upper()
        mods = key_event.mods or 0
        ctrl = bool(mods & 4)
        if k == "ESCAPE":
            if self.pick.query:
                self.pick.query = ""
                self._refilter()
            else:
                self.quit_loop()
        elif k == "ENTER":
            self._choose()
        elif k in ("DOWN",) or (ctrl and k == "N"):
            self.pick.move(1)
            self.draw_screen()
        elif k in ("UP",) or (ctrl and k == "P"):
            self.pick.move(-1)
            self.draw_screen()
        elif k == "PAGE_DOWN":
            self.pick.move(5)
            self.draw_screen()
        elif k == "PAGE_UP":
            self.pick.move(-5)
            self.draw_screen()
        elif k == "TAB":
            self.pick.cycle_side()
            self.draw_screen()
        elif ctrl and k == "T":
            self.pick.toggle_scope()
            self.draw_screen()
        elif ctrl and k == "C":
            self.quit_loop()
        elif k == "BACKSPACE":
            self.pick.backspace()
            self._refilter()
        elif not ctrl and (key_event.text or (len(key_event.key or "") == 1 and not (mods & ~1))):
            self.on_text(key_event.text or key_event.key)

    def _row_at(self, mouse_event) -> int:
        row = mouse_event.cell_y - 3 + self.scroll
        return row if 0 <= mouse_event.cell_y - 3 < max(1, self.screen_size.rows - _LIST_ROWS_RESERVED + 1) and 0 <= row < len(self.rows) else -1

    def on_mouse_move(self, mouse_event) -> None:
        row = self._row_at(mouse_event)
        if row >= 0 and row != self.pick.index:
            self.pick.index = row
            self.draw_screen()

    def on_click(self, mouse_event) -> None:
        if mouse_event.buttons & MouseButton.LEFT:        # a right/middle click is not "join"
            row = self._row_at(mouse_event)
            if row >= 0:
                self._choose(row)

    def on_resize(self, new_size) -> None:
        self.screen_size = new_size
        self.draw_screen()


@kitten_ui(allow_remote_control=True)
def main(args: list[str]) -> str:
    opts = parse_args(args[1:])
    if opts["to"] is not None:
        return json.dumps(opts) if opts["to"] >= 0 else ""
    ui = Join()
    Loop().loop(ui)
    return ui.result


# ── the move: runs inside kitty ──────────────────────────────────────────────
def _ours(window) -> bool:
    """The picker's own overlay (or anything else of this kitten): never a pane to move."""
    try:
        return any("join-kit" in str(part) for part in (getattr(window.child, "argv", None) or []))
    except Exception:
        return False


def _geometry(window) -> tuple[int, int, int, int]:
    g = window.geometry
    return int(g.left), int(g.top), int(g.right), int(g.bottom)


def perform(boss, window_id: int, to_tab_id: int, side: str = "auto", scope: str = "tab") -> bool:
    """Move the panes. Returns False (changing nothing) when there is nothing sensible to do: no such window or tab, or the same tab."""
    import inspect
    win = boss.window_id_map.get(window_id)
    src = win.tabref() if win is not None else None
    dst = boss.tab_for_id(int(to_tab_id))
    if src is None or dst is None or src is dst:
        return False
    movers = [w for w in list(src) if not _ours(w)] if scope != "pane" else [win]
    if not movers:
        return False
    geoms = [(w.id, _geometry(w)) for w in movers]                      # BEFORE anything moves
    anchor = dst.active_window
    if side == "auto":
        if anchor is not None:
            l, t, r, b = _geometry(anchor)
            side = J.auto_side(r - l, b - t)
        else:
            side = "right"
    horizontal, after = J.side_flags(side)
    by_id = {w.id: w for w in movers}
    can_place = (dst.current_layout.name == "splits" and anchor is not None and hasattr(dst, "attach_windows")
                 and "next_to" in inspect.signature(dst.attach_windows).parameters)
    with boss.suppress_focus_change_events():
        if can_place:
            edge = {"right": "right", "below": "bottom", "left": "left", "above": "top"}.get(side, "right")
            for n, step in enumerate(J.plan(geoms, horizontal, after)):
                w = by_id[step.window]
                group = src.detach_window(w)
                dst.attach_windows(group, next_to=anchor if step.next_to is None else by_id[step.next_to],
                                   horizontal=step.horizontal, after=step.after)
                if n == 0:
                    # Beside the anchor the whole incoming block would share HALF OF ONE PANE. Push the first pane to the tab's edge instead: it takes a
                    # whole side of the tab, and the panes that follow split that side — so nothing arrives as a sliver.
                    dst.set_active_window(w)
                    dst.layout_action("move_to_screen_edge", [edge])
        else:                                                           # another layout places windows itself (tall, grid, stack …) — that already balances
            for w, _g in sorted(((by_id[i], g) for i, g in geoms), key=lambda x: (x[1][1], x[1][0])):
                boss._move_window_to(window=w, target_tab_id=dst.id)
        boss._cleanup_tab_after_window_removal(src)
        dst.make_active()
        if win in movers:
            dst.set_active_window(win)
    return True


@result_handler()
def handle_result(args: list[str], answer: str, target_window_id: int, boss: BossType) -> None:
    try:
        data = json.loads(answer) if answer else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or "to" not in data:
        return
    try:
        perform(boss, target_window_id, int(data["to"]), str(data.get("side", "auto")), str(data.get("scope", "tab")))
    except Exception:
        import traceback
        traceback.print_exc()
