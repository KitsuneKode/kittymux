#!/usr/bin/env bash
# The command palette (ctrl+alt+shift+space → python/palette-kit.py → `kittymux act`) with REAL key and mouse events in a real kitty (socket-only, private config/state/socket):
# the chord opens it and lists the tabs and a needs-you event, typing filters, ONE Esc clears the filter and the NEXT closes it, the chord again closes it instead of stacking,
# Enter focuses a tab, Enter on a needs-you event jumps to its window, a click does it, a fixed action runs (quiet popups, then bring them back), and `kittymux act` refuses
# anything that is not one of the palette's own actions. Ends with a tripwire on every OTHER kitty on the machine. Needs Xvfb, xdotool, kitty >= 0.49, python3; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-palette.XXXXXX"); CFG=$T/cfg STATE=$T/state RUN=$T/run
mkdir -p "$CFG" "$STATE" "$RUN" "$T/a" "$T/b" "$T/c" && chmod 700 "$STATE" "$RUN"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -n "${KPID:-}" ] && { echo "--- palette screen:"; screen | head -16; echo "--- tabs:"; tabs; }; [ -s "$T/k.log" ] && tail -5 "$T/k.log"; [ -s "$STATE/sidebar-kit-err.log" ] && tail -5 "$STATE/sidebar-kit-err.log"; exit 1; }
for n in $(seq 500 529); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
sed "s|@KITTYMUX_HOME@|$HOME_DIR|g" "$HOME_DIR/kittymux-keys.conf.tpl" > "$CFG/kittymux-keys.conf"
printf 'allow_remote_control socket-only\nlisten_on unix:${XDG_RUNTIME_DIR}/mykitty\nconfirm_os_window_close 0\nfont_family JetBrainsMono Nerd Font Mono\ninclude %s/kittymux.conf\ninclude %s/kittymux-keys.conf\ngeninclude %s/python/kittymux_layout.py\n' "$HOME_DIR" "$CFG" "$HOME_DIR" > "$CFG/kitty.conf"
cat > "$T/session" <<S
new_tab main
cd $T/a
launch --title shell sh
new_tab api
cd $T/b
launch --title api-shell sh
new_tab web
cd $T/c
launch --title web-shell sh
focus_tab 0
S
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && case "$s" in "$RUN"/*) ;; *) kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))';; esac; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_RUNTIME_DIR=$RUN KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
  KITTYMUX_SOCKET_DIRS=$RUN \
  kitty -o linux_display_server=x11 --class kmx-palette --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 80); do ls "$RUN"/mykitty-* >/dev/null 2>&1 && break; sleep 0.25; done; sleep 3
SOCK=unix:$(ls "$RUN"/mykitty-* | head -1)
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-palette | head -1); X windowsize "$W" 1190 790; sleep 0.4; X windowsize "$W" 1200 800; X windowfocus "$W" 2>/dev/null; sleep 0.8
nwin() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; }
active() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if t["is_active"]: print(t["title"])'; }
tabs() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]: print(" ", t["title"], len(t["windows"]), "(active)" if t["is_active"] else "")'; }
screen() { kitty @ --to "$SOCK" get-text --match cmdline:palette-kit --extent screen 2>/dev/null; }
wait_open() { for _ in $(seq 40); do screen | grep -q "search tabs" && return 0; sleep 0.25; done; return 1; }
wait_text() { for _ in $(seq 40); do screen | grep -q -- "$1" && return 0; sleep 0.25; done; return 1; }
wait_gone() { for _ in $(seq 40); do screen | grep -q -- "$1" || return 0; sleep 0.25; done; return 1; }
wait_closed() { for _ in $(seq 20); do [ -z "$(screen)" ] && return 0; sleep 0.25; done; return 1; }
wait_active() { for _ in $(seq 24); do [ "$(active)" = "$1" ] && return 0; sleep 0.25; done; return 1; }
win_of_tab() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if t["title"] == sys.argv[1]: print(t["windows"][0]["id"])' "$1"; }
K() { X key --clearmodifiers "$@"; }
shot() { [ -n "${SMOKE_SHOT:-}" ] && command -v import >/dev/null 2>&1 && { DISPLAY=$DISP import -window root "$SMOKE_SHOT.$1.png" 2>/dev/null; }; return 0; }
CHORD=ctrl+alt+shift+space
base=$(nwin)
[ "$(active)" = main ] || fail "setup: the rig should start on the 'main' tab (active: $(active))"

# a needs-you event about the api tab's window, written with the real inbox module (pid = this kitty, so a jump can find it)
API_WIN=$(win_of_tab api); [ -n "$API_WIN" ] || fail "setup: no api tab"
KPID_REAL=$(python3 -c 'import re,sys;print(re.search(r"mykitty-(\d+)", sys.argv[1]).group(1))' "$SOCK")
HOME_DIR_FOR_PY=$HOME_DIR python3 - "$STATE" "$KPID_REAL" "$API_WIN" <<'PY'
import os, sys, time
sys.path.insert(0, os.path.join(os.environ["HOME_DIR_FOR_PY"], "python"))
import kittymux_inbox as I
state, pid, win = sys.argv[1], int(sys.argv[2]), sys.argv[3]
ev = I.make_event("permission", "claude", win, "screen", time.time() - 120, pid=pid, tab="api", title="Do you want to proceed?", body="rm -rf node_modules")
I.add(state, ev)
PY

# 1. the chord opens the palette: the search field, the needs-you event, and every tab
K $CHORD; wait_open || fail "$CHORD did not open the palette"
wait_text "Needs you" || fail "the needs-you event never appeared (is 'kittymux pick --json' working in the rig?)"
out=$(screen)
for t in main api web; do echo "$out" | grep -q "$t" || fail "the palette should list the tab $t"; done
echo "$out" | grep -q "rm -rf node_modules" || fail "the needs-you event text is missing"
echo "$out" | grep -q "Actions" || fail "the Actions group is missing"
shot palette
echo "  ok   $CHORD opens the palette: the event, the three tabs and the actions are listed"

# 2. typing filters; ONE Esc clears the filter, the NEXT one closes
X type --delay 70 "web"; wait_gone "api-shell" || true
sleep 0.4
out=$(screen)
echo "$out" | grep -q "web" || fail "typing 'web' should keep the web tab"
echo "$out" | grep -q "rm -rf node_modules" && fail "typing web should filter out the api event"
K Escape; sleep 0.6
screen | grep -q "rm -rf node_modules" || fail "the first Esc should clear the filter and show everything again"
[ "$(nwin)" -gt "$base" ] || fail "the first Esc must not close the palette"
K Escape; wait_closed || fail "the second Esc did not close the palette"
[ "$(nwin)" = "$base" ] || fail "window count changed after closing ($(nwin) vs $base)"
echo "  ok   typing filters; the first Esc clears the filter, the second closes; no window left behind"

# 3. the chord again closes it instead of stacking a second palette
K $CHORD; wait_open || fail "palette did not reopen"
K $CHORD; wait_closed || fail "pressing the chord again did not close it"
[ "$(nwin)" = "$base" ] || fail "the second chord stacked another overlay ($(nwin) windows, base $base)"
echo "  ok   the chord again closes the palette (no stacking)"

# 4. Enter on a tab focuses it, after the overlay is gone
K $CHORD; wait_open || fail "palette did not reopen"
X type --delay 70 "web"; sleep 0.6
K Return; wait_closed || fail "Enter did not close the palette"
wait_active web || fail "Enter on the web tab should focus it (active: $(active))"
[ "$(nwin)" = "$base" ] || fail "window count changed ($(nwin) vs $base)"
echo "  ok   Enter on a tab closes the palette and focuses that tab"

# 5. Enter on the needs-you event jumps to the api window (and marks it read)
K $CHORD; wait_open || fail "palette did not reopen"
wait_text "Needs you" || fail "event missing on the second open"
K Return; wait_closed || fail "Enter on the event did not close the palette"
wait_active api || fail "Enter on the needs-you event should jump to the api tab (active: $(active))"
python3 - "$STATE" "$HOME_DIR" <<'PY' || fail "the jumped-to event should be marked read"
import os, sys
sys.path.insert(0, os.path.join(sys.argv[2], "python"))
import kittymux_inbox as I
ev = [e for e in I.load(sys.argv[1]) if e["kind"] == "permission"]
sys.exit(0 if ev and all(e["status"] != "unread" for e in ev) else 1)
PY
echo "  ok   Enter on a needs-you event jumps to its window and marks it read"

# 6. a click does it: filter to one row, click it
K $CHORD; wait_open || fail "palette did not reopen"
X type --delay 70 "main"; sleep 0.7
rm -f "$T/geo.json"; kitty @ --to "$SOCK" kitten --match title:web-shell "$HOME_DIR/tests/probe_geometry.py" "$T/geo.json" >"$T/probe.out" 2>&1; sleep 0.5
XY=$(python3 - "$T/geo.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for t in d.values():
    for w in t["windows"]:
        if w["overlay"]:
            l, tp, r, b = w["g"]; cw, ch = (r - l) / w["cols"], (b - tp) / w["lines"]
            print(int(l + w["cols"] * cw / 2), int(tp + 3 * ch + ch / 2)); sys.exit(0)
sys.exit(1)
PY
) || fail "could not find the palette's first row ($(cat "$T/probe.out" 2>/dev/null | tail -3))"
set -- $XY
X mousemove "$1" "$2"; sleep 0.25; X mousedown 1; sleep 0.08; X mousemove_relative 2 1; sleep 0.08; X mouseup 1; sleep 0.8
wait_closed || fail "a click on a row should close the palette"
wait_active main || fail "clicking the main row should focus the main tab (active: $(active))"
echo "  ok   a (slightly wobbly) left click on a row does it"

# 7. a fixed action: quiet the popups (a flag in the private state), then bring them back
K $CHORD; wait_open || fail "palette did not reopen"
X type --delay 70 "quiet popups"; sleep 0.6
K Return; wait_closed || fail "the mute action did not close the palette"
for _ in $(seq 20); do ls "$STATE" | grep -qi "mute" && break; sleep 0.25; done
ls "$STATE" | grep -qi "mute" || fail "the 'quiet popups' action should leave a mute flag in the state dir ($(ls "$STATE" | tr '\n' ' '))"
K $CHORD; wait_open || fail "palette did not reopen"
X type --delay 70 "bring popups"; sleep 0.6
K Return; wait_closed || fail "the unmute action did not close the palette"
for _ in $(seq 20); do ls "$STATE" | grep -qi "mute" || break; sleep 0.25; done
ls "$STATE" | grep -qi "mute" && fail "the 'bring popups back' action should remove the mute flag ($(ls "$STATE" | tr '\n' ' '))"
echo "  ok   the fixed actions run (quiet the popups, bring them back)"

# 8. `kittymux act` refuses anything that is not a palette action, and changes nothing
for bad in '{"op":"rm"}' '{"op":"run","id":"rm -rf ~"}' '{"op":"spawn","agent":"--help","where":"tab"}' '{"op":"reopen","key":"../../etc/passwd"}' 'not json'; do
  KITTYMUX_STATE=$STATE XDG_RUNTIME_DIR=$RUN KITTYMUX_SOCKET_DIRS=$RUN "$HOME_DIR/bin/kittymux" act "$bad" >/dev/null 2>&1; rc=$?
  [ "$rc" = 2 ] || fail "kittymux act should refuse $bad with status 2 (got $rc)"
done
[ "$(nwin)" = "$base" ] || fail "a refused action changed the window count"
echo "  ok   kittymux act refuses five hostile actions and changes nothing"

[ "$(others)" = "$OTHERS_BEFORE" ] || fail "another kitty on this machine was touched (windows $OTHERS_BEFORE -> $(others))"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: command palette — the chord opens and closes it, typing filters, esc clears then closes, Enter and a click focus a tab or jump to an event, fixed actions run, hostile actions are refused"
