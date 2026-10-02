# Test helper, run INSIDE a kitty: `kitty @ kitten tests/probe_motion.py LOG SECONDS` records every call kitty makes to
# TabManager.handle_tab_bar_mouse for SECONDS seconds, one JSON line [x, y, button, action] each, then restores the method.
# Answers one question: does kitty hand Python mouse motion over the tab bar when no button is held?
import json

from kittens.tui.handler import result_handler


def main(args):
    return ""


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    from kitty.fast_data_types import add_timer
    from kitty.tabs import TabManager
    log, seconds = args[1], float(args[2])
    original = TabManager.handle_tab_bar_mouse

    def spy(self, x, y, button, modifiers, action):
        with open(log, "a") as f:
            f.write(json.dumps([round(x), round(y), button, action]) + "\n")
        return original(self, x, y, button, modifiers, action)

    TabManager.handle_tab_bar_mouse = spy

    def restore(_timer_id):
        TabManager.handle_tab_bar_mouse = original

    add_timer(restore, seconds, False)
