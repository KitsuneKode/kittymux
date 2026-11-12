# kittymux tab navigation: ctrl+tab / ctrl+shift+tab walk the tabs in the order the bar DRAWS them.
#   map ctrl+tab       kitten tabnav-kit.py next
#   map ctrl+shift+tab kitten tabnav-kit.py prev
# With the pixel tab bar up, the next row it shows (kittymux_groups.step: drawn order, wrapping, never into a folded group).
# Otherwise kitty's own next_tab / previous_tab. A no-UI kitten: it runs inside kitty, in the same process as the bar.
import os
import sys

from kittens.tui.handler import result_handler


def main(args):
    return ""


def _paths() -> None:
    here = os.path.dirname(os.path.realpath(_paths.__code__.co_filename))   # kitty runs a kitten without __file__
    for d in (os.environ.get("KITTY_CONFIG_DIRECTORY") or os.path.expanduser("~/.config/kitty"), here):
        if d and d not in sys.path:
            sys.path.insert(0, d)


def target(boss, direction: int):
    """(tab manager, tab) to activate, or None to let kitty step in its own order."""
    tm = boss.active_tab_manager
    if tm is None or tm.active_tab is None:
        return None
    _paths()
    import kittymux_groups
    import kittymux_pxbar
    if not kittymux_pxbar.active(tm.os_window_id):
        return None
    groups = kittymux_pxbar.drawn_groups(tm.os_window_id)
    if not groups:
        return None
    tid = kittymux_groups.step(groups, tm.active_tab.id, direction)
    tab = tm.tab_for_id(tid) if tid is not None else None
    return (tm, tab) if tab is not None else None


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    direction = -1 if len(args) > 1 and args[1] in ("prev", "previous") else 1
    try:
        got = target(boss, direction)
    except Exception:
        got = None
    if got is None:
        boss.combine("previous_tab" if direction < 0 else "next_tab")
        return
    tm, tab = got
    tm.set_active_tab(tab)
