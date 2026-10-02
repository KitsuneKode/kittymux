#!/usr/bin/env bash
# P0-b/d (MANUAL, Wayland + Hyprland): where does a layer-shell sheet land, and how fast does it start?
# Run from a shell INSIDE the kitty you want to measure. It opens a small os-panel beside that kitty's tab bar for 6 s.
# Look: is the panel's left edge flush with the bar's right edge, and does its top line up with the row you expect?
set -u
command -v hyprctl >/dev/null 2>&1 || { echo "needs Hyprland (hyprctl)"; exit 1; }
SOCK="${KITTY_LISTEN_ON:-}"; [ -n "$SOCK" ] || { echo "run this inside a kitty with listen_on set (allow_remote_control socket-only)"; exit 1; }
read -r AX AY AW AH < <(hyprctl activewindow -j | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["at"][0],d["at"][1],d["size"][0],d["size"][1])')
BAR_PX="${1:-260}"      # the bar's width in pixels (pass it if yours differs: `kitty @ kitten tests/probe_bar.py out.json` prints right-left)
ROW_PX="${2:-120}"      # distance from the window's top to the row you want the sheet beside
M=$(mktemp); START=$(date +%s%N)
echo "active window at ${AX},${AY} size ${AW}x${AH}; placing the panel at margin-left=$((AX + BAR_PX)) margin-top=$((AY + ROW_PX))"
kitty @ --to "$SOCK" launch --type os-panel --os-panel edge=left --os-panel layer=overlay --os-panel focus-policy=not-allowed \
  --os-panel columns=36 --os-panel lines=14 --os-panel margin-left=$((AX + BAR_PX)) --os-panel margin-top=$((AY + ROW_PX)) \
  sh -c "date +%s%N > $M; printf '\n   side-sheet placement probe\n   (closes in 6 s)\n'; sleep 6" >/dev/null
for _ in $(seq 40); do [ -s "$M" ] && break; sleep 0.05; done
[ -s "$M" ] && echo "panel process started $(( ($(cat "$M") - START) / 1000000 )) ms after the launch call (first paint is a little later; budget ≤ 150 ms)"
echo "Report: (1) flush with the bar's edge? (2) top aligned with the row? (3) did it steal focus? (4) the ms above."
