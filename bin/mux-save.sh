#!/usr/bin/env bash

# Save the active kitty session using kitty's native save_as_session action.
# Scratch tabs (!scratch) are excluded from the saved file.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/mux.sh"

SOURCE_WINDOW_ID=""
APPLY_MODE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)            APPLY_MODE=1 ;;
        --source-window-id) SOURCE_WINDOW_ID="$2"; shift ;;
    esac
    shift
done

if ! is_inside_kitty; then
    echo "Save session must be run from inside kitty."
    exit 1
fi

ensure_sessions_dir

if [[ -z "$SOURCE_WINDOW_ID" ]]; then
    SOURCE_WINDOW_ID="$(source_window_id)"
fi

[[ -n "$SOURCE_WINDOW_ID" ]] || { echo "Could not determine the current kitty window."; exit 1; }

if [[ "$APPLY_MODE" -eq 0 ]] && is_overlay_invocation; then
    spawn_detached_helper \
        "$0" \
        --apply \
        --source-window-id "$SOURCE_WINDOW_ID"
    exit 0
fi

# Build match string, excluding scratch tab window if present
OS_WIN_ID="$(source_os_window_id)"
SCRATCH_EXCL=""
scratch_win="$(scratch_win_id_for_os_window "$OS_WIN_ID" 2>/dev/null || true)"
if [[ -n "$scratch_win" ]]; then
    SCRATCH_EXCL=" and not id:${scratch_win}"
fi

# Save back to the active session file if window is session-backed,
# otherwise kitty prompts for a new path via the "." sentinel.
if window_belongs_to_session "$SOURCE_WINDOW_ID"; then
    MATCH="session:.${SCRATCH_EXCL}"
    SAVE_LABEL="$(current_live_session_name_for_window "$SOURCE_WINDOW_ID" 2>/dev/null || true)"
else
    MATCH="state:focused_os_window${SCRATCH_EXCL}"
    SAVE_LABEL="focused window"
fi

SAVE_ARGS="$(join_shell_words \
    --save-only \
    --use-foreground-process \
    --base-dir "$SESSIONS_DIR" \
    --match="$MATCH" \
    .
)"

kitty_action_for_window "id:${SOURCE_WINDOW_ID}" save_as_session "$SAVE_ARGS"
notify_kitty "Saved session: ${SAVE_LABEL:-focused window}"
