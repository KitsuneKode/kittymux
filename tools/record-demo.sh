#!/usr/bin/env bash
# Record the launch demo: `kittymux demo` (isolated config, state and fake agents) with the pixel tab bar, on a private Xvfb
# display, driven by real input (hover a row, jump to the agent that needs you, walk the bar); ffmpeg captures it.
# Touches nothing outside that display, and runs a neutral shell (bash --norc, a plain prompt): nothing of yours is shown.
#   tools/record-demo.sh OUT_DIR            # writes OUT_DIR/demo-raw.mp4 (H.264, 1600x900) and OUT_DIR/demo.gif (1200 wide)
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd); OUT=${1:?output dir}; mkdir -p "$OUT"
NEUTRAL=$(mktemp -d "${TMPDIR:-/tmp}/kmx-rec.XXXXXX")
printf '#!/bin/sh\nexport PS1="\\[\\e[2m\\]~/project\\[\\e[0m\\] ❯ "\nexec bash --norc --noprofile -i\n' > "$NEUTRAL/shell"; chmod +x "$NEUTRAL/shell"
for dep in Xvfb xdotool ffmpeg kitty; do command -v "$dep" >/dev/null || { echo "missing $dep"; exit 1; }; done
W=1600 H=900
for n in $(seq 401 439); do [ -e "/tmp/.X$n-lock" ] || { D=:$n; break; }; done
Xvfb "$D" -screen 0 ${W}x${H}x24 >/dev/null 2>&1 & XP=$!; sleep 1
cleanup() { rm -rf "$NEUTRAL"; [ -n "${FP:-}" ] && kill -INT "$FP" 2>/dev/null; sleep 1; [ -n "${DP:-}" ] && kill "$DP" 2>/dev/null; pkill -f "kitty --class kittymux-demo" -P $$ 2>/dev/null; kill "$XP" 2>/dev/null; }
trap cleanup EXIT
X() { DISPLAY=$D xdotool "$@"; }
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID __GLX_VENDOR_LIBRARY_NAME=mesa DISPLAY=$D LIBGL_ALWAYS_SOFTWARE=1 KITTYMUX_HOST=devbox KITTYMUX_PXBAR=on SHELL="$NEUTRAL/shell" \
  KITTY_ENABLE_WAYLAND=0 "$HOME_DIR/bin/kittymux" demo >/dev/null 2>&1 & DP=$!
WIN=""; for _ in $(seq 120); do WIN=$(X search --onlyvisible --class kittymux-demo 2>/dev/null | head -1); [ -n "$WIN" ] && break; sleep 0.25; done
[ -n "$WIN" ] || { echo "the demo window never appeared"; exit 1; }
sleep 1; X windowmove "$WIN" 0 0; X windowsize "$WIN" $((W-10)) $((H-10)); sleep 0.6; X windowsize "$WIN" $W $H; sleep 6   # visible first, then twice (shot_bar.sh)
X getwindowgeometry "$WIN"
ffmpeg -loglevel error -y -f x11grab -framerate 30 -video_size ${W}x${H} -i "$D" -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p "$OUT/demo-raw.mp4" & FP=$!
sleep 2.5                                                              # the bar at rest: who is working, who needs you
X mousemove --window "$WIN" 150 200; sleep 0.6; X mousemove --window "$WIN" 150 250; sleep 1.2     # a row lifts under the pointer
X mousemove --window "$WIN" 800 500; sleep 0.8
X key --clearmodifiers ctrl+alt+y; sleep 2.2                          # one key: the agent that needs you
X key --clearmodifiers ctrl+Tab; sleep 1.0; X key --clearmodifiers ctrl+Tab; sleep 1.2   # walk the bar
X key --clearmodifiers ctrl+alt+y; sleep 1.5
kill -INT "$FP"; wait "$FP" 2>/dev/null; FP=""
ffmpeg -loglevel error -y -i "$OUT/demo-raw.mp4" -vf "fps=20,scale=1200:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=sierra2_4a" "$OUT/demo.gif"
ls -la "$OUT"
