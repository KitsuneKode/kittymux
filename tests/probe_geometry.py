# Test helper, run INSIDE a kitty: `kitty @ kitten tests/probe_geometry.py OUT.json` writes every tab's layout and its windows' real geometry
# (pixels and cells), so a rig can check where panes ended up instead of trusting `kitty @ ls`, which has no positions.
import json

from kittens.tui.handler import result_handler


def main(args):
    return ""


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    out = {}
    for tab in boss.all_tabs:
        out[str(tab.id)] = {
            "os_window": tab.os_window_id,
            "layout": tab.current_layout.name,
            "windows": [{"id": w.id, "title": w.title, "g": [int(w.geometry.left), int(w.geometry.top), int(w.geometry.right), int(w.geometry.bottom)],
                         "cols": w.screen.columns, "lines": w.screen.lines, "overlay": w.overlay_parent is not None} for w in tab],
        }
    with open(args[1], "w") as f:
        f.write(json.dumps(out))
