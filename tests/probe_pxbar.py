# A test kitten (tests/smoke_pxbar.sh): writes the pixel tab bar's hit bands and the bar geometry as JSON.
#   kitty @ --to SOCK kitten tests/probe_pxbar.py OUT.json
import json
import sys

from kittens.tui.handler import result_handler


def main(args):
    return ""


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    rt = sys.modules.get("_kittymux_pxbar_rt")
    out = {"windows": {}}
    for osw, w in (getattr(rt, "windows", {}) or {}).items():
        sig = w.get("sig") or ()
        out["windows"][str(osw)] = {"right": w["right"], "scale": sig[4] if len(sig) > 4 else 1.0, "ms": getattr(rt, "last_ms", 0.0),
                                    "hits": [[h.kind, h.y0, h.y1, h.tab_id, h.project] for h in w["hits"]]}
    tm = boss.active_tab_manager
    if tm is not None:
        g = tm.tab_bar.window_geometry
        out["geom"] = [g.left, g.top, g.right, g.bottom]
        out["os_window_id"] = tm.os_window_id
    with open(args[1], "w") as f:
        json.dump(out, f)
