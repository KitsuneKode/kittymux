#!/usr/bin/env bash
# Joining a tab's panes into another tab (python/join-kit.py), in a real kitty: the panes keep their SHAPE and none is squeezed to a sliver.
# Moving a 3-pane tab pane-by-pane with `detach-window` left panes of 15, 7 and 7 columns; join-kit plans the placement and uses kitty's own
# Tab.attach_windows(next_to=…). Driven through the kitten's non-interactive mode (--to TAB); the picker UI is covered by smoke_join_ui.sh.
# Needs Xvfb, kitty >= 0.49, python3; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-join.XXXXXX"); SOCK=unix:$T/sock; XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$T/geo.json" ] && python3 -c 'import json,sys;[print(" tab",t,v["layout"],[(w["title"],w["cols"],w["lines"]) for w in v["windows"]]) for t,v in json.load(open(sys.argv[1])).items()]' "$T/geo.json"; [ -s "$T/k.log" ] && tail -8 "$T/k.log"; exit 1; }
for n in $(seq 410 439); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for _ in $(seq 40); do [ -S "/tmp/.X11-unix/X${DISP#:}" ] && break; sleep 0.25; done
mkdir -p "$T/cfg"
printf 'allow_remote_control socket-only\nenabled_layouts splits,tall,stack\nconfirm_os_window_close 0\ntab_bar_min_tabs 1\nwindow_padding_width 8\n' > "$T/cfg/kitty.conf"
cat > "$T/session" <<'S'
new_tab A
launch --title a1 sh
launch --location=vsplit --title a2 sh
launch --location=hsplit --title a3 sh
new_tab B
launch --title b1 sh
launch --location=vsplit --title b2 sh
new_tab C
launch --title c1 sh
new_tab D
layout tall
launch --title d1 sh
launch --title d2 sh
focus_tab 0
S
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP KITTY_CONFIG_DIRECTORY=$T/cfg \
  kitty -o linux_display_server=x11 --class kmx-join --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@" 2>/dev/null; }
command -v xdotool >/dev/null 2>&1 && { WID=$(X search --class kmx-join | head -1); X windowsize "$WID" 1390 890; sleep 0.4; X windowsize "$WID" 1400 900; sleep 1.5; }
geo() { kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_geometry.py" "$T/geo.json" >/dev/null 2>&1; sleep 0.5; }
# python helpers over the geometry dump
q() { python3 - "$T/geo.json" "$@" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); cmd = sys.argv[2:]
def tab_of(title):
    for t, v in d.items():
        if any(w["title"] == title for w in v["windows"]): return t, v
    return None, None
def win(title):
    t, v = tab_of(title)
    return next(w for w in v["windows"] if w["title"] == title) if v else None
if cmd[0] == "tab": print(tab_of(cmd[1])[0] or "")                        # tab id holding a window titled X
elif cmd[0] == "titles": print(" ".join(sorted(w["title"] for w in d[cmd[1]]["windows"])) if cmd[1] in d else "")
elif cmd[0] == "mincols": print(min(w["cols"] for w in d[cmd[1]]["windows"]))
elif cmd[0] == "minlines": print(min(w["lines"] for w in d[cmd[1]]["windows"]))
elif cmd[0] == "gone": print("yes" if cmd[1] not in d else "no")
elif cmd[0] == "left_of": a, b = win(cmd[1]), win(cmd[2]); print("yes" if a["g"][2] <= b["g"][0] else "no")        # a is entirely left of b
elif cmd[0] == "above": a, b = win(cmd[1]), win(cmd[2]); print("yes" if a["g"][3] <= b["g"][1] else "no")          # a is entirely above b
elif cmd[0] == "aligned": a, b = win(cmd[1]), win(cmd[2]); print("yes" if abs(a["g"][0] - b["g"][0]) < 20 else "no")  # same left edge: a stack
elif cmd[0] == "id": print(win(cmd[1])["id"])
elif cmd[0] == "osw": print(d[cmd[1]]["os_window"] if cmd[1] in d else "")                       # the OS window a tab lives in
PY
}
JOIN() { kitty @ --to "$SOCK" kitten --match "id:$1" "$HOME_DIR/python/join-kit.py" "${@:2}" >/dev/null 2>&1; sleep 1.5; geo; }

geo
A1=$(q id a1); B_TAB=$(q tab b1); A_TAB=$(q tab a1); C_TAB=$(q tab c1); D_TAB=$(q tab d1)
[ -n "$A1" ] && [ -n "$B_TAB" ] && [ -n "$A_TAB" ] && [ -n "$C_TAB" ] && [ -n "$D_TAB" ] || fail "could not map the tabs"
[ "$(q mincols "$B_TAB")" -gt 20 ] || fail "the target tab starts too narrow to test anything"

# 1. a three-pane tab (a big pane + a stack of two) joins a two-pane tab, to the right
JOIN "$A1" --to "$B_TAB" --side right
[ "$(q gone "$A_TAB")" = yes ] || fail "the emptied source tab should be gone"
[ "$(q titles "$B_TAB")" = "a1 a2 a3 b1 b2" ] || fail "the target tab should hold all five panes, has: $(q titles "$B_TAB")"
[ "$(q mincols "$B_TAB")" -ge 18 ] || fail "a pane was squeezed to a sliver (min $(q mincols "$B_TAB") columns)"
[ "$(q left_of a1 a2)" = yes ] || fail "a1 should still be left of a2"
[ "$(q above a2 a3)" = yes ] || fail "a2 should still be above a3"
[ "$(q aligned a2 a3)" = yes ] || fail "a2 and a3 should still be a stack"
echo "  ok   3 panes joined 2: all five present, the big-pane + stack shape kept, narrowest pane $(q mincols "$B_TAB") columns"

# 2. one pane only (--pane), below
C1=$(q id c1)
JOIN "$C1" --to "$B_TAB" --side below --pane
[ "$(q gone "$C_TAB")" = yes ] || fail "a one-pane source tab should be gone after its only pane moved"
[ "$(q titles "$B_TAB")" = "a1 a2 a3 b1 b2 c1" ] || fail "the target should hold six panes, has: $(q titles "$B_TAB")"
[ "$(q minlines "$B_TAB")" -ge 4 ] || fail "a pane was squeezed to a sliver (min $(q minlines "$B_TAB") lines)"
echo "  ok   one pane joined below: six panes, none squeezed"

# 3. the same tab, a missing tab and nonsense change nothing
B1=$(q id b1)
JOIN "$B1" --to "$B_TAB" --side right
[ "$(q titles "$B_TAB")" = "a1 a2 a3 b1 b2 c1" ] || fail "joining a tab into itself must change nothing"
JOIN "$B1" --to 999999 --side right
JOIN "$B1" --to notanumber
[ "$(q titles "$B_TAB")" = "a1 a2 a3 b1 b2 c1" ] || fail "a bad target must change nothing"
echo "  ok   the same tab, a missing tab and a bad argument leave everything as it was"

# 4. a target in another layout (tall) places the panes itself — and still works
kitty @ --to "$SOCK" launch --type=tab --tab-title E --title e1 sh >/dev/null 2>&1; sleep 0.8
kitty @ --to "$SOCK" launch --title e2 sh >/dev/null 2>&1; sleep 1; geo
E1=$(q id e1); E_TAB=$(q tab e1)
JOIN "$E1" --to "$D_TAB" --side right
[ "$(q gone "$E_TAB")" = yes ] || fail "the source tab (joined into a tall-layout tab) should be gone"
[ "$(q titles "$D_TAB")" = "d1 d2 e1 e2" ] || fail "the tall-layout tab should hold four panes, has: $(q titles "$D_TAB")"
echo "  ok   a tab in another layout (tall) takes the panes too"

# 5. the deck's `a` (pull) path: the target tab's ACTIVE pane is an overlay (the deck itself), the source is addressed by one of its windows, side auto
kitty @ --to "$SOCK" launch --match id:"$B1" --type=tab --tab-title F --title f1 sh >/dev/null 2>&1; sleep 0.8
kitty @ --to "$SOCK" launch --location=vsplit --title f2 sh >/dev/null 2>&1; sleep 0.6
kitty @ --to "$SOCK" launch --match id:"$B1" --type=tab --tab-title G --title g1 sh >/dev/null 2>&1; sleep 0.8
kitty @ --to "$SOCK" launch --type=overlay --title ov sh >/dev/null 2>&1; sleep 1; geo
F1=$(q id f1); F_TAB=$(q tab f1); G_TAB=$(q tab g1)
[ -n "$F1" ] && [ -n "$F_TAB" ] && [ -n "$G_TAB" ] && [ "$F_TAB" != "$G_TAB" ] || fail "could not set up the overlay case"
JOIN "$F1" --to "$G_TAB" --side auto
[ "$(q gone "$F_TAB")" = yes ] || fail "the source tab should be gone after the pull"
[ "$(q titles "$G_TAB")" = "f1 f2 g1 ov" ] || fail "the target should hold g1 + the overlay + f1 f2, has: $(q titles "$G_TAB")"
[ "$(q mincols "$G_TAB")" -ge 18 ] || fail "a pane was squeezed to a sliver (min $(q mincols "$G_TAB") columns)"
echo "  ok   pulling a tab into one whose active pane is an overlay (the deck) works, panes keep a usable width"

# 6. a tab in ANOTHER OS window is a valid target (the picker lists those as "other window")
kitty @ --to "$SOCK" launch --match id:"$B1" --type=tab --tab-title H --title h1 sh >/dev/null 2>&1; sleep 0.8
kitty @ --to "$SOCK" launch --location=vsplit --title h2 sh >/dev/null 2>&1; sleep 0.6
kitty @ --to "$SOCK" launch --type=os-window --title o1 sh >/dev/null 2>&1; sleep 2; geo
H1=$(q id h1); H_TAB=$(q tab h1); O_TAB=$(q tab o1)
[ -n "$H1" ] && [ -n "$H_TAB" ] && [ -n "$O_TAB" ] || fail "could not set up the second OS window"
[ "$(q osw "$H_TAB")" != "$(q osw "$O_TAB")" ] || fail "the second OS window did not open"
OSW=$(q osw "$O_TAB")
JOIN "$H1" --to "$O_TAB" --side right
[ "$(q gone "$H_TAB")" = yes ] || fail "the source tab should be gone after joining into the other OS window"
[ "$(q titles "$O_TAB")" = "h1 h2 o1" ] || fail "the other OS window's tab should hold o1 h1 h2, has: $(q titles "$O_TAB")"
[ "$(q osw "$O_TAB")" = "$OSW" ] || fail "the target tab moved OS window"
echo "  ok   a tab in another OS window takes the panes too"

[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty (before: $OTHERS_BEFORE after: $(others))"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: a tab joins another as splits, keeping its shape — no slivers, same-tab and bad input are harmless"
