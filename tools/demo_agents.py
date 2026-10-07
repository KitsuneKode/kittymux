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
import kittymux_titles as titles  # noqa: E402
import kittymux_ui as U  # noqa: E402

DARK = {"background": 0x1a1b26, "foreground": 0xc0caf5, "active_border_color": 0xf08fb8, "color9": 0xf7768e, "color10": 0x9ece6a, "color11": 0xe0af68, "color12": 0x7aa2f7}
LIGHT = {"background": 0xeff1f5, "foreground": 0x4c4f69, "active_border_color": 0x1e66f5, "color9": 0xd20f39, "color10": 0x40a02b, "color11": 0xdf8e1d, "color12": 0x1e66f5}


def rows():
    P = deck.PaneData
    split = (P(11, "\ue0a0", "codex", False, "working", "Mount unused partitions", True), P(12, "\ue0a0", "codex", False, "waiting", "Audit the Rust backend"),
             P(13, "\ue0a0", "codex", False, "idle", "Audit codebase security"))
    def shown(raw, agent, project):                       # what the bar and the panel really show
        return titles.tidy(raw, agent, project).text
    return [
        deck.RowData(1, 11, title=shown("Audit codebase security and dependencies", "codex", "api"), glyph="\ue0a0", agent="codex", branch="main", cwd="/home/u/api", panes=3,
                     status="working", ports=(34893, 42735), index=1, pane_rows=split, current=True),
        deck.RowData(2, 21, title=shown("Multi-Subagent Scan: 200-600G", "devin", "scan"), glyph="\ue0a0", agent="devin", branch="main", cwd="/home/u/scan", status="waiting", age="4m", index=2),
        deck.RowData(3, 31, title=shown("I can't do that. I don't have access to the files", "devin", "notes"), glyph="\ue0a0", agent="devin", branch="main", cwd="/home/u/notes",
                     status="done", age="3m", index=3),
        deck.RowData(4, 41, title=shown("Followup PRs and provider reliability audit for the web app", "devin", "web"), glyph="\ue0a0", agent="devin",
                     branch="fix/provider-reliability-audit", cwd="/home/u/web", pr="#118", status="", index=4, panes=2,
                     pane_rows=(P(41, "\ue0a0", "devin", False, "", "Followup PRs"), P(42, "\ue0a0", "devin", False, "", "devin: I can't access"))),
        deck.RowData(5, 51, title=shown("Claude Code", "claude", "hypr"), glyph="\ue0a0", agent="claude", branch="", cwd="/home/u/.config/hypr", ports=(33649,), status="limited", age="\u21bb42m", index=5),
        deck.RowData(6, 61, title=shown("\u2733 Session continuation and next steps", "claude", "kittymux"), glyph="\ue0a0", agent="claude", branch="main", cwd="/home/u/kittymux",
                     status="working", index=6),
        deck.RowData(7, 71, title="~", glyph="", agent="", branch="", cwd="/home/u", panes=2, status="", index=7),
    ]


def main():
    cols = int(sys.argv[1]) if len(sys.argv) > 1 else 38
    theme = LIGHT if (len(sys.argv) > 2 and sys.argv[2] == "light") else DARK
    k = U.Kit(T.from_colors(theme))
    rs = rows()
    sel = 1
    out = [V.summary_row(k, len(rs), sum(1 for r in rs if r.status in V.NEEDS), sum(1 for r in rs if r.status == "working"), cols),
           k.tabs([("\u25a6", "Agents", True, 0), ("\u25d4", "Usage", False, 0), ("\u2709", "Inbox", False, 3)], cols),
           V.header_row(k, "kitty session", len(rs), True, cols, sum(1 for r in rs if r.status in V.NEEDS))]
    for i, r in enumerate(rs):
        opened = r.tab_id == 1                                   # tab 1 is open (you are in it); tab 4 is a split left closed
        out += [V.title_row(k, r, i == sel, False, cols), V.context_row(k, r, i == sel, False, cols, "/home/u", (opened if len(r.pane_rows) >= 2 else None))]
        if r.pane_rows and opened:
            out += [V.pane_row(k, r, j, j == 0, cols) for j in range(len(r.pane_rows))]
    bar, _regions = V.action_bar(k, [("⏎", "jump", "ENTER"), ("/", "find", "/"), ("a", "join", "A"), ("t", "detach", "T")], cols, hot=1)
    out.append(bar)
    sys.stdout.write("\x1b[2J\x1b[H" + "\r\n".join(U.to_ansi(line) for line in out) + "\x1b[0m")
    sys.stdout.flush()
    import time
    time.sleep(3600)


if __name__ == "__main__":
    main()
