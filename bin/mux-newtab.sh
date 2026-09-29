#!/usr/bin/env bash

# Create a new tab without letting the scratch tab stop being the final tab.
#   (default)   append before the scratch tab (i.e. end of the tab list)
#   --next      open next to the current tab (scratch still stays last)
#   --home      open in $HOME instead of the current directory
# Fast path: let kitty match scratch in the focused OS window internally.

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

CWD_ARGS=(--cwd current)
MODE="end"
for arg in "$@"; do
    case "$arg" in
        --home) CWD_ARGS=(--cwd "$HOME") ;;
        --next) MODE="next" ;;
    esac
done

SOURCE_MATCH=()
if [[ -n "${KITTY_WINDOW_ID:-}" ]]; then
    SOURCE_MATCH=(--source-window "id:${KITTY_WINDOW_ID}")
fi

# --next: place right after the tab that triggered us. If that tab is the
# scratch tab, fall through to the before-scratch path so scratch stays last.
# NOTE: kitty does NOT set KITTY_WINDOW_ID for keybind background launches,
# so the reference tab is the active tab in the focused OS window. When run
# from inside a window (KITTY_WINDOW_ID set), that window's tab is used.
if [[ "$MODE" == "next" ]]; then
    REF_MATCH="state:active and state:focused_os_window"
    [[ -n "${KITTY_WINDOW_ID:-}" ]] && REF_MATCH="window_id:${KITTY_WINDOW_ID}"

    cur_is_scratch="$(kitty @ --to "$SOCKET" ls --match-tab "$REF_MATCH" 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
for ow in data:
    for tab in ow.get('tabs', []):
        print(1 if (tab.get('title') or '').startswith('!scratch') else 0)
        sys.exit(0)
raise SystemExit(1)
" 2>/dev/null || true)"

    if [[ "${cur_is_scratch:-0}" != "1" ]]; then
        if kitty @ --to "$SOCKET" launch \
            --type=tab \
            --match "$REF_MATCH" \
            "${SOURCE_MATCH[@]}" \
            "${CWD_ARGS[@]}" \
            --location after \
            2>/dev/null; then
            exit 0
        fi
    fi
fi

if kitty @ --to "$SOCKET" launch \
    --type=tab \
    --match 'title:^!scratch and state:focused_os_window' \
    "${SOURCE_MATCH[@]}" \
    "${CWD_ARGS[@]}" \
    --location before \
    2>/dev/null; then
    exit 0
fi

if [[ "${#SOURCE_MATCH[@]}" -gt 0 ]]; then
    kitty @ --to "$SOCKET" launch \
        --type=tab \
        "${SOURCE_MATCH[@]}" \
        "${CWD_ARGS[@]}" \
        --no-response \
        2>/dev/null || true
else
    kitty @ --to "$SOCKET" launch \
        --type=tab \
        "${CWD_ARGS[@]}" \
        --no-response \
        2>/dev/null || true
fi
