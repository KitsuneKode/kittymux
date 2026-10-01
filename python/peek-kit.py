# kittymux peek — a quick card for ONE tab: what runs there, what it wants from you, and the tail
# of its screen. Opened by right-clicking a tab in the vertical bar (kitty gives its tab bar no hover
# events, so a click is the nearest thing to a link-preview hover), or by hand:
#   kitten python/peek-kit.py <tab id>
# Enter jumps there (to the pane that is asking, if one is); Esc / q / a click closes the card.
# All colours derive from the live kitty theme; data comes from `kitty @ ls` on a worker thread.

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
_REFRESH_EVERY = 1.0
_CARD_WIDTH = 78
_PREVIEW_LINES = 14
_STALE_AFTER = 15.0
_ICON_BRANCH = ""
_ICON_FOLDER = ""


def _C(rgb: int) -> Color:
    return Color(rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255)


def _cells(s: str) -> int:
    return max(0, wcswidth(s))


def _short_home(p: str) -> str:
    home = os.path.expanduser("~")
    return "~" + p[len(home):] if p.startswith(home) else p


def _rc(*args: str) -> str:
    p = main.remote_control(list(args), capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def collect(tab_id: int) -> dict | None:
    """Everything the card shows, or None when the tab no longer exists."""
    try:
        data = json.loads(_rc("ls"))
    except Exception:
        return None
    tab = next((t for o in data for t in o.get("tabs", []) if t["id"] == tab_id), None)
    if tab is None:
        return None
    wins = [w for w in tab.get("windows") or [] if "kittens.runner" not in str(w.get("cmdline"))]
    if not wins:
        return None
    hist = [i for i in tab.get("active_window_history") or [] if any(w["id"] == i for w in wins)]
    aw = next((w for w in wins if w["id"] == (hist[0] if hist else wins[0]["id"])), wins[0])
    panes = kittymux_agents.load_panes(str(_STATE_DIR / f"panes-{os.getppid()}.json"))
    name, tool = kittymux_agents.identify(aw)
    now = time.monotonic()
    state, deciding = kittymux_agents.tab_verdict(panes, [w["id"] for w in wins], aw["id"], name is not None,
                                                  now, _STALE_AFTER)
    focus_id = int(deciding) if deciding and state in kittymux_agents.NEEDS_YOU else aw["id"]
    shown = next((w for w in wins if w["id"] == focus_id), aw)
    gi = kittymux_git.info(aw.get("cwd", "")) if aw.get("cwd") else None
    text = _rc("get-text", "--extent", "screen", "--match", f"id:{shown['id']}")
    tail = [ln.rstrip() for ln in text.rstrip().splitlines() if ln.strip()][-_PREVIEW_LINES:]
    return {
        "title": kittymux_agents.strip_title_prefix(tab.get("title") or aw.get("title") or ""),
        "agent": name or "", "tool": tool or "", "state": state,
        "reason": kittymux_agents.resolve_msg(panes.get(str(deciding or aw["id"])), state) if state else "",
        "cwd": aw.get("cwd", ""), "branch": "" if gi is None or gi.branch == "detached" else gi.branch,
        "tab_id": tab_id, "focus_id": focus_id,
        "panes": [{"agent": n or "", "glyph": (kittymux_agents.AGENTS[n].glyph if n else kittymux_agents.TOOLS.get(t or "", "")),
                   "state": kittymux_agents.fresh_verdict(panes.get(str(w["id"])), now) if w["id"] != aw["id"]
                   else kittymux_agents.resolve_status(panes.get(str(w["id"])), n is not None, now, _STALE_AFTER),
                   "title": kittymux_agents.strip_title_prefix(w.get("title") or ""), "active": w["id"] == aw["id"]}
                  for w in wins for n, t in [kittymux_agents.identify(w)]] if len(wins) > 1 else [],
        "tail": tail, "shown_title": kittymux_agents.strip_title_prefix(shown.get("title") or ""),
    }


class Peek(Handler):
    mouse_tracking = MouseTracking.buttons_only

    def __init__(self, tab_id: int):
        super().__init__()
        self.tab_id = tab_id
        self.card: dict | None = None
        self.gone = False
        self._alive = True

    def initialize(self) -> None:
        self.pal = kittymux_theme.from_colors(
            kittymux_theme.parse_kitty_colors(_rc("get-colors", "--configured")))
        self._refresh()
        self.draw_screen()

    def finalize(self) -> None:
        self._alive = False

    def _refresh(self) -> None:
        def work() -> None:
            card = None
            try:
                card = collect(self.tab_id)
            except Exception:
                pass
            try:
                self.asyncio_loop.call_soon_threadsafe(self._apply, card)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _apply(self, card) -> None:
        if not self._alive:
            return
        self.gone = card is None
        if card is not None:
            self.card = card
        self.draw_screen()
        self.asyncio_loop.call_later(_REFRESH_EVERY, self._refresh)

    # ---- drawing ----------------------------------------------------------
    def _seg(self, text, fg=None, bg=None, bold=False) -> str:
        return styled(text, fg=_C(fg) if fg is not None else None,
                      bg=_C(bg) if bg is not None else None, bold=bold)

    def _line(self, parts: list, width: int, bg: int) -> str:
        out, used = "", 0
        for text, fg, bold in parts:
            room = width - used
            if room <= 0:
                break
            t = deck.fit(text, room, _cells)
            out += self._seg(t, fg=fg, bg=bg, bold=bold)
            used += _cells(t)
        return out + (self._seg(" " * (width - used), bg=bg) if used < width else "")

    @Handler.atomic_update
    def draw_screen(self) -> None:
        cols, rows = self.screen_size.cols, self.screen_size.rows
        p = self.pal
        w = self.write
        width = min(cols, _CARD_WIDTH)
        bg = p.bar
        w(set_cursor_position(0, 0) + "\x1b[2J")
        card = self.card
        lines: list[str] = []
        if card is None:
            lines.append(self._line([(" " + ("this tab is gone" if self.gone else "loading…"), p.faint, False)], width, bg))
        else:
            st = card["state"]
            state_fg = {"waiting": p.waiting, "working": p.working, "limited": p.alert,
                        "done": kittymux_theme.blend(p.done, p.bg, 0.65)}.get(st)
            agent = kittymux_agents.AGENTS.get(card["agent"])
            glyph = agent.glyph if agent else kittymux_agents.TOOLS.get(card["tool"], "")
            head = [(" ", p.text, False), (glyph or " ", agent.brand if agent else p.muted, False), (" ", p.text, False),
                    (card["title"] or "—", p.text, True)]
            right = f"{kittymux_agents.state_glyph(st)} {st} " if state_fg is not None else ""
            lines.append(self._line(head + [(" " * max(1, width - 4 - _cells(card["title"] or "—") - _cells(right)), p.text, False),
                                            (right, state_fg, True)] if right else head, width, bg))
            lines.append(self._line([("─" * width, p.line, False)], width, bg))
            if card["reason"]:
                lines.append(self._line([(" " + card["reason"], state_fg or p.text, True)], width, bg))
            meta = []
            if card["branch"]:
                meta.append((f" {_ICON_BRANCH} {card['branch']}", p.muted, False))
            if card["cwd"]:
                meta.append(((" " if not meta else "   ") + f"{_ICON_FOLDER} {_short_home(card['cwd'])}", p.faint, False))
            if meta:
                lines.append(self._line(meta, width, bg))
            for i, pane in enumerate(card["panes"]):
                brand = kittymux_agents.AGENTS[pane["agent"]].brand if pane["agent"] in kittymux_agents.AGENTS else p.muted
                pfg = {"waiting": p.waiting, "working": p.working, "limited": p.alert,
                       "done": kittymux_theme.blend(p.done, p.bg, 0.65)}.get(pane["state"])
                mark = kittymux_agents.state_glyph(pane["state"]) if pfg is not None else " "
                lines.append(self._line([
                    ("  " + ("└" if i == len(card["panes"]) - 1 else "├") + " ", p.line, False),
                    (pane["glyph"] or "·", brand, False), (" ", p.text, False),
                    (pane["title"] or pane["agent"] or "shell", p.text if pane["active"] else p.muted, pane["active"]),
                    ("  " + mark, pfg if pfg is not None else p.text, True)], width, bg))
            lines.append(self._line([("─" * width, p.line, False)], width, bg))
            for ln in card["tail"] or ["(empty screen)"]:
                lines.append(self._line([(" " + ln, p.muted, False)], width, bg))
        footer = self._line([(" ⏎ go to it · esc close", p.faint, False)], width, bg)
        for y, ln in enumerate(lines[:max(1, rows - 1)]):
            w(set_cursor_position(0, y) + ln)
        w(set_cursor_position(0, min(rows - 1, len(lines))) + footer)
        self.flush()

    # ---- events -----------------------------------------------------------
    def on_key_event(self, key_event, in_bracketed_paste: bool = False) -> None:
        if key_event.type == EventType.RELEASE:
            return
        k = (key_event.key or "").upper()
        if k in ("Q", "ESCAPE"):
            self.quit_loop()
        elif k == "ENTER" and self.card is not None:
            _rc("focus-tab", "--match", f"id:{self.card['tab_id']}")
            _rc("focus-window", "--match", f"id:{self.card['focus_id']}")
            self.quit_loop()

    def on_click(self, mouse_event) -> None:
        self.quit_loop()

    def on_resize(self, new_size) -> None:
        self.screen_size = new_size
        self.draw_screen()


@kitten_ui(allow_remote_control=True)
def main(args: list[str]) -> str:
    try:
        tab_id = int(args[1])
    except (IndexError, ValueError):
        print("usage: kitten peek-kit.py <tab id>", file=sys.stderr)
        return ""
    Loop().loop(Peek(tab_id))
    return ""


@result_handler()
def handle_result(args: list[str], answer: str, target_window_id: int, boss: BossType) -> None:
    pass
