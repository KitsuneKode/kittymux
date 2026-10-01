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
_S = sys.modules.setdefault("_kittymux_barsize_rt", types.SimpleNamespace(
    hot=False,              # pointer over the handle or dragging — the tab bar draws it lit
    drag=None,              # active drag: {"tm": TabManager, "edge": "left|right", "width": int, "last": float}
    last_apply=0.0,
    installed=False,
    toggle_down=False,      # a press landed on the collapse/expand button; the release decides
    watchdog=None,          # timer id
))
_APPLY_EVERY = 0.03         # seconds — plenty smooth, keeps re-layout cost bounded


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


_WATCHDOG_S = 2.5           # a drag that goes silent this long is abandoned (mouse never stays captured)


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
        _, edge, _inner, cell_w, window_px = _bar_geometry(d["tm"])
        if ev.button == -1:                                        # motion
            now = time.monotonic()
            width = L.width_from_pointer(ev.x, cell_w, window_px, edge)
            if width != d["width"] and now - _S.last_apply >= _APPLY_EVERY:
                _S.last_apply = now
                d["width"] = width
                apply_width(boss, width)
        elif ev.button == GLFW_MOUSE_BUTTON_LEFT and ev.action == GLFW_RELEASE:
            tm, width = d["tm"], d["width"]
            _end_capture(boss)
            _finish(tm, width)
    except Exception:
        import traceback
        _debug(traceback.format_exc())
        _end_capture(boss)
        _set_hot(d["tm"], False)


def _toggle_zone(tm, x: float, y: float) -> bool:
    bar = tm.tab_bar
    g = bar.window_geometry
    compact = (g.right - g.left) / bar.cell_width <= L.COMPACT_MAX_COLS
    return L.in_toggle_zone(x, y, g.left, g.right, g.top, bar.cell_width, bar.cell_height, compact)


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


def _handle(tm, x: float, y: float, button: int, action: int) -> bool:
    """True when the event was ours: the collapse/expand button (acts on release, like a button),
    or a left press on the bar's inner edge, which starts a resize drag."""
    from kitty.fast_data_types import get_boss
    from kitty.fast_data_types import GLFW_MOUSE_BUTTON_LEFT, GLFW_PRESS, GLFW_RELEASE, redirect_mouse_handling
    if button == GLFW_MOUSE_BUTTON_LEFT and _S.drag is None and tm.tab_bar.is_vertical:
        if action == GLFW_PRESS and _toggle_zone(tm, x, y):
            _S.toggle_down = True
            return True
        if action == GLFW_RELEASE and _S.toggle_down:
            _S.toggle_down = False
            if _toggle_zone(tm, x, y):                      # released still on the button
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
    if getattr(boss, "mouse_handler", None) is not None:          # another modal mouse mode is active
        return False
    _S.drag = {"tm": tm, "edge": edge, "width": -1, "last": time.monotonic()}
    boss.mouse_handler = _mouse_handler
    redirect_mouse_handling(True)                                 # from now on we see every event
    _arm_watchdog()
    _set_hot(tm, True)
    return True


def _finish(tm, width: int) -> None:
    """Drag ended: persist as this instance's layout (full sidebar at the chosen width)."""
    try:
        from kitty.fast_data_types import get_boss
        sdir = L.state_dir()
        pid = os.getpid()
        base = L.base_layout(sdir, pid, os.environ.get("KITTY_CONFIG_DIRECTORY")
                             or os.path.expanduser("~/.config/kitty"))
        if width >= 0:
            L.save(sdir, pid, L.Layout(base.edge if base.edge in ("left", "right") else "left", "full", width))
            apply_width(get_boss(), width)
    finally:
        _set_hot(tm, False)


def make_tab_id_at(original):
    """`TabBar.tab_id_at` that also resolves the spacer rows of a vertical bar (see
    kittymux_layout.snap_tab_id). Anything unexpected falls back to kitty's own answer."""
    def tab_id_at(self, x, y):
        tid = original(self, x, y)
        if tid:
            return tid
        try:
            if not (getattr(self, "is_vertical", False) and self.laid_out_once):
                return tid
            g = self.window_geometry
            if not (g.left <= x < g.right and g.top <= y < g.bottom):
                return tid
            row = int((y - g.top) // self.cell_height)
            return L.snap_tab_id([(te.tab_id, te.y.start, te.y.end) for te in self.tab_extents], row)
        except Exception:
            return tid
    tab_id_at._kittymux_wrapped = True                          # type: ignore[attr-defined]
    return tab_id_at


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
