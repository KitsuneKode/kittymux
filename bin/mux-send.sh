#!/usr/bin/env bash
# mux-send.sh — send a prompt to an agent pane without leaving focus.
#
# Pick a pane from the agent list, type text, enter: the text plus a
# carriage return lands in that pane via send-text. Escapes follow
# kitty send-text rules (\n = newline, \e = esc).

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/mux.sh"
source "$SCRIPT_DIR/fzf-style.sh"

# Reuse the picker's listing via its --list mode.
list="$("$SCRIPT_DIR/mux-agents.sh" --list 2>/dev/null || true)"
[[ -n "$list" ]] || { notify_kitty "No agent panes running"; exit 0; }

sorted="$(printf '%s\n' "$list" | sort -t$'\t' -k7,7)"

selected="$(
    printf '%s\n' "$sorted" \
    | fzf \
        "${FZF_KITTY_BASE[@]}" \
        --prompt="  send to › " \
        --delimiter=$'\t' \
        --with-nth=1 \
        --header=$'▸ focused  ● busy  ! waiting  ○ idle' \
        --header-first \
        --footer=$'enter: choose pane   esc: cancel' \
        --preview="kitty @ --to unix:{8} get-text -m id:{2} 2>/dev/null | tail -n 24" \
        --preview-window=right:55%:wrap:border-left \
        --preview-label=' pane ' \
        --preview-label-pos=2 \
        --no-sort
)" || exit 0

wid="$(printf '%s\n' "$selected" | cut -f2)"
sock="$(printf '%s\n' "$selected" | cut -f8)"
[[ -n "$wid" && -n "$sock" ]] || exit 0

text="$(
    printf '\n' \
    | fzf \
        "${FZF_KITTY_BASE[@]}" \
        --phony \
        --print-query \
        --prompt="  prompt › " \
        --header=$'type the message — enter sends it + ⏎' \
        --header-first \
        --preview-window=hidden \
        --height=40%
)" || exit 0
text="$(printf '%s\n' "$text" | head -1)"
[[ -n "$text" ]] || exit 0

kitty @ --to "unix:$sock" send-text --match "id:${wid}" -- "${text}\r" >/dev/null 2>&1 || true
notify_kitty "Sent to agent pane ${wid}"
