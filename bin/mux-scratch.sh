#!/usr/bin/env bash

# scratch-tab.sh — one scratch tab per OS window, scoped to its kitty instance.
# shellcheck source=../lib/mux.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/../lib/mux.sh"
[[ -n "$KITTY_SOCKET" ]] || { echo 'kittymux: no trusted kitty socket' >&2; exit 1; }
SOCKET="$KITTY_SOCKET"

CWD="${HOME}"
CMD_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --cwd) CWD="$2"; shift ;;
        --)    shift; CMD_ARGS=("$@"); break ;;
        *)     CMD_ARGS+=("$1") ;;
    esac
    shift
done

# Find the OS window that owns the triggering window (KITTY_WINDOW_ID is set by kitty).
# Fallback to is_focused only if we don't know which window triggered us.
if [[ -n "${KITTY_WINDOW_ID:-}" ]]; then
    OS_WIN_ID="$(kitty @ --to "$SOCKET" ls 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
win_id = int(sys.argv[1])
for ow in data:
    for tab in ow.get('tabs', []):
        for w in tab.get('windows', []):
            if w['id'] == win_id:
                print(ow['id']); sys.exit(0)
sys.exit(1)
" "$KITTY_WINDOW_ID" 2>/dev/null || true)"
else
    OS_WIN_ID="$(kitty @ --to "$SOCKET" ls 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for ow in data:
    if ow.get('is_focused'):
        print(ow['id']); sys.exit(0)
sys.exit(1)
" 2>/dev/null || true)"
fi
[[ "$OS_WIN_ID" =~ ^[1-9][0-9]*$ ]] || { echo 'kittymux: cannot identify source OS window' >&2; exit 1; }
scratch_tab_file_for_os_window "$OS_WIN_ID" >/dev/null || exit 1

# Only close a tracked tab whose owner and per-launch identity still match.
old_tab="$(get_scratch_tab_id "$OS_WIN_ID" 2>/dev/null || true)"
if [[ -n "$old_tab" ]]; then
    kitty @ --to "$SOCKET" close-tab --match "id:${old_tab}" 2>/dev/null || exit 1
fi
clear_scratch_tab_id "$OS_WIN_ID"
SCRATCH_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"

# Open new scratch tab in the triggering OS window
LAUNCH_MATCH=()
if [[ -n "${KITTY_WINDOW_ID:-}" ]]; then LAUNCH_MATCH=(--match "id:${KITTY_WINDOW_ID}"); fi
if [[ "${#CMD_ARGS[@]}" -gt 0 ]]; then
    new_win="$(kitty @ --to "$SOCKET" launch --type=tab "${LAUNCH_MATCH[@]}" --tab-title "!scratch" --var "kittymux_scratch=$SCRATCH_TOKEN" --cwd "$CWD" -- "${CMD_ARGS[@]}" 2>/dev/null || true)"
else
    new_win="$(kitty @ --to "$SOCKET" launch --type=tab "${LAUNCH_MATCH[@]}" --tab-title "!scratch" --var "kittymux_scratch=$SCRATCH_TOKEN" --cwd "$CWD" 2>/dev/null || true)"
fi

# Track tab ID for next invocation (toggle off)
if [[ -n "$new_win" ]]; then
    new_tab="$(kitty @ --to "$SOCKET" ls 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
win_id = int(sys.argv[1])
for ow in data:
    for tab in ow.get('tabs', []):
        for w in tab.get('windows', []):
            if w['id'] == win_id:
                print(tab['id']); sys.exit(0)
sys.exit(1)
" "$new_win" 2>/dev/null || true)"
    if [[ -n "$new_tab" ]]; then
        set_scratch_tab_id "$OS_WIN_ID" "$new_tab" || exit 1
        # Move scratch to last position
        kitty @ --to "$SOCKET" ls 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
os_win_id = int('${OS_WIN_ID}')
tab_id = int('${new_tab}')
for ow in data:
    if ow['id'] == os_win_id:
        tabs = ow.get('tabs', [])
        last_pos = len(tabs) - 1
        for i, tab in enumerate(tabs):
            if tab['id'] == tab_id:
                windows = tab.get('windows', [])
                if not windows:
                    sys.exit(0)
                print(windows[0]['id'], max(0, last_pos - i))
                sys.exit(0)
sys.exit(1)
" 2>/dev/null | while read -r scratch_win moves; do
            [[ -z "$scratch_win" || -z "$moves" ]] && continue
            for ((i = 0; i < moves; i++)); do
                kitty @ --to "$SOCKET" action --match "id:${scratch_win}" move_tab_forward 2>/dev/null || true
            done
        done
    fi
fi
