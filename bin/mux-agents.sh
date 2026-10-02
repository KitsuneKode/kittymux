#!/usr/bin/env bash
# mux-agents.sh — jump to any agent pane across every kitty instance,
# OS window and session.
#
# fzf list of panes whose foreground process tree contains an agent CLI,
# with live attention state from python/pane-state.py (panes-<pid>.json)
# and a live preview of the pane's last lines.
#
# Row:  <status> <glyph> <agent>  <title>  <cwd>  <where>  [message]
# Status: ◆ waiting on you   ✓ done   ◐ working   ○ idle   ▸ focused
# (explicit status from agent hooks via bin/mux-status; falls back to title activity)
#
#   mux-agents.sh              fzf picker (jump)
#   mux-agents.sh --list       print rows (used by mux-send.sh)
#   mux-agents.sh --next-waiting   jump to the next agent waiting on you (round-robin)

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/mux.sh"
source "$SCRIPT_DIR/fzf-style.sh"

STATE_DIR="${KITTYMUX_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/kittymux}"
SOURCE_OS_WIN_ID="$(source_os_window_id 2>/dev/null || true)"

# Columns: label \t wid \t osid \t tabid \t session \t os_active_session \t sortkey \t socket \t status
list_agents() {
    local sock pid
    local sockets
    if [[ -n "${KITTYMUX_SOCKET_GLOB:-}" ]]; then sockets="$(ls $KITTYMUX_SOCKET_GLOB 2>/dev/null)"   # tests only
    else sockets="$(mux_kitty_sockets)"; fi
    for sock in $sockets; do
        mux_owned_socket "$sock" || continue          # never talk to a socket we don't own
        pid="${sock##*-}"
        kitty @ --to "unix:$sock" ls 2>/dev/null | python3 -c '
import json, os, re, sys, time

PANES = sys.argv[1]
SRC_OS = int(sys.argv[2] or 0)
SOCK = sys.argv[3]
sys.path.insert(0, sys.argv[4])
import kittymux_agents as KA
SYM = {"limited": "⊘", "waiting": "◆", "working": "◐", "done": "✓", "idle": "○"}
RANK = {"limited": 0, "waiting": 0, "done": 1, "working": 2, "idle": 3}

# hook status + the scanner'"'"'s verdicts (scan-<pid>.json), merged — the same view the tab bar has
panes = KA.load_panes(PANES)

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
    return KA.strip_title_prefix(title)

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
                agent = KA.agent_in(p.get("cmdline") or []) or ""
                if agent:
                    break
            if not agent:
                continue

            # Agent in the foreground tree = running. The scanner verdict (screen + hooks,
            # see kittymux_state.py) is the answer; a quiet title is never read as waiting.
            entry = panes.get(str(w["id"])) or {}
            status_word = KA.resolve_status(entry, True, now)
            msg = KA.resolve_msg(entry, status_word)
            ts = float(entry.get("ts_status") or entry.get("ts_title") or 0)
            status, rank = SYM.get(status_word, "○"), RANK.get(status_word, 3)
            if ow.get("is_focused") and t.get("is_active") and w.get("is_focused"):
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
                status, KA.AGENTS.get(agent, KA.FALLBACK).glyph, agent,
                title[:38], cwd[:26], " · ".join(where))
            if msg:
                label += "  — " + msg[:60]
            key = "%d:%014.3f" % (rank, ts)      # oldest first: longest-waiting on top
            print("\t".join(re.sub(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2066-\u2069]", " ", field) for field in
                            [label, str(w["id"]), str(oid), str(t["id"]),
                             sess, os_sess, key, SOCK, status_word]))
' "$STATE_DIR/panes-$pid.json" "$SOURCE_OS_WIN_ID" "$sock" "$SCRIPT_DIR/../python" || true
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

# Bash treats tab as IFS whitespace and collapses empty columns. Split literally.
parse_agent_row() {
    local row="$1"
    local -a fields=()
    while [[ "$row" == *$'\t'* ]]; do
        fields+=("${row%%$'\t'*}")
        row="${row#*$'\t'}"
    done
    fields+=("$row")
    [[ ${#fields[@]} == 9 ]] || return 1
    label="${fields[0]}" wid="${fields[1]}" osid="${fields[2]}"
    sess="${fields[4]}" os_sess="${fields[5]}" sock="${fields[7]}"
}

jump_to() {  # wid osid sess os_sess sock
    local wid="$1" osid="$2" sess="$3" os_sess="$4" sock="$5"
    [[ -n "$wid" && -n "$sock" ]] || return 0

    # Parked-session target: switch that OS window's group first.
    if [[ -n "$sess" && "$sess" != "$os_sess" ]]; then
        kitty @ --to "unix:$sock" action --match "id:${wid}" goto_session "$sess" >/dev/null 2>&1 || true
    fi

    kitty @ --to "unix:$sock" focus-window --match "id:${wid}" >/dev/null 2>&1 || true
    # Wayland: kitty can't move desktop focus across OS windows — help via hyprctl.
    if [[ "$sock" == "${KITTY_SOCKET:-}" && "$osid" == "$SOURCE_OS_WIN_ID" ]]; then
        :
    else
        local title
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
}

# --next-waiting: the attention queue. Round-robin over agents waiting on you,
# longest-waiting first; never re-picks the pane you are already in.
if [[ "${1:-}" == "--next-waiting" ]]; then
    waiting="$(printf '%s\n' "$sorted" | awk -F'\t' '$9=="waiting" || $9=="limited"')"
    [[ -n "$waiting" ]] || { notify_kitty "No agents are waiting on you"; exit 0; }
    last_file="$STATE_DIR/next-waiting.last"
    last="$(cat "$last_file" 2>/dev/null || true)"
    pick=""; take_next=0
    if [[ -z "$last" ]]; then take_next=1; fi
    while IFS= read -r row; do
        parse_agent_row "$row" || continue
        id="$sock:$wid"
        [[ "$label" == "▸"* ]] && continue          # you are already here
        if (( take_next )); then pick="$row"; break; fi
        [[ "$id" == "$last" ]] && take_next=1
    done <<<"$waiting"
    if [[ -z "$pick" ]]; then   # wrapped around: take the first non-focused one
        while IFS= read -r row; do
            parse_agent_row "$row" || continue
            [[ "$label" == "▸"* ]] && continue
            pick="$row"; break
        done <<<"$waiting"
    fi
    [[ -n "$pick" ]] || { notify_kitty "The only waiting agent is this one"; exit 0; }
    parse_agent_row "$pick" || exit 0
    mkdir -p "$STATE_DIR"; printf '%s' "$sock:$wid" > "$last_file"
    jump_to "$wid" "$osid" "$sess" "$os_sess" "$sock"
    exit 0
fi

selected="$(
    printf '%s\n' "$sorted" \
    | fzf \
        "${FZF_KITTY_BASE[@]}" \
        --prompt="  agents › " \
        --delimiter=$'\t' \
        --with-nth=1 \
        --header=$'▸ focused  ◆ waiting  ✓ done  ◐ working  ○ idle' \
        --header-first \
        --footer=$'enter: jump   esc: cancel' \
        --preview="kitty @ --to unix:{8} get-text -m id:{2} 2>/dev/null | tail -n 24" \
        --preview-window=right:55%:wrap:border-left \
        --preview-label=' pane ' \
        --preview-label-pos=2 \
        --no-sort
)" || exit 0

parse_agent_row "$selected" || exit 0
jump_to "$wid" "$osid" "$sess" "$os_sess" "$sock"
