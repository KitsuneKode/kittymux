"""A synthetic tabs.json for the client rigs (tests/shot_client.sh): every state, a muted agent, progress, a split tab, two spaces.
Every name is made up (calm-otter, quiet-heron); nothing is copied from a real machine.
Usage: client_fixture.py STATE_DIR VARIANT PID   (PID: a live process standing in for the kitty; the client hides rows whose pid exited)."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_tabsnap as T  # noqa: E402

COLORS = {"background": 0x101014, "foreground": 0xE6E6EA, "active_border_color": 0xC792EA,
          **{f"color{n}": c for n, c in zip(range(1, 16), (0xF07178, 0xC3E88D, 0xFFCB6B, 0x82AAFF, 0xC792EA, 0x89DDFF, 0xBBBBBB,
                                                           0x545454, 0xF07178, 0xC3E88D, 0xFFCB6B, 0x82AAFF, 0xC792EA, 0x89DDFF, 0xFFFFFF))}}
LIGHT = {"background": 0xF6F6F4, "foreground": 0x2A2A2E, "active_border_color": 0x7C4DFF,
         **{f"color{n}": c for n, c in zip(range(1, 16), (0xD32F2F, 0x2E7D32, 0xB26A00, 0x1565C0, 0x7B1FA2, 0x00838F, 0x555555,
                                                          0x888888, 0xD32F2F, 0x2E7D32, 0xB26A00, 0x1565C0, 0x7B1FA2, 0x00838F, 0x111111))}}


BASE = ""                 # set by main(): the rig's private folder for the synthetic projects

def win(wid, active=False, agent="", state="", **kw):
    return {"window_id": wid, "active": active, "cwd": kw.pop("cwd", ""), "agent": agent, "state": state, **kw}


def tabs(variant):
    a = os.path.join(BASE, "calm-otter")
    b = os.path.join(BASE, "quiet-heron")
    rows = [
        {"tab_id": 1, "title": "Port the config loader", "active": True, "windows": [win(11, True, "claude", "working", cwd=a, progress=0.64)]},
        {"tab_id": 2, "title": "Review the parser", "windows": [win(12, True, "codex", "waiting", cwd=a, reason="Allow edit to parser.rs?")]},
        {"tab_id": 3, "title": "api dev server", "windows": [win(13, True, cwd=a), win(14, False, cwd=a)]},
        {"tab_id": 4, "title": "Fix the flaky test", "windows": [win(15, True, "gemini", "done", cwd=b)]},
        {"tab_id": 5, "title": "Write the release notes", "windows": [win(16, True, "opencode", "working", cwd=b)]},
        {"tab_id": 6, "title": "Background lint", "windows": [win(17, True, "claude", "waiting", cwd=b, muted=True, reason="Run cargo fmt?")]},
        {"tab_id": 7, "title": "Migrate the schema", "windows": [win(18, True, "claude", "error", cwd=b, reason="Tool failed")]},
    ]
    if variant == "changed":
        rows[1]["windows"][0].update(state="working", reason="")
        rows[0]["windows"][0]["progress"] = 0.71
        rows.pop(3)
    return rows


def main(argv):
    global BASE
    sdir, variant, pid = argv[1], argv[2], int(argv[3])
    os.makedirs(sdir, exist_ok=True)
    # synthetic folders inside the rig's own private tree (next to its state dir): never a shared /tmp path, never a real repository
    BASE = os.path.join(os.path.dirname(os.path.abspath(sdir)), "fixture-home")
    for d in (os.path.join(BASE, "calm-otter"), os.path.join(BASE, "quiet-heron")):
        os.makedirs(d, exist_ok=True)
    spec = {"os_window_id": 1, "wm_class": "kitty", "focused": True, "colors": LIGHT if variant == "light" else COLORS, "tabs": tabs(variant)}
    T.publish(sdir, pid, [spec], time.time() - 240, alive=lambda p: True, home=BASE)
    doc = json.load(open(T.path_for(sdir)))
    for w in doc["windows"]:          # the age a finished tab shows: four minutes
        for t in w["tabs"]:
            if t["since"]:
                t["since"] = round(time.time() - 240, 1)
    with open(T.path_for(sdir) + ".tmp", "w") as f:
        json.dump(doc, f)
    os.replace(T.path_for(sdir) + ".tmp", T.path_for(sdir))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
