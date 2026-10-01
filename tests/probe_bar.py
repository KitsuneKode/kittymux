# Test helper, run INSIDE a kitty: `kitty @ kitten tests/probe_bar.py OUT.json` writes the vertical bar's real geometry
# (cell size in px, bar rectangle, every tab's row extent), so the real-mouse smoke tests click where things actually
# are instead of where one machine's font puts them.
import json

from kittens.tui.handler import result_handler


def main(args):
    return ""


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    from kitty.fast_data_types import get_os_window_size
    tm = boss.active_tab_manager
    bar = tm.tab_bar
    g = bar.window_geometry
    size = get_os_window_size(tm.os_window_id) or {}
    out = {"cw": bar.cell_width, "ch": bar.cell_height, "left": g.left, "top": g.top, "right": g.right, "bottom": g.bottom,
           "os_w": size.get("width"), "os_h": size.get("height"),
           "extents": [[te.tab_id, te.y.start, te.y.end] for te in bar.tab_extents]}
    with open(args[1], "w") as f:
        f.write(json.dumps(out))
