#!/usr/bin/env bash
# The native divider, in a real kitty: kitty's own border renderer draws it (two exact-colour hairlines in the pane padding), the pointer over it
# is kitty's NATIVE resize arrow, and pressing it starts a native divider drag that resizes the sidebar. In a single-pane tab (kitty does not
# hit-test borders there) the bar-side grab zone still works. Needs Xvfb, xdotool, ImageMagick, kitty >= 0.49.2 and libXfixes; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3 import convert; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
python3 -c 'import ctypes;ctypes.CDLL("libXfixes.so.3");ctypes.CDLL("libX11.so.6")' 2>/dev/null || { echo "SKIP: libXfixes not found"; exit 0; }
kitty --version | python3 -c 'import re,sys;v=tuple(map(int,re.search(r"(\d+)\.(\d+)\.(\d+)",sys.stdin.read()).groups()));sys.exit(0 if v>=(0,49,2) else 1)' || { echo "SKIP: needs kitty >= 0.49.2"; exit 0; }
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-native.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$STATE/barsize-debug.log" ] && tail -8 "$STATE/barsize-debug.log"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1600x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in tab_bar.py kittymux_theme.py kittymux_deck.py kittymux_git.py kittymux_layout.py kittymux_barsize.py kittymux_agents.py kittymux_state.py kittymux_scan.py; do
  ln -s "$HOME_DIR/python/$f" "$CFG/$f"
done
printf 'background #282828\nforeground #ebdbb2\nwindow_padding_width 25\nallow_remote_control yes\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ntab_bar_background #282828\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
printf 'new_tab split\nlaunch sh\nlaunch --location=vsplit sh\nnew_tab single\nlaunch sh\nfocus_tab 0\n' > "$T/session"
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_DEBUG=1 \
  kitty -o linux_display_server=x11 --class kmx-native --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --class kmx-native | head -1)
X windowsize "$W" 1590 890; sleep 0.4; X windowsize "$W" 1600 900; sleep 1.5
probe() { kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_bar.py" "$T/geom.json" >/dev/null 2>&1; }
g() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$T/geom.json" "$1"; }
cursor() { sleep 0.4; python3 "$HOME_DIR/tests/cursorname.py" "$DISP" | cut -d' ' -f1; }
pixel() {   # #rrggbb of one screen pixel (ImageMagick's srgb(r,g,b) form: its #hex form can be 16-bit on some builds)
  local rgb; rgb=$(DISPLAY=$DISP import -window root -crop 1x1+"$1"+"$2" txt:- 2>/dev/null | tail -1 | sed -n 's/.*srgb(\([0-9]*\),\([0-9]*\),\([0-9]*\)).*/\1 \2 \3/p')
  [ -n "$rgb" ] && printf '#%02x%02x%02x\n' $rgb
}
probe; EDGE=$(python3 -c "print(int($(g right)))"); CW=$(g cw); CH=$(g ch); Y=$(python3 -c "print(int($(g top) + 14 * $CH))")
[ -n "$CW" ] || fail "could not probe the bar"
read -r EXP700 EXP950 < <(python3 -c "
import sys; sys.path.insert(0, '$HOME_DIR/python'); import kittymux_theme as T
p = T.from_colors({'background': 0x282828, 'foreground': 0xEBDBB2}); print('#%06x #%06x' % (p.sep_700, p.sep_950))")

# 1. drawn by kitty's border renderer: exact colours, in the pane padding right next to the bar
X mousemove 900 500; sleep 0.5; X windowsize "$W" 1590 890; sleep 0.4; X windowsize "$W" 1600 900; sleep 1
got700=$(pixel $((EDGE + 1)) 500); got950=$(pixel $((EDGE + 6)) 500)
[ "$got700" = "$EXP700" ] || fail "700 hairline: expected $EXP700 at x=$((EDGE+1)), got '$got700'"
[ "$got950" = "$EXP950" ] || fail "950 hairline: expected $EXP950 at x=$((EDGE+6)), got '$got950'"
echo "  ok   the divider is drawn natively: $got700 then $got950, just right of the bar edge ($EDGE)"

# 2. the native resize arrow over the divider in a split tab; the hand over the bar; the text cursor in the pane
X mousemove "$((EDGE + 3))" 500; c=$(cursor); [ "$c" = sb_h_double_arrow ] || fail "over the divider the cursor is '$c', not the native resize arrow"
X mousemove "$((EDGE + 40))" 500; c=$(cursor); [ "$c" = xterm ] || fail "over pane text the cursor is '$c'"
X mousemove "$((EDGE - 40))" 500; c=$(cursor); [ "$c" = hand2 ] || fail "over the bar the cursor is '$c' (kitty's own hand)"
echo "  ok   split tab: resize arrow on the divider, text cursor in the pane, kitty's hand on the bar"

# 3. a native divider drag resizes the sidebar and ends cleanly
X mousemove "$((EDGE + 3))" 500 mousedown 1; sleep 0.2
burst=(); for x in $(seq $((EDGE - 2)) -5 $((EDGE - 60))); do burst+=(mousemove "$x" 500); done
FINAL=$((EDGE - 60)); X "${burst[@]}"; sleep 0.3
c=$(cursor); [ "$c" = sb_h_double_arrow ] || fail "during the drag the cursor is '$c'"
probe; NOW=$(python3 -c "print(int($(g right)))")
lag=$(python3 -c "print(abs($FINAL - $NOW))")
[ "$(python3 -c "print(1 if $lag <= 1.6 * $CW else 0)")" = 1 ] || fail "native drag: the bar edge is ${lag}px from the pointer (bar $NOW, pointer $FINAL)"
X mouseup 1; sleep 1
[ "$NOW" -lt "$EDGE" ] || fail "native drag did not shrink the bar ($EDGE → $NOW)"
echo "  ok   native drag: arrow stays during the drag, the bar edge followed the pointer ($EDGE → $NOW)"
X mousemove 900 500 click 1; sleep 0.3
probe; EDGE=$(python3 -c "print(int($(g right)))")

# 4. a single-pane tab: kitty does not hit-test borders there — the bar-side zone still resizes
kitty @ --to "$SOCK" focus-tab --match title:single; sleep 1
X mousemove 900 500; sleep 0.3
X mousemove "$((EDGE + 3))" 500; c=$(cursor); [ "$c" != sb_h_double_arrow ] || fail "single-pane tab unexpectedly shows the arrow (kitty only hit-tests borders with 2+ windows)"
X mousemove "$((EDGE - 6))" "$Y" mousedown 1; sleep 0.2
burst=(); for x in $(seq $((EDGE - 11)) -5 $((EDGE - 50))); do burst+=(mousemove "$x" "$Y"); done
X "${burst[@]}"; sleep 0.4; X mouseup 1; sleep 0.8
probe; AFTER=$(python3 -c "print(int($(g right)))")
[ "$AFTER" -lt "$EDGE" ] || fail "single-pane tab: dragging the bar-side zone did not resize ($EDGE → $AFTER)"
echo "  ok   single-pane tab: bar-side grab zone still resizes ($EDGE → $AFTER)"
echo "PASS: native divider — drawn by kitty, native resize arrow and drag in split tabs, bar-side fallback in single-pane tabs"
