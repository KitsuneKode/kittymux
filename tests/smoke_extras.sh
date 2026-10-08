#!/usr/bin/env bash
# kitty >= 0.49.2 features kittymux adopts, in a real kitty: `kittymux screenshot` writes a valid PNG only its owner can read, and (when
# kitty's shader compiler `slangc` is installed) `kittymux dim on` dims the unfocused pane — the render changes, no config error.
# Needs Xvfb, kitty >= 0.49.2, ImageMagick; else SKIP. Without slangc only the screenshot half runs.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty python3 compare identify; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
kitty --version | python3 -c 'import re,sys;v=tuple(map(int,re.search(r"(\d+)\.(\d+)\.(\d+)",sys.stdin.read()).groups()));sys.exit(0 if v>=(0,49,2) else 1)' \
    || { echo "SKIP: needs kitty >= 0.49.2"; exit 0; }
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-extras.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -f "$T/k.log" ] && tail -5 "$T/k.log"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
cp "$HOME_DIR/python/kittymux_layout.py" "$CFG/"
printf 'allow_remote_control socket-only\nenabled_layouts splits\nbackground #f0f0f0\nforeground #202020\ngeninclude %s/kittymux_layout.py\n' "$CFG" > "$CFG/kitty.conf"
printf 'layout splits\nlaunch sh\nlaunch --location=vsplit sh\n' > "$T/session"
export KITTYMUX_STATE=$STATE KITTYMUX_TARGET=$SOCK KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_NOTIFY=0
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  kitty -o linux_display_server=x11 --class kmx-extras --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 2
# the bin/kittymux target check wants a socket named mykitty-<pid> or an explicit one owned by us: explicit is allowed
"$HOME_DIR/bin/kittymux" screenshot "$T/off.png" >/dev/null 2>&1 || fail "kittymux screenshot failed"
[ "$(stat -c %a "$T/off.png")" = 600 ] || fail "screenshot is not private (mode $(stat -c %a "$T/off.png"))"
identify "$T/off.png" >/dev/null 2>&1 || fail "screenshot is not a valid image"
if ! python3 -c 'import sys;sys.path.insert(0,sys.argv[1]);import kittymux_layout as L;sys.exit(0 if L.have_slangc() else 1)' "$HOME_DIR/python"; then
    "$HOME_DIR/bin/kittymux" dim on >/dev/null 2>&1 && fail "dim on should refuse without slangc"
    [ ! -e "$STATE/dim-inactive" ] || fail "dim on left its flag behind without slangc"
    echo "PASS (screenshot only): screenshots are private valid PNGs; dim refuses cleanly without slangc (dim render not checked here)"
    exit 0
fi
"$HOME_DIR/bin/kittymux" dim on >/dev/null 2>&1 || fail "kittymux dim on failed"
sleep 1.5
grep -qiE "custom shader|slangc|Failed to build|unknown (config|option)" "$T/k.log" && fail "kitty reported a problem after dim on"
"$HOME_DIR/bin/kittymux" screenshot "$T/on.png" >/dev/null 2>&1 || fail "second screenshot failed"
diff=$(compare -metric AE "$T/off.png" "$T/on.png" null: 2>&1 | awk '{print int($1)}')
[ "${diff:-0}" -gt 2000 ] || fail "dim on did not change the render (only ${diff:-0} pixels differ)"
"$HOME_DIR/bin/kittymux" dim off >/dev/null 2>&1; sleep 1.5
"$HOME_DIR/bin/kittymux" screenshot "$T/off2.png" >/dev/null 2>&1 || fail "third screenshot failed"
back=$(compare -metric AE "$T/off.png" "$T/off2.png" null: 2>&1 | awk '{print int($1)}')
[ "${back:-999999}" -lt "$diff" ] || fail "dim off did not restore the render ($back pixels differ from the original)"
echo "PASS: dim on changes ~$diff pixels, dim off restores them; screenshots are private valid PNGs"
