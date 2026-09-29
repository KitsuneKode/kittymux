#!/usr/bin/env bash

# session-cycle.sh prev|next|last
# Switch between sessions that are live in the current OS window.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/mux.sh"

ACTION="${1:-next}"

SOURCE_WINDOW_ID="$(source_window_id 2>/dev/null || true)"
[[ -n "$SOURCE_WINDOW_ID" ]] || exit 0

case "$ACTION" in
    prev|next)
        target="$(cycle_live_session_name_for_window "$SOURCE_WINDOW_ID" "$ACTION" 2>/dev/null || true)"
        [[ -n "$target" ]] || { notify_kitty "No live sessions in this window"; exit 0; }
        if session_is_active_in_focused_window "$target" 2>/dev/null; then
            notify_kitty "Only one live session here"
            exit 0
        fi
        focus_live_session_name "$SOURCE_WINDOW_ID" "$target"
        ;;
    last)
        target="$(last_live_session_name_for_window "$SOURCE_WINDOW_ID" 2>/dev/null || true)"
        [[ -n "$target" ]] || { notify_kitty "No previous live session here"; exit 0; }
        focus_live_session_name "$SOURCE_WINDOW_ID" "$target"
        ;;
esac
