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
            mark_os_window_dirty(tm.os_window_id)          # the lit separator must paint now, not at the next blink
            wakeup_main_loop()
        except Exception:
            pass


def apply_width(boss, n: int) -> None:
    """Change tab_title_max_length live for THIS kitty instance (all its OS windows)."""
    from kitty.constants import is_wayland
    from kitty.fast_data_types import get_options, set_options
    opts = copy.copy(get_options())
    opts.tab_title_max_length = n
    set_options(opts, is_wayland(), boss.args.debug_rendering, boss.args.debug_font_fallback)
    for tm in boss.all_tab_managers:
        tm.apply_options()
        tm.resize()


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


def _end_capture(boss) -> None:
    """Give the mouse back to kitty. Always safe to call."""
    try:
        from kitty.fast_data_types import redirect_mouse_handling, remove_timer
        redirect_mouse_handling(False)
        if boss is not None and getattr(boss, "mouse_handler", None) is not None \
                and getattr(boss.mouse_handler, "__name__", "") == "_mouse_handler":
            boss.mouse_handler = None                 # (by name: a reload makes a NEW function object)
        if _S.watchdog is not None:
            remove_timer(_S.watchdog)
    except Exception:
        pass
    _S.watchdog = None
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
            _end_capture(get_boss())
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
            now = time.monotonic()
            width = L.width_from_pointer(ev.x, cell_w, window_px, edge)
            if width != d["width"] and now - _S.last_apply >= max(_APPLY_MIN, 1.5 * _S.last_cost):
                _S.last_apply = now
                d["width"] = width
                t0 = time.perf_counter()
                apply_width(boss, width)
                _S.last_cost = time.perf_counter() - t0
        elif ev.button == GLFW_MOUSE_BUTTON_LEFT and ev.action == GLFW_RELEASE:
            tm = d["tm"]
            width = L.width_from_pointer(ev.x, cell_w, window_px, edge)
            _end_capture(boss)
            _finish(tm, width, edge)
    except Exception:
        import traceback
        _debug(traceback.format_exc())
        _end_capture(boss)
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
    if not L.in_grab_zone(x, inner, cell_w):
        return False
    boss = get_boss()
    handler = getattr(boss, "mouse_handler", None)
    if handler is not None:
        if getattr(handler, "__name__", "") == "_mouse_handler" and _S.drag is None:
            boss.mouse_handler = None             # OUR capture, left behind by an older version across a reload: let go of it
        else:
            return False                          # another modal mouse mode is active
    _S.drag = {"tm": tm, "edge": edge, "width": -1, "last": time.monotonic()}
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


def install() -> bool:
    """Wrap TabManager.handle_tab_bar_mouse once (+ the spacer-row hit test). Safe to call
    repeatedly; never raises."""
    _install_tab_hit_testing()
    _install_tab_drag()
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
            except Exception:
                import traceback
                _debug(traceback.format_exc())                  # never break kitty's own handling
            return original(self, x, y, button, modifiers, action)

        wrapped._kittymux_wrapped = True                        # type: ignore[attr-defined]
        TabManager.handle_tab_bar_mouse = wrapped               # type: ignore[method-assign]
        _S.installed = True
        return True
    except Exception:
        return False
