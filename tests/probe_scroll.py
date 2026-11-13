# A test kitten (tests/smoke_scroll.sh): how far a window is scrolled and the last line window.as_text() shows.
#   kitty @ --to SOCK kitten tests/probe_scroll.py OUT.json WINDOW_ID
import json

from kittens.tui.handler import result_handler


def main(args):
    return ""


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    w = boss.window_id_map.get(int(args[2]))
    shown = [ln for ln in w.as_text().splitlines() if ln.strip()]
    with open(args[1], "w") as f:
        json.dump({"scrolled_by": w.screen.scrolled_by, "shown_last": shown[-1] if shown else ""}, f)
