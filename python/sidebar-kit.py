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
import types
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
def _source_dir():
    # Kitty execs compiled source without __file__; argv[0] belongs to the runner.
    return os.path.dirname(os.path.realpath(_source_dir.__code__.co_filename))


for _d in (_CONFIG_DIR, _source_dir()):
    if _d:
        if _d in sys.path:
            sys.path.remove(_d)
        sys.path.insert(0, _d)
import kittymux_agents  # noqa: E402
import kittymux_agentsview  # noqa: E402
import kittymux_features  # noqa: E402
import kittymux_deck as deck  # noqa: E402
import kittymux_git  # noqa: E402
import kittymux_theme  # noqa: E402
import kittymux_inbox  # noqa: E402
import kittymux_inboxview  # noqa: E402
import kittymux_meters  # noqa: E402
import kittymux_ui  # noqa: E402
import kittymux_usageview  # noqa: E402
import kittymux_place  # noqa: E402
import kittymux_files  # noqa: E402

_STATE_DIR = Path(os.environ["KITTYMUX_STATE"]) if os.environ.get("KITTYMUX_STATE") else \
    Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "kittymux"
_ERR_LOG = _STATE_DIR / "sidebar-kit-err.log"

_ICON_BRANCH = ""
_ICON_FOLDER = ""
_RAIL = "▌"
_STALE_AFTER = 15.0
_PR_TTL = 120.0
_REFRESH_EVERY = 1.5
_UNDO_S = 8.0                 # how long `z` can take a dismissal back (the footer says so while it can)


def _C(rgb: int) -> Color:
    return Color(rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255)


def _cells(s: str) -> int:
    return max(0, wcswidth(s))


def _find_join_kit() -> str:
    """join-kit.py sits next to the kittymux modules. Kittens are run by path and are exec'd (no __file__; sys.argv[0] is not the script inside a running
    kitten), so anchor on a module that WAS imported: kittymux_deck is linked into the config dir from the checkout, and its real path is that checkout's python/."""
    here = os.path.dirname(os.path.realpath(deck.__file__)) if getattr(deck, "__file__", None) else ""
    own = os.path.dirname(os.path.realpath(sys.argv[0])) if sys.argv and sys.argv[0] else ""
    for d in (here, own, _CONFIG_DIR):
        if d and os.path.exists(os.path.join(d, "join-kit.py")):
            return os.path.join(d, "join-kit.py")
    return os.path.join(here or _CONFIG_DIR, "join-kit.py")


_JOIN_KIT = _find_join_kit()


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


def _panes_state(data: list) -> dict:
    try:
        pid = os.getppid()
        if _TARGET:
            pid = int(os.environ.get("KITTYMUX_TARGET_PID", "0"))
            if pid <= 0 or deck.target_pid(data) != pid:
                return {}
        return kittymux_agents.load_panes(str(_STATE_DIR / f"panes-{pid}.json"))
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
    __slots__ = ("rows", "items", "current_session", "source", "query")

    def __init__(self, rows: list, current_session: str, query: str = ""):
        self.source, self.query = rows, query
        groups = deck.filter_groups(deck.group_rows(rows, current_session), query)   # indexes are assigned BEFORE filtering
        self.items, self.rows = deck.flatten(groups, current_session)
        self.current_session = current_session

    def with_query(self, query: str) -> "Snapshot":
        return Snapshot(self.source, self.current_session, query)


class Collector:
    """Builds a Snapshot from `kitty @ ls`. Runs on a worker thread only."""

    def __init__(self):
        self._pr = PrCache()

    def branch(self, cwd: str) -> str:
        gi = kittymux_git.info(cwd)                 # reads .git/HEAD; no subprocess
        return "" if gi is None or gi.branch == "detached" else gi.branch

    def _pane(self, w: dict, active_id: int, panes: dict, now: float) -> deck.PaneData:
        name, tool = kittymux_agents.identify(w)
        agent = kittymux_agents.AGENTS.get(name) if name else None
        if w["id"] == active_id:
            state = kittymux_agents.resolve_status(panes.get(str(w["id"])), agent is not None, now, _STALE_AFTER)
        else:
            state = kittymux_agents.fresh_verdict(panes.get(str(w["id"])), now)
        title = (w.get("title") or "").strip() or _short_home(w.get("cwd", ""))
        return deck.PaneData(win_id=w["id"], glyph=agent.glyph if agent else kittymux_agents.TOOLS.get(tool, ""),
                             agent=name or "", tool=bool(tool and not agent), state=state,
                             title=kittymux_agents.strip_title_prefix(title), active=w["id"] == active_id, cwd=w.get("cwd", ""))

    def collect(self) -> Snapshot | None:
        try:
            data = json.loads(_rc("ls"))
        except Exception:
            return None
        panes = _panes_state(data)
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
                name, tool_name = kittymux_agents.identify(aw)
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
                    title=kittymux_agents.strip_agent_prefix(tab.get("title") or "", name),
                    glyph=agent.glyph if agent else kittymux_agents.TOOLS.get(tool_name, ""),
                    tool=bool(tool_name and not agent),
                    agent=name or "", branch=branch, cwd=cwd,
                    panes=len(wins), status=status, unread=unread, current=current,
                    msg=kittymux_agents.resolve_msg(panes.get(str(deciding or aw["id"])), st) if st else "",
                    pr=self._pr.get(cwd, branch), ports=ports, pane_rows=pane_rows,
                    win_ids=tuple(w["id"] for w in wins)))
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
        self._preview_inflight = False
        self._view, self._usage_scroll, self._usage_data = "agents", 0, {}
        self._usage_trends, self._usage_details = {}, False
        self._usage_process, self._usage_last = None, 0.0
        self.kit = kittymux_ui.Kit(self.pal, cells=_cells)
        self._usage_sel, self._usage_history, self._usage_regions = 0, {}, []
        self._inbox, self._inbox_mtime, self._inbox_sel, self._inbox_filter, self._inbox_scroll = [], -1.0, 0, "all", 0
        self._inbox_regions = ([], [], [])        # (filter chips, cards, buttons) in SCREEN coordinates, rebuilt on every draw
        self._inbox_undo = None                   # (ids, expires on the monotonic clock) of the last dismissal, while `z` can still take it back
        self._tab_regions = []
        self._preview_timer = None
        self._preview_rects = ()
        self._hover_pane = (-1, -1)             # (row, pane) of the child line under the pointer
        self.query, self.searching, self.full = "", False, None     # the `/` search
        self._alive = True
        self._preview_worker = deck.LatestWorker(
            self._fetch_preview, lambda generation, lines: self._post(self._apply_preview, generation, lines))
        self._resize_worker = deck.LatestWorker(
            self._perform_resize, lambda *args: None,
            coalesce=lambda old, new: (new[0], old[1] or new[1]),
            daemon=False)  # a queued release write must survive normal interpreter shutdown
        self._collecting = False
        self._collector = Collector()
        self._first = True
        self._request_refresh()
        self.draw_screen()
        self._schedule()

    def finalize(self) -> None:
        self._alive = False
        if self._preview_timer is not None:
            self._preview_timer.cancel()
            self._preview_timer = None
        if hasattr(self, "_preview_worker"):
            self._preview_worker.close()
        if hasattr(self, "_resize_worker"):
            self._resize_worker.close(drain=True)  # release writes must outlive a closing UI
        if self._can_drag():
            self._pointer("")

    # ---- data (worker threads → event loop) -------------------------------
    def _request_refresh(self) -> None:
        if self._collecting or not self._alive:
            return
        self._collecting = True

        def work() -> None:
            snap = None
            try:
                # Usage and Inbox need no agent ls/PR/ports scan. Read files on this worker only.
                if getattr(self, "_view", "agents") == "agents":
                    snap = self._collector.collect()
                usage = kittymux_files.read_json(_STATE_DIR / "agent-usage.json", {})
                trends = kittymux_files.read_json(_STATE_DIR / "agent-usage-trends.json", {})
                self._post(self._apply_usage, usage, trends)
                self._post(self._apply_side, *self._load_side())
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

    def _apply_usage(self, data, trends=None):
        if self._alive and isinstance(data, dict):
            self._usage_data = data
            if trends is not None:
                self._usage_trends = trends
            if getattr(self, "_view", "agents") == "usage":
                self.draw_screen()

    def _usage_pick(self, k: str) -> None:
        """← → (h l, Tab) or 1..9 pick the provider whose card is shown; the strip wraps."""
        count = len([x for x in (self._usage_data.get("providers") if isinstance(self._usage_data, dict) else None) or [] if isinstance(x, dict)])
        if not count:
            return
        if len(k) == 1 and k in "123456789":
            self._usage_sel = min(count - 1, int(k) - 1)
        else:
            self._usage_sel = (self._usage_sel + (-1 if k in ("LEFT", "H") else 1)) % count
        self._usage_scroll = 0
        self.draw_screen()

    def _inbox_items(self) -> list:
        return kittymux_inboxview.visible(self._inbox, self._inbox_filter, time.time())

    def _inbox_key(self, k: str, shifted: bool) -> None:
        keys = [f for f, _ in kittymux_inboxview.FILTERS]
        n = len(self._inbox_items())
        if k in ("A", "ESCAPE"):
            self._set_view("agents")
            return
        if k == "Q":
            self.quit_loop()
            return
        if k in ("J", "DOWN"):
            self._inbox_sel = min(max(0, n - 1), self._inbox_sel + 1)
        elif k in ("K", "UP"):
            self._inbox_sel = max(0, self._inbox_sel - 1)
        elif k in ("HOME",) or (k == "G" and not shifted):
            self._inbox_sel = 0
        elif k in ("END",) or (k == "G" and shifted):
            self._inbox_sel = max(0, n - 1)
        elif k in ("TAB", "F"):
            self._inbox_filter = keys[(keys.index(self._inbox_filter) + (-1 if shifted else 1)) % len(keys)]
            self._inbox_sel = 0
        elif len(k) == 1 and k in "1234":
            self._inbox_filter, self._inbox_sel = keys[int(k) - 1], 0
        elif k == "ENTER":
            self._inbox_act("jump")
            return
        elif k == "X":
            self._inbox_act("dismiss_all" if shifted else "dismiss")
            return
        elif k == "Z":
            self._inbox_undo_do()
            return
        elif k == "R":
            self._inbox_mtime = -1.0
            self._request_refresh()
            return
        else:
            return
        self.draw_screen()

    def _inbox_act(self, action: str, idx: int | None = None) -> None:
        """jump: focus the agent's window (the CLI resolves its kitty and the window manager, and marks the event read).
        dismiss: hide the event. Nothing here ever sends text to an agent."""
        items = self._inbox_items()
        i = self._inbox_sel if idx is None else idx
        if action == "dismiss_all":
            ids = [e["id"] for e in items if isinstance(e.get("id"), str)]
        elif 0 <= i < len(items) and isinstance(items[i].get("id"), str):
            ids = [items[i]["id"]]
        else:
            return
        if action == "jump":
            root = Path(deck.__file__).resolve().parent.parent
            try:
                subprocess.Popen([str(root / "bin" / "kittymux"), "inbox", "jump", ids[0]], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                return
            if not _PANEL:
                self.quit_loop()
            return
        kittymux_inbox.ack(str(_STATE_DIR), time.time(), ids=ids, status="dismissed")
        self._inbox_reload()
        self._inbox_sel = min(self._inbox_sel, max(0, len(self._inbox_items()) - 1))
        self._inbox_undo = (ids, time.monotonic() + _UNDO_S)
        if self._alive:
            self.asyncio_loop.call_later(_UNDO_S + 0.1, self._undo_expired)       # the offer goes away by itself: one redraw, no polling
        self.draw_screen()

    def _inbox_reload(self) -> None:
        self._inbox = kittymux_inbox.load(str(_STATE_DIR))
        try:
            self._inbox_mtime = os.stat(kittymux_inbox.store_path(str(_STATE_DIR))).st_mtime
        except OSError:
            self._inbox_mtime = 0.0

    def _undo_live(self) -> bool:
        return bool(self._inbox_undo) and time.monotonic() < self._inbox_undo[1]

    def _undo_expired(self) -> None:
        if self._alive and self._inbox_undo and not self._undo_live():
            self._inbox_undo = None
            if getattr(self, "_view", "agents") == "inbox":
                self.draw_screen()

    def _inbox_undo_do(self) -> None:
        """`z`: bring back what the last dismissal hid (one step, for _UNDO_S seconds). The cards come back where the clock puts them."""
        if not self._undo_live():
            self._inbox_undo = None
            return
        ids, _ = self._inbox_undo
        self._inbox_undo = None
        kittymux_inbox.restore(str(_STATE_DIR), time.time(), ids)
        self._inbox_reload()
        self.draw_screen()

    def _load_side(self):
        """(history or None, inbox events or None, store mtime): the week of usage (only when that view is up) and the inbox (only when
        its file changed). Runs on the worker thread; never raises."""
        history = events = None
        mtime = self._inbox_mtime
        try:
            if getattr(self, "_view", "agents") == "usage":
                history = kittymux_meters.load_history(str(_STATE_DIR))
            try:
                mtime = os.stat(kittymux_inbox.store_path(str(_STATE_DIR))).st_mtime
            except OSError:
                mtime = 0.0
            if mtime != self._inbox_mtime:
                events = kittymux_inbox.load(str(_STATE_DIR))
        except Exception:
            _log_error()
        return history, events, mtime

    def _apply_side(self, history, events, mtime):
        if not self._alive:
            return
        changed = False
        if history is not None and history != self._usage_history:
            self._usage_history, changed = history, True
        if events is not None:
            badge_moved = kittymux_inboxview.unread(events) != kittymux_inboxview.unread(self._inbox)
            self._inbox, self._inbox_mtime = events, mtime
            changed = changed or badge_moved or getattr(self, "_view", "agents") == "inbox"     # the deck only redraws when the badge moved
        if changed:
            self.draw_screen()

    def _request_usage(self, force=False):
        process = getattr(self, "_usage_process", None)
        if process is not None and process.poll() is None:
            return
        now = time.monotonic()
        if not force and now - getattr(self, "_usage_last", 0) < 60:
            return
        root = Path(deck.__file__).resolve().parent.parent
        env = dict(os.environ, KITTYMUX_HOME=str(root))
        try:
            self._usage_process = subprocess.Popen(["python3", str(root / "bin/mux-usage.py"), "--collect-only"],
                                                   env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                   stderr=subprocess.DEVNULL, start_new_session=True)
            self._usage_last = now
        except OSError:
            pass

    def _set_view(self, view):
        self._view = view
        self._foot_hot = None
        if view == "usage":
            self._request_usage()
        if view == "agents":
            self._request_refresh()                   # the list is not collected while another view is up: catch it up now, not on the next tick
            self._schedule_spin()
        self.draw_screen()

    # ---- the three views share a tab strip, a footer and the resize handle ----
    def _ansi(self, line) -> str:
        return "".join(self._seg(sp.text, sp.fg, sp.bg, sp.bold, sp.dim) for sp in line)

    def _body_width(self, cols: int) -> int:
        return cols - 1 if self._can_drag() else cols                   # the last column is the resize handle

    def _tabs_line(self, width: int, hint: str = "") -> str:
        """The strip: three pills (the picked one carries its name, the others an icon and a count). `hint` rides at the right edge when the
        strip leaves room for it."""
        view = getattr(self, "_view", "agents")
        items = [("▦", "Agents", view == "agents", 0), ("◔", "Usage", view == "usage", 0),
                 ("✉", "Inbox", view == "inbox", kittymux_inboxview.unread(self._inbox))]
        hint_w = _cells(hint) + 1 if hint else 0
        room = width - hint_w if hint and width - hint_w >= self.kit.tab_regions(items, width)[-1][1] + 2 else width      # the hint only rides along when the pills leave room
        regions = self.kit.tab_regions(items, room)
        self._tab_regions = [(a, b, name) for (a, b), name in zip(regions, ("agents", "usage", "inbox"))]
        line = self.kit.tabs(items, room)
        if room != width:
            line = line + [kittymux_ui.S(hint + " ", self.pal.faint, self.pal.bar)]
        return self._ansi(line)

    def _footer(self, lead: list, pairs: list, width: int) -> str:
        """Clickable keycaps after an optional lead (e.g. "+3 more"). Records where each drew so a click or a hover can find it; the one the
        pointer is on lights up."""
        pairs = [x if len(x) == 3 else (x[0], x[1], None) for x in pairs]          # (key, label[, token]): no token = a hint, not a button
        lead_w = kittymux_ui.line_cells(lead, self.kit.cells)
        line, regions = kittymux_agentsview.action_bar(self.kit, pairs, max(0, width - lead_w), getattr(self, "_foot_hot", None))
        self._foot_regions = [(x0 + lead_w, x1 + lead_w, token, i) for x0, x1, token, i in regions]
        return self._ansi(lead + line)

    def _press(self, token: str) -> None:
        """A click on a keycap does exactly what the key does: the same handler, a synthetic press."""
        self.on_key_event(types.SimpleNamespace(type=EventType.PRESS, key=token, mods=0, text=""))

    def _draw_handle(self, cols: int, rows_n: int) -> None:
        if self._can_drag():                      # the drag handle: lights up on hover / while dragging
            p = self.pal
            hot = getattr(self, "_drag", False) or getattr(self, "_handle_hot", False)
            for y2 in range(rows_n):
                self.write(set_cursor_position(cols - 1, y2) + self._seg("▕", fg=p.accent if hot else p.line, bg=p.bar))

    def _draw_body(self, cols: int, height: int, header, lines, scroll: int, footer) -> int:
        """Header row, tab strip, `lines` from `scroll`, footer keycaps. Returns the scroll actually used."""
        w, width = self.write, self._body_width(cols)
        page = max(1, height - 3)
        scroll = max(0, min(scroll, max(0, len(lines) - page)))
        w(set_cursor_position(0, 0) + self._ansi(header))
        w(set_cursor_position(0, 1) + self._tabs_line(width))
        blank = self._seg(" " * width, bg=self.pal.bar)
        for y in range(page):
            i = scroll + y
            w(set_cursor_position(0, y + 2) + (self._ansi(lines[i]) if i < len(lines) else blank))
        self._foot_y = height - 1
        w(set_cursor_position(0, height - 1) + self._footer([], footer, width))
        self._draw_handle(cols, height)
        self.flush()
        return scroll

    def _draw_usage(self, cols, height):
        v = kittymux_usageview.view(self._usage_data, self._usage_history, self._body_width(cols), self._usage_sel, self.kit,
                                    trends=kittymux_usageview.trend_lines(self._usage_trends, max(1, self._body_width(cols) - 6)),
                                    details=self._usage_details)
        self._usage_sel = v.sel
        self._usage_scroll = self._draw_body(cols, height, v.header, v.lines, getattr(self, "_usage_scroll", 0),
                                             [("r", "refresh", "R"), ("d", "details" if not self._usage_details else "hide", "D"), ("←→", "pick"), ("a", "agents", "A")])
        self._usage_regions = [(x0, x1, y0 - self._usage_scroll + 2, y1 - self._usage_scroll + 2, idx) for x0, x1, y0, y1, idx in v.tiles]

    def _draw_inbox(self, cols, height):
        v = kittymux_inboxview.view(self._inbox, self._inbox_filter, self._inbox_sel, self._body_width(cols), self.kit)
        self._inbox_sel = v.sel
        page, top = max(1, height - 3), self._inbox_scroll
        if v.cards:                                                       # keep the picked card on screen
            y0, y1, _ = v.cards[v.sel]
            top = 0 if v.sel == 0 else len(v.lines) if v.sel == v.count - 1 else y0 if y0 < top else y1 - page if y1 > top + page else top      # the last card reveals what is under it (the ledger)
        footer = [("⏎", "jump", "ENTER"), ("x", "dismiss", "X"), ("j k", "move"), ("tab", "filter", "TAB")]       # buttons first: a narrow panel drops from the right
        if self._undo_live():                                             # the way back is offered where the hand just was, replacing what it does not need
            footer = [("z", "undo " + (f"{len(self._inbox_undo[0])} dismissed" if len(self._inbox_undo[0]) > 1 else "dismiss"), "Z")] + footer[:2]
        self._inbox_scroll = self._draw_body(cols, height, v.header, v.lines, top, footer)
        off = 2 - self._inbox_scroll
        self._inbox_regions = ([(x0, x1, off, filt) for x0, x1, filt in v.chips], [(y0 + off, y1 + off, i) for y0, y1, i in v.cards],
                               [(x0, x1, y + off, i, act) for x0, x1, y, i, act in v.buttons])

    def _apply(self, snap) -> None:
        self._collecting = False
        if not self._alive or snap is None:
            return
        keep = self.snap.rows[self.sel].tab_id if self.snap.rows else None
        hovered = self.preview_for if self._hover_pane[0] == self.sel else 0
        self.full = snap                         # the unfiltered view; self.snap is what the `/` search leaves of it
        self.snap = snap.with_query(self.query) if self.query else snap
        snap = self.snap
        self._hover_pane = (-1, -1)             # row indices changed under it
        if not snap.rows:
            self._request_preview()
            self.draw_screen()
            return
        if self._first:
            self._first = False
            self.sel = next((i for i, r in enumerate(snap.rows) if r.current), 0)
        elif keep is not None:
            self.sel = next((i for i, r in enumerate(snap.rows) if r.tab_id == keep),
                            min(self.sel, len(snap.rows) - 1))
        self._clamp()
        if hovered:
            pane = next((i for i, p in enumerate(snap.rows[self.sel].pane_rows) if p.win_id == hovered), -1)
            if pane >= 0:
                self._hover_pane = (self.sel, pane)
        # A slow same-pane read must be allowed to finish before periodic refresh
        # invalidates it; actual selection changes still submit a new generation.
        self._request_preview(force=not self._preview_inflight)
        self.draw_screen()
        self._schedule_spin()

    # ---- spinner: redraw at frame rate only while something is working ----
    def _schedule_spin(self) -> None:
        if getattr(self, "_spin_pending", False) or not self._alive or getattr(self, "_view", "agents") != "agents":
            return
        if self._motion() and any(r.status == "working" for r in self.snap.rows):
            self._spin_pending = True
            self.asyncio_loop.call_later(0.1, self._spin)

    def _motion(self) -> bool:
        """The `motion` switch, read at most once a second (a stat per frame would cost more than the frame)."""
        now = time.monotonic()
        if now - getattr(self, "_motion_at", -9.0) >= 1.0:
            self._motion_at = now
            try:
                self._motion_on = kittymux_features.enabled("motion", str(_STATE_DIR))
            except Exception:
                self._motion_on = True
        return self._motion_on

    def _spin(self) -> None:
        self._spin_pending = False
        if self._alive and getattr(self, "_view", "agents") == "agents" and self._motion() and any(r.status == "working" for r in self.snap.rows):
            self.draw_screen()
            self._schedule_spin()

    def _request_preview(self, force: bool = False, delay: bool = False) -> None:
        if not self._alive:
            return
        if not self.snap.rows:
            if self._preview_timer is not None:
                self._preview_timer.cancel()
                self._preview_timer = None
            self._preview_rects = ()
            self._preview_worker.invalidate()
            self._preview_inflight = False
            self.preview_for = 0
            self.preview = []
            return
        r = self.snap.rows[self.sel]
        row, pane = self._hover_pane
        wid = r.pane_rows[pane].win_id if row == self.sel and 0 <= pane < len(r.pane_rows) else r.win_id
        if wid == self.preview_for and not force:
            return
        if self._preview_timer is not None:
            self._preview_timer.cancel()
            self._preview_timer = None
        if wid != self.preview_for:
            self._preview_worker.invalidate()
            self.preview = []
            self._preview_rects = ()
        self.preview_for = wid
        self._preview_inflight = True
        request = (wid, self.screen_size.rows, r.tab_id, r.panes > 1)
        if delay:
            self._preview_timer = self.asyncio_loop.call_later(0.15, self._submit_preview, request)
        else:
            self._submit_preview(request)

    def _submit_preview(self, request):
        self._preview_timer = None
        if self._alive and request[0] == self.preview_for:
            self._preview_worker.submit(request)

    def _fetch_preview(self, request) -> list:
        wid, rows_n, tab_id, split = request
        try:
            txt = _rc("get-text", "--extent", "screen", "--match", f"id:{wid}")
        except Exception:
            txt = ""
        lines = txt.rstrip().splitlines()
        lines = lines[-max(4, rows_n - 4):] if lines else ["(empty pane)"]
        if split:
            try:
                snap = json.loads(_rc("kitten", str(Path(deck.__file__).resolve().parent / "pane-snapshot.py"), str(tab_id)))
                return {"lines": lines, "rects": (snap or {}).get("rects", [])}
            except (ValueError, TypeError):
                pass
        return lines

    def _apply_preview(self, generation: int, lines: list) -> None:
        if self._alive and self._preview_worker.is_current(generation):
            self._preview_inflight = False
            self._preview_rects = tuple(tuple(r) for r in lines.get("rects", [])) if isinstance(lines, dict) else ()
            self.preview = (lines["lines"] if isinstance(lines, dict) else lines) or ["(empty pane)"]
            self.draw_screen()

    def _schedule(self) -> None:
        if self._alive:
            self.asyncio_loop.call_later(_REFRESH_EVERY, self._tick)

    def _tick(self) -> None:
        if not self._alive:
            return
        if getattr(self, "_view", "agents") == "usage":
            self._request_usage()
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

    def _drawer_rows(self) -> int:
        """A narrow deck (the docked panel) has no room for a preview column, so it gets a drawer under the
        list instead: the hovered tab/pane's screen, like a link preview. 0 when the window is wide or short."""
        cols, rows = self.screen_size.cols, self.screen_size.rows
        return min(13, rows // 3) if cols < 64 and rows >= 24 else 0

    def _avail(self) -> int:
        return max(1, self.screen_size.rows - 3 - self._drawer_rows())   # 2 header lines + 1 footer line + the drawer

    def _clamp(self) -> None:
        n = len(self.snap.rows)
        self.sel = max(0, min(self.sel, n - 1)) if n else 0
        self.scroll = deck.ensure_visible(self.snap.items, self.scroll, self.sel, self._avail())

    # ---- drawing ----------------------------------------------------------
    def _seg(self, text, fg=None, bg=None, bold=False, dim=False) -> str:
        return styled(kittymux_place.clean_line(text), fg=_C(fg) if fg is not None else None,
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
        home = os.path.expanduser("~")
        animate = self._motion()
        return (self._ansi(kittymux_agentsview.title_row(self.kit, r, selected, False, bar_w, animate)),
                self._ansi(kittymux_agentsview.context_row(self.kit, r, selected, False, bar_w, home)))

    def _pane_line(self, r, j: int, bar_w: int, hovered: bool) -> str:
        return self._ansi(kittymux_agentsview.pane_row(self.kit, r, j, hovered, bar_w, self._motion()))

    @Handler.atomic_update
    def draw_screen(self) -> None:
        cols, rows_n, bar_w = self._geom()
        p = self.pal
        view = getattr(self, "_view", "agents")
        if view == "usage":
            self._draw_usage(cols, rows_n)
            return
        if view == "inbox":
            self._draw_inbox(cols, rows_n)
            return
        w = self.write
        snap = self.snap
        # header: counts + hint
        waiting = sum(1 for r in snap.rows if r.status in kittymux_agents.NEEDS_YOU)
        working = sum(1 for r in snap.rows if r.status == "working")
        w(set_cursor_position(0, 0) + self._ansi(kittymux_agentsview.summary_row(self.kit, len(snap.rows), waiting, working, bar_w, self._motion())))
        if self.searching or self.query:
            total = len(self.full.rows) if self.full is not None else len(snap.rows)
            line = [(" / ", p.accent, True), (self.query, p.text, True), ("▏" if self.searching else "", p.accent, False),
                    (f"   {len(snap.rows)}/{total}", p.faint, False)]
            w(set_cursor_position(0, 1) + self._line(line, bar_w, p.surface))
        else:
            w(set_cursor_position(0, 1) + self._tabs_line(bar_w))
        # list
        avail = self._avail()
        y = 2
        blank = self._seg(" " * bar_w, bg=p.bar)
        drawn = 0
        for off, it in deck.visible(snap.items, self.scroll, avail):
            if it.kind == "header":
                w(set_cursor_position(0, y + off) + self._ansi(kittymux_agentsview.header_row(self.kit, it.label, it.count, it.current, bar_w)))
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
        dr = self._drawer_rows()
        for yy in range(y + drawn, rows_n - dr):
            w(set_cursor_position(0, yy) + blank)
        shown = sum(1 for _o, it in deck.visible(snap.items, self.scroll, avail) if it.kind == "row")
        hidden = sum(1 for it in snap.items[self.scroll:] if it.kind == "row") - shown
        more = [kittymux_ui.S(f" +{hidden} more ", self.kit.ink(p.faint, p.bar, 3.0), p.bar)] if hidden > 0 else []
        self._foot_y = rows_n - 1 - dr
        # most useful first: a narrow panel drops buttons from the right
        w(set_cursor_position(0, self._foot_y) + self._footer(
            more, [("⏎", "jump", "ENTER"), ("/", "find", "/"), ("a", "join", "A"), ("t", "detach", "T")], bar_w))
        if not snap.rows:
            w(set_cursor_position(0, 2) + self._line([(" no tabs", p.faint, False)], bar_w, p.bar))
        if dr and snap.rows:                      # the preview drawer: what the hovered tab/pane shows right now
            r = snap.rows[self.sel]
            row, pane = self._hover_pane
            pd = r.pane_rows[pane] if row == self.sel and 0 <= pane < len(r.pane_rows) else None
            top = rows_n - dr
            w(set_cursor_position(0, top) + self._line([("─" * bar_w, p.line, False)], bar_w, p.bar))
            who = pd.title if pd else r.title
            w(set_cursor_position(0, top + 1) + self._line(
                [(" " + deck.fit(f"{who} · {_short_home(pd.cwd if pd else r.cwd)}", bar_w - 2, _cells), p.faint, True)], bar_w, p.bar))
            body = [ln.strip() for ln in self.preview if ln.strip()][-(dr - 2):]
            for j in range(dr - 2):
                text = body[j] if j < len(body) else ""
                w(set_cursor_position(0, top + 2 + j) + self._line([(" " + text, p.muted, False)], bar_w, p.bar))
        # separator + preview
        if cols >= 64:
            px = bar_w + 2
            pw = cols - px - 1
            for y2 in range(rows_n):
                w(set_cursor_position(bar_w, y2) + self._seg("▕", fg=p.line, bg=p.bar))
                w(set_cursor_position(bar_w + 1, y2) + " " * (cols - bar_w - 1))
            if snap.rows:
                r = snap.rows[self.sel]
                row, pane = self._hover_pane
                pd = r.pane_rows[pane] if row == self.sel and 0 <= pane < len(r.pane_rows) else None
                who = pd.title if pd else r.title
                w(set_cursor_position(px, 0) + self._seg(
                    deck.fit(f"{who or 'pane'} · {_short_home(pd.cwd if pd else r.cwd)}", pw, _cells), fg=p.faint))
                drawing = deck.numbered_layout(self._preview_rects, min(32, pw), min(10, max(5, r.panes * 3 + 1)), self.preview_for) if {rect[0] for rect in self._preview_rects} == {child.win_id for child in r.pane_rows} else []
                body = drawing + ([f"{r.panes} panes · [{next((i + 1 for i, child in enumerate(r.pane_rows) if child.win_id == self.preview_for), 1)}] preview"] if drawing else []) + self.preview
                for j, ln in enumerate(body[:rows_n - 2]):
                    w(set_cursor_position(px, j + 2) + self._seg(deck.fit(ln, pw, _cells), fg=p.muted))
        self._draw_handle(cols, rows_n)
        self.flush()

    # ---- events -----------------------------------------------------------
    def _refilter(self) -> None:
        if self.full is None:
            return
        self.snap = self.full.with_query(self.query)
        self._hover_pane = (-1, -1)
        self.sel = 0
        self._clamp()
        self._request_preview()
        self.draw_screen()

    def on_text(self, text: str, in_bracketed_paste: bool = False) -> None:
        """Typing while the `/` search is open: printable characters extend the query."""
        if not self.searching:
            return
        clean = "".join(ch for ch in text if ch.isprintable())
        if clean and len(self.query) < 60:
            self.query = (self.query + clean)[:60]
            self._refilter()

    def _search_key(self, k: str) -> bool:
        """Keys while the search is open. True when consumed."""
        n = len(self.snap.rows)
        if k == "ESCAPE":
            if self.query:
                self.query = ""
                self._refilter()
            else:
                self.searching = False
                self.draw_screen()
            return True
        if k == "BACKSPACE":
            self.query = self.query[:-1]
            self._refilter()
            return True
        if k == "ENTER":
            self.searching = False
            self._jump()
            return True
        if k in ("DOWN", "TAB"):
            self.sel = deck.step_row(self.sel, 1, n)
        elif k == "UP":
            self.sel = deck.step_row(self.sel, -1, n)
        else:
            return True                           # printable keys arrive through on_text
        self._clamp()
        self._request_preview()
        self.draw_screen()
        return True

    def on_key_event(self, key_event, in_bracketed_paste: bool = False) -> None:
        if key_event.type == EventType.RELEASE:   # press+release both arrive; act once
            return
        k = (key_event.key or "").upper()
        view = getattr(self, "_view", "agents")
        if not self.searching and k == "U":
            self._set_view("agents" if view == "usage" else "usage")
            return
        if not self.searching and k == "I":
            self._set_view("agents" if view == "inbox" else "inbox")
            return
        if view == "usage":
            if k in ("A", "ESCAPE"):
                self._set_view("agents")
            elif k == "Q":
                self.quit_loop()
            elif k == "D":
                self._usage_details = not getattr(self, "_usage_details", False)
                self.draw_screen()
            elif k == "R":
                self._request_usage(force=True)
            elif k in ("LEFT", "H", "RIGHT", "L", "TAB") or (len(k) == 1 and k in "123456789"):
                self._usage_pick(k)
            elif k in ("J", "K", "UP", "DOWN", "PAGE_UP", "PAGE_DOWN"):
                delta = (-1 if k in ("K", "UP", "PAGE_UP") else 1) * (max(1, self.screen_size.rows - 3) if k.startswith("PAGE") else 1)
                self._usage_scroll = max(0, self._usage_scroll + delta)
                self.draw_screen()
            return
        if view == "inbox":
            self._inbox_key(k, bool(key_event.mods & 1))
            return
        if self.searching:
            ch = getattr(key_event, "text", "") or (key_event.key if len(key_event.key or "") == 1 and not (key_event.mods & ~1) else "")
            if ch and k not in ("ESCAPE", "ENTER", "BACKSPACE", "TAB"):
                self.on_text(ch)                  # with kitty's keyboard protocol, typing arrives as key events with text
            else:
                self._search_key(k)
            return
        if (key_event.key or "") == "/":
            self.searching = True
            self.draw_screen()
            return
        if k == "ESCAPE" and self.query:          # a finished search stays applied until Esc clears it
            self.query = ""
            self._refilter()
            return
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
        elif k == "A" and not shifted:
            self._absorb()
            return
        elif k == "T" and not shifted:
            self._promote()
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
                self._pointer("ew-resize" if over else "")     # the resize cursor, like a split border
                self.draw_screen()
        super().on_mouse_event(mouse_event)

    def _pointer(self, shape: str) -> None:
        """Pointer-shape protocol (OSC 22): `=name` sets it, `=` alone puts the default back."""
        try:
            self.write(f"\x1b]22;={shape}\x1b\\")
            self.flush()
        except Exception:
            pass

    def _resize_panel(self, cell_x: int, final: bool = False) -> None:
        if not self._alive:
            return
        cols = deck.drag_columns(cell_x)
        if self._throttle.should_send(time.monotonic(), cols, final):
            self._resize_worker.submit((cols, final))

    def _perform_resize(self, request) -> None:
        cols, final = request
        try:
            r = subprocess.run(["kitten", "@", "--to", f"unix:{_PANEL_SOCK}", "resize-os-window",
                                "--action=os-panel", "--incremental", f"columns={cols}"],
                               capture_output=True, text=True, timeout=3)
            if r.returncode != 0 or os.environ.get("KITTYMUX_DEBUG"):
                _log_line(f"panel resize to {cols} rc={r.returncode} final={final} "
                          f"out={r.stdout.strip()[:100]!r} err={r.stderr.strip()[:200]!r}")
        except Exception:
            _log_error()
        finally:
            if final:
                try:
                    _STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
                    (_STATE_DIR / "panel-columns").write_text(str(cols))
                except OSError:
                    pass

    def _row_at(self, y: int) -> int:
        return deck.row_at(self.snap.items, self.scroll, self._avail(), y - 2)

    def _pane_at(self, y: int) -> tuple:
        return deck.pane_at(self.snap.items, self.scroll, self._avail(), y - 2)

    def _foot_hit(self, mouse_event):
        """(index, token) of the keycap under the pointer, else None."""
        if mouse_event.cell_y != getattr(self, "_foot_y", -1):
            return None
        for x0, x1, token, i in getattr(self, "_foot_regions", []):
            if x0 <= mouse_event.cell_x < x1:
                return i, token
        return None

    def on_mouse_move(self, mouse_event) -> None:
        hit = self._foot_hit(mouse_event)
        hot = hit[0] if hit else None
        if hot != getattr(self, "_foot_hot", None):
            self._foot_hot = hot                              # a keycap lights up under the pointer: it is a button before it is pressed
            self.draw_screen()
        if hit or getattr(self, "_view", "agents") != "agents":
            return
        if mouse_event.cell_x >= self._geom()[2]:
            return
        idx = self._row_at(mouse_event.cell_y)
        hover = self._pane_at(mouse_event.cell_y) if idx < 0 else (-1, -1)
        if hover[0] >= 0:                                    # a child line: select its tab, preview THAT pane
            idx = hover[0]
        if idx >= 0 and (idx != self.sel or hover != self._hover_pane):
            self.sel, self._hover_pane = idx, hover
            self._request_preview(delay=True)
            self.draw_screen()

    def on_click(self, mouse_event) -> None:
        x, y = mouse_event.cell_x, mouse_event.cell_y
        view = getattr(self, "_view", "agents")
        hit = self._foot_hit(mouse_event)
        if hit and not (self.searching and view == "agents"):
            self._press(hit[1])
            return
        if y == 1 and not self.searching:                              # the tab strip, in every view
            for x0, x1, name in self._tab_regions:
                if x0 <= x < x1:
                    if name != view:
                        self._set_view(name)
                    return
            return
        if view == "usage":
            for x0, x1, y0, y1, idx in self._usage_regions:
                if x0 <= x < x1 and y0 <= y < y1:
                    self._usage_sel, self._usage_scroll = idx, 0
                    self.draw_screen()
                    return
            return
        if view == "inbox":
            chips, cards, buttons = self._inbox_regions
            for x0, x1, by, idx, act in buttons:
                if y == by and x0 <= x < x1:
                    self._inbox_sel = idx
                    self._inbox_act(act, idx)
                    return
            for x0, x1, cy, filt in chips:
                if y == cy and x0 <= x < x1:
                    self._inbox_filter, self._inbox_sel = filt, 0
                    self.draw_screen()
                    return
            for y0, y1, idx in cards:
                if y0 <= y < y1:
                    self._inbox_sel = idx
                    self.draw_screen()
                    return
            return
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

    def _promote(self) -> None:
        """`t`: the hovered pane (else the tab's focused pane) of a split tab becomes its own tab — the keyboard/deck
        twin of dragging a pane's title bar onto the bar's empty space."""
        win = deck.promote_target(self.snap.rows, self.sel, self._hover_pane)
        if not win:
            return
        _rc("detach-window", "--match", f"id:{win}", "--target-tab", "new")
        _rc("focus-window", "--match", f"id:{win}")
        if not _PANEL:
            self.quit_loop()
        else:
            self._request_refresh()

    def _absorb(self) -> None:
        """`a`: the selected tab's panes become splits of the tab you are in (reversible with
        ctrl+alt+shift+d on a pane). The emptied tab closes itself."""
        ids, target = deck.absorb_plan(self.snap.rows, self.sel)
        if not ids:
            return
        # One `detach-window` for every window splits the same pane again and again (7-column slivers). The join kitten places each pane next to its
        # old neighbour — the same mover `ctrl+alt+shift+j` uses, run from the selected tab's window so it moves THAT tab.
        _rc("kitten", "--match", f"id:{ids[0]}", _JOIN_KIT, "--to", str(target), "--side", "auto")
        _rc("focus-window", "--match", f"id:{ids[0]}")
        if not _PANEL:
            self.quit_loop()
        else:
            self._request_refresh()

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
    finally:
        handler.finalize()
    return ""


@result_handler()
def handle_result(args: list[str], answer: str, target_window_id: int, boss: BossType) -> None:
    pass
