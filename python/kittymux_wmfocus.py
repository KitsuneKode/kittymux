"""Bring ONE kitty OS window to the front in the compositor, the one that holds a given kitty window.

One kitty process usually owns several OS windows, often on different workspaces and monitors. Asking Hyprland to
`focuswindow pid:<kitty>` focuses whichever of them it lists first: a notification for an agent on workspace 3 could
switch the other monitor to workspace 1. So we name the exact OS window instead: kitty first focuses the window (which
also selects its tab and makes it its OS window's active window, so that OS window takes its title), then we find the
Hyprland client of that pid with that title. When two OS windows show the same title, the window is tagged with a
unique title for a moment so its client can be told apart, and the title is handed back to the program afterwards.

Without Hyprland only kitty's own focus happens (the compositor decides the rest). Never raises.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

TAG_WAIT = 0.6          # seconds to wait for the compositor to see a tagged title


def os_window_title(ls: list, window_id: int) -> str | None:
    """The title the OS window holding `window_id` shows: its active tab's active window's title."""
    for osw in ls or []:
        if not any(w.get("id") == window_id for t in osw.get("tabs", []) for w in t.get("windows", [])):
            continue
        tab = next((t for t in osw.get("tabs", []) if t.get("is_active")), None)
        win = next((w for w in (tab or {}).get("windows", []) if w.get("is_active")), None)
        return (win or {}).get("title")
    return None


def pick_address(clients: list, pid: int, title: str | None) -> str | None:
    """The one client of this pid (with this title, when the pid has several); None when it can't be told."""
    mine = [c for c in clients or [] if c.get("pid") == pid]
    if len(mine) == 1:
        return mine[0].get("address")
    same = [c for c in mine if title is not None and c.get("title") == title]
    return same[0].get("address") if len(same) == 1 else None


def _hyprland(env) -> bool:
    return bool(env.get("HYPRLAND_INSTANCE_SIGNATURE")) and shutil.which("hyprctl") is not None


def _json(run, argv: list[str]):
    try:
        out = run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=4)
        return json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def focus(socket: str, window_id: int | str, pid: int | str, run=subprocess.run, env=None, sleep=time.sleep) -> bool:
    """Focus kitty window `window_id` (and its tab) in the kitty at `socket`, then its OS window in the compositor.
    True if kitty took the focus."""
    env = os.environ if env is None else env
    try:
        wid, kpid = int(window_id), int(pid)
    except (TypeError, ValueError):
        return False
    q = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    try:
        if run(["kitty", "@", "--to", socket, "focus-window", "--match", f"id:{wid}"], **q).returncode != 0:
            return False
    except (OSError, subprocess.SubprocessError):
        return False
    if not _hyprland(env):
        return True
    title = os_window_title(_json(run, ["kitty", "@", "--to", socket, "ls"]) or [], wid)
    clients = _json(run, ["hyprctl", "clients", "-j"]) or []
    address = pick_address(clients, kpid, title)
    if address is None and sum(1 for c in clients if c.get("pid") == kpid) > 1:
        address = _tagged(socket, wid, kpid, run, sleep)
    if address:
        try:
            run(["hyprctl", "dispatch", "focuswindow", f"address:{address}"], **q)
        except (OSError, subprocess.SubprocessError):
            pass
    return True


def _tagged(socket: str, wid: int, kpid: int, run, sleep) -> str | None:
    """Two OS windows look alike: title ours uniquely for a moment, find it, hand the title back."""
    q = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    tag = f"kittymux-focus-{os.getpid()}-{time.monotonic_ns() % 1_000_000}"
    try:
        run(["kitty", "@", "--to", socket, "set-window-title", "--match", f"id:{wid}", tag], **q)
        waited = 0.0
        while waited < TAG_WAIT:
            clients = _json(run, ["hyprctl", "clients", "-j"]) or []
            hit = pick_address(clients, kpid, tag)
            if hit:
                return hit
            sleep(0.05)
            waited += 0.05
        return None
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        try:      # no title: kitty goes back to the one the program set
            run(["kitty", "@", "--to", socket, "set-window-title", "--match", f"id:{wid}"], **q)
        except (OSError, subprocess.SubprocessError):
            pass
