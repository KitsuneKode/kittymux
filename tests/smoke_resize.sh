#!/usr/bin/env bash
# Drag-resizing the vertical bar must keep up with the pointer: after a FAST burst of motion that then stops, the bar's inner edge is where
# the pointer is within a moment (the old pacing dropped the events inside its window, so the bar stayed behind until release), and on release
# every tab — not just the visible one — has been re-flowed to the new width. Real pointer events; needs Xvfb, xdotool, kitty; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-resize.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$STATE/barsize-debug.log" ] && tail -8 "$STATE/barsize-debug.log"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1600x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in tab_bar.py kittymux_theme.py kittymux_deck.py kittymux_git.py kittymux_features.py kittymux_place.py kittymux_layout.py kittymux_barsize.py kittymux_agents.py kittymux_state.py kittymux_scan.py; do
  ln -s "$HOME_DIR/python/$f" "$CFG/$f"
done
printf 'allow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
for i in $(seq 1 12); do printf 'new_tab tab%s\nlaunch sh\n' "$i"; done > "$T/session"; printf 'focus_tab 3\n' >> "$T/session"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_DEBUG=1 \
  kitty ${SMOKE_KITTY_ARGS:-} -o linux_display_server=x11 --class kmx-resize --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --class kmx-resize | head -1)
X windowsize "$W" 1590 890; sleep 0.4; X windowsize "$W" 1600 900; sleep 1.2
probe() { kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_bar.py" "$T/geom.json" >/dev/null 2>&1; }
g() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$T/geom.json" "$1"; }
probe; CW=$(g cw); CH=$(g ch); TOP=$(g top); EDGE0=$(python3 -c "print(int($(g right)))")
[ -n "$CW" ] || fail "could not probe the bar geometry"
Y=$(python3 -c "print(int($TOP + 14 * $CH))")
cols_of_tabs() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
print(" ".join(str(t["windows"][0]["columns"]) for t in json.load(sys.stdin)[0]["tabs"]))'; }

# a fast burst to the right, then stop and hold (button still down)
X mousemove "$((EDGE0 - 3))" "$Y" mousedown 1; sleep 0.2
burst=(); for x in $(seq $((EDGE0 + 2)) 5 $((EDGE0 + 90))); do burst+=(mousemove "$x" "$Y"); done
FINAL=$((EDGE0 + 90))      # inside the allowed range (the bar is capped at a third of the window)
X "${burst[@]}"
sleep 0.25                                   # the pointer has stopped; the bar must have caught up with it by now
probe; EDGE1=$(python3 -c "print(int($(g right)))")
lag=$(python3 -c "print(abs($FINAL - $EDGE1))")
[ "$(python3 -c "print(1 if $lag <= 1.6 * $CW else 0)")" = 1 ] || fail "the bar is ${lag}px behind the pointer 250 ms after it stopped (edge $EDGE1, pointer $FINAL, cell $CW)"
echo "  ok   after a fast burst the bar edge is ${lag}px from the pointer (cell $CW px)"
X mouseup 1; sleep 1.2

# every tab was re-flowed, not just the visible one
sizes=$(cols_of_tabs); uniq=$(printf '%s\n' $sizes | sort -u | wc -l)
[ "$uniq" = 1 ] || fail "tabs have different widths after the drag: $sizes"
echo "  ok   all 12 tabs have the same width after release ($(printf '%s\n' $sizes | sort -u))"

# the hit area: centred on the visible divider, ±1 cell (the bar's last two columns); a press on the tab content just outside it must NOT resize
reset() {   # a known starting width, so every trial is comparable
  python3 -c "import sys;sys.path.insert(0,'$HOME_DIR/python');import kittymux_layout as L;L.save('$STATE',$KPID,L.Layout('left','full',22))"
  kitty @ --to "$SOCK" load-config; sleep 1; kitty @ --to "$SOCK" load-config; sleep 1.2
  probe; EDGE=$(python3 -c "print(int($(g right)))")
}
trial() {   # trial <px offset from the bar's inner edge> → prints the bar's right edge before/after dragging 45 px left
  reset; before=$EDGE
  X mousemove "$((EDGE + $1))" "$Y" mousedown 1; sleep 0.15
  for x in $(seq $((EDGE + $1 - 5)) -5 $((EDGE + $1 - 45))); do X mousemove "$x" "$Y"; sleep 0.02; done; sleep 0.3; X mouseup 1; sleep 0.7
  probe; echo "$before $(python3 -c "print(int($(g right)))")"
}
INSIDE=$(python3 -c "print(int($CW * 2) - 2)"); OUTSIDE=$(python3 -c "print(int($CW * 2) + 6)")
for off in -2 -$((CW / 2)) -$CW -$INSIDE; do
  read -r b a < <(trial "$off"); [ "$a" -lt "$b" ] || fail "a press ${off}px from the edge (on the divider) did not start a resize ($b → $a)"
done
echo "  ok   presses on the divider (2, $((CW / 2)), $CW and $INSIDE px from the edge) all start a resize"
read -r b a < <(trial "-$OUTSIDE"); [ "$a" = "$b" ] || fail "a press on the tab content ${OUTSIDE}px from the edge resized the bar ($b → $a)"
echo "  ok   a press ${OUTSIDE}px from the edge (tab content) leaves the bar alone"

# and the mouse is ours again
X mousemove 900 500 click 1; sleep 0.3
echo "PASS: bar resize keeps up with a fast pointer and re-flows every tab on release"
