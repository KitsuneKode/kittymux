#!/usr/bin/env bash
# tab-edge-toggle.sh — cycle tab_bar_edge bottom ⇄ left via an include file
# + live reload. Vertical tabs shine when a session runs many tabs.

set -u

EDGE_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/kitty/include-tab-edge.conf"
cur=$(grep -oE 'tab_bar_edge[[:space:]]+[a-z]+' "$EDGE_FILE" 2>/dev/null | awk '{print $2}' | tail -1)
cur="${cur:-bottom}"

if [[ "$cur" == "bottom" ]]; then next=left
elif [[ "$cur" == "left" ]]; then next=right
else next=bottom
fi

printf '# managed by tab-edge-toggle.sh — do not edit by hand\ntab_bar_edge %s\n' "$next" > "$EDGE_FILE"

# Reload every kitty instance — the include file is global state.
if [[ -n "${KITTY_LISTEN_ON:-}" ]]; then
    kitty @ --to "$KITTY_LISTEN_ON" load-config >/dev/null 2>&1
fi
for sock in /tmp/mykitty-*; do
    [[ -S "$sock" ]] && kitty @ --to "unix:$sock" load-config >/dev/null 2>&1
done
exit 0
