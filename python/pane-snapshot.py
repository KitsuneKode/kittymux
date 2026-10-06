# A tab-scoped snapshot from kitty's own objects, for preview kittens.
# Return JSON through the native no_ui kitten API; never export env or user vars.
import json
from kittens.tui.handler import result_handler


def main(args):
    return ""


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    try:
        tab = boss.tab_for_id(int(args[1]))
    except (IndexError, ValueError):
        return "null"
    if tab is None:
        return "null"
    groups = list(tab.windows.groups)
    wins = [boss.window_id_map[g.main_window_id] for g in groups if g.main_window_id in boss.window_id_map]
    active = tab.windows.active_group
    active_id = active.main_window_id if active is not None else 0
    rects = [[g.main_window_id, g.geometry.left, g.geometry.top, g.geometry.right, g.geometry.bottom]
             for g in groups if g.is_visible_in_layout and g.geometry is not None]
    return json.dumps({"id": tab.id, "title": tab.name or tab.title, "active_window_history": [active_id],
                       "windows": [{"id": w.id, "title": w.title, "cwd": w.child.current_cwd or w.child.cwd,
                                    "foreground_processes": [{"cmdline": p.get("cmdline", [])}
                                                             for p in w.child.foreground_processes]} for w in wins],
                       "rects": rects})
