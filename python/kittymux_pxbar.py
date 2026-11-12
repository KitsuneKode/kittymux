"""The pixel tab bar inside kitty (plan 015; the `pxbar` switch). tab_bar.py draws blank cells in the default background
and hands this module the rows; it renders them (kittymux_barpx) and sets the picture as the OS window's background
image, which kitty shows through those cells. It keeps the picture's hit bands so a click lands on the tab drawn there.

Verified in kitty 0.50 (docs/agents/conventions.md): graphics sent into the tab bar's Screen draw as black boxes, but the
OS window's background image shows through cells drawn with bg 0. `Boss.set_background_image` takes PNG bytes with any
non-empty path (None clears it) and needs `mark_os_window_dirty` + `wakeup_main_loop` to show at once. A swap costs
1.5 to 3.5 ms and happens only when what the picture shows changed.

State lives in sys.modules["_kittymux_pxbar_rt"]: a config reload re-runs this module, and the picture's hit bands and
signature must survive it. No timers.
"""
from __future__ import annotations

import sys
import time
import types

PLACEHOLDER = "/kittymux/pxbar"          # any non-empty path: kitty takes the PNG bytes, the path only says "an image"
_S = sys.modules.setdefault("_kittymux_pxbar_rt", types.SimpleNamespace(windows={}, resources=None, last_ms=0.0, expanded=set()))
if not hasattr(_S, "expanded"):
    _S.expanded = set()
if not hasattr(_S, "view"):
    _S.view = {}                          # os window id → {"start", "user", "active"}: where the picture is scrolled to; dropped by clear()


def _resources():
    if _S.resources is None:
        import kittymux_deckpx as dp
        _S.resources = dp.Resources()
    return _S.resources


def metrics(os_window_id: int):
    """(bar_right_px, window_height_px, scale) for an OS window whose bar is on the left, else None."""
    from kitty.fast_data_types import get_boss, get_os_window_size
    tm = get_boss().os_window_map.get(os_window_id)
    if tm is None or getattr(tm, "tab_bar", None) is None:
        return None
    g = tm.tab_bar.window_geometry
    size = get_os_window_size(os_window_id) or {}
    fb_h = int(size.get("framebuffer_height") or g.bottom)
    scale = float(size.get("xscale") or 1.0) or 1.0
    if g.left > 2 * scale * 10:               # the bar is not at the left edge (a right-hand bar): not handled yet
        return None
    return int(g.right), fb_h, scale


def publish(os_window_id: int, groups, pal, host: str = "") -> bool:
    """Render and show the picture when what it shows changed. Returns True when it swapped."""
    m = metrics(os_window_id)
    if m is None:                             # no bar on the left (moved to the right edge): no picture, no hit bands
        clear(os_window_id)
        return False
    right, fb_h, scale = m
    rows = [r for g in groups for r in g.rows]
    active = next((r.tab_id for r in rows if r.active), 0)
    view = _S.view.setdefault(os_window_id, {"start": 0, "user": False, "active": active})
    if view["active"] != active:                 # you moved to another tab: the view follows it again
        view.update(user=False, active=active)
    sig = (tuple(groups), pal, right, fb_h, scale, host, view["start"], view["user"])
    w = _S.windows.get(os_window_id)
    if w is not None and w.get("sig") == sig:
        return False
    import kittymux_barpx as bp
    t0 = time.perf_counter()
    pic = None
    for _ in range(4):                           # at most a few renders: the "↑ above" band changes how many fit
        pic = bp.render(groups, pal, width=right / scale, height=fb_h / scale, scale=scale, host=host,
                        resources=_resources(), start=view["start"])
        i = next((k for k, r in enumerate(rows) if r.tab_id == active), None)
        if view["user"] or i is None or pic.start <= i < pic.start + max(1, pic.shown):
            break
        view["start"] = i if i < pic.start else max(0, i - max(1, pic.shown) + 1)
    view["start"] = pic.start
    sig = (tuple(groups), pal, right, fb_h, scale, host, view["start"], view["user"])
    from kitty.fast_data_types import get_boss, mark_os_window_dirty, wakeup_main_loop
    get_boss().set_background_image(PLACEHOLDER, (os_window_id,), False, "clamped", png_data=pic.png)
    mark_os_window_dirty(os_window_id)
    wakeup_main_loop()
    _S.last_ms = (time.perf_counter() - t0) * 1000
    _S.windows[os_window_id] = {"sig": sig, "hits": pic.hits, "right": right, "shown": pic.shown, "total": pic.total}
    return True


def page(os_window_id: int, direction: int) -> None:
    """A click on "↑ N above" (-1) or "↓ N below" (+1): scroll a page that way. The view stays there until you change tab."""
    w = _S.windows.get(os_window_id)
    view = _S.view.get(os_window_id)
    if w is None or view is None:
        return
    step = max(1, int(w.get("shown") or 1) - 1)
    view["start"] = max(0, min(int(w.get("total") or 0) - 1, view["start"] + direction * step))
    view["user"] = True


def configured_background(opts) -> tuple:
    """(path, layout) of the background_image in kitty.conf, or (None, None): what the window shows without the picture."""
    path = getattr(opts, "background_image", None)
    if not path or str(path).lower() == "none":
        return None, None
    return str(path), getattr(opts, "background_image_layout", None)


def clear(os_window_id: int) -> None:
    """Take the picture away (the switch went off, the bar moved, the client attached): the window's own background, the
    one kitty.conf configures if any, comes back."""
    _S.view.pop(os_window_id, None)
    if _S.windows.pop(os_window_id, None) is None:
        return
    try:
        from kitty.fast_data_types import get_boss, get_options, mark_os_window_dirty, wakeup_main_loop
        path, layout = configured_background(get_options())
        get_boss().set_background_image(path, (os_window_id,), False, layout)
        mark_os_window_dirty(os_window_id)
        wakeup_main_loop()
    except Exception:
        pass


def active(os_window_id: int) -> bool:
    return os_window_id in _S.windows


def band_at(os_window_id: int, x_px: float, y_px: float):
    """The picture's band under a window-pixel point: a kittymux_barpx.Hit, or None (no picture here, or outside it)."""
    w = _S.windows.get(os_window_id)
    if w is None or x_px < 0 or x_px >= w["right"]:
        return None
    for h in w["hits"]:
        if h.y0 <= y_px < h.y1:
            return h
    return None


CLOSE_W = 34            # logical px at a row's right end that are the close cross (matches the shader's cover)
TITLE_LINE = 32         # logical px: the cross sits in a row's first line


def cross_shown(opts=None) -> bool:
    """The close cross is drawn by kittymux-pxbar.slang: without that shader running there is no cross, so no click may
    close a tab (the geninclude loads it only with kitty >= 0.49, slangc and the switch on)."""
    try:
        if opts is None:
            from kitty.fast_data_types import get_options
            opts = get_options()
        return "kittymux-pxbar" in str(getattr(opts, "custom_shaders", "") or "")
    except Exception:
        return False


def close_hit(os_window_id: int, x_px: float, y_px: float) -> int:
    """The tab whose close cross is under a window-pixel point, else 0 (also when the cross is not drawn)."""
    if not cross_shown():
        return 0
    w = _S.windows.get(os_window_id)
    band = band_at(os_window_id, x_px, y_px)
    if w is None or band is None or band.kind != "tab":
        return 0
    scale = w["sig"][4] if w.get("sig") else 1.0
    if x_px < w["right"] - CLOSE_W * scale or y_px >= band.y0 + TITLE_LINE * scale:
        return 0
    return band.tab_id


def toggle_group(project: str) -> None:
    """Open a folded group, or fold it again (a click on its label). The next pass redraws."""
    if project in _S.expanded:
        _S.expanded.discard(project)
    else:
        _S.expanded.add(project)


def expanded() -> frozenset:
    return frozenset(_S.expanded)


def prune_expanded(live_projects) -> None:
    """Forget opened groups whose tabs are all gone, so the set never outgrows the projects on screen."""
    _S.expanded &= set(live_projects)


def close_tab(boss, tab_id: int) -> None:
    """The close cross: closes the tab, except that a tab with a busy agent asks on its row first and a second click inside
    the guard's window closes it (kittymux_closeguard, the same rule as the close keys; no dialog)."""
    tab = boss.tab_for_id(tab_id)
    if tab is None:
        return
    try:
        import kittymux_agents
        import kittymux_closeguard as guard
        import kittymux_switches
        if not kittymux_switches.enabled("closeguard"):
            boss.close_tab(tab)
            return
        wins = list(tab)
        states = guard.window_states(wins)
        busy = guard.busy_windows({k: v[0] for k, v in states.items()}, [w.id for w in wins])
        if guard.decide("tab", tab.id, busy) == "close":
            (boss.close_tab_no_confirm if busy else boss.close_tab)(tab)
            return
        state, agent = states[str(busy[0])]
        guard.set_text(guard.question(kittymux_agents.product_label(agent) if agent else "", state, "click ×", "tab", len(busy) - 1),
                       guard.short("click ×"))
        guard.refresh(boss, busy)
        import kittymux_timers
        kittymux_timers.add("kittymux_closeguard", "lapse", guard.CONFIRM_S + 0.05, False)
    except Exception:
        boss.close_tab(tab)                      # never trap a close behind a bug
