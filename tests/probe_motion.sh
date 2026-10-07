#!/usr/bin/env bash
# P0-a: does kitty deliver idle mouse motion over a vertical tab bar to Python? Prints the counts; no pass/fail — it is an answer.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-motion.XXXXXX"); SOCK=unix:$T/sock; XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
for n in $(seq 230 259); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!; sleep 1
kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for _ in $(seq 40); do [ -S "/tmp/.X11-unix/X${DISP#:}" ] && break; sleep 0.25; done      # Xvfb accepts connections a moment after it starts
mkdir -p "$T/cfg"; printf 'allow_remote_control socket-only\ntab_bar_edge left\ntab_bar_min_tabs 1\ntab_bar_style separator\nconfirm_os_window_close 0\n' > "$T/cfg/kitty.conf"
printf 'new_tab one\nlaunch sh\nnew_tab two\nlaunch sh\nnew_tab three\nlaunch sh\nfocus_tab 0\n' > "$T/session"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP KITTY_CONFIG_DIRECTORY=$T/cfg \
  kitty -o linux_display_server=x11 --class kmx-motion --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --class kmx-motion | head -1); X windowsize "$W" 1190 790; sleep 0.3; X windowsize "$W" 1200 800; sleep 1.5
kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_bar.py" "$T/geom.json" >/dev/null 2>&1
BX=$(python3 -c "import json;g=json.load(open('$T/geom.json'));print(int((g['left']+g['right'])/2))")
BY=$(python3 -c "import json;g=json.load(open('$T/geom.json'));print(int(g['top']+40))")
: > "$T/motion.log"
kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_motion.py" "$T/motion.log" 12 >/dev/null 2>&1
sleep 0.5
for i in 1 2 3 4 5 6 7 8; do X mousemove $((BX + i)) $((BY + i * 6)); sleep 0.15; done          # no button held
idle=$(python3 -c "import json;print(sum(1 for l in open('$T/motion.log') if json.loads(l)[2] == -1))")
X mousemove $BX $BY mousedown 1; sleep 0.1; for i in 1 2 3 4 5; do X mousemove $((BX + 20 + i * 4)) $((BY + 30)); sleep 0.1; done; X mouseup 1; sleep 0.5
total=$(wc -l < "$T/motion.log")
echo "idle motion events (button -1, no button held): $idle"
echo "all calls to handle_tab_bar_mouse (incl. press/release/drag): $total"
echo "RESULT: $([ "$idle" -gt 0 ] && echo 'idle motion REACHES Python — hover on the bar is possible' || echo 'idle motion does NOT reach Python — hover must live in the sheet/panel, not the bar')"
