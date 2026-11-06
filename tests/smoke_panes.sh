#!/usr/bin/env bash
# Pane jumping with REAL key events: ctrl+alt+shift+N focuses pane N of the tab, and N is the digit that
# ctrl+alt+e draws on that pane (tmux's display-panes). Needs Xvfb, xdotool, kitty; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-panes.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
sed "s|@KITTYMUX_HOME@|$HOME_DIR|g" "$HOME_DIR/kittymux-keys.conf.tpl" > "$CFG/kittymux-keys.conf"
cat > "$CFG/kitty.conf" <<CONF
allow_remote_control socket-only
enabled_layouts splits
include $CFG/kittymux-keys.conf
CONF
printf 'layout splits\nlaunch sh\nlaunch --location=vsplit sh\nlaunch --location=hsplit sh\nlaunch --location=vsplit sh\n' > "$T/session"
# the last-pane/last-tab keys run `kittymux workflow …`, which only trusts a PID-suffixed socket it can verify (see smoke_workflows.sh)
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_SOCKET_GLOB="$T/mykitty-*" KITTYMUX_SOCKET_DIRS="$T" XDG_RUNTIME_DIR="$T" \
  kitty -o linux_display_server=x11 --class kmx-panes --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done
ln -s "$T/sock" "$T/mykitty-$KPID"; sleep 2
# tripwire: this rig must never touch any OTHER kitty (the person running it may be typing in one). A signature of every other kitty's focus
# (which OS window, active tab and focused pane) is taken now and compared at the end: a stray `kittymux workflow …` would change it.
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && [ "$s" != "$T/sock" ] && [ "$s" != "$T/mykitty-$KPID" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    print(o["id"], o["is_focused"], [(t["id"], t["is_active"], [w["id"] for w in t["windows"] if w["is_focused"]]) for t in o["tabs"]])'; done; }
OTHERS_BEFORE=$(others)
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-panes | head -1); X windowfocus "$W" 2>/dev/null; sleep 0.5
focused() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for w in json.load(sys.stdin)[0]["tabs"][0]["windows"]:
    if w["is_focused"]: print(w["id"])'; }
ids() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(" ".join(str(w["id"]) for w in json.load(sys.stdin)[0]["tabs"][0]["windows"]))'; }
read -ra IDS <<<"$(ids)"
[ "${#IDS[@]}" -eq 4 ] || fail "expected 4 panes, got ${#IDS[@]}"
for n in 1 2 3 4; do
    X key --clearmodifiers "ctrl+alt+$n"; sleep 0.5
    got=$(focused); want=${IDS[$((n-1))]}
    [ "$got" = "$want" ] || fail "ctrl+alt+$n focused window $got, wanted pane $n (window $want)"
done
# ctrl+alt+0 is the LAST pane (the highest number), not "previous"
X key --clearmodifiers "ctrl+alt+1"; sleep 0.4
X key --clearmodifiers "ctrl+alt+0"
for _ in $(seq 20); do [ "$(focused)" = "${IDS[3]}" ] && break; sleep 0.25; done        # it runs the CLI (python + a few remote-control calls): poll, do not guess
if [ "$(focused)" != "${IDS[3]}" ]; then
    echo "--- by hand, from inside the first pane:"; KITTY_WINDOW_ID=${IDS[0]} KITTY_LISTEN_ON="$SOCK" "$HOME_DIR/bin/kittymux" workflow pane last; echo "rc=$?"
    fail "ctrl+alt+0 focused $(focused), wanted the last pane ${IDS[3]}"
fi
# alt+N is still a TAB jump, not a pane jump: with one session and a single tab it must leave the focused pane alone
before=$(focused); X key --clearmodifiers "alt+3"; sleep 2
[ "$(focused)" = "$before" ] || fail "alt+3 moved the focus inside the tab (it is a tab jump now)"
before=$(focused); X key --clearmodifiers "alt+0"; sleep 2
[ "$(focused)" = "$before" ] || fail "alt+0 (last tab) moved the focus inside a one-tab session"
# resize and equalize: alt+shift+l widens the focused pane, alt+shift+equal makes the splits even again
cols() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
want=int(sys.argv[1])
for w in json.load(sys.stdin)[0]["tabs"][0]["windows"]:
    if w["id"] == want: print(w["columns"])' "$1"; }
X key --clearmodifiers "ctrl+alt+1"; sleep 0.4
w0=$(cols "${IDS[0]}"); r0=$(cols "${IDS[1]}")
for _ in 1 2 3 4; do X key --clearmodifiers "alt+shift+l"; sleep 0.3; done
w1=$(cols "${IDS[0]}")
echo "resize: pane 1 is $w0 columns, 4 presses of alt+shift+l make it $w1 ($(( (w1 - w0) / 4 )) per press)"
[ "$w1" -gt "$w0" ] || fail "alt+shift+l did not widen the pane ($w0 -> $w1)"
[ $(( (w1 - w0) / 4 )) -ge ${MIN_STEP:-2} ] || fail "a press of alt+shift+l moves the edge by less than ${MIN_STEP:-2} columns ($w0 -> $w1 in 4 presses)"
X key --clearmodifiers "alt+shift+h"; sleep 0.4; w2=$(cols "${IDS[0]}")
[ "$w2" -lt "$w1" ] || fail "alt+shift+h did not narrow the pane back ($w1 -> $w2)"
X key --clearmodifiers "alt+shift+equal"; sleep 0.8
we=$(cols "${IDS[0]}"); re=$(cols "${IDS[1]}")
d=$(( we > re ? we - re : re - we ))
[ "$d" -le 2 ] || fail "alt+shift+= did not equalize the columns (pane 1 has $we, pane 2 has $re)"
echo "equalize: pane 1 and pane 2 are $we and $re columns wide"
# zoom fills a corner pane on both axes (plain maximize is horizontal only), then the same chord restores it.
# The script is a background launch, so poll. Stack is not this rig (enabled_layouts splits).
geom() { kitty @ --to "$SOCK" ls | python3 -c 'import json,sys
want=int(sys.argv[1]); field=sys.argv[2]
for w in json.load(sys.stdin)[0]["tabs"][0]["windows"]:
    if w["id"]==want: print(w[field])' "$1" "$2"; }
read -r ZID ZC ZL MC ML <<EOF
$(kitty @ --to "$SOCK" ls | python3 -c '
import json, sys
ws = json.load(sys.stdin)[0]["tabs"][0]["windows"]
mc, ml = max(w["columns"] for w in ws), max(w["lines"] for w in ws)
for w in ws:
    if w["columns"] < mc and w["lines"] < ml:
        print(w["id"], w["columns"], w["lines"], mc, ml)
        break
else:
    print("0 0 0 0 0")
')
EOF
[ "$ZID" != 0 ] || fail "no corner pane: zoom on both axes has nothing to grow"
n=1
for id in "${IDS[@]}"; do [ "$id" = "$ZID" ] && break; n=$((n + 1)); done
X key --clearmodifiers "ctrl+alt+$n"; sleep 0.4
X key --clearmodifiers "ctrl+alt+z"
c1=$ZC; l1=$ZL; grew=0
for _ in $(seq 25); do
    c1=$(geom "$ZID" columns); l1=$(geom "$ZID" lines)
    [ -n "$c1" ] && [ -n "$l1" ] && [ "$c1" -gt "$ZC" ] && [ "$l1" -gt "$ZL" ] && { grew=1; break; }
    sleep 0.2
done
[ "$grew" = 1 ] || fail "ctrl+alt+z did not grow the corner pane on both axes ($ZC x $ZL -> ${c1:-?} x ${l1:-?})"
# full zoom reaches the tab: at least as wide as the widest pane and as tall as the tallest (a cell or two of border)
dc=$(( MC > c1 ? MC - c1 : 0 )); dl=$(( ML > l1 ? ML - l1 : 0 ))
[ "$dc" -le 2 ] && [ "$dl" -le 2 ] || fail "ctrl+alt+z did not fill the tab ($c1 x $l1, extent $MC x $ML)"
echo "zoom: corner pane $ZC x $ZL -> $c1 x $l1"
X key --clearmodifiers "ctrl+alt+z"
back=0
for _ in $(seq 25); do
    c2=$(geom "$ZID" columns); l2=$(geom "$ZID" lines)
    dc=$(( c2 > ZC ? c2 - ZC : ZC - c2 )); dl=$(( l2 > ZL ? l2 - ZL : ZL - l2 ))
    [ "$dc" -le 2 ] && [ "$dl" -le 2 ] && { back=1; break; }
    sleep 0.2
done
[ "$back" = 1 ] || fail "ctrl+alt+z again did not restore the corner pane ($ZC x $ZL, now ${c2:-?} x ${l2:-?})"
# the overview's digits agree with the direct keys
for n in 1 2 3 4; do
    X key --clearmodifiers "ctrl+alt+1"; sleep 0.4
    X key --clearmodifiers ctrl+alt+e; sleep 0.6
    X key --clearmodifiers "$n"; sleep 0.6
    got=$(focused); want=${IDS[$((n-1))]}
    [ "$got" = "$want" ] || fail "overview digit $n focused window $got, direct key says $want"
done
# keyboard scrolling: a page up moves the view into the history, End returns to the live screen
kitty @ --to "$SOCK" send-text --match "id:${IDS[0]}" $'seq 1 300\n'; X key --clearmodifiers "ctrl+alt+1"; sleep 1
top() { kitty @ --to "$SOCK" get-text --match "id:${IDS[0]}" --extent screen | grep -m1 -E '^[0-9]+$'; }
live=$(top); [ -n "$live" ] || fail "no seq output on the first pane"
X key --clearmodifiers ctrl+alt+Prior; sleep 0.8; up=$(top)
[ -n "$up" ] && [ "$up" -lt "$live" ] || fail "ctrl+alt+PgUp did not scroll back (live top $live, now ${up:-none})"
X key --clearmodifiers ctrl+alt+Home; sleep 0.8; home=$(top)
[ -n "$home" ] && [ "$home" -lt "$up" ] || fail "ctrl+alt+Home did not go further back ($home vs $up)"
X key --clearmodifiers ctrl+alt+End; sleep 0.8; back=$(top)
[ "$back" = "$live" ] || fail "ctrl+alt+End did not return to the live screen ($back vs $live)"
[ "$(others)" = "$OTHERS_BEFORE" ] || fail "another kitty on this machine changed its focus while this rig ran (tripwire)"
echo "PASS: ctrl+alt+1..4, ctrl+alt+0 (last pane), alt+shift+h/l resize, alt+shift+= equalize, ctrl+alt+z zoom on both axes, and the ctrl+alt+e overview agree on pane numbers; ctrl+alt+PgUp/Home/End scroll the scrollback"
