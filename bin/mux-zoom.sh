#!/usr/bin/env bash
# Zoom the focused pane so it fills the tab (both axes). Press again to restore.
# On the stack layout the pane already fills the tab, and layout_action there rings the bell, so this sends nothing.
# An axis kitty already has maximized is not toggled: that would leave the pane half-zoomed.
# Started by a key (launch --type=background): it has no terminal, so a failure is a notification.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/mux.sh
source "$HERE/../lib/mux.sh"
PY="$HERE/../python"

if ! ls_json="$(kitty_remote ls 2>/dev/null)"; then
    notify_kitty "Zoom could not read this kitty"
    exit 1
fi
plan="$(printf '%s\n' "$ls_json" | python3 "$PY/kittymux_zoom.py" plan)" || {
    notify_kitty "Zoom could not read the layout"
    exit 1
}
wid="$(printf '%s\n' "$plan" | head -n 1)"
actions="$(printf '%s\n' "$plan" | tail -n +2)"
[[ -n "${actions//[$' \t\n']/}" ]] || exit 0
failed=0
while IFS=$'\t' read -r name axis direction; do
    [[ -n "${name:-}" ]] || continue
    if [[ -n "$wid" ]]; then
        kitty_action_for_window "id:${wid}" "$name" "$axis" "$direction" || failed=1
    else
        kitty_action "$name" "$axis" "$direction" || failed=1
    fi
done <<<"$actions"
if [[ "$failed" -ne 0 ]]; then
    notify_kitty "Zoom did not finish"
    exit 1
fi
