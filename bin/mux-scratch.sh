#!/usr/bin/env bash

# scratch-tab.sh — one scratch tab per OS window.
# Self-contained: no session-lib dependency.

# Socket: KITTY_LISTEN_ON is set by kitty for background keybind launches.
if [[ -n "${KITTY_LISTEN_ON:-}" ]]; then
    SOCKET="$KITTY_LISTEN_ON"
elif [[ -S "/tmp/mykitty-${PPID}" ]]; then
    SOCKET="unix:/tmp/mykitty-${PPID}"
elif [[ -S "/tmp/kitty-${PPID}" ]]; then
    SOCKET="unix:/tmp/kitty-${PPID}"
else
    _sock=$(ls /tmp/mykitty-* 2>/dev/null | head -1)
    SOCKET="unix:${_sock:-/tmp/mykitty}"
    unset _sock
fi

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
win_id = int('${KITTY_WINDOW_ID}')
for ow in data:
    for tab in ow.get('tabs', []):
        for w in tab.get('windows', []):
            if w['id'] == win_id:
                print(ow['id']); sys.exit(0)
sys.exit(1)
" 2>/dev/null || echo "0")"
else
    OS_WIN_ID="$(kitty @ --to "$SOCKET" ls 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for ow in data:
    if ow.get('is_focused'):
        print(ow['id']); sys.exit(0)
sys.exit(1)
" 2>/dev/null || echo "0")"
fi

FLAG="/tmp/kitty-scratch-${OS_WIN_ID}"

# Close existing scratch tab if tracked
if [[ -f "$FLAG" ]]; then
    old_tab="$(cat "$FLAG")"
    kitty @ --to "$SOCKET" close-tab --match "id:${old_tab}" 2>/dev/null || true
    rm -f "$FLAG"
fi

# Open new scratch tab in the triggering OS window
LAUNCH_MATCH="${KITTY_WINDOW_ID:+--match id:${KITTY_WINDOW_ID}}"
if [[ "${#CMD_ARGS[@]}" -gt 0 ]]; then
    new_win="$(kitty @ --to "$SOCKET" launch --type=tab $LAUNCH_MATCH --tab-title "!scratch" --cwd "$CWD" -- "${CMD_ARGS[@]}" 2>/dev/null || true)"
else
    new_win="$(kitty @ --to "$SOCKET" launch --type=tab $LAUNCH_MATCH --tab-title "!scratch" --cwd "$CWD" 2>/dev/null || true)"
fi

# Track tab ID for next invocation (toggle off)
if [[ -n "$new_win" ]]; then
    new_tab="$(kitty @ --to "$SOCKET" ls 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
win_id = int('${new_win}')
for ow in data:
    for tab in ow.get('tabs', []):
        for w in tab.get('windows', []):
            if w['id'] == win_id:
                print(tab['id']); sys.exit(0)
sys.exit(1)
" 2>/dev/null || true)"
    if [[ -n "$new_tab" ]]; then
        echo "$new_tab" > "$FLAG"
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
