#!/usr/bin/env bash
# Drag-to-reorder in the vertical bar with REAL pointer events (kitty's own drag and drop, driven by xdotool).
# The bugs this guards: the dragged tab jumped to the top the moment it was grabbed (kitty's first drop-move
# call has no position), and tabs of different heights swapped in a cascade. Needs Xvfb, xdotool, kitty; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-drag.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$STATE/tab_bar-error.log" ] && tail -8 "$STATE/tab_bar-error.log"; [ -s "$STATE/barsize-debug.log" ] && tail -8 "$STATE/barsize-debug.log"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in tab_bar.py kittymux_theme.py kittymux_deck.py kittymux_git.py kittymux_layout.py kittymux_barsize.py kittymux_agents.py kittymux_state.py kittymux_scan.py; do ln -s "$HOME_DIR/python/$f" "$CFG/$f"; done
cat > "$CFG/kitty.conf" <<CONF
allow_remote_control yes
include $HOME_DIR/kittymux.conf
watcher $HOME_DIR/python/pane-state.py
tab_bar_edge left
tab_bar_min_tabs 1
geninclude $HOME_DIR/python/kittymux_layout.py
CONF
printf 'new_tab one\nlaunch sh\nnew_tab two\nlaunch sh\nnew_tab three\nlaunch sh\nnew_tab four\nlaunch sh\nnew_tab five\nlaunch sh\nfocus_tab 0\n' > "$T/session"
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_DEBUG=1 \
  kitty -o linux_display_server=x11 --class kmx-drag --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-drag | head -1)
X windowsize "$W" 1190 790; sleep 0.4; X windowsize "$W" 1200 800; sleep 1.5
order() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(" ".join(t["title"] for t in json.load(sys.stdin)[0]["tabs"]))'; }

# Bar geometry at the default font: a two-row header (y 10-54), then every tab is 2 rows (44 px) + a spacer
# row, so tab N's rows start at 54 + 66*(N-1) for N≥1 ... tab 1 is at 54-98, tab 2 at 120-164, tab 3 at 186-230, ...
drag() {   # drag <from_y> <to_y> — a slow press-move-release at x=120, like a hand
  local from=$1 to=$2 y step=$(( $2 > $1 ? 12 : -12 ))
  X mousemove 120 "$from" mousedown 1; sleep 0.3
  for ((y = from + step; step > 0 ? y < to : y > to; y += step)); do X mousemove 120 "$y"; sleep 0.1; done
  X mousemove 120 "$to"; sleep 0.5; X mouseup 1; sleep 1
}
expect() { local got; got=$(order); [ "$got" = "$2" ] || fail "$1: expected '$2', got '$got'"; echo "  ok   $1 → $got"; }

expect "start" "one two three four five"
drag 140 300;  expect "tab 2 dragged down past two tabs lands after the second" "one three four two five"
drag 270 135;  expect "…and dragged back up two places" "one two three four five"
drag 75 300;   expect "the tall first tab (it carries the header) dragged down" "two three four one five"
drag 140 150;  expect "a small wiggle changes nothing" "two three four one five"
drag 340 60;   expect "the last tab dragged all the way to the top" "five two three four one"
[ -s "$STATE/barsize-debug.log" ] && fail "barsize logged an error"
kill -0 "$KPID" 2>/dev/null || fail "kitty died"
echo "PASS: dragging tabs in the vertical bar reorders them predictably (no jump on grab, no cascade)"
