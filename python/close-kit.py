# kittymux close guard: kitty's close keys, but a busy agent (Working or Needs you) asks first, on one line in its own pane title bar.
#   map ctrl+shift+w kitten close-kit.py window ctrl+shift+w          (kitty's close_window)
#   map ctrl+alt+q   kitten close-kit.py window ctrl+alt+q confirm    (close_window_with_confirmation: kitty's dialog for a running program stays)
#   map ctrl+shift+q kitten close-kit.py tab ctrl+shift+q             (close_tab)
# The `closeguard` switch off: every key does what kitty's own action does, without asking.
# A no-UI kitten: it runs inside kitty, reads the scanner's verdicts from the same process (as the pane title bar does), and closes the way
# kitty's own `close_window` / `close_tab` do when nothing is busy. The rules are in kittymux_closeguard (pure, unit-tested).
import os
import sys
import time

from kittens.tui.handler import result_handler


def main(args):
    return ""


def _paths() -> None:
    here = os.path.dirname(os.path.realpath(_paths.__code__.co_filename))   # kitty runs a kitten without __file__
    for d in (os.environ.get("KITTY_CONFIG_DIRECTORY") or os.path.expanduser("~/.config/kitty"), here):
        if d and d not in sys.path:
            sys.path.insert(0, d)


def _states(windows) -> dict:
    import kittymux_closeguard
    return kittymux_closeguard.window_states(windows)


def _can_ask_inline(boss, ids) -> bool:
    """The question shows on the tab's row in the bar, and on a pane title bar when kitty draws one with kittymux's hook. With neither on
    screen (bar hidden, title bars off) there is nowhere to ask in a line."""
    try:
        import kittymux_features
        for wid in ids:
            w = boss.window_id_map.get(int(wid))
            if w is None:
                continue
            tab = w.tabref()
            tm = tab.tab_manager_ref() if tab is not None else None
            if tm is not None and tm.tab_bar_should_be_visible:
                return True
            if getattr(w, "_title_bar_screen", None) is not None and kittymux_features.enabled("panetitle"):
                return True
    except Exception:
        pass
    return False


def _close(boss, what, window, tab, confirm=False, answered=False) -> None:
    """Close as kitty's own action would. `answered`: the user already said yes to our question, so kitty does not ask again."""
    if what == "tab" and tab is not None:
        if answered:
            boss.close_tab_no_confirm(tab)
        else:
            boss.close_tab(tab)                  # kitty's own tab close (its confirm_os_window_close rules still apply)
    elif confirm and not answered:
        boss.close_window_with_confirmation()    # kitty's dialog when a program runs, as this key always did
    else:
        boss.mark_window_for_close(window)       # exactly kitty's close_window


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    what = args[1] if len(args) > 1 and args[1] in ("window", "tab") else "window"
    chord = args[2] if len(args) > 2 else ("ctrl+shift+q" if what == "tab" else "ctrl+shift+w")
    confirm = "confirm" in args[3:]
    window = boss.window_id_map.get(target_window_id) or boss.active_window
    if window is None:
        return
    tab = window.tabref()
    try:
        _paths()
        import kittymux_agents
        import kittymux_closeguard as guard
        import kittymux_switches
        if not kittymux_switches.enabled("closeguard"):
            _close(boss, what, window, tab, confirm)
            return
        wins = list(tab) if (what == "tab" and tab is not None) else [window]
        states = _states(wins)
        busy = guard.busy_windows({k: v[0] for k, v in states.items()}, [w.id for w in wins])
        target = tab.id if (what == "tab" and tab is not None) else window.id
        if guard.decide(what, target, busy) == "close":
            _close(boss, what, window, tab, confirm, answered=bool(busy))
            return
        first = str(busy[0])
        state, agent = states[first]
        line = guard.question(kittymux_agents.product_label(agent) if agent else "", state, chord, what, len(busy) - 1)
        if not _can_ask_inline(boss, busy):
            guard.clear()                        # no title bar to ask on: kitty's own confirmation is the honest fallback
            boss.confirm(line.split(" · ")[0], lambda ok, *_: ok and _close(boss, what, window, tab, answered=True), window=window,
                         title="Close a busy agent?")
            return
        guard.set_text(line, guard.short(chord))
        guard.refresh(boss, busy)
        import kittymux_timers
        kittymux_timers.add("kittymux_closeguard", "lapse", guard.CONFIRM_S + 0.05, False)   # the question lapses on its own
    except Exception:
        import traceback
        sys.stderr.write("kittymux close guard: " + traceback.format_exc())
        _close(boss, what, window, tab, confirm)  # never trap a close behind a bug
