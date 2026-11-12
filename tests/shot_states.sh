#!/usr/bin/env bash
# The all-states screen (plan 015 §4): every agent state and edge case at once, dark and light, at the default width,
# 16 columns and the rail, plus 40 tabs. Writes one PNG per combination and a contact sheet, for looking at
# ("Look at anything visual", AGENTS.md).
#   bash tests/shot_states.sh OUTDIR
# Each shot runs tests/shot_bar.sh: its own Xvfb and kitty, KITTYMUX_STATE in a temp dir, nothing outside it touched.
# Needs Xvfb, xdotool, kitty, git, ImageMagick; else SKIP (shot_bar.sh says which).
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=${1:-state-shots}
mkdir -p "$OUT"
shots=()
for theme in dark light; do
  for size in "22 full wide" "8 full narrow" "22 compact rail"; do
    set -- $size
    f="$OUT/states-$theme-$3.png"
    KMX_SHOT_SCENE=states bash "$HOME_DIR/tests/shot_bar.sh" "$theme" "$f" "$1" "$2" >/dev/null || exit 1
    [ -s "$f" ] && shots+=("$f")
  done
  f="$OUT/many-$theme-wide.png"
  KMX_SHOT_SCENE=many bash "$HOME_DIR/tests/shot_bar.sh" "$theme" "$f" 22 full >/dev/null || exit 1
  [ -s "$f" ] && shots+=("$f")
done
if [ ${#shots[@]} -eq 0 ]; then echo "SKIP: no shots (see tests/shot_bar.sh)"; exit 0; fi
command -v montage >/dev/null 2>&1 && montage "${shots[@]}" -tile "${#shots[@]}x1" -geometry +6+6 -background '#777' "$OUT/sheet.png"
echo "wrote ${#shots[@]} shots to $OUT"
