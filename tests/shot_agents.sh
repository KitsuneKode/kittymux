#!/usr/bin/env bash
# A screenshot of the panel's Agents rows (tools/demo_agents.py draws the real row functions on made-up tabs) in a private kitty under Xvfb.
#   bash tests/shot_agents.sh dark|light OUT.png [COLS] [LINES]       (default 38 x 36)
# Needs Xvfb, kitty, ImageMagick (`import`); otherwise SKIP (exit 0). Never touches another kitty or your real state.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
THEME=${1:-dark}; OUT=${2:-agents.png}; COLS=${3:-38}; LINES_N=${4:-36}
for dep in Xvfb kitty import python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-ag.XXXXXX"); CFG=$T/cfg; mkdir -p "$CFG" "$T/data/fonts"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
cp "$HOME_DIR/assets/kittymux-icons.ttf" "$T/data/fonts/" 2>/dev/null
if [ "$THEME" = light ]; then BG=#eff1f5; FG=#4c4f69; else BG=#1a1b26; FG=#c0caf5; fi
cat > "$CFG/kitty.conf" <<CONF
font_family JetBrainsMono Nerd Font Mono
font_size ${KMX_FONT_SIZE:-11}
window_padding_width 0
confirm_os_window_close 0
remember_window_size no
initial_window_width ${COLS}c
initial_window_height ${LINES_N}c
foreground $FG
background $BG
CONF
for n in $(seq 380 399); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1100x1700x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_DATA_HOME=$T/data KITTY_CONFIG_DIRECTORY=$CFG \
  kitty -o linux_display_server=x11 --class kmx-ag python3 "$HOME_DIR/tools/demo_agents.py" "$COLS" "$THEME" >"$T/k.log" 2>&1 & KPID=$!
sleep 4
W=$(DISPLAY=$DISP xdotool search --onlyvisible --class kmx-ag 2>/dev/null | head -1)
if [ -n "$W" ]; then DISPLAY=$DISP xdotool windowsize "$W" 1100 1700 2>/dev/null; sleep 1; fi
DISPLAY=$DISP import -window root "$OUT" 2>/dev/null || { echo "FAIL: could not capture"; exit 1; }
echo "wrote $OUT"
