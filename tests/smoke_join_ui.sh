#!/usr/bin/env bash
# The join picker (ctrl+alt+shift+j → python/join-kit.py) with REAL key and mouse events in a real kitty: the chord opens it, ONE Esc closes it,
# the chord again closes it instead of stacking, typing filters (Esc clears the filter first), Tab cycles the side, ctrl+t flips tab/pane, hovering
# a row selects it, Enter joins, a left click joins, a right click does not. smoke_join.sh covers where the panes END UP; this covers how you get there.
# Needs Xvfb, xdotool, kitty >= 0.49, python3; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-joinui.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$T/probe.out" ] && { echo "--- probe said:"; tail -6 "$T/probe.out"; }; [ -n "${KPID:-}" ] && { echo "--- picker screen:"; screen | head -14; echo "--- tabs:"; tabs; }; [ -s "$T/k.log" ] && tail -6 "$T/k.log"; exit 1; }
for n in $(seq 440 469); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
sed "s|@KITTYMUX_HOME@|$HOME_DIR|g" "$HOME_DIR/kittymux-keys.conf.tpl" > "$CFG/kittymux-keys.conf"
printf 'allow_remote_control socket-only\nenabled_layouts splits,tall,stack\nconfirm_os_window_close 0\ntab_bar_min_tabs 99\nwindow_padding_width 0\ninclude %s/kittymux-keys.conf\n' "$CFG" > "$CFG/kitty.conf"
cat > "$T/session" <<'S'
new_tab Alpha
launch --title a1 sh
launch --location=vsplit --title a2 sh
new_tab Beta
launch --title b1 sh
new_tab Gamma
launch --title c1 sh
new_tab Delta
launch --title d1 sh
focus_tab 0
S
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_SOCKET_DIRS=$T/no-sockets \
  kitty -o linux_display_server=x11 --class kmx-joinui --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-joinui | head -1); X windowsize "$W" 1190 790; sleep 0.4; X windowsize "$W" 1200 800; X windowfocus "$W" 2>/dev/null; sleep 0.8
nwin() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; }
screen() { kitty @ --to "$SOCK" get-text --match cmdline:join-kit --extent screen 2>/dev/null; }
tabs() { kitty @ --to "$SOCK" ls | python3 -c '
import sys, json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        print(" ", t["title"], sorted(w["title"] for w in t["windows"] if "join-kit" not in str(w.get("cmdline"))), "(active)" if t["is_focused"] else "")'; }
panes_of() { tabs | grep -E "^  $1 " | head -1; }
wait_open() { for _ in $(seq 28); do screen | head -1 | grep -q "Join" && return 0; sleep 0.25; done; return 1; }
wait_closed() { for _ in $(seq 16); do [ -z "$(screen)" ] && return 0; sleep 0.25; done; return 1; }
K() { X key --clearmodifiers "$@"; }
CHORD=ctrl+alt+shift+j
row_xy() { # "x y" in pixels, inside list row N of the picker (the overlay covers ONE pane, wherever that pane is; rows start on line 3)
  rm -f "$T/geo.json"; kitty @ --to "$SOCK" kitten --match title:b1 "$HOME_DIR/tests/probe_geometry.py" "$T/geo.json" >"$T/probe.out" 2>&1; sleep 0.5      # run from the plain pane b1, not from the picker
  python3 - "$T/geo.json" "$1" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); row = int(sys.argv[2])
for t in d.values():
    for w in t["windows"]:
        if w["overlay"]:
            l, tp, r, b = w["g"]; cw, ch = (r - l) / w["cols"], (b - tp) / w["lines"]
            print(int(l + 4 * cw), int(tp + (row + 3) * ch + ch / 2)); sys.exit(0)
sys.exit(1)
PY
}
wobble_click() { # a real press and release with the pointer drifting 2 px — like a hand
  X mousemove "$1" "$2"; sleep 0.2; X mousedown "$3"; sleep 0.08; X mousemove_relative 2 1; sleep 0.08; X mouseup "$3"; sleep 0.8; }

base=$(nwin)
# 1. the chord opens the picker; it lists the OTHER tabs, not the one being moved
K $CHORD; wait_open || fail "$CHORD did not open the picker"
out=$(screen)
for t in Beta Gamma Delta; do echo "$out" | grep -q "$t" || fail "the picker should list the tab $t"; done
echo "$out" | grep -qE "^ +▸? *.? *Alpha" && fail "the tab being moved must not be offered as a target"
echo "$out" | grep -q "Alpha" || fail "the header should name the tab being moved (Alpha)"
echo "  ok   $CHORD opens the picker: Beta, Gamma, Delta offered, Alpha (the tab being moved) named in the header"

# 2. ONE Esc closes it; the chord again closes it instead of stacking
K Escape; wait_closed || fail "ONE Escape did not close the picker"
[ "$(nwin)" = "$base" ] || fail "window count changed after closing ($(nwin) vs $base)"
K $CHORD; wait_open || fail "the picker did not reopen"
K $CHORD; wait_closed || fail "pressing $CHORD again did not close it"
[ "$(nwin)" = "$base" ] || fail "the second $CHORD stacked another picker ($(nwin) windows, base $base)"
echo "  ok   one Esc closes it; the chord again closes it (no stacking)"

# 3. typing filters; the first Esc clears the filter, the second closes
K $CHORD; wait_open || fail "the picker did not reopen"
X type --delay 80 "gam"; sleep 0.8
out=$(screen)
echo "$out" | grep -q "Gamma" || fail "typing 'gam' should keep Gamma"
echo "$out" | grep -q "Beta" && fail "typing 'gam' should hide Beta"
K Escape; sleep 0.6
screen | grep -q "Beta" || fail "the first Esc should clear the filter and show every tab again"
K Escape; wait_closed || fail "the second Esc did not close the picker"
echo "  ok   typing filters, Esc clears the filter first, then closes"

# 4. Tab cycles the side, ctrl+t flips tab/pane
K $CHORD; wait_open || fail "the picker did not reopen"
screen | grep -q "auto side" || fail "the side should start on auto"
K Tab; sleep 0.5; screen | grep -q "to the right" || fail "Tab should pick 'to the right'"
K Tab; sleep 0.5; screen | grep -q "below" || fail "a second Tab should pick 'below'"
K ctrl+t; sleep 0.5; screen | head -1 | grep -q "this pane" || fail "ctrl+t should switch the header to 'this pane'"
K ctrl+t; sleep 0.5; screen | head -1 | grep -q "this pane" && fail "ctrl+t again should go back to the whole tab"
K Escape; wait_closed || fail "Esc did not close the picker"
echo "  ok   Tab cycles auto → right → below; ctrl+t flips whole tab / this pane"

# 5. hovering a row selects it; Enter joins it (Alpha → Gamma, whole tab)
K $CHORD; wait_open || fail "the picker did not reopen"
read -r GX GY <<<"$(row_xy 1)"                           # rows: Beta, Gamma, Delta → Gamma is the second
X mousemove "$GX" "$GY"; sleep 0.2; X mousemove_relative 3 0; sleep 0.8
screen | grep -E "▸" | grep -q "Gamma" || fail "hovering Gamma should select it (the ▸ marker)"
K Return; sleep 2.2
[ "$(panes_of Alpha)" = "" ] || fail "Alpha should be gone after it joined Gamma: $(panes_of Alpha)"
panes_of Gamma | grep -q "a1.*a2.*c1\|a1.*a2\|c1" || fail "Gamma should now hold Alpha's panes: $(panes_of Gamma)"
for p in a1 a2 c1; do panes_of Gamma | grep -q "'$p'" || fail "Gamma lost the pane $p: $(panes_of Gamma)"; done
[ "$(nwin)" = "$base" ] || fail "joining must not create or lose windows ($(nwin) vs $base)"
echo "  ok   hover selects a row; Enter joins: Gamma holds a1 a2 c1, Alpha is gone"

# 6. a LEFT click on a row joins (Gamma → Delta); the rows now are Beta, Delta
K $CHORD; wait_open || fail "the picker did not reopen from Gamma"
read -r DX DY <<<"$(row_xy 1)"
wobble_click "$DX" "$DY" 1
for p in a1 a2 c1 d1; do panes_of Delta | grep -q "'$p'" || fail "a left click on Delta should have joined Gamma into it; Delta: $(panes_of Delta)"; done
[ "$(panes_of Gamma)" = "" ] || fail "Gamma should be gone: $(panes_of Gamma)"
echo "  ok   a left click joins: Delta holds a1 a2 c1 d1"

# 7. a RIGHT click does not join anything
K $CHORD; wait_open || fail "the picker did not reopen from Delta"
before=$(tabs)
read -r RX RY <<<"$(row_xy 0)"
wobble_click "$RX" "$RY" 3
screen | head -1 | grep -q "Join" || fail "a right click closed the picker — it must only be a left click that joins"
K Escape; wait_closed || fail "Esc did not close the picker"
[ "$(tabs)" = "$before" ] || fail "a right click changed the tabs"
echo "  ok   a right click joins nothing"

[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty (before: $OTHERS_BEFORE after: $(others))"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: the join picker — chord, one Esc, no stacking, filter, side, scope, hover, Enter, left click; a right click does nothing"
