#!/usr/bin/env bash
# The ctrl+alt+/ keymap overlay with REAL key events: Esc closes it in ONE press (it used to need several), pressing the
# chord again closes it instead of stacking a second overlay, typing filters the list, PgDn scrolls. Needs Xvfb, xdotool, kitty.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-keys.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
sed "s|@KITTYMUX_HOME@|$HOME_DIR|g" "$HOME_DIR/kittymux-keys.conf.tpl" > "$CFG/kittymux-keys.conf"
printf 'allow_remote_control socket-only\ninclude %s/kittymux-keys.conf\n' "$CFG" > "$CFG/kitty.conf"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE \
  kitty -o linux_display_server=x11 --class kmx-keys --listen-on "$SOCK" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 2
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-keys | head -1); X windowfocus "$W" 2>/dev/null; sleep 0.5
nwin() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(sum(len(t["windows"]) for t in json.load(sys.stdin)[0]["tabs"]))'; }
screen() { kitty @ --to "$SOCK" get-text --match title:kittymux-keys --extent screen 2>/dev/null; }
wait_open() { for _ in $(seq 24); do screen | grep -q "keymap" && return 0; sleep 0.25; done; return 1; }
wait_closed() { for _ in $(seq 12); do screen | grep -q "keymap" || return 0; sleep 0.25; done; return 1; }
base=$(nwin)
X key --clearmodifiers ctrl+alt+slash; wait_open || fail "ctrl+alt+/ did not open the overlay"
screen | grep -q "bindings" || fail "overlay has no content"
X key --clearmodifiers Escape; wait_closed || fail "ONE Escape did not close the overlay"
[ "$(nwin)" = "$base" ] || fail "window count changed after closing ($(nwin) vs $base)"
X key --clearmodifiers ctrl+alt+slash; wait_open || fail "overlay did not reopen"
X key --clearmodifiers ctrl+alt+slash; wait_closed || fail "pressing ctrl+alt+/ again did not close it"
[ "$(nwin)" = "$base" ] || fail "the second ctrl+alt+/ stacked another overlay ($(nwin) windows, base $base)"
X key --clearmodifiers ctrl+alt+slash; wait_open || fail "overlay did not reopen for the search check"
screen | grep -q "SESSIONS" || fail "expected the full list before searching"
X type --delay 80 "promote"; sleep 0.8
out=$(screen)
echo "$out" | grep -q "promote the pane" || fail "typing 'promote' did not show the matching row"
echo "$out" | grep -q "SESSIONS" && fail "typing 'promote' did not filter the list"
X key --clearmodifiers Escape; sleep 0.6
screen | grep -q "SESSIONS" || fail "the first Escape should clear the search and show everything again"
X key --clearmodifiers Next; sleep 0.6
screen | grep -q "keymap" || fail "PgDn closed the overlay"
X key --clearmodifiers q; wait_closed || fail "q did not close the overlay"
echo "PASS: one Esc / q / the chord closes the keymap overlay; typing filters; esc clears the search first"
