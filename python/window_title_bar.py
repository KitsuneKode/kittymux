# kitty's per-pane title bar asks this file (in the kitty config dir) for `{custom}` — see `window_title_template` in kittymux_layout.gated_conf.
#
# kitty loads it ONCE per process and never again, so it holds no logic: it hands over to kittymux_panetitle, which tab_bar.py reloads on every config
# load. "" (any failure, the switch off, a pane without a directory) makes the template fall back to kitty's own title — never a blank bar.
import os
import sys

_dirs = [os.environ.get("KITTY_CONFIG_DIRECTORY") or os.path.expanduser("~/.config/kitty")]
for _d in _dirs:
    if _d and _d not in sys.path:
        sys.path.insert(0, _d)


def draw_window_title(data):
    try:
        import kittymux_panetitle
        return kittymux_panetitle.draw(data)
    except Exception:
        return ""
