#!/usr/bin/env bash

# Move the current tab to another Kitty OS window via an fzf picker.
# Replaces the native `detach_tab ask` chooser with Kitty Home styling,
# then focuses the destination OS window (Kitty + Hyprland).

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/mux.sh"
source "$SCRIPT_DIR/fzf-style.sh"

SOURCE_WINDOW_ID=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source-window-id) SOURCE_WINDOW_ID="$2"; shift ;;
        *) ;;
    esac
    shift
done

if ! is_inside_kitty; then
    echo "move-tab.sh must run inside Kitty." >&2
    exit 1
fi

if [[ -z "$SOURCE_WINDOW_ID" ]]; then
    SOURCE_WINDOW_ID="$(source_window_id 2>/dev/null || true)"
fi
[[ -n "$SOURCE_WINDOW_ID" ]] || { echo "Could not determine kitty window."; exit 1; }

SOURCE_OS_WIN_ID="$(os_window_id_for_window "$SOURCE_WINDOW_ID" 2>/dev/null || true)"
if [[ -z "$SOURCE_OS_WIN_ID" ]]; then
    SOURCE_OS_WIN_ID="$(source_os_window_id 2>/dev/null || true)"
fi
[[ -n "$SOURCE_OS_WIN_ID" ]] || { echo "Could not determine OS window."; exit 1; }

build_move_list() {
    list_move_tab_targets "$SOURCE_OS_WIN_ID" || true
    printf '+ %-28s(fresh desktop container)\tnew\t\t\t\t\n' "New OS Window "
}

PREVIEW_SCRIPT="$SCRIPT_DIR/session-preview.sh"
HEADER=$'↗ Move tab    choose a destination OS window    esc cancels'
FOOTER=$'enter: move + follow focus   esc: cancel'

list="$(build_move_list)"
if ! printf '%s\n' "$list" | grep -q .; then
    notify_kitty "No destination windows"
    exit 0
fi

selected="$(
    printf '%s\n' "$list" \
    | fzf \
        "${FZF_KITTY_HOME[@]}" \
        --prompt="  move › " \
        --delimiter=$'\t' \
        --with-nth=1 \
        --header="$HEADER" \
        --header-first \
        --footer="$FOOTER" \
        --preview="$PREVIEW_SCRIPT {2} {3} {4}" \
        --preview-window=right:48%:wrap:border-left \
        --preview-label=' destination ' \
        --preview-label-pos=2 \
        --header-label=' Move tab ' \
        --ghost='Filter OS windows' \
        --no-sort
)" || exit 0

[[ -n "$selected" ]] || exit 0

kind="$(printf '%s\n' "$selected" | cut -f2)"
target_os="$(printf '%s\n' "$selected" | cut -f3)"
target_tab="$(printf '%s\n' "$selected" | cut -f4)"

case "$kind" in
    new)
        if move_tab_for_window "$SOURCE_WINDOW_ID" new; then
            notify_kitty "Tab moved to new OS window"
        else
            notify_kitty "Move failed"
            exit 1
        fi
        ;;
    os_window)
        if move_tab_for_window "$SOURCE_WINDOW_ID" os_window "$target_tab"; then
            notify_kitty "Tab moved to win ${target_os}"
        else
            notify_kitty "Move failed"
            exit 1
        fi
        ;;
    *)
        exit 0
        ;;
esac
