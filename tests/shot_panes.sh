#!/usr/bin/env bash
# Screenshots of the pane keys for the docs, taken with REAL key events in a private kitty under Xvfb (nothing is staged or drawn by hand):
#   1 layout    four panes, the first focused
#   2 numbers   ctrl+alt+e: kitty draws a digit on every pane but the focused one (the same numbers ctrl+alt+1..9 use)
#   3 resized   alt+shift+l pressed six times: the focused pane is wider
#   4 equalized alt+shift+=: every split is the same size again
#   bash tests/shot_panes.sh dark|light OUT_DIR       writes OUT_DIR/panes-{layout,numbers,resized,equalized}-<theme>.png
# Needs Xvfb, xdotool, kitty, ImageMagick (`import`); otherwise SKIP (exit 0). Never touches another kitty or your real state.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
THEME=${1:-dark}; OUT=${2:-pane-shots}
for dep in Xvfb xdotool kitty import python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
mkdir -p "$OUT"
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-pshot.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" "$T/data/fonts" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; exit 1; }
cp "$HOME_DIR/assets/kittymux-icons.ttf" "$T/data/fonts/" 2>/dev/null
if [ "$THEME" = light ]; then BG='#eff1f5' FG='#4c4f69' ACT='#1e66f5' IDLE='#acb0be'; else BG='#1a1b26' FG='#c0caf5' ACT='#f08fb8' IDLE='#414868'; fi
sed "s|@KITTYMUX_HOME@|$HOME_DIR|g" "$HOME_DIR/kittymux-keys.conf.tpl" > "$CFG/kittymux-keys.conf"
cat > "$CFG/kitty.conf" <<CONF
font_family JetBrainsMono Nerd Font Mono
font_size 12
allow_remote_control socket-only
enabled_layouts splits
tab_bar_style hidden
confirm_os_window_close 0
remember_window_size no
initial_window_width 104c
initial_window_height 24c
window_padding_width 10
window_border_width 2px
draw_minimal_borders no
active_border_color $ACT
inactive_border_color $IDLE
foreground $FG
background $BG
cursor $ACT
include $CFG/kittymux-keys.conf
CONF
printf 'layout splits\nlaunch sh\nlaunch --location=vsplit sh\nlaunch --location=hsplit sh\nlaunch --location=vsplit sh\n' > "$T/session"
for n in $(seq 200 229); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID \
  __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_DATA_HOME=$T/data KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE \
  kitty -o linux_display_server=x11 --class kmx-pshot --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 2
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-pshot | head -1); [ -n "$W" ] || fail "no kitty window"
X windowfocus "$W" 2>/dev/null; sleep 0.5
ids() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(" ".join(str(w["id"]) for w in json.load(sys.stdin)[0]["tabs"][0]["windows"]))'; }
read -ra IDS <<<"$(ids)"
[ "${#IDS[@]}" -eq 4 ] || fail "expected 4 panes, got ${#IDS[@]}"
for i in 0 1 2 3; do                       # each pane says which pane it is and which key reaches it: the screenshot teaches by itself
  n=$((i + 1))
  kitty @ --to "$SOCK" send-text --match "id:${IDS[$i]}" "PS1='\$ '; clear; printf '\\n  pane $n\\n\\n  ctrl+alt+$n\\n\\n'"$'\n'
done
sleep 1
read -r GX GY GW GH < <(X getwindowgeometry --shell "$W" | python3 -c 'import sys;d=dict(l.strip().split("=") for l in sys.stdin if "=" in l);print(d["X"],d["Y"],d["WIDTH"],d["HEIGHT"])')
redraw() { X windowsize "$W" $((GW - 10)) $((GH - 10)); sleep 0.4; X windowsize "$W" "$GW" "$GH"; sleep 1.0; }
shot() { redraw; DISPLAY=$DISP import -window root -crop "${GW}x${GH}+${GX}+${GY}" +repage "$OUT/panes-$1-$THEME.png" 2>/dev/null || fail "could not capture $1"; echo "wrote $OUT/panes-$1-$THEME.png"; }
key() { X key --clearmodifiers "$@"; sleep 0.5; }
cols() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
want=int(sys.argv[1])
for w in json.load(sys.stdin)[0]["tabs"][0]["windows"]:
    if w["id"] == want: print(w["columns"])' "$1"; }

key ctrl+alt+1; shot layout
# the digits are drawn by kitty on top of every pane: take the picture while they are up, then pick pane 1 (a digit closes the overlay)
X key --clearmodifiers ctrl+alt+e; sleep 0.8
DISPLAY=$DISP import -window root -crop "${GW}x${GH}+${GX}+${GY}" +repage "$OUT/panes-numbers-$THEME.png" 2>/dev/null || fail "could not capture numbers"
echo "wrote $OUT/panes-numbers-$THEME.png"
key Escape                                  # the focused pane has no digit, so there is nothing to pick: Escape closes the overlay
key ctrl+alt+1
w0=$(cols "${IDS[0]}")
for _ in 1 2 3 4 5 6; do X key --clearmodifiers alt+shift+l; sleep 0.25; done
sleep 0.5; w1=$(cols "${IDS[0]}")
[ "$w1" -gt "$w0" ] || fail "alt+shift+l did not widen the pane ($w0 -> $w1)"
shot resized
X key --clearmodifiers alt+shift+equal; sleep 0.8
w2=$(cols "${IDS[0]}"); r2=$(cols "${IDS[1]}")
d=$(( w2 > r2 ? w2 - r2 : r2 - w2 ))
[ "$d" -le 2 ] || fail "alt+shift+= did not equalize (pane 1 has $w2 columns, pane 2 has $r2)"
shot equalized
echo "PASS: panes $w0 -> $w1 columns after six alt+shift+l, back to $w2 / $r2 after alt+shift+=; PNGs in $OUT"
