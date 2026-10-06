# Native pane controls. The choice overlay disappears BEFORE kitty moves the pane.
# No remote-control discovery, subprocesses, timers or focus guessing.
from kittens.tui.handler import result_handler


def main(args):
    return ""


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    window = boss.window_id_map.get(target_window_id)
    tab = window.tabref() if window is not None else None
    if tab is None:
        return

    def chosen(key):
        current = boss.window_id_map.get(target_window_id)
        if current is not window or current.tabref() is not tab or key not in {"h", "j", "k", "l", "r", "s", "e", "a"} or not key:
            return
        tab.set_active_window(window)
        if key in "hjkl":
            tab.move_window({"h": "left", "j": "down", "k": "up", "l": "right"}[key])
        elif key == "a":
            tab.swap_with_window()
        else:
            action, args = {"r": ("rotate", ()), "s": ("rotate", ("180",)), "e": ("equalize", ())}[key]
            tab.layout_action(action, args)

    popup = boss.choose("Pane controls\nSwap with a neighbor, or rearrange the current split.\nRotate and equalize use the splits layout. Esc cancels.",
                chosen, "h:h · Swap left", "j:j · Swap down", "k:k · Swap up", "l:l · Swap right", "r:r · Rotate split",
                "s:s · Swap split sides", "e:e · Equalize", "a:a · Choose a pane to swap", window=window, title="kittymux-panes")

    if popup is not None:
        popup.set_title("kittymux-panes")
