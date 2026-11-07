#!/usr/bin/env bash
# The kittymux client (client/, Quickshell) on a synthetic tabs.json, under Xvfb, as an ordinary window (KITTYMUX_CLIENT_FLOAT=1): no
# kitty, no compositor, nothing of the user's. Pictures to READ, plus checks:
#   1. it loads with no QML error or warning;
#   2. by space, then `g` (a real key event): by state, and the panel's own group file says "state";
#   3. a click on a row runs `kittymux act` with that tab's jump action; a right-click opens the menu, and Mute runs
#      `kittymux mute --pid P --window W` (KITTYMUX_BIN is a recorder here, so nothing acts on any kitty);
#   4. a change to tabs.json (one tab finishes, one leaves) reaches the screen without a restart.
# Usage: shot_client.sh [dark|light] [OUTDIR] [WIDTH]      Needs Xvfb, xdotool, ImageMagick `import`, qs (Quickshell); else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
THEME=${1:-dark}; OUT=${2:-/tmp/kmx-client-shots}; W=${3:-340}; H=640
for dep in Xvfb xdotool import qs python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
mkdir -p "$OUT"
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-client.XXXXXX"); STATE=$T/state; mkdir -p "$STATE"; chmod 700 "$STATE"
XPID="" QPID="" SPID=""
cleanup() { for p in $QPID $XPID $SPID; do kill "$p" 2>/dev/null; done; wait 2>/dev/null; [ -n "${KEEP:-}" ] && cp -r "$T" "$KEEP"; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; tail -20 "$T/qs.log" 2>/dev/null; exit 1; }
# a recorder in place of bin/kittymux: every call the client makes lands in calls.log, one argument per line, then a blank line
printf '#!/bin/sh\nfor a; do printf "%%s\\n" "$a"; done >> %s/calls.log\necho >> %s/calls.log\n' "$T" "$T" > "$T/kittymux"; chmod +x "$T/kittymux"
sleep 600 & SPID=$!                        # stands in for the kitty: the client hides rows whose kitty_pid has exited
python3 "$HOME_DIR/tests/client_fixture.py" "$STATE" "$THEME" "$SPID" || fail "the fixture did not build"
for n in $(seq 210 260); do [ -e "/tmp/.X$n-lock" ] || [ -e "/tmp/.X11-unix/X$n" ] || { D=:$n; break; }; done
Xvfb "$D" -screen 0 $((W + 60))x${H}x24 >/dev/null 2>&1 & XPID=$!
for _ in $(seq 50); do [ -e "/tmp/.X11-unix/X${D#:}" ] && break; sleep 0.1; done
kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; exit 0; }
X() { DISPLAY=$D xdotool "$@"; }
env -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE DISPLAY=$D QT_QPA_PLATFORM=xcb KITTYMUX_STATE=$STATE KITTYMUX_ICONS=$HOME_DIR/assets/icons \
  KITTYMUX_BIN=$T/kittymux KITTYMUX_CLIENT_FLOAT=1 KITTYMUX_CLIENT_WIDTH=$W KITTYMUX_CLIENT_HEIGHT=$((H - 24)) QT_QUICK_BACKEND=${QT_QUICK_BACKEND:-software} ${CLIENT_ENV:-} \
  qs -p "$HOME_DIR/client" >"$T/qs.log" 2>&1 & QPID=$!
WIN=""
for _ in $(seq 60); do WIN=$(X search --name "kittymux client" 2>/dev/null | head -1); [ -n "$WIN" ] && break; sleep 0.2; done
[ -n "$WIN" ] || fail "the client window never appeared"
X mousemove $((W + 58)) $((H - 2)); sleep 2.5      # park the pointer off the panel; let the software renderer settle
shot() { DISPLAY=$D import -window root "$OUT/$1.png"; echo "  shot $OUT/$1.png"; }
calls() { cat "$T/calls.log" 2>/dev/null; }
errs=$(grep -E "ERROR|WARN" "$T/qs.log" | grep -v "Saving logs\|X11 connection\|xcb-cursor" || true)
[ -z "$errs" ] || fail "QML reported: $errs"
echo "  ok   loads with no QML error or warning"
shot "client-$THEME-by-space"

# 2. g toggles by state; the panel's group file follows
X mousemove 60 300 click 1; sleep 0.6; : > "$T/calls.log"      # a click gives it the keyboard (and jumps: cleared above)
X key g; sleep 1.2
[ "$(cat "$STATE/panel-group" 2>/dev/null)" = "state" ] || fail "g did not write the panel's group file (got: $(cat "$STATE/panel-group" 2>/dev/null))"
X mousemove $((W + 58)) $((H - 2)); sleep 1.5
shot "client-$THEME-by-state"
echo "  ok   g groups by state, and the panel's group file says so"
X key g; sleep 1
[ ! -s "$STATE/panel-group" ] || fail "g again did not go back to by space"

# 3. a click jumps with the row's own action; right-click -> Mute runs the direct mute
: > "$T/calls.log"
X mousemove 80 $((8 + 58 + 28 + 23)) click 1; sleep 0.8         # the first row: margin 8, header 58, section 28, half a row
calls | tr '\n' ' ' | grep -q 'act {"op":"jump","pid":'"$SPID"',"w":"11"}' || fail "a click did not jump to the row's window (calls: $(calls | tr '\n' ' '))"
echo "  ok   a click runs kittymux act with the row's jump action"
: > "$T/calls.log"
X mousemove 80 $((8 + 58 + 28 + 23)) click 3; sleep 0.8
shot "client-$THEME-menu"
X mousemove 80 $((8 + 58 + 28 + 46 + 4 + 32 + 16)) click 1; sleep 0.8    # the menu's second item (it opens under the row)
calls | tr '\n' ' ' | grep -q "mute --pid $SPID --window 11" || fail "Mute did not run the direct mute (calls: $(calls | tr '\n' ' '))"
echo "  ok   right-click -> Mute runs kittymux mute --pid P --window W"

# 4. a live change reaches the screen
python3 "$HOME_DIR/tests/client_fixture.py" "$STATE" changed "$SPID"
X mousemove $((W + 58)) $((H - 2)); sleep 2
shot "client-$THEME-changed"
kill -0 "$QPID" 2>/dev/null || fail "the client exited"
errs=$(grep -E "ERROR|WARN" "$T/qs.log" | grep -v "Saving logs\|X11 connection\|xcb-cursor" || true)
[ -z "$errs" ] || fail "QML reported: $errs"
echo "PASS: the client draws tabs.json, groups with g, jumps and mutes through kittymux, and follows changes (read the pictures in $OUT)"
