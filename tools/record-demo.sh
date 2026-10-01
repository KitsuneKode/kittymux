#!/usr/bin/env bash
# Re-record assets/demo.gif (the README hero) from the real thing: `kittymux demo` in a virtual X display,
# driven with real key and mouse events. Needs Xvfb, xdotool, ffmpeg, kitty.
#   tools/record-demo.sh [out.gif]            record
#   STILLS=dir tools/record-demo.sh           only save a PNG per scene (to check coordinates)
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=${1:-$HOME_DIR/assets/demo.gif}
for dep in Xvfb xdotool ffmpeg kitty; do command -v "$dep" >/dev/null || { echo "need $dep"; exit 1; }; done
for n in $(seq 170 199); do [ -e "/tmp/.X$n-lock" ] || { D=:$n; break; }; done
W=1200 H=700
Xvfb "$D" -screen 0 ${W}x${H}x24 >/dev/null 2>&1 & XP=$!
KP= FP=
TMP=$(mktemp -d); trap '[ -n "$KP" ] && pkill -P $KP 2>/dev/null; kill $KP $XP $FP 2>/dev/null; rm -rf "$TMP"' EXIT   # (pkill -P: the demo launcher'"'"'s kitty child)
sleep 1
export DISPLAY=$D __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1
unset WAYLAND_DISPLAY
"$HOME_DIR/bin/kittymux" demo --own-icon-font >/dev/null 2>&1 & KP=$!
for _ in $(seq 80); do xdotool search --onlyvisible --class kittymux-demo >/dev/null 2>&1 && break; sleep 0.25; done
sleep 2
for WIN in $(xdotool search --onlyvisible --class kittymux-demo); do          # every visible kitty window of the demo
  xdotool windowmove "$WIN" 0 0 windowsize "$WIN" $((W-10)) $((H-10)) 2>/dev/null
  sleep 0.5; xdotool windowsize "$WIN" $W $H 2>/dev/null
done
sleep 3
X() { xdotool "$@"; }
still() { [ -n "${STILLS:-}" ] && { mkdir -p "$STILLS"; ffmpeg -loglevel error -y -f x11grab -video_size ${W}x${H} -i "$D" -frames:v 1 "$STILLS/$1.png"; }; return 0; }
PAUSE() { sleep "$1"; }
scene() {
  X mousemove 700 400; PAUSE 2.2; still bar
  X key ctrl+alt+b; PAUSE 2.0; still deck
  X key j; PAUSE 0.7; X key j; PAUSE 0.7; X key j; PAUSE 0.7; X key j; PAUSE 0.7; X key j; PAUSE 1.0; still deck2
  X key q; PAUSE 1.0
  X mousemove 120 392 click 3; PAUSE 2.2; still peek
  X key Escape; PAUSE 0.8
  X mousemove 255 20 click 1; PAUSE 1.8; still rail
  X mousemove 40 20 click 1; PAUSE 1.8
  X mousemove 700 400; PAUSE 1.0
}
if [ -n "${STILLS:-}" ]; then scene; exit 0; fi
ffmpeg -loglevel error -y -f x11grab -framerate 8 -video_size ${W}x${H} -i "$D" -t 22 "$TMP/raw.mkv" & FP=$!
sleep 0.5; scene; wait $FP 2>/dev/null
ffmpeg -loglevel error -y -i "$TMP/raw.mkv" -vf "fps=8,scale=760:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" "$OUT"
ls -la "$OUT"
