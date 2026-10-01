# kittymux barsize — drag the vertical tab bar's inner edge to resize it.
#
# Kitty routes every mouse event on the tab bar to TabManager.handle_tab_bar_mouse(), and
# our watcher (pane-state.py) runs inside kitty's own process, so it can wrap that method:
# a press near the bar's inner edge starts a drag, pointer motion becomes a new width
# (tab_title_max_length), and release saves it as this kitty's layout so it survives
# reloads. Everything else is passed straight through to kitty.
#
# Constraints (see kittymux_layout.width_from_pointer): never narrower than WIDTH_MIN, never
# wider than half the window or the hard cap. Dragging never switches modes silently — a
# drag from the slim rail promotes it to the full sidebar, like the width keys do.

import copy
import os
import subprocess
import sys
import time
import types

_here = globals().get("__file__")
for _d in (os.environ.get("KITTY_CONFIG_DIRECTORY") or os.path.expanduser("~/.config/kitty"),
           (os.path.dirname(os.path.realpath(_here)) if _here else "")):   # own dir inserted LAST → searched FIRST
    if _d and _d not in sys.path:
        sys.path.insert(0, _d)
import kittymux_layout as L  # noqa: E402

# Live state lives in sys.modules, NOT in module globals: changing the width makes kitty re-run
# tab_bar.py, which reloads this module — globals would be wiped in the middle of a drag (the
# first motion event applied a width, the second found no drag and the mouse was given back).
_DEFAULTS = dict(
    hot=False,              # pointer over the handle or dragging — the tab bar draws it lit
    drag=None,              # active drag: {"tm": TabManager, "edge": "left|right", "width": int, "last": float}
    last_apply=0.0,
    last_cost=0.0,          # how long the last width change took (s): the next one waits at least this long
    installed=False,
    toggle_down=False,      # a press landed on the collapse/expand button; the release decides
    peek_down=0,            # tab id under a right-button press; the release opens its peek card
    watchdog=None,          # timer id
    trail=None,             # timer id of the pending "apply the latest pointer position" (see _drag_to)
    edge_installed=False,   # the native divider hooks (kitty.borders.set_borders_rects, Boss.drag_resize_*) are in place
    pal_key=None,           # cache of the theme palette the native divider is coloured from
    pal=None,
    tap=None,               # the left press on a tab awaiting its release: (tab id, x, y, monotonic time) — see _tap_before
    tap_drag=False,         # a tab drag had already started when the release arrived
)
_S = sys.modules.setdefault("_kittymux_barsize_rt", types.SimpleNamespace(**_DEFAULTS))
for _k, _v in _DEFAULTS.items():        # a namespace made by an OLDER version of this file lacks the newer fields
    if not hasattr(_S, _k):
        setattr(_S, _k, _v)
_APPLY_MIN = 0.016         # seconds: at most ~60 width changes a second, and never faster than 1.5x what the last one cost
                            # (a re-layout resizes every pane's terminal: queueing them faster than they finish is what janks)


def _debug(text: str) -> None:
    """KITTYMUX_DEBUG=1: record exceptions from this module (it must never raise into kitty)."""
    if os.environ.get("KITTYMUX_DEBUG"):
        try:
            with open(os.path.join(L.state_dir(), "barsize-debug.log"), "a") as f:
                f.write(text + "\n")
        except Exception:
            pass


def is_hot() -> bool:
    return bool(_S.hot)


def _set_hot(tm, value: bool) -> None:
    if _S.hot != value:
        _S.hot = value
        try:
            tm.update_tab_bar_data()
            tm.mark_tab_bar_dirty()
            from kitty.fast_data_types import mark_os_window_dirty, wakeup_main_loop
            if _S.edge_installed and tm.active_tab is not None:
                tm.active_tab.relayout_borders()           # the native divider's colours follow the lit state
            mark_os_window_dirty(tm.os_window_id)          # the lit separator must paint now, not at the next blink
            wakeup_main_loop()
        except Exception:
            pass


def apply_width(boss, n: int, final: bool = True) -> None:
    """Change tab_title_max_length live for THIS kitty instance (all its OS windows).

    `final=False` is the per-mouse-event path while dragging: re-layout the bar, redraw it and re-flow only the tab you are looking at
    (every other tab's panes are invisible, and re-flowing 20 of them was ~30 % of the cost). The release applies `final=True`, which
    re-flows everything once, so no tab is left with a stale size."""
    from kitty.constants import is_wayland
    from kitty.fast_data_types import get_options, mark_os_window_dirty, set_options, wakeup_main_loop
    opts = copy.copy(get_options())
    opts.tab_title_max_length = n
    set_options(opts, is_wayland(), boss.args.debug_rendering, boss.args.debug_font_fallback)
    for tm in boss.all_tab_managers:
        if final:
            tm.apply_options()
            tm.resize()
        else:
            tm.tab_bar.apply_options()                 # the bar's draw data carries the new width
            tm.layout_tab_bar()                        # …its screen takes the new column count…
            tm.update_tab_bar_data()                   # …and is redrawn at that size
            if tm.active_tab is not None:
                tm.active_tab.relayout()
        mark_os_window_dirty(tm.os_window_id)          # paint this frame, not whenever the cursor next blinks
    wakeup_main_loop()


def next_apply(now: float, last_apply: float, last_cost: float, applied: int, target: int, interval: float = 0.016):
    """When to apply the pointer's latest width while dragging: None (already there), 0.0 (right now) or a delay in
    seconds (too soon after the last one — wait, then apply whatever the pointer says THEN). Applying only inside the
    pacing window and dropping the rest left the bar stuck behind the pointer once it stopped moving."""
    if target == applied:
        return None
    wait = max(interval, 1.5 * last_cost) - (now - last_apply)
    return 0.0 if wait <= 0 else wait


def _bar_geometry(tm):
    """(vertical?, edge, inner_edge_px, cell_w, window_px) or None."""
    from kitty.fast_data_types import LEFT_EDGE, RIGHT_EDGE, get_options, get_os_window_size
    bar = tm.tab_bar
    if not bar.is_vertical:
        return None
    edge = "left" if get_options().tab_bar_edge == LEFT_EDGE else "right"
    g = bar.window_geometry
    inner = g.right if edge == "left" else g.left
    size = get_os_window_size(tm.os_window_id) or {}
    return True, edge, float(inner), float(bar.cell_width), float(size.get("width") or 0)


_WATCHDOG_S = 12.0          # a drag that goes silent this long is abandoned (the mouse never stays captured). Long enough that
                            # holding the edge while you think is not a lost release (it used to give up after 2.5 s)


def _end_capture(boss, finalize: bool = False) -> None:
    """End the current drag. Always safe to call. For a captured (in-bar) drag this gives the mouse back to kitty; for a native one (kitty's own
    divider machinery drives it) it only un-pauses the panes' resize notifications. `finalize`: the drag did not end with a release (watchdog,
    error, a stale drag), so re-flow every tab at the width it reached — the per-event path only re-flows the visible one."""
    d = _S.drag
    if finalize and d is not None and d.get("dirty") and boss is not None:
        try:
            apply_width(boss, d["width"], final=True)
        except Exception:
            pass
    native = bool(d and d.get("native"))
    try:
        from kitty.fast_data_types import redirect_mouse_handling, remove_timer
        if not native:
            redirect_mouse_handling(False)
            if boss is not None and getattr(boss, "mouse_handler", None) is not None \
                    and getattr(boss.mouse_handler, "__name__", "") == "_mouse_handler":
                boss.mouse_handler = None             # (by name: a reload makes a NEW function object)
        if _S.watchdog is not None:
            remove_timer(_S.watchdog)
        if _S.trail is not None:
            remove_timer(_S.trail)
    except Exception:
        pass
    if native and boss is not None:
        for wid in d.get("paused", ()):
            try:
                cw = boss.window_id_map.get(wid)
                if cw is not None:
                    cw.pause_resize_notifications_to_child(pause=False)
            except Exception:
                pass
    _S.watchdog = None
    _S.trail = None
    _S.drag = None


def _watchdog(timer_id) -> None:
    """No event for _WATCHDOG_S while dragging → assume the release was lost; restore the mouse."""
    _S.watchdog = None
    if _S.drag is None:
        return
    if time.monotonic() - _S.drag["last"] >= _WATCHDOG_S:
        try:
            from kitty.fast_data_types import get_boss
            tm = _S.drag["tm"]
            _end_capture(get_boss(), finalize=True)
            _set_hot(tm, False)
        except Exception:
            _end_capture(None)
    else:
        _arm_watchdog()


def _arm_watchdog() -> None:
    try:
        from kitty.fast_data_types import add_timer
        _S.watchdog = add_timer(_watchdog, _WATCHDOG_S, False)
    except Exception:
        _S.watchdog = None


def _drag_to(boss) -> None:
    """Bring the bar to the pointer's latest width: now if the pacing allows, else on a one-shot timer that applies
    whatever the target is by then. One timer at most, cancelled when the drag ends."""
    d = _S.drag
    if d is None:
        return
    when = next_apply(time.monotonic(), _S.last_apply, _S.last_cost, d["width"], d.get("target", d["width"]), _APPLY_MIN)
    if when is None:
        return
    if when > 0:
        if _S.trail is None:
            try:
                from kitty.fast_data_types import add_timer
                _S.trail = add_timer(_trail, when, False)
            except Exception:
                _S.trail = None
        return
    width = d["target"]
    _S.last_apply = time.monotonic()
    d["width"], d["dirty"] = width, True
    t0 = time.perf_counter()
    apply_width(boss, width, final=False)
    _S.last_cost = time.perf_counter() - t0


def _trail(timer_id) -> None:
    _S.trail = None
    try:
        from kitty.fast_data_types import get_boss
        _drag_to(get_boss())
    except Exception:
        import traceback
        _debug(traceback.format_exc())


def _mouse_handler(ev) -> None:
    """Boss.mouse_handler while dragging: kitty forwards EVERY mouse event here — motion and
    the final release too, even far outside the tab bar (that is what pointer capture is)."""
    from kitty.fast_data_types import get_boss
    from kitty.fast_data_types import GLFW_MOUSE_BUTTON_LEFT, GLFW_RELEASE
    d = _S.drag
    boss = get_boss()
    if d is None:
        _end_capture(boss)
        return
    d["last"] = time.monotonic()
    try:
        _, _edge, _inner, cell_w, window_px = _bar_geometry(d["tm"])
        edge = d["edge"]  # a config reload during capture must not change the drag's coordinate system
        if ev.button == -1:                                        # motion
            d["target"] = L.width_from_pointer(ev.x, cell_w, window_px, edge)
            _drag_to(boss)
        elif ev.button == GLFW_MOUSE_BUTTON_LEFT and ev.action == GLFW_RELEASE:
            tm = d["tm"]
            width = L.width_from_pointer(ev.x, cell_w, window_px, edge)
            _end_capture(boss)
            _finish(tm, width, edge)
    except Exception:
        import traceback
        _debug(traceback.format_exc())
        _end_capture(boss, finalize=True)
        _set_hot(d["tm"], False)


def _toggle_zone(tm, x: float, y: float, slop: float = 0.0) -> bool:
    bar = tm.tab_bar
    g = bar.window_geometry
    cw, ch = bar.cell_width, bar.cell_height
    compact = (g.right - g.left) / cw <= L.COMPACT_MAX_COLS
    rows = L.header_rows(int((g.bottom - g.top) // ch), bar.max_tab_title_lines, compact)
    return L.in_toggle_zone(x, y, g.left, g.right, g.top, cw, ch, compact, rows, slop)


def _live_layout(tm) -> "L.Layout":
    """The layout the bar has RIGHT NOW (edge from kitty's options, mode from its width) — the truth
    when nothing was saved for this kitty, e.g. a bar placed by a plain `tab_bar_edge left` line."""
    from kitty.fast_data_types import LEFT_EDGE, RIGHT_EDGE, TOP_EDGE, get_options
    opts = get_options()
    edge = {LEFT_EDGE: "left", RIGHT_EDGE: "right", TOP_EDGE: "top"}.get(opts.tab_bar_edge, "bottom")
    bar = tm.tab_bar
    compact = (bar.window_geometry.right - bar.window_geometry.left) / bar.cell_width <= L.COMPACT_MAX_COLS
    return L.Layout(edge, "compact" if compact else "full", int(opts.tab_title_max_length or L.DEFAULT_WIDTH)).normalized()


def _toggle_collapsed(tm) -> None:
    """The sidebar's collapse button: save the toggled layout for this kitty and reload its config
    (the layout include reads it). Deferred one tick so we are out of the mouse handler."""
    try:
        from kitty.fast_data_types import add_timer, get_boss
        sdir, pid = L.state_dir(), os.getpid()
        base = L.load(sdir, pid) or _live_layout(tm)
        L.save(sdir, pid, L.toggle_collapsed(base))
        add_timer(lambda _id: get_boss().load_config_file(), 0.01, False)
    except Exception:
        import traceback
        _debug(traceback.format_exc())


def _open_peek(tm, tab_id: int) -> None:
    """Right-click on a tab: show its peek card (python/peek-kit.py) over the active window. kitty gives
    its tab bar no hover events, so a click is the closest thing to a link-preview hover."""
    try:
        from kitty.fast_data_types import get_boss
        sock = getattr(get_boss(), "listening_on", "") or ""
        kit = os.path.join(os.path.dirname(os.path.realpath(__file__)), "peek-kit.py")
        window = tm.active_tab.active_window if tm.active_tab is not None else None
        if not (sock and window is not None and os.path.isfile(kit)):
            _debug(f"peek unavailable: socket={sock!r} window={window!r} kitten={kit}")
            return
        subprocess.Popen(["kitty", "@", "--to", sock, "kitten", "--match", f"id:{window.id}", kit, str(tab_id)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:
        import traceback
        _debug(traceback.format_exc())


def _handle(tm, x: float, y: float, button: int, action: int) -> bool:
    """True when the event was ours: the collapse/expand button (acts on release, like a button),
    or a left press on the bar's inner edge, which starts a resize drag."""
    from kitty.fast_data_types import get_boss
    from kitty.fast_data_types import GLFW_MOUSE_BUTTON_LEFT, GLFW_MOUSE_BUTTON_RIGHT, GLFW_PRESS, GLFW_RELEASE, redirect_mouse_handling
    if button == GLFW_MOUSE_BUTTON_RIGHT and tm.tab_bar.is_vertical:
        if action == GLFW_PRESS:
            tid = tm.tab_bar.tab_id_at(int(x), int(y))
            if tid > 0:
                _S.peek_down = tid
                return True
        elif action == GLFW_RELEASE and _S.peek_down:
            tid, _S.peek_down = _S.peek_down, 0
            if tm.tab_bar.tab_id_at(int(x), int(y)) == tid:      # released on the same tab
                _open_peek(tm, tid)
            return True
    if button == GLFW_MOUSE_BUTTON_LEFT and _S.drag is None and tm.tab_bar.is_vertical:
        if action == GLFW_PRESS and _toggle_zone(tm, x, y):
            _S.toggle_down = True
            return True
        if action == GLFW_RELEASE and _S.toggle_down:
            _S.toggle_down = False
            if _toggle_zone(tm, x, y, slop=tm.tab_bar.cell_height / 2):   # released on (or a half row off) the button
                _toggle_collapsed(tm)
            return True
    if button != GLFW_MOUSE_BUTTON_LEFT or action != GLFW_PRESS or _S.drag is not None:
        return False
    geo = _bar_geometry(tm)
    if geo is None:
        return False
    _, edge, inner, cell_w, _window_px = geo
    if not L.in_grab_zone(x, inner, cell_w, native=native_edge_active(tm.os_window_id)):
        return False
    boss = get_boss()
    handler = getattr(boss, "mouse_handler", None)
    if handler is not None:
        if getattr(handler, "__name__", "") == "_mouse_handler" and _S.drag is None:
            boss.mouse_handler = None             # OUR capture, left behind by an older version across a reload: let go of it
        else:
            return False                          # another modal mouse mode is active
    _S.drag = {"tm": tm, "edge": edge, "width": -1, "target": -1, "dirty": False, "last": time.monotonic()}
    boss.mouse_handler = _mouse_handler
    redirect_mouse_handling(True)                                 # from now on we see every event
    _arm_watchdog()
    _set_hot(tm, True)
    return True


def _finish(tm, width: int, edge: str) -> None:
    """Drag ended: persist as this instance's layout (full sidebar at the chosen width)."""
    try:
        from kitty.fast_data_types import get_boss
        sdir = L.state_dir()
        pid = os.getpid()
        base = L.load(sdir, pid)
        saved_edge = base.edge if base is not None and base.edge in ("left", "right") else edge
        if width >= 0:
            L.save(sdir, pid, L.Layout(saved_edge, "full", width))
            apply_width(get_boss(), width)
    finally:
        _set_hot(tm, False)


def make_tab_id_at(original):
    """`TabBar.tab_id_at` for a vertical bar: spacer rows resolve to the nearer tab (see
    kittymux_layout.snap_tab_id), and while a tab is being dragged a tab only counts once the pointer is
    past its midpoint (kittymux_layout.drag_target), so reordering does not cascade. Anything unexpected
    falls back to kitty's own answer."""
    def tab_id_at(self, x, y):
        tid = original(self, x, y)
        try:
            if not (getattr(self, "is_vertical", False) and self.laid_out_once):
                return tid
            g = self.window_geometry
            inside = g.left <= x < g.right and g.top <= y < g.bottom
            extents = [(te.tab_id, te.y.start, te.y.end) for te in self.tab_extents]
            if not tid and inside:
                tid = L.snap_tab_id(extents, int((y - g.top) // self.cell_height))
            if native_insert_drag():                                  # kitty >= 0.49.2 handles the drag itself
                return tid
            from kitty.fast_data_types import get_tab_being_dragged
            dragged, started = get_tab_being_dragged()[:2]
            if started and dragged and inside:
                compact = (g.right - g.left) / self.cell_width <= L.COMPACT_MAX_COLS
                hdr = L.header_rows(int((g.bottom - g.top) // self.cell_height), self.max_tab_title_lines, compact)
                if extents and extents[0][2] - extents[0][1] + 1 > hdr:       # the first tab's extent includes the header
                    extents[0] = (extents[0][0], extents[0][1] + hdr, extents[0][2])
                tid = L.drag_target(extents, dragged, tid, (y - g.top) / self.cell_height)
            return tid
        except Exception:
            return tid
    tab_id_at._kittymux_wrapped = True                          # type: ignore[attr-defined]
    return tab_id_at


def native_insert_drag() -> bool:
    """kitty >= 0.49.2 reorders dragged tabs by INSERTING at the nearest boundary (with a drop marker) and lets a
    pane dropped on a tab's outer 10% or a gap become a new tab. Our 0.49.1 drag fixes are then not just
    unnecessary: kitty's internals changed shape (TabBeingDropped), so they must not run."""
    try:
        from kitty.tab_bar import TabBar
        return hasattr(TabBar, "tab_insertion_target_at")
    except Exception:
        return False


def make_on_tab_drop_move(original):
    """`TabManager.on_tab_drop_move` with a sane start. kitty's FIRST call of a drag has no pointer position
    (x=y=0) and builds the new order from the laid-out tabs, which no longer include the dragged one, so the
    dragged tab lands at the END and then swaps with whatever is at the top: on a vertical bar it jumped
    around the moment you grabbed it. Seed the order as it is now and use the real drag-start position."""
    def on_tab_drop_move(self, tab_id=0, is_dest=False, x=0, y=0):
        try:
            if is_dest and self.tab_being_dropped is None:
                from kitty.fast_data_types import get_boss, get_tab_being_dragged
                from kitty.tabs import TabBeingDropped
                ids = [t.id for t in self.tabs_to_be_shown_in_tab_bar]
                tab = get_boss().tab_for_id(tab_id)
                _id, started, sx, sy = get_tab_being_dragged()
                if tab is not None and tab_id in ids and started:
                    self.tab_being_dropped = TabBeingDropped(
                        data=tab.data_for_tab_bar(tab is get_boss().active_tab), tab_ids=ids,
                        last_drop_move_coordinate=self.tab_bar.drag_axis_coordinate(int(sx), int(sy)))
                    if x == 0 and y == 0:
                        x, y = int(sx), int(sy)
                    self.layout_tab_bar()
        except Exception:
            import traceback
            _debug(traceback.format_exc())
        return original(self, tab_id, is_dest, x, y)
    on_tab_drop_move._kittymux_wrapped = True                   # type: ignore[attr-defined]
    return on_tab_drop_move


def make_drop_spans(original):
    """kitty >= 0.49.2 `TabBar._drop_spans` for a vertical bar: the first tab's extent includes the header, so its
    insertion midpoint sat in the header and dropping at the top of the list landed AFTER the first tab. Count only
    its content rows."""
    def _drop_spans(self, x, y):
        coordinate, spans = original(self, x, y)
        try:
            if getattr(self, "is_vertical", False) and spans:
                g = self.window_geometry
                compact = (g.right - g.left) / self.cell_width <= L.COMPACT_MAX_COLS
                hdr_px = L.header_rows(int((g.bottom - g.top) // self.cell_height), self.max_tab_title_lines, compact) * self.cell_height
                tid, start, end = spans[0]
                if end - start > hdr_px and start == 0:
                    spans = [(tid, start + hdr_px, end)] + list(spans[1:])
        except Exception:
            pass
        return coordinate, spans
    _drop_spans._kittymux_wrapped = True                          # type: ignore[attr-defined]
    return _drop_spans


def _install_tab_drag() -> None:
    if native_insert_drag():
        try:
            from kitty.tab_bar import TabBar
            if hasattr(TabBar, "_drop_spans") and not getattr(TabBar._drop_spans, "_kittymux_wrapped", False):
                TabBar._drop_spans = make_drop_spans(TabBar._drop_spans)              # type: ignore[method-assign]
        except Exception:
            pass
        return
    try:
        from kitty.tabs import TabManager
        if not getattr(TabManager.on_tab_drop_move, "_kittymux_wrapped", False):
            TabManager.on_tab_drop_move = make_on_tab_drop_move(TabManager.on_tab_drop_move)   # type: ignore[method-assign]
    except Exception:
        pass


def _install_tab_hit_testing() -> None:
    try:
        from kitty.tab_bar import TabBar
        if not getattr(TabBar.tab_id_at, "_kittymux_wrapped", False):
            TabBar.tab_id_at = make_tab_id_at(TabBar.tab_id_at)  # type: ignore[method-assign]
    except Exception:
        pass


# ── forgiving tab clicks ──────────────────────────────────────────────────────
# kitty activates a tab on the left RELEASE, and only if it counts the press+release as a click: within click_interval (0.5 s), less than
# 5 px apart, on the same tab. Beyond 5 px kitty still waits for drag_threshold (kittymux sets 14 so a wobbly click is not a drag) before it
# starts a drag — so a click that drifts 5–14 px is NEITHER: nothing happens. Real mice and touchpads wobble that much (physical px: more on
# a scaled display); a scripted click never does, which is how this survived the smoke tests. We record the press and, when kitty did not
# act on the release, activate the tab ourselves under a click rule that matches the drag threshold instead of the 5 px.
TAP_MAX_S = 1.5             # a slow click still counts
TAP_MIN_PX = 5.0            # …and at least kitty's own click tolerance


def _tab_has_agent(tm, tab_id: int) -> bool:
    try:
        tab = tm.tab_for_id(tab_id)
        verdicts = getattr(sys.modules.get("_kittymux_scan_rt"), "verdicts", {}) or {}
        return tab is not None and any((verdicts.get(str(w.id)) or {}).get("state") for w in tab)
    except Exception:
        return False


def _tap_before(tm, x: float, y: float, button: int, action: int) -> bool:
    """Called before kitty's own tab-bar mouse handler. Records the left press / whether a drag already started. Returns True when the event
    must be swallowed: a middle-click on a tab running an agent (kitty closes the tab on a middle-click, with no confirmation, and a touchpad
    two-finger tap or a stray wheel-click is enough to lose a running agent; `ctrl+alt+q` closes a pane with confirmation)."""
    from kitty.fast_data_types import GLFW_MOUSE_BUTTON_LEFT, GLFW_MOUSE_BUTTON_MIDDLE, GLFW_PRESS, GLFW_RELEASE, get_tab_being_dragged
    if button == GLFW_MOUSE_BUTTON_LEFT and action == GLFW_PRESS:
        tid = tm.tab_bar.tab_id_at(int(x), int(y))
        _S.tap = (tid, x, y, time.monotonic()) if tid > 0 else None
        _S.tap_drag = False
    elif button == GLFW_MOUSE_BUTTON_LEFT and action == GLFW_RELEASE:
        _S.tap_drag = bool(get_tab_being_dragged()[1])
    elif button == GLFW_MOUSE_BUTTON_MIDDLE:
        tid = tm.tab_bar.tab_id_at(int(x), int(y))
        if tid > 0 and _tab_has_agent(tm, tid):
            return True
    return False


def _tap_after(tm, x: float, y: float, button: int, action: int) -> None:
    """Called after kitty's handler for a left release: if kitty did not activate the tab we pressed on (a wobbly click), do it."""
    from kitty.fast_data_types import GLFW_MOUSE_BUTTON_LEFT, GLFW_RELEASE, get_options
    if button != GLFW_MOUSE_BUTTON_LEFT or action != GLFW_RELEASE:
        return
    tap, dragged = _S.tap, _S.tap_drag
    _S.tap, _S.tap_drag = None, False
    if tap is None or dragged:
        return
    tid, px, py, t0 = tap
    slop = max(TAP_MIN_PX, float(get_options().drag_threshold or 0))
    if time.monotonic() - t0 > TAP_MAX_S or (x - px) ** 2 + (y - py) ** 2 > slop * slop:
        return                                                  # held too long or moved far: that was a drag attempt, not a click
    if tm.tab_bar.tab_id_at(int(x), int(y)) != tid:
        return                                                  # released on another tab
    tab = tm.tab_for_id(tid)
    if tab is not None and tm.active_tab is not tab:
        tm.set_active_tab(tab)


# ── the native divider ────────────────────────────────────────────────────────
# kitty draws and hit-tests window borders itself: every tab's border rectangles (kitty.borders.set_borders_rects) are drawn by its GPU border
# renderer, and a rectangle with a non-zero border_type is a hit target — hovering it shows the resize cursor IN C, and pressing it calls
# Boss.drag_resize_start, after which kitty routes the whole drag to Boss.drag_resize_update/_end and restores the cursor. We hand kitty two
# more rectangles (the 700 and 950 hairlines, in the pane padding right next to the bar) and one invisible hit rectangle over them, and answer
# the drag callbacks for it. Facts measured in kitty 0.49.2: the cursor over the TAB BAR is always a hand (chosen in C); border hit-testing
# only runs in tabs with 2+ visible windows, so a single-pane tab keeps the bar-side grab zone; the colour field takes (rgb << 8) | window_bg.
EDGE_FALLBACK = None


def _theme():
    """The theme palette (cached per colour set) for the native hairlines. Never raises."""
    try:
        from kitty.fast_data_types import get_options
        from kitty.rgb import color_as_int
        import kittymux_theme as T
        o = get_options()
        bg = color_as_int(o.tab_bar_background or o.background)
        colors = T.colors_from_options(o, bg, color_as_int)
        key = (tuple(sorted(colors.items())), os.environ.get("KITTYMUX_ACCENT", ""))
        if _S.pal_key != key:
            _S.pal_key, _S.pal = key, T.from_colors(colors)
        return _S.pal
    except Exception:
        return None


def _edge_plan(os_window_id: int):
    """(side, geometry, central_rect) for this OS window's vertical bar, or None when the native divider does not apply (horizontal bar,
    too little padding, hooks missing, a kitty without the pieces)."""
    if not _S.edge_installed:
        return None
    try:
        from kitty.constants import version
        if tuple(version) < L.NATIVE_EDGE_MIN:                  # a kitty we have not verified the border internals on: keep the cell divider
            return None
        from kitty.fast_data_types import LEFT_EDGE, RIGHT_EDGE, get_options, pt_to_px, viewport_for_window
        opts = get_options()
        if opts.tab_bar_edge not in (LEFT_EDGE, RIGHT_EDGE):
            return None
        side = "left" if opts.tab_bar_edge == LEFT_EDGE else "right"
        central, bar, _vw, _vh, cell_w, _cell_h = viewport_for_window(os_window_id)
        if bar.width <= 0:
            return None
        pad = pt_to_px(getattr(opts.window_padding_width, side), os_window_id)
        geo = L.edge_geometry(side, central.left, central.right, cell_w, pad)
        return (side, geo, central) if geo else None
    except Exception:
        return None


def native_edge_active(os_window_id: int) -> bool:
    """True when this OS window's divider is drawn by kitty itself (the bar then leaves its last columns blank)."""
    return _edge_plan(os_window_id) is not None


def _borders_hook(orig, os_window_id: int, tab_id: int, rects):
    """Add the divider's rectangles to what kitty is about to hand to its border renderer for one tab. Must never raise."""
    try:
        plan = _edge_plan(os_window_id)
        if plan is not None:
            from kitty.borders import Border, BorderColor
            import kittymux_theme as T
            from kitty.fast_data_types import get_boss
            side, geo, central = plan
            pal = _theme()
            if pal is not None:
                hot = bool(_S.hot)
                tone = {700: pal.accent if hot else pal.sep_700, 950: T.shade(pal.accent, 950) if hot else pal.sep_950}
                extra = [Border(x0, central.top, x1, central.bottom, ((tone[t] & 0xFFFFFF) << 8) | int(BorderColor.window_bg), 0, False, True)
                         for x0, x1, t in geo["lines"]]
                tab = get_boss().tab_for_id(tab_id)
                groups = list(tab.windows.iter_all_layoutable_groups(only_visible=True)) if tab is not None else []
                if len(groups) > 1 and tab.active_window is not None:
                    # the hit target: invisible, over the lines. border_type < 0 reads as a LEFT edge (horizontal resize cursor), > 0 as RIGHT.
                    wid = tab.active_window.id
                    extra.append(Border(geo["hit"][0], central.top, geo["hit"][1], central.bottom, BorderColor.default_bg,
                                        -wid if side == "left" else wid, False, False))
                rects = list(rects) + extra
    except Exception:
        _debug_exc()
    return orig(os_window_id, tab_id, rects)


def _debug_exc() -> None:
    if os.environ.get("KITTYMUX_DEBUG"):
        import traceback
        _debug(traceback.format_exc())


def _native_start(boss, edges: int, x: float, y: float, window_id: int, cell_w, cell_h):
    """Boss.drag_resize_start for a press kitty found on one of OUR hit rectangles: begin the bar drag. None = not ours (kitty's own divider)."""
    try:
        w = boss.window_id_map.get(window_id)
        tab = w.tabref() if w is not None else None
        tm = tab.tab_manager_ref() if tab is not None else None
        if tm is None:
            return None
        plan = _edge_plan(tm.os_window_id)
        if plan is None:
            return None
        side, geo, _central = plan
        from kitty.fast_data_types import LEFT_EDGE, RIGHT_EDGE
        if edges != (LEFT_EDGE if side == "left" else RIGHT_EDGE):
            return None
        slop = 2 * (cell_w or 0) / 5.0                                       # kitty adds its own tolerance; this only rejects far-away dividers
        if not (geo["hit"][0] - slop <= x <= geo["hit"][1] + slop):
            return None
        if _S.drag is not None:
            _end_capture(boss, finalize=True)                                 # a stale drag (lost release): finish it, then start fresh
        paused = []
        for cw in tab:                                                        # like kitty's own divider drag: children get the final size once, not every step
            cw.pause_resize_notifications_to_child()
            paused.append(cw.id)
        _S.drag = {"tm": tm, "edge": side, "width": -1, "target": -1, "dirty": False, "last": time.monotonic(), "native": True, "paused": paused}
        _set_hot(tm, True)
        return True
    except Exception:
        _debug_exc()
        return None


def _native_update(boss, x: float, y: float) -> bool:
    d = _S.drag
    if d is None or not d.get("native"):
        return False
    try:
        _, _edge, _inner, cell_w, window_px = _bar_geometry(d["tm"])
        d["last"] = time.monotonic()
        d["target"] = L.width_from_pointer(x, cell_w, window_px, d["edge"])
        _drag_to(boss)
    except Exception:
        _debug_exc()
    return True


def _native_end(boss) -> bool:
    d = _S.drag
    if d is None or not d.get("native"):
        return False
    tm, edge = d["tm"], d["edge"]
    width = d["target"] if d["target"] >= 0 else d["width"]
    _end_capture(boss)                                                        # cancels the trailing timer, un-pauses the panes, clears state
    _finish(tm, width, edge)
    return True


def _install_native_edge() -> None:
    """Hook kitty's border hand-off and its divider-drag callbacks, once per process. The wrappers only delegate to this module's functions
    (looked up by name at call time), so a later reload's new code takes effect without re-wrapping."""
    try:
        import kitty.borders as B
        from kitty.boss import Boss
        if not getattr(B.set_borders_rects, "_kittymux_wrapped", False):
            orig_rects = B.set_borders_rects

            def set_borders_rects(os_window_id, tab_id, rects):
                return _borders_hook(orig_rects, os_window_id, tab_id, rects)

            set_borders_rects._kittymux_wrapped = True                         # type: ignore[attr-defined]
            B.set_borders_rects = set_borders_rects
        if not getattr(Boss.drag_resize_start, "_kittymux_wrapped", False):
            o_start, o_update, o_end = Boss.drag_resize_start, Boss.drag_resize_update, Boss.drag_resize_end

            def drag_resize_start(self, edges, x, y, window_id, cell_width, cell_height):
                got = _native_start(self, edges, x, y, window_id, cell_width, cell_height)
                return got if got is not None else o_start(self, edges, x, y, window_id, cell_width, cell_height)

            def drag_resize_update(self, x, y):
                if not _native_update(self, x, y):
                    o_update(self, x, y)

            def drag_resize_end(self):
                if not _native_end(self):
                    o_end(self)

            drag_resize_start._kittymux_wrapped = True                         # type: ignore[attr-defined]
            Boss.drag_resize_start, Boss.drag_resize_update, Boss.drag_resize_end = drag_resize_start, drag_resize_update, drag_resize_end
        _S.edge_installed = True
    except Exception:
        _S.edge_installed = False
        _debug_exc()


def install() -> bool:
    """Wrap TabManager.handle_tab_bar_mouse once (+ the spacer-row hit test). Safe to call
    repeatedly; never raises."""
    _install_tab_hit_testing()
    _install_tab_drag()
    _install_native_edge()
    if _S.installed:
        return True
    try:
        from kitty.tabs import TabManager
        if getattr(TabManager.handle_tab_bar_mouse, "_kittymux_wrapped", False):
            _S.installed = True
            return True
        original = TabManager.handle_tab_bar_mouse

        def wrapped(self, x, y, button, modifiers, action):
            try:
                if _handle(self, x, y, button, action):
                    return None
                if _tap_before(self, x, y, button, action):
                    return None
            except Exception:
                import traceback
                _debug(traceback.format_exc())                  # never break kitty's own handling
            result = original(self, x, y, button, modifiers, action)
            try:
                _tap_after(self, x, y, button, action)
            except Exception:
                _debug_exc()
            return result

        wrapped._kittymux_wrapped = True                        # type: ignore[attr-defined]
        TabManager.handle_tab_bar_mouse = wrapped               # type: ignore[method-assign]
        _S.installed = True
        return True
    except Exception:
        return False
