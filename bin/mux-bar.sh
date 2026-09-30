#!/usr/bin/env bash
# mux-bar.sh — collapse/restore the tab bar (ctrl+alt+v, "sidebar minimize").
# Writes a managed include file, then reloads every live kitty instance.

set -u

STYLE_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/kitty/include-tab-bar.conf"
cur=$(grep -oE 'tab_bar_style[[:space:]]+[a-z]+' "$STYLE_FILE" 2>/dev/null | awk '{print $2}' | tail -1)
cur="${cur:-custom}"

if [[ "$cur" == "hidden" ]]; then next=custom; else next=hidden; fi

printf '# managed by kittymux mux-bar.sh — do not edit\ntab_bar_style %s\n' "$next" > "$STYLE_FILE"

if [[ -n "${KITTY_LISTEN_ON:-}" ]]; then
    kitty @ --to "$KITTY_LISTEN_ON" load-config >/dev/null 2>&1
fi
for sock in /tmp/mykitty-*; do
    [[ -S "$sock" ]] && kitty @ --to "unix:$sock" load-config >/dev/null 2>&1
done
exit 0
