#!/usr/bin/env bash
# Zoom the focused pane so it fills the tab (both axes). Press again to restore.
# On the stack layout the pane already fills the tab, and layout_action there rings the bell, so this sends nothing.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/mux.sh
source "$HERE/../lib/mux.sh"
PY="$HERE/../python"

layout=""
if ls_json="$(kitty_remote ls 2>/dev/null)"; then
    layout="$(printf '%s\n' "$ls_json" | python3 "$PY/kittymux_zoom.py" layout)"
fi

actions="$(python3 "$PY/kittymux_zoom.py" actions "$layout")"
[[ -n "$actions" ]] || exit 0
while IFS=$'\t' read -r name axis direction; do
    [[ -n "${name:-}" ]] || continue
    kitty_action "$name" "$axis" "$direction"
done <<<"$actions"
