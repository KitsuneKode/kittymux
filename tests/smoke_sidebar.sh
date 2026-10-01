#!/usr/bin/env bash
# End-to-end sidebar smoke test: a real kitty under Xvfb, the vertical bar, real mouse events.
#   1. the collapse button (header row, far right) turns the sidebar into the slim rail
#   2. the expand button (rail header) brings the full sidebar back, at the same width
#   3. neither click activates a tab (the press/release are consumed by the button)
#   4. dragging the inner edge resizes the sidebar, and gives the mouse back on release
#
# Needs Xvfb, xdotool, kitty; otherwise SKIP (exit 0). Private display/config/socket/state.
set -u

HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do
  command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }
done

T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-side.XXXXXX")
CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; cat "$STATE/barsize-debug.log" 2>/dev/null | tail -8; cat "$STATE"/layout-*.json 2>/dev/null; echo; [ -s "$STATE/tab_bar-error.log" ] && sed 's/^/  | /' "$STATE/tab_bar-error.log" | tail -12
         [ -s "$STATE/barsize-debug.log" ] && sed 's/^/  | /' "$STATE/barsize-debug.log" | tail -12; exit 1; }

for n in $(seq 161 190); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1600x900x24 >/dev/null 2>&1 &
XPID=$!
sleep 1
kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }

for f in tab_bar.py kittymux_theme.py kittymux_deck.py kittymux_git.py kittymux_layout.py kittymux_barsize.py \
         kittymux_agents.py kittymux_state.py kittymux_scan.py; do
  ln -s "$HOME_DIR/python/$f" "$CFG/$f"
done
cat > "$CFG/kitty.conf" <<CONF
allow_remote_control yes
include $HOME_DIR/kittymux.conf
watcher $HOME_DIR/python/pane-state.py
tab_bar_edge left
tab_bar_min_tabs 1
geninclude $HOME_DIR/python/kittymux_layout.py
CONF
printf 'new_tab one\nlaunch sh\nnew_tab two\nlaunch sh\nnew_tab three\nlaunch sh\nfocus_tab 1\n' > "$T/session"

env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_DEBUG=1 \
  kitty -o linux_display_server=x11 --class kmx-side --listen-on "$SOCK" --session "$T/session" \
  >"$T/kitty.log" 2>&1 &
KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done
[ -S "$T/sock" ] || fail "kitty never opened its control socket"
sleep 2

X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --class kmx-side | head -1)
redraw() { X windowsize "$W" 1590 890; sleep 0.4; X windowsize "$W" 1600 900; sleep 0.8; }
shot() { [ -n "${SMOKE_SHOT:-}" ] && command -v import >/dev/null 2>&1 && { redraw; DISPLAY=$DISP import -window root -crop 1000x400+0+0 "$SMOKE_SHOT.$1.png" 2>/dev/null; }; return 0; }
redraw
cols()   { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d[0]["tabs"][0]["windows"][0]["columns"])'; }
active() { kitty @ --to "$SOCK" ls | python3 -c '
import sys, json
for t in json.load(sys.stdin)[0]["tabs"]:
    if t["is_active"]: print(t["title"])'; }
# poll until `cols` satisfies a test (the layout reload is asynchronous)
wait_cols() {   # wait_cols <name> <test using $c>
  local c
  for _ in $(seq 20); do c=$(cols); eval "$2" && return 0; sleep 0.4; done
  fail "$1 (window columns: $c)"
}

C0=$(cols)
[ -n "$C0" ] || fail "could not read the window columns"
CW=$(python3 -c "print(1600 / ($C0 + 28))")                 # cell width: the full sidebar is 28 columns
EDGE=$(python3 -c "print(int(28 * $CW))")
BTN=$(python3 -c "print(int(28 * $CW - 2 * $CW))")            # inside the header's last 3 cells
X mousemove 900 500; shot full
echo "  full sidebar: $C0 columns, ${EDGE}px wide, collapse button near x=$BTN"
[ "$(active)" = "two" ] || fail "setup: expected tab 'two' active, got '$(active)'"

X mousemove "$((BTN - 25))" 46 click 1             # the second header row, a button-and-a-half left of the glyph: still the button
wait_cols "collapse button did not turn the sidebar into the rail" '[ "$c" -gt "$C0" ]'
C1=$(cols)
shot rail
echo "  ok   collapse button → slim rail ($C0 → $C1 columns)"
[ "$(active)" = "two" ] || fail "the collapse click activated a tab ('$(active)')"
echo "  ok   …and did not activate a tab"

redraw
X mousemove 70 46 click 1                          # rail: the whole 2-row header is the button
wait_cols "expand button did not bring the full sidebar back" '[ "$c" -eq "$C0" ]'
echo "  ok   expand button → full sidebar again ($C0 columns)"
[ "$(active)" = "two" ] || fail "the expand click activated a tab ('$(active)')"

# right-click a tab → its peek card opens over the active window; Esc closes it. (kitty gives its
# tab bar no hover events, so this is the preview gesture.)
nwin() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; }
redraw
N0=$(nwin)
X mousemove 100 66 click 3
for _ in $(seq 15); do [ "$(nwin)" -gt "$N0" ] && break; sleep 0.4; done
[ "$(nwin)" -gt "$N0" ] || fail "right-click on a tab did not open the peek card"
shot peek
echo "  ok   right-click on a tab opens its peek card"
[ "$(active)" = "two" ] || fail "the right-click activated a tab ('$(active)')"
sleep 1.5                                    # the card's TUI needs a moment before it reads keys
for _ in 1 2 3; do X key Escape; for _ in $(seq 6); do [ "$(nwin)" -le "$N0" ] && break 2; sleep 0.4; done; done
[ "$(nwin)" -le "$N0" ] || fail "Escape did not close the peek card"
echo "  ok   Escape closes it"

# deck: `a` pulls the selected tab's panes into the tab you are in (tab → split, from the keyboard)
tabs_of() { kitty @ --to "$SOCK" ls | python3 -c '
import sys, json
print(" ".join("%s:%d" % (t["title"], len(t["windows"])) for t in json.load(sys.stdin)[0]["tabs"]))'; }
before=$(tabs_of)
kitty @ --to "$SOCK" kitten "$HOME_DIR/python/sidebar-kit.py" >/dev/null 2>&1
sleep 3
X key j a                                   # select the next tab ("three"), absorb it into the current one ("two")
for _ in $(seq 20); do [ "$(tabs_of)" = "one:1 two:2" ] && break; sleep 0.4; done   # (the deck overlay closes itself)
after=$(tabs_of)
[ "$after" = "one:1 two:2" ] || fail "absorb: expected 'one:1 two:2', got '$after' (before: '$before')"
echo "  ok   deck 'a' absorbed the next tab's pane into the current tab ($before → $after)"
sleep 1

# drag the inner edge 120 px to the right → the sidebar grows, the panes shrink
redraw
X mousemove "$((EDGE - 3))" 400 mousedown 1
for x in $(seq $((EDGE + 3)) 6 $((EDGE + 120))); do X mousemove "$x" 400; sleep 0.02; done
sleep 0.3
X mouseup 1
wait_cols "dragging the edge did not resize" '[ "$c" -lt "$C0" ]'
echo "  ok   dragging the inner edge resizes the sidebar ($C0 → $(cols) columns)"
X mousemove 900 400 click 1; sleep 0.5          # the mouse must be ours again: a click in a pane focuses it
[ "$(active)" = "two" ] || fail "mouse not returned after the drag ('$(active)')"
echo "  ok   mouse handed back after the drag"

[ -s "$STATE/tab_bar-error.log" ] && fail "tab bar logged an error"
[ -s "$STATE/barsize-debug.log" ] && fail "barsize logged an error"
kill -0 "$KPID" 2>/dev/null || fail "kitty died"
echo "PASS: collapse/expand button and edge drag work with real mouse events"
