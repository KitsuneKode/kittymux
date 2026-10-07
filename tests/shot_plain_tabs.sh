#!/usr/bin/env bash
# The "before" picture for the docs: a stock kitty tab strip with nine tabs titled the way agents leave them ("claude", "Claude Code",
# "I can't do that", "zsh"…), no kittymux. A private kitty under Xvfb; nothing of yours is read.
#   bash tests/shot_plain_tabs.sh dark|light OUT.png [COLS]       (default 96 columns; the picture is the strip and one line of window)
# Needs Xvfb, kitty, ImageMagick (`import`, `convert`); otherwise SKIP (exit 0). Never touches another kitty or your real state.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
THEME=${1:-dark}; OUT=${2:-plain-tabs-$THEME.png}; COLS=${3:-96}
for dep in Xvfb kitty import convert python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-plain.XXXXXX"); CFG=$T/cfg; mkdir -p "$CFG" "$T/data/fonts"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
if [ "$THEME" = light ]; then BG=#eff1f5 FG=#4c4f69; else BG=#1a1b26 FG=#c0caf5; fi
cat > "$CFG/kitty.conf" <<CONF
font_family JetBrainsMono Nerd Font Mono
font_size ${KMX_FONT_SIZE:-12}
tab_bar_style powerline
tab_bar_edge top
tab_bar_min_tabs 1
window_padding_width 0
confirm_os_window_close 0
remember_window_size no
initial_window_width ${COLS}c
initial_window_height 1c
foreground $FG
background $BG
CONF
python3 - "$T/session" <<'PY'
import json, sys
titles = ["claude", "codex", "devin", "Claude Code", "zsh", "I can't do that", "codex", "~/api", "opencode"]
open(sys.argv[1], "w").write("".join(f"new_tab\nlaunch --title {json.dumps(t)} sleep 600\n" for t in titles) + "focus_tab 0\n")
PY
for n in $(seq 400 429); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x400x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  XDG_DATA_HOME=$T/data KITTY_CONFIG_DIRECTORY=$CFG \
  kitty -o linux_display_server=x11 --class kmx-plain --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
sleep 4
DISPLAY=$DISP import -window root "$T/full.png" 2>/dev/null || { echo "FAIL: could not capture"; exit 1; }
# the window is placed at the top-left: keep the strip and the first lines under it
W=$(identify -format %w "$T/full.png"); convert "$T/full.png" -trim +repage "$OUT" 2>/dev/null || cp "$T/full.png" "$OUT"
echo "wrote $OUT"
