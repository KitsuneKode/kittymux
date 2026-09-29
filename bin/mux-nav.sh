#!/usr/bin/env bash

# session-nav.sh prev|next|N
#
# Navigate tabs within the CURRENT session only.
# Prevents shift+left/right from bleeding into another session's tabs.
# Falls back to normal next/prev if no session is active.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/mux.sh"

ACTION="${1:-next}"

# Get ordered tab IDs that belong to the current session in the focused OS window
mapfile -t TAB_IDS < <(
    kitty_remote ls --match-tab "state:focused_os_window and session:." 2>/dev/null \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
for ow in data:
    for tab in ow.get('tabs', []):
        print(tab['id'])
" 2>/dev/null || true
)

n="${#TAB_IDS[@]}"

# No session tabs found — fall back to global next/prev
if [[ "$n" -eq 0 ]]; then
    case "$ACTION" in
        prev) kitty_remote action previous_tab ;;
        next) kitty_remote action next_tab ;;
        [0-9]*) kitty_remote action "goto_tab ${ACTION}" ;;
    esac
    exit 0
fi

CURRENT_TAB_ID="$(source_tab_id 2>/dev/null || true)"

# Find current position
current_idx=-1
for i in "${!TAB_IDS[@]}"; do
    if [[ "${TAB_IDS[$i]}" == "$CURRENT_TAB_ID" ]]; then
        current_idx=$i
        break
    fi
done

case "$ACTION" in
    prev)
        if [[ "$current_idx" -ge 0 ]]; then
            target=$(( (current_idx - 1 + n) % n ))
        else
            target=$(( n - 1 ))
        fi
        kitty_remote focus-tab --match "id:${TAB_IDS[$target]}"
        ;;
    next)
        if [[ "$current_idx" -ge 0 ]]; then
            target=$(( (current_idx + 1) % n ))
        else
            target=0
        fi
        kitty_remote focus-tab --match "id:${TAB_IDS[$target]}"
        ;;
    [0-9]*)
        idx=$(( ACTION - 1 ))
        if [[ "$idx" -lt "$n" ]]; then
            kitty_remote focus-tab --match "id:${TAB_IDS[$idx]}"
        else
            notify_kitty "No tab ${ACTION} in this session"
        fi
        ;;
esac
