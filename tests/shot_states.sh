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
RUN=$(mktemp -d "$OUT/.run.XXXXXX")              # this run's shots only: old PNGs in OUT never count as captured
trap 'rm -rf "$RUN"' EXIT
# tripwire: every OTHER kitty's window count before and after (each shot_bar.sh also keeps KITTYMUX_SOCKET_DIRS to its own dir)
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty*; do [ -S "$s" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
shots=()
shoot() {   # shoot NAME SCENE THEME WIDTH_STEP MODE
  KMX_SHOT_SCENE=$2 bash "$HOME_DIR/tests/shot_bar.sh" "$3" "$RUN/$1.png" "$4" "$5" >/dev/null || exit 1
  [ -s "$RUN/$1.png" ] && { mv "$RUN/$1.png" "$OUT/$1.png"; shots+=("$OUT/$1.png"); }
}
for theme in dark light; do
  for size in "22 full wide" "8 full narrow" "22 compact rail"; do
    set -- $size
    shoot "states-$theme-$3" states "$theme" "$1" "$2"
  done
  shoot "many-$theme-wide" many "$theme" 22 full
done
[ "$(others)" = "$OTHERS_BEFORE" ] || { echo "FAIL: another kitty on this machine changed (before: $OTHERS_BEFORE after: $(others))"; exit 1; }
if [ ${#shots[@]} -eq 0 ]; then echo "SKIP: no shots (see tests/shot_bar.sh)"; exit 0; fi
command -v montage >/dev/null 2>&1 && montage "${shots[@]}" -tile "${#shots[@]}x1" -geometry +6+6 -background '#777' "$OUT/sheet.png"
echo "wrote ${#shots[@]} shots to $OUT"
