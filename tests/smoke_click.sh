#!/usr/bin/env bash
# Tab clicks the way a hand makes them: with wobble. kitty counts press+release as a click only within 5 px (and 0.5 s, on the same tab) but
# starts a drag only past drag_threshold (14) — a click that drifts 5–14 px did NOTHING. Scripted clicks never drift, which is how that hid.
# Also: a middle-click closes a plain tab (kitty's own behaviour) but must not close a tab running an agent. Needs Xvfb, xdotool, kitty; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-click.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$STATE/barsize-debug.log" ] && tail -8 "$STATE/barsize-debug.log"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in tab_bar.py kittymux_theme.py kittymux_deck.py kittymux_git.py kittymux_features.py kittymux_place.py kittymux_layout.py kittymux_barsize.py kittymux_agents.py kittymux_state.py kittymux_scan.py; do
  ln -s "$HOME_DIR/python/$f" "$CFG/$f"
done
printf 'window_padding_width 10\nconfirm_os_window_close 0\nallow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
cat > "$T/session" <<'S'
new_tab alpha
launch sh
new_tab bravo
launch sh
new_tab agent
launch bash -c 'printf "· Pondering… (12s · ↓ 1.2k tokens)\n"; exec -a claude sleep 86400'
new_tab delta
launch sh
new_tab echo
launch sh
focus_tab 0
S
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_DEBUG=1 \
  kitty -o linux_display_server=x11 --class kmx-click --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 4
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --class kmx-click | head -1)
X windowsize "$W" 1390 890; sleep 0.4; X windowsize "$W" 1400 900; sleep 2
probe() { kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_bar.py" "$T/geom.json" >/dev/null 2>&1; }
probe
tab_y() {   # pixel y of the middle of the Nth tab (1-based) in the bar
  python3 -c "import json,sys;g=json.load(open('$T/geom.json'));e=g['extents'][int(sys.argv[1])-1];print(int(g['top']+(e[1]+e[2]+1)/2*g['ch']))" "$1"
}
y_of() {    # pixel y of the tab with this TITLE (tabs get reordered by the drag test, so never rely on a row number)
  local idx; idx=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;t=[x["title"] for x in json.load(sys.stdin)[0]["tabs"]];print(t.index(sys.argv[1])+1)' "$1")
  tab_y "$idx"
}
active() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for t in json.load(sys.stdin)[0]["tabs"]:
    if t["is_active"]: print(t["title"])'; }
titles() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(" ".join(t["title"] for t in json.load(sys.stdin)[0]["tabs"]))'; }
reset() { kitty @ --to "$SOCK" focus-tab --match title:alpha >/dev/null 2>&1; sleep 0.5; }
BX=80

# 1. a clean click works (sanity)
reset; X mousemove $BX "$(y_of bravo)" click 1; sleep 0.6
[ "$(active)" = bravo ] || fail "a clean click on 'bravo' left '$(active)' active"
echo "  ok   clean click activates the tab"

# 2. the bug: press, drift 8 px (more than kitty's 5 px click tolerance, less than the 14 px drag threshold), release
for dx in 6 9 12; do
  reset; X mousemove $BX "$(y_of delta)" mousedown 1; sleep 0.12; X mousemove $((BX + dx)) "$(y_of delta)"; sleep 0.12; X mouseup 1; sleep 0.7
  [ "$(active)" = delta ] || fail "a click that drifted ${dx} px did nothing ('$(active)' is still active, wanted 'delta')"
done
echo "  ok   a click that drifts 6, 9 or 12 px still activates the tab"

# 3. a slow click (held 0.9 s: kitty's own limit is 0.5 s)
reset; X mousemove $BX "$(y_of echo)" mousedown 1; sleep 0.9; X mouseup 1; sleep 0.7
[ "$(active)" = echo ] || fail "a slow click (0.9 s) did nothing ('$(active)')"
echo "  ok   a slow click activates the tab"

# 4. a real drag away from the tab is NOT turned into a click on the tab it started on
Y2=$(y_of bravo); reset; X mousemove $BX "$Y2" mousedown 1; sleep 0.12
for dy in 10 25 45 70 90; do X mousemove $BX "$(( Y2 + dy ))"; sleep 0.05; done; X mouseup 1; sleep 1
[ "$(active)" != "" ] || fail "no active tab after a drag"
echo "  ok   a long drag does not crash or wedge the bar (active: $(active))"

# 5. middle-click: closes a plain tab (kitty's behaviour) but never a tab running an agent
sleep 3
before=$(titles)
reset; X mousemove $BX "$(y_of agent)" click 2; sleep 1.5
case " $(titles) " in *" agent "*) ;; *) fail "a middle-click closed the tab running an agent (tabs: $(titles))" ;; esac
echo "  ok   a middle-click does not close the tab running an agent"
X mousemove $BX "$(y_of bravo)" click 2; sleep 1.5
case " $(titles) " in *" bravo "*) fail "a middle-click on a plain tab no longer closes it (tabs: $(titles))" ;; esac
echo "  ok   a middle-click still closes a plain tab (before: $before; after: $(titles))"
echo "PASS: tab clicks survive wobble and slowness; agent tabs survive a stray middle-click"
