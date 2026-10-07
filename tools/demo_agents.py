#!/usr/bin/env python3
"""Print the panel's Agents view for a made-up world, drawn by the real row functions (no kitty needed to run; a terminal to look at).
   python3 tools/demo_agents.py [COLS] [dark|light] — used by tests/shot_agents.sh. Titles and paths are synthetic."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
import kittymux_agentsview as V  # noqa: E402
import kittymux_deck as deck  # noqa: E402
import kittymux_theme as T  # noqa: E402
import kittymux_ui as U  # noqa: E402

DARK = {"background": 0x1a1b26, "foreground": 0xc0caf5, "active_border_color": 0xf08fb8, "color9": 0xf7768e, "color10": 0x9ece6a, "color11": 0xe0af68, "color12": 0x7aa2f7}
LIGHT = {"background": 0xeff1f5, "foreground": 0x4c4f69, "active_border_color": 0x1e66f5, "color9": 0xd20f39, "color10": 0x40a02b, "color11": 0xdf8e1d, "color12": 0x1e66f5}


def rows():
    P = deck.PaneData
    return [
        deck.RowData(1, 11, title="Audit codebase security and dependencies", glyph="", agent="codex", branch="main", cwd="/home/u/api", panes=3, status="working",
                     ports=(34893, 42735), index=1, pane_rows=(P(11, "", "codex", False, "working", "Mount unused partitions", True), P(12, "", "codex", False, "waiting", "Audit the Rust backend"),
                                                                P(13, "", "codex", False, "idle", "Audit codebase security"))),
        deck.RowData(2, 21, title="Multi-Subagent Scan: 200-600G", glyph="", agent="devin", branch="main", cwd="/home/u/scan", status="waiting", index=2, current=False),
        deck.RowData(3, 31, title="I can't do that. I don't have access to the files", glyph="", agent="devin", branch="main", cwd="/home/u/x", status="done", index=3),
        deck.RowData(4, 41, title="Followup PRs and provider reliability", glyph="", agent="devin", branch="fix/provider-reliability-audit", cwd="/home/u/web", pr="#118", status="", index=4),
        deck.RowData(5, 51, title="Port Hyprland configs to Lua", glyph="", agent="codex", branch="", cwd="/home/u/.config/hypr", ports=(33649,), status="limited", index=5),
        deck.RowData(6, 61, title="Session continuation", glyph="", agent="claude", branch="main", cwd="/home/u/kittymux", status="working", index=6, current=True),
        deck.RowData(7, 71, title="~", glyph="", agent="", branch="", cwd="/home/u", panes=2, status="", index=7),
    ]


def main():
    cols = int(sys.argv[1]) if len(sys.argv) > 1 else 38
    theme = LIGHT if (len(sys.argv) > 2 and sys.argv[2] == "light") else DARK
    k = U.Kit(T.from_colors(theme))
    rs = rows()
    sel = 1
    out = [V.summary_row(k, len(rs), sum(1 for r in rs if r.status in V.NEEDS), sum(1 for r in rs if r.status == "working"), cols),
           k.tabs([("▦", "Agents", True, 0), ("◔", "Usage", False, 0), ("✉", "Inbox", False, 3)], cols),
           V.header_row(k, "kitty session", len(rs), True, cols)]
    for i, r in enumerate(rs):
        out += [V.title_row(k, r, i == sel, False, cols), V.context_row(k, r, i == sel, False, cols, "/home/u")]
        if r.pane_rows and i == 0:
            out += [V.pane_row(k, r, j, j == 0, cols) for j in range(len(r.pane_rows))]
    bar, _regions = V.action_bar(k, [("⏎", "jump", "ENTER"), ("/", "find", "/"), ("a", "join", "A"), ("t", "detach", "T")], cols, hot=1)
    out.append(bar)
    sys.stdout.write("\x1b[2J\x1b[H" + "\r\n".join(U.to_ansi(line) for line in out) + "\x1b[0m")
    sys.stdout.flush()
    import time
    time.sleep(3600)


if __name__ == "__main__":
    main()
