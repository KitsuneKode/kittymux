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
for f in tab_bar.py kittymux_theme.py kittymux_deck.py kittymux_git.py kittymux_features.py kittymux_place.py kittymux_layout.py kittymux_barsize.py kittymux_agents.py kittymux_state.py kittymux_scan.py; do ln -s "$HOME_DIR/python/$f" "$CFG/$f"; done
cat > "$CFG/kitty.conf" <<CONF
allow_remote_control socket-only
include $HOME_DIR/kittymux.conf
watcher $HOME_DIR/python/pane-state.py
tab_bar_edge left
tab_bar_min_tabs 1
geninclude $HOME_DIR/python/kittymux_layout.py
CONF
printf 'new_tab one\nlaunch sh\nlaunch --location=vsplit sh\nnew_tab two\nlaunch sh\nnew_tab three\nlaunch sh\nnew_tab four\nlaunch sh\nnew_tab five\nlaunch sh\nfocus_tab 0\n' > "$T/session"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_DEBUG=1 \
  kitty ${SMOKE_KITTY_ARGS:-} -o linux_display_server=x11 --class kmx-drag --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-drag | head -1)
X windowsize "$W" 1190 790; sleep 0.4; X windowsize "$W" 1200 800; sleep 1.5
probe() { kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_bar.py" "$T/geom.json" >/dev/null 2>&1; }
g() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$T/geom.json" "$1"; }
probe; CW=$(g cw); CH=$(g ch); TOP=$(g top); RIGHT=$(g right)
[ -n "$CH" ] || fail "could not probe the bar geometry"
Y() { python3 -c "print(int($TOP + ($1) * $CH))"; }            # pixel y of a (fractional) row of the bar
BX=$(python3 -c "print(int($RIGHT / 3))")                      # an x inside the bar
order() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(" ".join(t["title"] for t in json.load(sys.stdin)[0]["tabs"]))'; }

# Layout of the bar (rows): a two-row header (0-1), then tab 1 = rows 0-3 (it owns the header), a spacer row, and every
# further tab is 2 rows + a spacer: tab 2 = rows 5-6, tab 3 = 8-9, tab 4 = 11-12, tab 5 = 14-15 (spacers 4, 7, 10, 13).
drag() {   # drag <from_row> <to_row> — a slow press-move-release inside the bar, like a hand
  local from to i
  from=$(Y "$1"); to=$(Y "$2")
  X mousemove "$BX" "$from" mousedown 1; sleep 0.3
  for i in 1 2 3 4 5 6 7 8; do X mousemove "$BX" $(( from + (to - from) * i / 8 )); sleep 0.12; done
  sleep 0.5; X mouseup 1; sleep 1
}
expect() { local got; got=$(order); [ "$got" = "$2" ] || fail "$1: expected '$2', got '$got'"; echo "  ok   $1 → $got"; }

expect "start" "one two three four five"
drag 5.5 13.5;  expect "tab 2 dragged down past two tabs lands after the second" "one three four two five"
drag 11.5 5.3;   expect "…and dragged back up two places" "one two three four five"
drag 2.5 13.5;   expect "the tall first tab (it carries the header) dragged down" "two three four one five"
drag 5.5 6.1;    expect "a small wiggle changes nothing" "two three four one five"
drag 14.5 0.8;   expect "the last tab dragged all the way to the top" "five two three four one"

# a split pane promoted to a tab by dragging its title bar (shown with the toggle) onto the bar: empty space → its own tab,
# a tab row → joins that tab
tabs() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(" ".join("%s:%d" % (t["title"], len(t["windows"])) for t in json.load(sys.stdin)[0]["tabs"]))'; }
kitty @ --to "$SOCK" focus-tab --match "title:one" >/dev/null 2>&1; sleep 0.5
kitty @ --to "$SOCK" action toggle_window_title_bars >/dev/null 2>&1; sleep 1
before=$(tabs)
PX=$(python3 -c "print(int($RIGHT + (1200 - $RIGHT) * 0.75))")        # inside the right-hand pane
PY=$(python3 -c "print(int($TOP + $CH / 2))")                          # its title bar
X mousemove "$PX" "$PY" mousedown 1; sleep 0.4
for i in 1 2 3 4 5 6 7 8; do X mousemove $(( PX + (BX - PX) * i / 8 )) $(( PY + ($(Y 20) - PY) * i / 8 )); sleep 0.12; done; sleep 0.5; X mouseup 1; sleep 1.2
after=$(tabs)
[ "$(printf '%s' "$after" | wc -w)" -eq "$(( $(printf '%s' "$before" | wc -w) + 1 ))" ] || fail "dragging a pane title onto empty bar space did not make a new tab ('$before' → '$after')"
echo "  ok   a split pane dragged (by its title bar) onto the bar's empty space became its own tab ('$before' → '$after')"
[ -s "$STATE/barsize-debug.log" ] && fail "barsize logged an error"
kill -0 "$KPID" 2>/dev/null || fail "kitty died"
echo "PASS: dragging tabs in the vertical bar reorders them predictably (no jump on grab, no cascade)"
