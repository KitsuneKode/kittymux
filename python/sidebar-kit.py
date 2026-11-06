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
import kittymux_panelfocus  # noqa: E402
import kittymux_panelhit as panelhit  # noqa: E402
import kittymux_helpview  # noqa: E402
import kittymux_deck as deck  # noqa: E402
import kittymux_git  # noqa: E402
import kittymux_theme  # noqa: E402
import kittymux_inbox  # noqa: E402
import kittymux_inboxview  # noqa: E402
import kittymux_settingsview  # noqa: E402
import kittymux_switches  # noqa: E402
import kittymux_meters  # noqa: E402
import kittymux_ui  # noqa: E402
import kittymux_usageview  # noqa: E402
import kittymux_place  # noqa: E402
import kittymux_titles  # noqa: E402
import kittymux_files  # noqa: E402
import kittymux_progress  # noqa: E402
import kittymux_layout  # noqa: E402

_STATE_DIR = Path(os.environ["KITTYMUX_STATE"]) if os.environ.get("KITTYMUX_STATE") else \
    Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "kittymux"
_ERR_LOG = _STATE_DIR / "sidebar-kit-err.log"

_ICON_BRANCH = ""
_ICON_FOLDER = ""
_RAIL = "▌"
_STALE_AFTER = 15.0
_PR_TTL = 120.0
_REFRESH_EVERY = 1.5
_HELP_SLOT = 999               # the `?` keycap is not one of a view's buttons: it has its own hover slot
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
    __slots__ = ("rows", "items", "current_session", "source", "query", "open_tabs")

    def __init__(self, rows: list, current_session: str, query: str = "", open_tabs=None):
        self.source, self.query, self.open_tabs = rows, query, open_tabs
        groups = deck.filter_groups(deck.group_rows(rows, current_session), query)   # indexes are assigned BEFORE filtering
        self.items, self.rows = deck.flatten(groups, current_session, open_tabs)
        self.current_session = current_session

    def with_query(self, query: str) -> "Snapshot":
        return Snapshot(self.source, self.current_session, query, self.open_tabs)

    def with_open(self, open_tabs) -> "Snapshot":
        return Snapshot(self.source, self.current_session, self.query, None if open_tabs is None else frozenset(open_tabs))


class Collector:
    """Builds a Snapshot from `kitty @ ls`. Runs on a worker thread only."""

    def __init__(self):
        self._pr = PrCache()
        self._tidy = True                           # the `titles` switch, read once per collect

    def branch(self, cwd: str) -> str:
        gi = kittymux_git.info(cwd)                 # reads .git/HEAD; no subprocess
        return "" if gi is None or gi.branch == "detached" else gi.branch

    def _project(self, cwd: str) -> str:
        """The repo or folder a directory belongs to (what a tab is called when its title says nothing); "~" for home, "" when unknown."""
        if not cwd:
            return ""
        try:
            return kittymux_place.facts(cwd, kittymux_git.info(cwd), os.path.expanduser("~")).project
        except Exception:
            return ""

    def _pane(self, w: dict, active_id: int, panes: dict, now: float) -> deck.PaneData:
        name, tool = kittymux_agents.identify(w)
        agent = kittymux_agents.AGENTS.get(name) if name else None
        if w["id"] == active_id:
            state = kittymux_agents.resolve_status(panes.get(str(w["id"])), agent is not None, now, _STALE_AFTER)
        else:
            state = kittymux_agents.fresh_verdict(panes.get(str(w["id"])), now)
        # a pane row says what RUNS there (an agent, a command, the shell): its tab row already names the repo, and two panes
        # in one repo used to read "website" twice. The window title is the fallback when kitty reports no process.
        title = kittymux_agents.running_label(w)
        if not title:
            title = (w.get("title") or "").strip() or _short_home(w.get("cwd", ""))
            if self._tidy:
                title = kittymux_titles.tidy(title, name, self._project(w.get("cwd", ""))).text or title
        return deck.PaneData(win_id=w["id"], glyph=agent.glyph if agent else kittymux_agents.TOOLS.get(tool, ""),
                             agent=name or "", tool=bool(tool and not agent), state=state,
                             title=kittymux_agents.strip_title_prefix(title), active=w["id"] == active_id, cwd=w.get("cwd", ""))

    def collect(self) -> Snapshot | None:
        try:
            data = json.loads(_rc("ls"))
        except Exception:
            return None
        panes = _panes_state(data)
        try:
            self._tidy = kittymux_features.enabled("titles", str(_STATE_DIR))
        except Exception:
            self._tidy = True
        children = deck.children_map(_proc_ppids())
        listeners = _listeners()
        reports = _progress_reports(data)
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
                raw_title = kittymux_agents.strip_agent_prefix(tab.get("title") or "", name)
                shown = kittymux_titles.tidy(tab.get("title") or "", name, self._project(cwd)).text if self._tidy else raw_title
                try:
                    progress = reports.get(tab.get("id")) or kittymux_progress.from_ls(tab, wins)
                except Exception:
                    progress = None
                rows.append(deck.RowData(
                    tab_id=tab["id"], win_id=jump_to, session=session,
                    title=shown or raw_title, raw_title=raw_title,
                    glyph=agent.glyph if agent else kittymux_agents.TOOLS.get(tool_name, ""),
                    tool=bool(tool_name and not agent),
                    agent=name or "", branch=branch, cwd=cwd,
                    panes=len(wins), status=status, unread=unread, current=current,
                    msg=kittymux_agents.resolve_msg(panes.get(str(deciding or aw["id"])), st) if st else "",
                    age=(lambda e: kittymux_agents.state_age(st, e.get("ts_state"), now, reset_at=e.get("reset_at"), wall=time.time()))(panes.get(str(deciding or aw["id"])) or {}) if st else "",
                    pr=self._pr.get(cwd, branch), ports=ports, pane_rows=pane_rows,
                    win_ids=tuple(w["id"] for w in wins), progress=progress))
        return Snapshot(rows, current_session)


def _kitty_pid(data: list) -> int:
    """The kitty this panel is drawing for: the same process `_panes_state` reads, or 0 when it cannot be checked."""
    try:
        pid = os.getppid()
        if _TARGET:
            pid = int(os.environ.get("KITTYMUX_TARGET_PID", "0"))
            if pid <= 0 or deck.target_pid(data) != pid:
                return 0
        return pid
    except Exception:
        return 0


def _progress_reports(data: list) -> dict:
    """OSC 9;4 the bar published for this kitty. Missing file, or a future `ls` that carries progress itself."""
    try:
        pid = _kitty_pid(data)
        if not pid:
            return {}
        return kittymux_progress.load_reports(_STATE_DIR / f"progress-{pid}.json")
    except Exception:
        return {}


class _PxOut:
    """Graphics commands join the kitten's own write buffer. flush is the loop's job."""

    def __init__(self, handler):
        self.handler = handler

    def write(self, data: str) -> None:
        self.handler.write(data)

    def flush(self) -> None:
        pass


class _GfxProbe:
    """Kitty delivers graphics replies only to the image manager. This one never touches /tmp and never hangs."""

    def __init__(self, handler):
        self.handler = handler

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def handle_response(self, apc) -> None:
        try:
            self.handler._gfx_reply(apc)
        except Exception:
            pass


class Sidebar(Handler):
    mouse_tracking = MouseTracking.full
    image_manager_class = _GfxProbe

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
        self._inbox_regions = ([], [], [])        # (filter chips, cards, buttons) in BODY line coordinates, rebuilt on every draw
        self._inbox_undo = None                   # (ids, expires on the monotonic clock) of the last dismissal, while `z` can still take it back
        self._settings_sel, self._settings_scroll, self._settings_asking, self._settings_notice = 0, 0, None, None
        self._settings_regions = ([], [], [], [])   # (rows, state pills, presets, confirm buttons) in BODY line coordinates, rebuilt on every draw
        self._settings_apply_handle = None          # the coalesced reload of the running kitties after a change
        self._tab_regions = []
        self._preview_timer = None
        self._preview_rects = ()
        self._hover_pane = (-1, -1)             # (row, pane) of the child line under the pointer
        self._help = False                      # the `?` card is showing instead of the view body
        self._open = None                       # tab ids whose panes are listed under them; None until the first snapshot (then: the tab you are in)
        self.query, self.searching, self.full = "", False, None     # the `/` search
        self._gfx = None                        # None until the graphics probe, then "wait" | "ok" | "no"
        self._px = None
        self._px_active = False
        self._px_sig = None
        self._px_hits = []
        self._px_scroll = 0.0
        self._px_hover = None
        self._px_hpane = None
        self._px_sel_key = None
        self._px_model = None
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
        self._drop_cover()
        if self._preview_timer is not None:
            self._preview_timer.cancel()
            self._preview_timer = None
        if hasattr(self, "_preview_worker"):
            self._preview_worker.close()
        if hasattr(self, "_resize_worker"):
            self._resize_worker.close(drain=True)  # release writes must outlive a closing UI
        if self._can_drag():
            self._pointer("")
        self._px_clear()

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
            else:
                self._release_grab()
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
        self._help = False
        self._foot_hot = None
        if view != "settings":
            self._settings_asking = None             # a question left open does not wait for you in another view
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
        """The strip: four pills (the picked one carries its name, the others an icon and a count). `hint` rides at the right edge when the
        strip leaves room for it."""
        view = getattr(self, "_view", "agents")
        items = [("▦", "Agents", view == "agents", 0), ("◔", "Usage", view == "usage", 0),
                 ("✉", "Inbox", view == "inbox", kittymux_inboxview.unread(self._inbox)), ("⚙", "Settings", view == "settings", 0)]
        hint_w = _cells(hint) + 1 if hint else 0
        room = width - hint_w if hint and width - hint_w >= self.kit.tab_regions(items, width)[-1][1] + 2 else width      # the hint only rides along when the pills leave room
        regions = self.kit.tab_regions(items, room)
        self._tab_regions = [(a, b, name) for (a, b), name in zip(regions, ("agents", "usage", "inbox", "settings"))]
        line = self.kit.tabs(items, room)
        if room != width:
            line = line + [kittymux_ui.S(hint + " ", self.pal.faint, self.pal.bar)]
        return self._ansi(line)

    def _footer(self, lead: list, pairs: list, width: int) -> str:
        """Clickable keycaps after an optional lead (e.g. "+3 more"). Records where each drew so a click or a hover can find it; the one the
        pointer is on lights up."""
        pairs = [x if len(x) >= 3 else (x[0], x[1], None) for x in pairs]          # (key, label[, token[, short label]]): no token = a hint, not a button
        lead_w = kittymux_ui.line_cells(lead, self.kit.cells)
        hot = getattr(self, "_foot_hot", None)
        help_cap, help_w = [], 0
        if width - lead_w >= 18:                       # a small `?` at the right edge: always there, never squeezed out by the buttons
            p = self.pal
            lit = hot == _HELP_SLOT
            help_cap = [kittymux_ui.S(" ? ", p.on_accent if lit else self.kit.ink(p.text, p.card_hi), p.accent if lit else p.card_hi, bold=True)]
            help_w = 3
        line, regions = kittymux_agentsview.action_bar(self.kit, pairs, max(0, width - lead_w - (help_w + 1 if help_w else 0)), hot)
        self._foot_regions = [(x0 + lead_w, x1 + lead_w, token, i) for x0, x1, token, i in regions]
        if help_w:
            gap = width - lead_w - help_w - kittymux_ui.line_cells(line, self.kit.cells)
            line = line + [kittymux_ui.S(" " * max(0, gap), None, self.pal.bar)] + help_cap
            self._foot_regions.append((width - help_w, width, "?", _HELP_SLOT))
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

    def _draw_help(self, cols, height, view):
        width = self._body_width(cols)
        header = self.kit.fit_line([kittymux_ui.S(" keys and gestures", self.kit.ink(self.pal.text, self.pal.bar), self.pal.bar, bold=True)], width, self.pal.bar)
        lines = kittymux_helpview.view(view, width, self.kit)
        self._draw_body(cols, height, header, lines, 0, [("esc", "back", "ESCAPE")])

    def _draw_usage(self, cols, height):
        v = kittymux_usageview.view(self._usage_data, self._usage_history, self._body_width(cols), self._usage_sel, self.kit,
                                    trends=kittymux_usageview.trend_lines(self._usage_trends, max(1, self._body_width(cols) - 6)),
                                    details=self._usage_details)
        self._usage_sel = v.sel
        self._usage_scroll = self._draw_body(cols, height, v.header, v.lines, getattr(self, "_usage_scroll", 0),
                                             [("r", "refresh", "R"), ("d", "details" if not self._usage_details else "hide", "D", "info" if not self._usage_details else "hide"), ("←→", "pick"), ("a", "agents", "A")])
        self._usage_regions = list(v.tiles)

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
        self._inbox_regions = (list(v.chips), list(v.cards), list(v.buttons))

    # ---- the Settings view: the switch catalog (kittymux_switches), edited as flag files in the state directory ----
    def _settings_rows(self) -> list:
        return kittymux_settingsview.rows(str(_STATE_DIR))

    def _settings_ids(self) -> list:
        return kittymux_settingsview.ids_in_order()

    def _settings_row(self, sw_id: str):
        return next((r for r in self._settings_rows() if r.sw.id == sw_id), None)

    def _settings_say(self, sw_id: str, text: str, tone: str = "ok") -> None:
        self._settings_notice = (sw_id, text, tone)

    def _settings_key(self, k: str, shifted: bool) -> None:
        ids = self._settings_ids()
        cur = ids[max(0, min(self._settings_sel, len(ids) - 1))]
        if k == "ESCAPE":
            if self._settings_asking:
                self._settings_asking = None
                self.draw_screen()
            else:
                self._set_view("agents")
            return
        if k == "Q":
            self.quit_loop()
            return
        if k in ("A",):
            self._set_view("agents")
            return
        self._settings_notice = None
        if k in ("J", "DOWN", "TAB") and not (k == "J" and shifted):
            self._settings_move(1)
        elif k in ("K", "UP"):
            self._settings_move(-1)
        elif k == "G":
            self._settings_sel, self._settings_asking = (len(ids) - 1 if shifted else 0), None
        elif k in (" ", "SPACE", "ENTER"):
            if self._settings_asking and k == "ENTER":
                self._settings_confirm()
                return
            self._settings_toggle(cur)
            return
        elif k == "P":
            self._settings_cycle_preset(-1 if shifted else 1)
            return
        elif k == "R":
            self._settings_reset(cur, group=shifted)
            return
        self.draw_screen()

    def _settings_move(self, delta: int) -> None:
        n = len(self._settings_ids())
        self._settings_sel = max(0, min(n - 1, self._settings_sel + delta))
        self._settings_asking = None

    def _settings_toggle(self, sw_id: str) -> None:
        row = self._settings_row(sw_id)
        if row is None:
            return
        if row.sw.status == kittymux_switches.PLANNED:
            self._settings_say(sw_id, "Not built yet: nothing reads it today.", "error")
        elif kittymux_settingsview.locked(row):
            self._settings_say(sw_id, f"Held by {row.what} in your environment: kittymux does not edit your shell.", "error")
        elif kittymux_settingsview.needs_confirm(row) and self._settings_asking != sw_id:
            self._settings_asking = sw_id
        else:
            self._settings_asking = None
            self._settings_set(sw_id, not row.on)
            return
        self.draw_screen()

    def _settings_confirm(self) -> None:
        sw_id, self._settings_asking = self._settings_asking, None
        if sw_id:
            self._settings_set(sw_id, True)
        else:
            self.draw_screen()

    def _settings_set(self, sw_id: str, on: bool) -> None:
        try:
            kittymux_switches.set_switch(str(_STATE_DIR), sw_id, on)
        except OSError as e:
            self._settings_say(sw_id, f"Cannot save: {e.strerror or e}", "error")
        else:
            self._settings_say(sw_id, "Saved. Applying…")
            self._settings_changed()
        self.draw_screen()

    def _settings_cycle_preset(self, step: int) -> None:
        names = list(kittymux_settingsview.PRESET_NAMES)
        now = kittymux_settingsview.current_preset(self._settings_rows())
        name = names[(names.index(now) + step) % len(names)] if now in names else names[0 if step > 0 else -1]
        self._settings_preset(name)

    def _settings_preset(self, name: str) -> None:
        try:
            kittymux_features.apply_preset(str(_STATE_DIR), name)
        except (OSError, ValueError) as e:
            self._settings_say("", f"Cannot apply {name}: {getattr(e, 'strerror', None) or e}", "error")
        else:
            self._settings_say("", f"Preset {name} applied.")
            self._settings_changed()
        self.draw_screen()

    def _settings_reset(self, sw_id: str, group: bool = False) -> None:
        ids = [sw_id]
        if group:
            sw = kittymux_switches.get(sw_id)
            ids = [s.id for s in kittymux_switches.CATALOG if s.group == sw.group]
        try:
            gone = kittymux_switches.reset(str(_STATE_DIR), ids)
        except OSError as e:
            self._settings_say(sw_id, f"Cannot reset: {e.strerror or e}", "error")
        else:
            self._settings_say(sw_id, "Back to the default." if gone else "Already the default.")
            if gone:
                self._settings_changed()
        self.draw_screen()

    def _settings_changed(self) -> None:
        """Reload the running kitties once, after the last of a burst of changes (ten quick toggles are one reload), never on the UI thread."""
        if self._settings_apply_handle is not None:
            self._settings_apply_handle.cancel()
        self._settings_apply_handle = self.asyncio_loop.call_later(0.6, self._settings_apply)

    def _settings_apply(self) -> None:
        self._settings_apply_handle = None
        root = Path(deck.__file__).resolve().parent.parent

        def work() -> None:
            text = ""
            try:
                r = subprocess.run([str(root / "bin" / "kittymux"), "settings", "apply"], capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
                text = (r.stdout or "").strip().splitlines()[-1] if r.returncode == 0 and (r.stdout or "").strip() else "Saved."
            except Exception:
                text = "Saved. The bar picks it up on its next redraw."
            self._post(self._settings_applied, text)

        threading.Thread(target=work, daemon=True).start()

    def _settings_applied(self, text: str) -> None:
        if not self._alive:
            return
        n = self._settings_notice
        if n and n[2] == "ok":
            self._settings_notice = (n[0], text, "ok")
        if getattr(self, "_view", "agents") == "settings":
            self.draw_screen()

    def _settings_click(self, x: int, y: int) -> None:
        rows_, pills, presets, buttons = self._settings_regions
        scroll = self._settings_scroll
        for x0, x1, by, act in buttons:
            if panelhit.hit_body_row(x, y, scroll, x0, x1, by):
                if act == "confirm":
                    self._settings_confirm()
                else:
                    self._settings_asking = None
                    self.draw_screen()
                return
        for x0, x1, py, name in presets:
            if panelhit.hit_body_row(x, y, scroll, x0, x1, py):
                self._settings_preset(name)
                return
        ids = self._settings_ids()
        for x0, x1, py, sw_id in pills:
            if panelhit.hit_body_row(x, y, scroll, x0, x1, py):
                self._settings_sel = ids.index(sw_id)
                self._settings_notice = None
                self._settings_toggle(sw_id)
                return
        for y0, y1, sw_id in rows_:
            if panelhit.hit_body_lines(y, scroll, y0, y1):
                if self._settings_sel != ids.index(sw_id):
                    self._settings_asking = None
                self._settings_sel = ids.index(sw_id)
                self._settings_notice = None
                self.draw_screen()
                return

    def _draw_settings(self, cols, height):
        rows_ = self._settings_rows()
        v = kittymux_settingsview.view(rows_, self._settings_sel, self._body_width(cols), self.kit, asking=self._settings_asking, notice=self._settings_notice)
        self._settings_sel = v.sel
        page, top = max(1, height - 3), self._settings_scroll
        picked = next(((y0, y1) for y0, y1, i in v.rows if i == v.ids[v.sel]), None)
        if picked:                                                         # keep the picked row (and what it opened) on screen
            y0, y1 = picked
            top = 0 if v.sel == 0 else y0 - 1 if y0 < top + 1 else y1 - page if y1 > top + page else top
        footer = [("␣", "toggle", "SPACE"), ("p", "preset", "P"), ("r", "reset", "R"), ("j k", "move"), ("esc", "back", "ESCAPE")]       # buttons first: a narrow panel drops from the right
        self._settings_scroll = self._draw_body(cols, height, v.header, v.lines, top, footer)
        self._settings_regions = (list(v.rows), list(v.toggles), list(v.presets), list(v.buttons))

    def _apply(self, snap) -> None:
        self._collecting = False
        if not self._alive or snap is None:
            return
        keep = self.snap.rows[self.sel].tab_id if self.snap.rows else None
        hovered = self.preview_for if self._hover_pane[0] == self.sel else 0
        alive = {r.tab_id for r in snap.rows}
        if self._open is None:
            self._open = {r.tab_id for r in snap.rows if r.current and len(r.pane_rows) >= 2}      # the first look: your own tab is open, the rest are one line each
        self._open &= alive                      # a closed tab does not keep a seat
        snap = snap.with_open(self._open)        # panes appear under a split tab only when it is open: nothing moves under the pointer by itself
        self.full = snap                         # the unfiltered view; self.snap is what the `/` search leaves of it
        self.snap = snap.with_query(self.query) if self.query else snap
        snap = self.snap
        self._clear_pointer_hover()              # row indices changed under it
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

    # ---- working glyph: one redraw per step, only while something is working ----
    def _schedule_spin(self) -> None:
        if self._deckpx_on():                    # the spinner is a kitty animation; a timer here would spend idle CPU
            return
        if getattr(self, "_spin_pending", False) or not self._alive or getattr(self, "_view", "agents") != "agents":
            return
        if self._motion() and any(r.status == "working" for r in self.snap.rows):
            self._spin_pending = True
            # one redraw per step of the working glyph (kittymux_agents.SPINNER_FPS, every 3 s): a 10 Hz redraw here repainted
            # an unchanged screen and kept this kitty at about a quarter of a core while any agent worked
            self.asyncio_loop.call_later(1.0 / kittymux_agents.SPINNER_FPS, self._spin)

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
        if self._deckpx_on() and self.screen_size.cols < 64:
            # the narrow pixel list shows no preview (the pane already shows its prompt): fetch none, and drop one already on its way
            if self._preview_timer is not None:
                self._preview_timer.cancel()
                self._preview_timer = None
            self._preview_worker.invalidate()
            self._preview_inflight = False
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

    # ---- keyboard grab: a summoned panel (exclusive focus) gives the keys back when you are done ----
    def _summoned(self) -> bool:
        if not _PANEL:
            return False
        try:
            return kittymux_panelfocus.parse_mode((_STATE_DIR / "panel-mode").read_text()) == kittymux_panelfocus.SUMMONED
        except OSError:
            return False

    def _release_grab(self) -> None:
        """Hand the keyboard back (`mux-panel dock`), detached: it is a remote-control call and must never block the UI."""
        if not self._summoned():
            return
        root = Path(deck.__file__).resolve().parent.parent
        try:
            subprocess.Popen([str(root / "bin" / "mux-panel"), "dock"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            pass

    def _take_view_request(self) -> None:
        """`kittymux settings open` asks the running panel to show a view by writing its name to `panel-view`: take it once and show it."""
        req = _STATE_DIR / "panel-view"
        try:
            name = req.read_text().strip()
            req.unlink()
        except OSError:
            return
        if name in ("agents", "usage", "inbox", "settings") and name != getattr(self, "_view", "agents"):
            self._set_view(name)

    def _schedule(self) -> None:
        if self._alive:
            self.asyncio_loop.call_later(_REFRESH_EVERY, self._tick)

    def _tick(self) -> None:
        if not self._alive:
            return
        if getattr(self, "_view", "agents") == "usage":
            self._request_usage()
        if _PANEL:
            self._take_view_request()
        if getattr(self, "_view", "agents") == "settings":
            self.draw_screen()                         # a flag file changed by `kittymux settings` or another panel shows here within a tick
        if _PANEL:
            summoned = self._summoned()
            if summoned and not getattr(self, "_was_summoned", False):
                self._last_key = time.monotonic()       # the idle clock starts when the summon does, not at the last key of an earlier visit
            self._was_summoned = summoned
            if kittymux_panelfocus.should_dock("summoned" if summoned else "docked", getattr(self, "_last_key", time.monotonic()), time.monotonic(),
                                               kittymux_panelfocus.idle_limit(os.environ.get("KITTYMUX_PANEL_IDLE_S"))):
                self._last_key = time.monotonic()      # one try per idle period; a failed dock tries again after another one
                self._release_grab()
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
                self._ansi(kittymux_agentsview.context_row(self.kit, r, selected, False, bar_w, home,
                                                            (r.tab_id in (self._open or ())) if len(r.pane_rows) >= 2 else None)))

    def _pane_line(self, r, j: int, bar_w: int, hovered: bool) -> str:
        return self._ansi(kittymux_agentsview.pane_row(self.kit, r, j, hovered, bar_w, self._motion()))

    # ---- the pixel panel covers the cell bar (kittymux_layout.cover) ----------
    # The pixel list repeats every tab of the kitty it watches, so while the panel runs in pixels that kitty's bar is hidden.
    # Tied to the panel's pixel MODE, not the view on screen: flipping to Usage must not resize the user's panes. Settled for
    # COVER_SETTLE_S so a burst (a probe, a switch toggled twice) is one reload. A killed panel is undone by `mux-panel stop`
    # and by the scanner's sweep in the watched kitty.
    COVER_SETTLE_S = 0.8

    def _cover_target(self) -> int:
        try:
            return int(os.environ.get("KITTYMUX_TARGET_PID", "0")) if (_PANEL and _TARGET) else 0
        except ValueError:
            return 0

    def _want_cover(self) -> bool:
        """Cover while this panel can draw the pixel list: the switch on (read live, so turning it off in Settings gives the bar back at
        once), the graphics probe answered, and the last Agents draw fitted in pixels (a panel too small falls back to cells)."""
        if self._cover_target() <= 0:
            return False
        try:
            on = self._deckpx_enabled()
        except Exception:
            on = False
        return (on and getattr(self, "_gfx", None) == "ok" and bool(getattr(self, "_px_fits", False))
                and kittymux_layout.cover_switch_on(str(_STATE_DIR)))

    def _sync_cover(self) -> None:
        want = self._want_cover()
        if want == getattr(self, "_cover_want", False):
            return
        self._cover_want = want
        handle = getattr(self, "_cover_timer", None)
        if handle is not None:
            handle.cancel()
        try:
            self._cover_timer = self.asyncio_loop.call_later(self.COVER_SETTLE_S, self._apply_cover)
        except Exception:
            self._cover_timer = None
            self._apply_cover()

    def _apply_cover(self) -> None:
        self._cover_timer = None
        pid = self._cover_target()
        if pid <= 0:
            return
        try:
            if getattr(self, "_cover_want", False) and self._alive:
                changed = kittymux_layout.cover(str(_STATE_DIR), pid, os.getpid())
            else:
                changed = kittymux_layout.uncover(str(_STATE_DIR), pid, os.getpid())
        except Exception:
            _log_error()
            self._cover_want = None                  # unknown: the next draw tries again
            return
        if changed:
            self._reload_target()

    def _drop_cover(self) -> None:
        handle = getattr(self, "_cover_timer", None)
        if handle is not None:
            handle.cancel()
        self._cover_timer = None
        self._cover_want = False
        pid = self._cover_target()
        try:
            if pid > 0 and kittymux_layout.uncover(str(_STATE_DIR), pid, os.getpid()):
                self._reload_target()
        except Exception:
            _log_error()

    def _reload_target(self) -> None:
        """Re-read the watched kitty's config (its layout geninclude prints the cover). Never waits: the UI stays live."""
        try:
            subprocess.Popen(["kitty", "@", "--to", _TARGET, "load-config"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception:
            _log_error()

    # ---- pixel Agents list (opt-in `deckpx`; the cell list below is unchanged) ----
    def _pxmods(self):
        cached = getattr(self, "_px_mods", None)
        if cached is False:
            return None
        if cached:
            return cached
        try:
            # kitty replaces sys.path after the kitten loads, so a later import would miss the repo
            for _d in (_CONFIG_DIR, _source_dir()):
                if _d and _d not in sys.path:
                    sys.path.insert(0, _d)
            import kittymux_deckadapt
            import kittymux_deckpx
            import kittymux_decktransport
            self._px_mods = (kittymux_deckpx, kittymux_deckadapt, kittymux_decktransport)
        except Exception:
            _log_error()
            try:
                here = _source_dir()
                _log_line("deckpx path " + repr(sys.path[:6]))
                _log_line("deckpx source " + here + " exists=" + str(os.path.exists(os.path.join(here, "kittymux_deckadapt.py"))))
            except Exception:
                _log_error()
            self._px_mods = False
            return None
        return self._px_mods

    def _deckpx_enabled(self) -> bool:
        try:
            on = kittymux_switches.enabled("deckpx", str(_STATE_DIR))
        except Exception:
            on = False
        if on and not getattr(self, "_px_switch", False) and getattr(self, "_gfx", None) == "no":
            self._gfx = None                         # turned back on: ask the terminal once more
        self._px_switch = on
        return on

    def _deckpx_on(self) -> bool:
        return bool(getattr(self, "_px_active", False)) and getattr(self, "_view", "agents") == "agents" and not self._help

    def _px_clear(self) -> None:
        gfx = getattr(self, "_px", None)
        self._px_active = False
        self._px_hot_key = None
        self._px_sig = None
        self._px_hits = []
        self._px_last = None
        self._px_cancel_fade()
        self._px_step_stop()
        if gfx is None:
            return
        self._px = None
        try:
            gfx.close()
        except Exception:
            _log_error()

    def _clear_pointer_hover(self) -> None:
        self._hover_pane = (-1, -1)
        self._px_hover = None
        self._px_hpane = None

    def _gfx_probe(self) -> None:
        self._gfx = "wait"
        self.write("\x1b_Ga=q,i=999,f=24,s=1,v=1;AAAA\x1b\\")
        try:
            self.asyncio_loop.call_later(0.7, self._gfx_timeout)
        except Exception:
            self._gfx = "no"

    def _gfx_timeout(self) -> None:
        if getattr(self, "_gfx", None) == "wait":
            self._px_note("graphics probe timed out")
            self._gfx = "no"
            if self._alive:
                self.draw_screen()

    def _gfx_reply(self, apc) -> None:
        mods = self._pxmods()
        if not mods:
            return
        verdict = mods[1].graphics_verdict(apc, False)
        if verdict == "wait":
            return
        if verdict == "no" and getattr(self, "_gfx", None) != "wait":
            return
        self._gfx = verdict
        if verdict == "ok" and self._alive:
            self.draw_screen()

    def _px_note(self, msg: str) -> None:
        if getattr(self, "_px_noted", False):
            return
        self._px_noted = True
        _log_line("deckpx: " + msg)

    def _px_host(self) -> str:
        host = getattr(self, "_px_host_name", "")
        if not host:
            import socket
            host = (socket.gethostname().split(".")[0] or "this machine")
            self._px_host_name = host
        return host

    def _px_frames(self, deckpx, transport, pal):
        """The working ring's STEP_FRAMES arcs, made once per colour: kitty steps them every STEP_MS, so at rest nothing runs."""
        if getattr(self, "_px_spin_key", None) != (pal.working, pal.bar):
            size, surfs = deckpx.ring_frames(pal, 1)
            self._px_spin_key, self._px_spin_frames = (pal.working, pal.bar), (size, [transport.rgba_of(f) for f in surfs])
        return self._px_spin_frames

    def _px_inside(self, mouse_event) -> bool:
        ch = self.screen_size.cell_height or 1
        return ch <= mouse_event.pixel_y < ch + getattr(self, "_px_h", 0) and 0 <= mouse_event.pixel_x < getattr(self, "_px_w", 0)

    def _px_hit(self, mouse_event):
        mods = self._pxmods()
        if not mods:
            return None
        ch = self.screen_size.cell_height or 1
        return mods[0].hit_at(self._px_hits, mouse_event.pixel_x, mouse_event.pixel_y - ch)

    def _draw_agents_chrome(self, cols, rows_n, bar_w) -> None:
        """Tab strip (or the search line), and the preview column on a wide window. The list, its key hints and the
        bottom are the image: no cell footer and no preview drawer under it."""
        p, w, snap = self.pal, self.write, self.snap
        self._foot_y, self._foot_regions = -1, []
        if self.searching or self.query:
            total = len(self.full.rows) if self.full is not None else len(snap.rows)
            line = [(" / ", p.accent, True), (self.query, p.text, True), ("▏" if self.searching else "", p.accent, False),
                    (f"   {len(snap.rows)}/{total}", p.faint, False)]
            w(set_cursor_position(0, 0) + self._line(line, bar_w, p.surface))
        else:
            w(set_cursor_position(0, 0) + self._tabs_line(bar_w))
        blank = self._seg(" " * bar_w, bg=p.bar)
        for yy in range(1, rows_n):
            w(set_cursor_position(0, yy) + blank)
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

    # the Agents view's key hints, most useful first (a narrow panel drops them from the right); the pixel list draws them itself
    _AGENT_KEYS = (("\u23ce", "jump", "ENTER"), ("/", "find", "/"), ("a", "join", "A"), ("t", "detach", "T"))

    def _draw_agents_px(self) -> bool:
        if not self._deckpx_enabled():
            return False
        mods = self._pxmods()
        if not mods:
            self._px_note("pixel modules did not import")
            return False
        deckpx, adapt, transport = mods
        if getattr(self, "_gfx", None) is None:
            self._gfx_probe()
            return False
        if self._gfx != "ok":
            self._px_note(f"graphics probe is {self._gfx}")
            return False
        cols, rows_n, bar_w = self._geom()
        ss = self.screen_size
        cw, ch = ss.cell_width or 1, ss.cell_height or 1
        # the image runs from under the tab strip to the bottom: the key hints are its own pixels, and there is no preview
        # drawer (the pane already shows its prompt)
        px_w = min(getattr(ss, "width", 0) or bar_w * cw, bar_w * cw)
        px_h = max(0, (rows_n - 1) * ch)
        self._px_w, self._px_h = px_w, px_h
        self._px_fits = not (px_w < 40 or px_h < deckpx.HEADER_END + 40)
        if not self._px_fits:
            return False
        snap = self.snap
        model = adapt.to_model(snap, self.sel, self._hover_pane, self._px_host(), snap.current_session or self._px_host(),
                               project_of=self._collector._project)
        self._px_model = model
        items = deckpx.body_items(model)
        keys = [(k, label) for k, label, _t in self._AGENT_KEYS]
        view_h = deckpx.body_bottom(px_h, keys) - deckpx.HEADER_END
        key = (self.sel, self._hover_pane)
        scroll = getattr(self, "_px_scroll", 0.0)
        if key != getattr(self, "_px_sel_key", None):
            target = adapt.selected_target(model)
            if target:
                scroll = deckpx.scroll_to_item(items, scroll, view_h, target[0], target[1])
            self._px_sel_key = key
        scroll = deckpx.clamp_scroll(scroll, deckpx.content_height(model), view_h)
        self._px_scroll = scroll
        frame = deckpx.Frame(hover=self._px_hover, hover_pane=self._px_hpane, scroll=scroll,
                             hot_key=getattr(self, "_px_hot_key", None))
        motion = self._motion()
        working = any(a.state == "working" or any(c.state == "working" for c in a.children) for a in model.agents) or any(s.state == "working" for s in model.spaces)
        tokens = (self.pal.bg, self.pal.fg, self.pal.bar, self.pal.accent, self.pal.working, self.pal.waiting,
                  self.pal.done, self.pal.alert, self.pal.text, self.pal.muted, self.pal.card, self.pal.card_hi)
        sig = (px_w, px_h, round(scroll, 1), frame.hover, frame.hover_pane, frame.hot_key, model, tokens, motion and working)
        self._draw_agents_chrome(cols, rows_n, bar_w)
        if sig != getattr(self, "_px_sig", None) or getattr(self, "_px", None) is None:
            hits: list = []
            slots: list = []
            resources = getattr(self, "_px_res", None) or deckpx.Resources()
            self._px_res = resources
            surf = deckpx.render(model, self.pal, px_w, px_h, 1, frame, hits=hits, resources=resources,
                                 spinners=slots if motion and working else None, keys=keys)
            if getattr(self, "_px", None) is None:
                self._px = transport.Graphics(_PxOut(self), "auto")
            states = _px_states(model)
            old = getattr(self, "_px_last", None)
            fade = (motion and old is not None and old[1] != states and old[0].get_width() == surf.get_width()
                    and old[0].get_height() == surf.get_height())
            self._px_last = (surf, states)
            if fade:
                # a state changed: cross-fade over ~FADE_MS in FADE_STEPS frames, then the real one. Hover and scroll never fade.
                self._px_fade(deckpx, transport, old[0], surf, slots)
            else:
                self._px_cancel_fade()
                self._px.show(transport.rgba_of(surf), surf.get_width(), surf.get_height(), col=1, row=2, z=1)
                self._px_place_rings(deckpx, transport, slots, cw, ch)
            self._px_hits = hits
            self._px_sig = sig
        self._px_active = True
        self.flush()
        return True

    def _px_place_rings(self, deckpx, transport, slots, cw, ch) -> None:
        if slots:
            size, frames = self._px_frames(deckpx, transport, self.pal)
            positions = [(round(cx - size / 2), round(cy + ch - size / 2)) for cx, cy, _r, _c in slots]
            self._px.spinner(frames, size, positions, (cw, ch), deckpx.STEP_MS, z=2)
            self._px_step_arm(deckpx)
        else:
            self._px.clear_spinner()
            self._px_step_stop()

    def _px_step_arm(self, deckpx) -> None:
        """One timer while a ring is placed: every STEP_MS it moves the rings a quarter turn. None at rest."""
        if getattr(self, "_px_step_handle", None) is None:
            self._px_step_handle = self.asyncio_loop.call_later(deckpx.STEP_MS / 1000.0, self._px_step_tick)

    def _px_step_stop(self) -> None:
        handle = getattr(self, "_px_step_handle", None)
        if handle is not None:
            handle.cancel()
        self._px_step_handle = None

    def _px_step_tick(self) -> None:
        self._px_step_handle = None
        mods = self._pxmods()
        gfx = getattr(self, "_px", None)
        if not self._alive or gfx is None or not mods or not gfx.spinner_ready:
            return
        deckpx = mods[0]
        self._px_step_n = (getattr(self, "_px_step_n", 0) + 1) % deckpx.STEP_FRAMES
        gfx.step(self._px_step_n + 1)
        self._px_step_arm(deckpx)

    def _px_cancel_fade(self) -> None:
        handle = getattr(self, "_px_fade_handle", None)
        if handle is not None:
            handle.cancel()
        self._px_fade_handle = None

    def _px_fade(self, deckpx, transport, old, new, slots) -> None:
        """Show old→new blends FADE_STEPS times, FADE_MS apart in all, then `new` with its rings. One short burst per
        state change: no timer outlives it."""
        self._px_cancel_fade()
        steps = max(1, deckpx.FADE_STEPS)
        gap = deckpx.FADE_MS / 1000.0 / (steps + 1)
        ss = self.screen_size
        cw, ch = ss.cell_width or 1, ss.cell_height or 1

        def step(k: int) -> None:
            self._px_fade_handle = None
            if not self._alive or getattr(self, "_px", None) is None or getattr(self, "_px_last", (None,))[0] is not new:
                return
            if k <= steps:
                blend = deckpx.crossfade(old, new, k / (steps + 1))
                self._px.show(transport.rgba_of(blend), blend.get_width(), blend.get_height(), col=1, row=2, z=1)
                if k == 1:
                    self._px.clear_spinner()
                self.flush()
                self._px_fade_handle = self.asyncio_loop.call_later(gap, step, k + 1)
                return
            self._px.show(transport.rgba_of(new), new.get_width(), new.get_height(), col=1, row=2, z=1)
            self._px_place_rings(deckpx, transport, slots, cw, ch)
            self.flush()

        step(1)

    def _px_click(self, mouse_event) -> None:
        hit = self._px_hit(mouse_event)
        model = getattr(self, "_px_model", None)
        mods = self._pxmods()
        if not hit or model is None or not mods:
            return
        kind, index = hit
        adapt = mods[1]
        if kind == "key":                                # a key hint does exactly what its key does
            token = self._AGENT_KEYS[index][2] if 0 <= index < len(self._AGENT_KEYS) else "?"
            self._press(token)
            return
        if kind == "search":
            self.searching = True
            self.draw_screen()
            return
        if kind == "space":
            return
        if kind == "needs":
            row, pane = adapt.first_waiting(model)
            if row < 0:
                return
            self.sel = row
            self._clear_pointer_hover()
            self.draw_screen()
            self._jump(row, pane)
            return
        row, pane = adapt.hit_target(model, kind, index)
        if row < 0:
            return
        if kind == "toggle":
            self._toggle_open(row)
            return
        self.sel = row
        if kind == "pane":
            self._hover_pane = (row, pane)
            self._px_hover, self._px_hpane = None, index
            self.draw_screen()
            self._jump(row, pane)
            return
        self._clear_pointer_hover()
        self.draw_screen()
        self._jump()

    def _px_move(self, mouse_event) -> None:
        if not self._px_inside(mouse_event):
            if self._px_hover is not None or self._px_hpane is not None or getattr(self, "_px_hot_key", None) is not None:
                self._px_hover = self._px_hpane = self._px_hot_key = None
                self.draw_screen()
            return
        hit = self._px_hit(mouse_event)
        hot = hit[1] if hit and hit[0] == "key" else None
        if hot != getattr(self, "_px_hot_key", None):     # the hint under the pointer lights up: a button before it is pressed
            self._px_hot_key = hot
            self.draw_screen()
            if hot is not None:
                return
        model = getattr(self, "_px_model", None)
        mods = self._pxmods()
        if not hit or model is None or not mods or hit[0] not in ("agent", "pane"):
            if self._px_hover is not None or self._px_hpane is not None:
                self._px_hover = self._px_hpane = None
                self.draw_screen()
            return
        kind, index = hit
        row, pane = mods[1].hit_target(model, kind, index)
        if row < 0:
            return
        if kind == "pane":
            hover, px_h, px_p = (row, pane), None, index
        else:
            hover, px_h, px_p = (-1, -1), index, None
        if row != self.sel or hover != self._hover_pane or px_h != self._px_hover or px_p != self._px_hpane:
            self.sel, self._hover_pane = row, hover
            self._px_hover, self._px_hpane = px_h, px_p
            self._request_preview(delay=True)
            self.draw_screen()

    @Handler.atomic_update
    def draw_screen(self) -> None:
        view = getattr(self, "_view", "agents")
        pixel = False
        if view == "agents" and not self._help:
            try:
                pixel = bool(self._draw_agents_px())
            except Exception:
                _log_error()
                self._gfx = "no"
                self._px_clear()
        if not pixel:
            self._px_clear()
        self._sync_cover()
        if pixel:
            return
        cols, rows_n, bar_w = self._geom()
        p = self.pal
        if self._help:
            self._draw_help(cols, rows_n, view)
            return
        if view == "usage":
            self._draw_usage(cols, rows_n)
            return
        if view == "inbox":
            self._draw_inbox(cols, rows_n)
            return
        if view == "settings":
            self._draw_settings(cols, rows_n)
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
                w(set_cursor_position(0, y + off) + self._ansi(kittymux_agentsview.header_row(self.kit, it.label, it.count, it.current, bar_w, it.attn)))
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
            for j, ln in enumerate(kittymux_agentsview.empty_rows(self.kit, bar_w, self.query)):
                w(set_cursor_position(0, 2 + j) + self._ansi(ln))
        if dr and snap.rows:                      # the preview drawer: what the hovered tab/pane shows right now
            r = snap.rows[self.sel]
            row, pane = self._hover_pane
            pd = r.pane_rows[pane] if row == self.sel and 0 <= pane < len(r.pane_rows) else None
            top = rows_n - dr
            w(set_cursor_position(0, top) + self._line([("─" * bar_w, p.line, False)], bar_w, p.bar))
            who = pd.title if pd else r.title
            w(set_cursor_position(0, top + 1) + self._line(
                [(" " + deck.fit(f"{who} · {_short_home(pd.cwd if pd else r.cwd)}", bar_w - 2, _cells), p.faint, True)], bar_w, p.bar))
            body = deck.tidy_preview(self.preview, dr - 2)
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
        self._clear_pointer_hover()
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
        self._last_key = time.monotonic()
        view = getattr(self, "_view", "agents")
        if self._help:                                          # the `?` card: one keypress closes it, whatever the key
            self._help = False
            self.draw_screen()
            return
        if not self.searching and ((key_event.key or "") == "?" or getattr(key_event, "text", "") == "?" or ((key_event.key or "") == "/" and key_event.mods & 1)):
            self._help = True
            self.draw_screen()
            return
        if not self.searching and k == "U":
            self._set_view("agents" if view == "usage" else "usage")
            return
        if not self.searching and k == "I":
            self._set_view("agents" if view == "inbox" else "inbox")
            return
        if not self.searching and k == "S":
            self._set_view("agents" if view == "settings" else "settings")
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
        if view == "settings":
            self._settings_key(k, bool(key_event.mods & 1))
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
            else:
                self._release_grab()
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
        elif k in ("RIGHT", "L") and not shifted:
            self._toggle_open(self.sel, True)
            return
        elif k in ("LEFT", "H") and not shifted:
            self._toggle_open(self.sel, False)
            return
        elif k == "O" and not shifted:
            self._toggle_open(self.sel)
            return
        elif k == "A" and not shifted:
            self._absorb()
            return
        elif k == "T" and not shifted:
            self._promote()
            return
        else:
            return
        self._clear_pointer_hover()
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
        if self._deckpx_on() and not getattr(self, "_drag", False) and mouse_event.buttons in (MouseButton.WHEEL_UP, MouseButton.WHEEL_DOWN):
            cols = self.screen_size.cols
            over = self._can_drag() and deck.in_grab_zone(mouse_event.pixel_x // max(1, self.screen_size.cell_width), cols)
            if not over:
                step = -48 if mouse_event.buttons == MouseButton.WHEEL_UP else 48
                self._px_scroll = getattr(self, "_px_scroll", 0.0) + step
                self.draw_screen()
                return
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
        if self._deckpx_on():
            self._px_move(mouse_event)
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
        if self._help:
            self._help = False
            self.draw_screen()
            return
        if y == (0 if self._deckpx_on() else 1) and not self.searching:  # the tab strip: row 0 when the list is pixels, else under the summary
            for x0, x1, name in self._tab_regions:
                if x0 <= x < x1:
                    if name != view:
                        self._set_view(name)
                    return
            return
        if view == "usage":
            scroll = self._usage_scroll
            for x0, x1, y0, y1, idx in self._usage_regions:
                if panelhit.hit_in_body(x, y, scroll, x0, x1, y0, y1):
                    self._usage_sel, self._usage_scroll = idx, 0
                    self.draw_screen()
                    return
            return
        if view == "settings":
            self._settings_click(x, y)
            return
        if view == "inbox":
            chips, cards, buttons = self._inbox_regions
            scroll = self._inbox_scroll
            for x0, x1, by, idx, act in buttons:
                if panelhit.hit_body_row(x, y, scroll, x0, x1, by):
                    self._inbox_sel = idx
                    self._inbox_act(act, idx)
                    return
            for x0, x1, filt in chips:
                if panelhit.hit_body_row(x, y, scroll, x0, x1, 0):
                    self._inbox_filter, self._inbox_sel = filt, 0
                    self.draw_screen()
                    return
            for y0, y1, idx in cards:
                if panelhit.hit_body_lines(y, scroll, y0, y1):
                    self._inbox_sel = idx
                    self.draw_screen()
                    return
            return
        if mouse_event.cell_x >= self._geom()[2]:
            return
        if self._deckpx_on() and self._px_inside(mouse_event):
            self._px_click(mouse_event)
            return
        line_row, line = deck.row_line_at(self.snap.items, self.scroll, self._avail(), mouse_event.cell_y - 2)
        if line_row >= 0 and line == 1 and 1 <= x <= 3 and len(self.snap.rows[line_row].pane_rows) >= 2:
            self._toggle_open(line_row)                  # the ▸ / ▾ in front of the context line: open or close this tab's panes (it does not jump)
            return
        row, pane = self._pane_at(mouse_event.cell_y)
        if row >= 0:
            self.sel = row
            self._hover_pane = (row, pane) if pane >= 0 else (-1, -1)
            self._jump(row, pane)
            return
        idx = self._row_at(mouse_event.cell_y)
        if idx >= 0:
            self.sel = idx
            self._clear_pointer_hover()
            self._jump()

    def on_resize(self, new_size) -> None:
        self.screen_size = new_size
        self._px_clear()
        self._clamp()
        self.draw_screen()

    def _toggle_open(self, row: int, to=None) -> None:
        """Show or hide the panes of split tab `row`. Only a click on its ▸/▾ or →/←/o does this: hovering and an agent starting to ask never do."""
        if not (0 <= row < len(self.snap.rows)) or len(self.snap.rows[row].pane_rows) < 2:
            return
        tab = self.snap.rows[row].tab_id
        opened = tab in self._open
        want = (not opened) if to is None else bool(to)
        if want == opened:
            return
        (self._open.add if want else self._open.discard)(tab)
        self.full = self.full.with_open(self._open) if self.full is not None else None
        self.snap = self.snap.with_open(self._open)
        self._clear_pointer_hover()
        self.sel = next((i for i, r in enumerate(self.snap.rows) if r.tab_id == tab), self.sel)
        self._clamp()
        self._request_preview()
        self.draw_screen()

    def _act(self, *steps: tuple[str, ...]) -> None:
        """Run remote-control steps for a deck action (promote, absorb, jump), then hand the keyboard back.

        In the docked panel the calls go over a socket with a 4 s timeout EACH and a join takes a moment: on the UI thread that froze every click and key
        for seconds after a pull. They run on a worker there. The overlay deck talks over its own tty channel, which only the loop thread may use, and it closes
        itself afterwards, so it runs them inline. The grab goes back afterwards in both cases: focus moved to another window, and an exclusive grab that stays
        up sends the user's next keys to the panel instead (up to IDLE_DOCK_S of 'my keyboard stopped working')."""
        if not _PANEL:
            for step in steps:
                _rc(*step)
            self.quit_loop()
            return

        def work() -> None:
            try:
                for step in steps:
                    _rc(*step)
            except Exception:
                _log_error()
            finally:
                self._post(self._after_action)

        threading.Thread(target=work, daemon=True).start()

    def _after_action(self) -> None:
        if self._alive:
            self._release_grab()
            self._request_refresh()

    def _promote(self) -> None:
        """`t`: the hovered pane (else the tab's focused pane) of a split tab becomes its own tab — the keyboard/deck
        twin of dragging a pane's title bar onto the bar's empty space."""
        win = deck.promote_target(self.snap.rows, self.sel, self._hover_pane)
        if not win:
            return
        self._act(("detach-window", "--match", f"id:{win}", "--target-tab", "new"), ("focus-window", "--match", f"id:{win}"))

    def _absorb(self) -> None:
        """`a`: the selected tab's panes become splits of the tab you are in (reversible with
        ctrl+alt+shift+d on a pane). The emptied tab closes itself."""
        ids, target = deck.absorb_plan(self.snap.rows, self.sel)
        if not ids:
            return
        # One `detach-window` for every window splits the same pane again and again (7-column slivers). The join kitten places each pane next to its
        # old neighbour — the same mover `ctrl+alt+shift+j` uses, run from the selected tab's window so it moves THAT tab.
        self._act(("kitten", "--match", f"id:{ids[0]}", _JOIN_KIT, "--to", str(target), "--side", "auto"), ("focus-window", "--match", f"id:{ids[0]}"))

    def _jump(self, row: int = -1, pane: int = -1) -> None:
        if not self.snap.rows:
            return
        r = self.snap.rows[self.sel if row < 0 else row]
        win = r.pane_rows[pane].win_id if 0 <= pane < len(r.pane_rows) else r.win_id
        steps = [("focus-tab", "--match", f"id:{r.tab_id}")]
        if win:
            steps.append(("focus-window", "--match", f"id:{win}"))
        self._act(*steps)


def _px_states(model) -> tuple:
    """What a cross-fade watches: each tab's and pane's state. Hover, scroll and selection are not in it."""
    return tuple((a.row, a.state, tuple(c.state for c in a.children)) for a in model.agents)


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
