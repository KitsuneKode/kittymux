#!/usr/bin/env bash
# mux-agents.sh — jump to any agent pane across every kitty instance,
# OS window and session.
#
# fzf list of panes whose foreground process tree contains an agent CLI,
# with live attention state from python/pane-state.py (panes-<pid>.json)
# and a live preview of the pane's last lines.
#
# Row:  <status> <glyph> <agent>  <title>  <cwd>  <where>
# Status: ● busy (title changing)   ! waiting (stale)   ○ idle

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/mux.sh"
source "$SCRIPT_DIR/fzf-style.sh"

STATE_DIR="${KITTYMUX_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/kittymux}"
SOURCE_OS_WIN_ID="$(source_os_window_id 2>/dev/null || true)"
AGENT_RE='claude|codex|cursor-agent|cursor|gemini|opencode|amp|devin|aider|crush|grok'

# Columns: label \t wid \t osid \t tabid \t session \t os_active_session \t sortkey \t socket
list_agents() {
    local sock pid
    for sock in /tmp/mykitty-*; do
        [[ -S "$sock" ]] || continue
        pid="${sock##*-}"
        kitty @ --to "unix:$sock" ls 2>/dev/null | python3 -c '
import json, os, re, sys, time

AGENT_RE = re.compile(r"^(" + sys.argv[1] + r")$")
PANES = sys.argv[2]
SRC_OS = int(sys.argv[3] or 0)
SOCK = sys.argv[4]

GLYPH = {
    "claude": "", "codex": "", "cursor-agent": "", "cursor": "",
    "gemini": "", "opencode": "", "amp": "", "devin": "",
    "aider": "✎", "crush": "♥", "grok": "✗",
}

panes = {}
try:
    with open(PANES) as f:
        panes = json.load(f)
except Exception:
    pass

data = json.load(sys.stdin)
now = time.monotonic()

ws_by_title = {}
try:
    import subprocess
    raw = subprocess.check_output(["hyprctl", "clients", "-j"], text=True,
                                  stderr=subprocess.DEVNULL)
    for c in json.loads(raw):
        if c.get("class") == "kitty" and c.get("title"):
            ws = (c.get("workspace") or {}).get("name") or ""
            if ws:
                ws_by_title[c["title"]] = ws
except Exception:
    pass

def abbrev(path):
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + "/"):
        path = "~/" + path[len(home)+1:]
    parts = path.split("/")
    return path if len(parts) <= 3 else "…/" + "/".join(parts[-2:])

def clean(title):
    return re.sub(r"^[\s⠁-⣿✳✻✽✦•●◐◓◑◒∙·.-]+", "", title or "").strip()

for ow in data:
    oid = ow.get("id")
    tabs = ow.get("tabs") or []
    active_tab = next((t for t in tabs if t.get("is_active")), tabs[0] if tabs else None)
    os_sess = ""
    if active_tab:
        for w in active_tab.get("windows") or []:
            os_sess = (w.get("session_name") or "").strip()
            if os_sess:
                break
    os_title = (active_tab or {}).get("title") or ""
    ws = ws_by_title.get(os_title, "")

    for t in tabs:
        for w in t.get("windows") or []:
            agent = ""
            for p in w.get("foreground_processes") or []:
                for arg in p.get("cmdline") or []:
                    name = os.path.basename(str(arg)).lower()
                    if AGENT_RE.match(name):
                        agent = name
                        break
                if agent:
                    break
            if not agent:
                continue

            # Agent in the foreground tree = running. Title churn is the
            # busy signal: agents animate titles while working and go
            # quiet when waiting for input.
            st = panes.get(str(w["id"])) or {}
            ts = float(st.get("ts_title") or 0)
            fresh = ts and (now - ts) < 15
            if fresh:
                status, rank = "●", 1
            else:
                status, rank = "!", 0
            if w.get("is_focused"):
                status = "▸"

            title = clean(w.get("title") or t.get("title") or "")
            cwd = abbrev(w.get("cwd") or "")
            sess = (w.get("session_name") or "").strip()
            where = []
            if ws:
                where.append("ws " + ws)
            if oid != SRC_OS:
                where.append("win " + str(oid))
            if sess:
                where.append(sess)
            label = "%s %s %-12s %-38s %-26s %s" % (
                status, GLYPH.get(agent, "⚡"), agent,
                title[:38], cwd[:26], " · ".join(where))
            key = "%d:%014.3f" % (rank, -ts)
            print("\t".join([label, str(w["id"]), str(oid), str(t["id"]),
                             sess, os_sess, key, SOCK]))
' "$AGENT_RE" "$STATE_DIR/panes-$pid.json" "$SOURCE_OS_WIN_ID" "$sock" || true
    done
}

list="$(list_agents)"
[[ -n "$list" ]] || { notify_kitty "No agent panes running"; exit 0; }

# --list: print rows and exit (used by mux-send.sh)
if [[ "${1:-}" == "--list" ]]; then
    printf '%s\n' "$list"
    exit 0
fi

sorted="$(printf '%s\n' "$list" | sort -t$'\t' -k7,7)"

selected="$(
    printf '%s\n' "$sorted" \
    | fzf \
        "${FZF_KITTY_BASE[@]}" \
        --prompt="  agents › " \
        --delimiter=$'\t' \
        --with-nth=1 \
        --header=$'▸ focused  ● busy  ! waiting  ○ idle' \
        --header-first \
        --footer=$'enter: jump   esc: cancel' \
        --preview="kitty @ --to unix:{8} get-text -m id:{2} 2>/dev/null | tail -n 24" \
        --preview-window=right:55%:wrap:border-left \
        --preview-label=' pane ' \
        --preview-label-pos=2 \
        --no-sort
)" || exit 0

wid="$(printf '%s\n' "$selected" | cut -f2)"
osid="$(printf '%s\n' "$selected" | cut -f3)"
sess="$(printf '%s\n' "$selected" | cut -f5)"
os_sess="$(printf '%s\n' "$selected" | cut -f6)"
sock="$(printf '%s\n' "$selected" | cut -f8)"
[[ -n "$wid" && -n "$sock" ]] || exit 0

# Parked-session target: switch that OS window's group first.
if [[ -n "$sess" && "$sess" != "$os_sess" ]]; then
    kitty @ --to "unix:$sock" action --match "id:${wid}" goto_session "$sess" >/dev/null 2>&1 || true
fi

kitty @ --to "unix:$sock" focus-window --match "id:${wid}" >/dev/null 2>&1 || true
# Wayland: kitty can't move desktop focus across OS windows — help via hyprctl.
if [[ "$sock" == "${KITTY_SOCKET:-}" && "$osid" == "$SOURCE_OS_WIN_ID" ]]; then
    :
else
    title="$(kitty @ --to "unix:$sock" ls 2>/dev/null | python3 -c "
import json, sys
target = int('$osid' or 0)
for ow in json.load(sys.stdin):
    if ow['id'] != target:
        continue
    for t in ow.get('tabs') or []:
        if t.get('is_active'):
            print(t.get('title') or ''); sys.exit(0)
" 2>/dev/null || true)"
    focus_hyprland_by_title "$title" 2>/dev/null || true
fi
