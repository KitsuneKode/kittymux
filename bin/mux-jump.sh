#!/usr/bin/env bash
# agent-jump.sh — cycle focus to the next pane running an agent CLI,
# scoped to the current session's tabs.
# Bound to ctrl+alt+a. Repeat presses rotate through all agent panes.

set -u

AGENTS='claude|codex|devin|aider|opencode|gemini|cursor-agent|amp|crush'
STATE=/tmp/kittymux-jump.last

rc_to="${KITTY_LISTEN_ON:-}"
if [[ -z "$rc_to" ]]; then
    # Prefer the kitty process that owns the compositor-focused window —
    # socket files are named /tmp/mykitty-<pid>.
    pid=$(hyprctl activewindow -j 2>/dev/null | jq -r '.pid // empty')
    if [[ -n "$pid" && -S "/tmp/mykitty-$pid" ]]; then
        rc_to="unix:/tmp/mykitty-$pid"
    else
        sock=$(ls -t /tmp/mykitty-* 2>/dev/null | head -1)
        [[ -n "$sock" ]] && rc_to="unix:$sock"
    fi
fi
[[ -n "$rc_to" ]] || exit 0

# session:. alone matches every tab for background launches (no source
# window to resolve "." against); scoping to the focused OS window makes
# kitty resolve the session properly — same filter as tab_bar_filter.
ids=$(kitty @ --to "$rc_to" ls --match-tab 'state:focused_os_window and session:.' 2>/dev/null | \
    jq -r --arg agents "$AGENTS" '
        [ .. | objects
            | select(.foreground_processes | type == "array")
            | select([.foreground_processes[]? | objects | .cmdline[]?
                    | select(type == "string")
                    | split("/")[-1] | ascii_downcase
                    | test("^(" + $agents + ")$")] | any)
            | .id
        ] | .[]' 2>/dev/null)

[[ -n "$ids" ]] || exit 0
mapfile -t arr <<< "$ids"
n=${#arr[@]}

last=""
[[ -f "$STATE" ]] && last=$(cat -- "$STATE" 2>/dev/null || true)

target=""
for (( i=0; i<n; i++ )); do
    if [[ "${arr[i]}" == "$last" ]]; then
        target="${arr[ (i+1) % n ]}"
        break
    fi
done
[[ -z "$target" ]] && target="${arr[0]}"

kitty @ --to "$rc_to" focus-window --match "id:$target" >/dev/null 2>&1 && \
    printf '%s' "$target" > "$STATE"
exit 0
