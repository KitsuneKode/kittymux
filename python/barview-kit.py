# kittymux bar view: the pixel tab bar's mouse-only controls, from the keyboard (leader f, leader , and leader .).
#   kitten barview-kit.py folds       open every group the bar shows folded, or fold back the ones opened
#   kitten barview-kit.py up|down     page the bar's list when its tabs don't all fit (as the "↑ N" / "↓ N" bands do)
# A no-UI kitten: it runs inside kitty, in the same process as the bar, and acts on the OS window you are in. Without the
# pixel bar there is nothing to fold or page, and it does nothing.
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


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    what = args[1] if len(args) > 1 else ""
    window = boss.window_id_map.get(target_window_id)
    tm = boss.os_window_map.get(window.os_window_id) if window is not None else boss.active_tab_manager
    if tm is None:
        return
    _paths()
    import kittymux_pxbar
    import kittymux_scan
    osw = tm.os_window_id
    if not kittymux_pxbar.active(osw):
        return
    if what == "folds":
        changed = kittymux_pxbar.toggle_folds(osw)
    elif what in ("up", "down"):
        kittymux_pxbar.page(osw, -1 if what == "up" else 1)
        changed = True
    else:
        return
    if changed:
        kittymux_scan.refresh_bar(tm)
