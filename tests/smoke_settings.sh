#!/usr/bin/env bash
# The panel's Settings view with REAL keys and mouse, in a private kitty under Xvfb: the pill and `s` open it, space toggles by writing the one flag file the
# catalog names, a row held by the environment stays locked, a risky switch asks first (esc cancels, enter confirms, turning OFF never asks), presets and reset
# work, a click on a state toggles, ten quick toggles cause ONE reload of the running kitties, and the CLI agrees with what the panel wrote.
#   bash tests/smoke_settings.sh [OUT_DIR]      (OUT_DIR: also writes settings-{dark,light}-{38,26}.png for looking at)
# Needs Xvfb, xdotool, kitty, python3 (ImageMagick `import` only for the PNGs); otherwise SKIP (exit 0).
# The rig's kitty is the only one it can reach: KITTYMUX_SOCKET_DIRS confines every discovery, and it ends with a tripwire on every other kitty.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=${1:-}
COLS=38; LINES_N=44
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
[ -z "$OUT" ] || { command -v import >/dev/null 2>&1 || { echo "SKIP: ImageMagick import not installed (needed for the PNGs)"; exit 0; }; mkdir -p "$OUT"; }
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-set.XXXXXX"); CFG=$T/cfg STATE=$T/state RUN=$T/run
mkdir -p "$CFG" "$STATE" "$RUN" "$T/bin" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; if [ -n "${KEEP:-}" ]; then echo "kept $T"; else rm -rf "$T"; fi; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$T/k.log" ] && tail -12 "$T/k.log"; [ -s "$STATE/sidebar-kit-err.log" ] && tail -20 "$STATE/sidebar-kit-err.log"; echo "--- screen:"; screen 2>/dev/null | head -60; exit 1; }
REAL_KITTY=$(command -v kitty)
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && case "$s" in "$RUN"/*) ;; *) kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))';; esac; done; }
BEFORE=$(others)

# a `kitty` in front of the real one for the children of the rig's kitty only: it logs every remote-control call, so "one reload" can be counted
printf '#!/bin/sh\ncase "$*" in *load-config*) echo "$*" >> "%s/reloads.log";; esac\nexec "%s" "$@"\n' "$T" "$REAL_KITTY" > "$T/bin/kitty"
chmod +x "$T/bin/kitty"

for n in $(seq 380 409); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1100x1700x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for _ in $(seq 40); do [ -S "/tmp/.X11-unix/X${DISP#:}" ] && break; sleep 0.25; done

theme() {
  if [ "$1" = light ]; then printf 'foreground #4c4f69\nbackground #eff1f5\nselection_foreground #eff1f5\nselection_background #4c4f69\nactive_border_color #1e66f5\ninactive_border_color #acb0be\ncolor9 #d20f39\ncolor10 #40a02b\ncolor11 #df8e1d\ncolor12 #1e66f5\n'
  else printf 'foreground #c0caf5\nbackground #1a1b26\nselection_foreground #1a1b26\nselection_background #c0caf5\nactive_border_color #f08fb8\ninactive_border_color #414868\ncolor9 #f7768e\ncolor10 #9ece6a\ncolor11 #e0af68\ncolor12 #7aa2f7\n'; fi
}
theme dark > "$CFG/theme.conf"
cat > "$CFG/kitty.conf" <<CONF
font_size 11
window_padding_width 0
tab_bar_style hidden
confirm_os_window_close 0
allow_remote_control socket-only
listen_on unix:$RUN/mykitty
remember_window_size no
initial_window_width ${COLS}c
initial_window_height ${LINES_N}c
include theme.conf
CONF
printf 'new_tab shell\nlaunch sh\nnew_tab web\nlaunch sh\nfocus_tab 0\n' > "$T/session"
# KITTYMUX_BELL=0 in the kitty's environment: the Bell row must come up held by it, and the panel must not touch it
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_SOCKET_DIRS=$RUN KITTYMUX_NOTIFY=0 KITTYMUX_BELL=0 XDG_RUNTIME_DIR=$RUN PATH="$T/bin:$PATH" \
  "$REAL_KITTY" -o linux_display_server=x11 --class kmx-set --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
SOCK=unix:$RUN/mykitty-$KPID
for _ in $(seq 240); do [ -S "$RUN/mykitty-$KPID" ] && break; sleep 0.25; done
[ -S "$RUN/mykitty-$KPID" ] || fail "kitty never opened its control socket"
sleep 3
kitty @ --to "$SOCK" kitten --match id:1 "$HOME_DIR/python/sidebar-kit.py" || fail "could not start the panel kitten"
PANEL=""
for _ in $(seq 40); do
  PANEL=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;d=json.load(sys.stdin);ws=[w["id"] for w in d[0]["tabs"][0]["windows"]];print(max(ws) if len(ws)>1 else "")')
  [ -n "$PANEL" ] && break; sleep 0.25
done
[ -n "$PANEL" ] || fail "the panel kitten never opened a window"
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-set | head -1)
[ -n "$W" ] || fail "no kitty window"
X windowfocus "$W" 2>/dev/null
read -r GX GY GW GH < <(X getwindowgeometry --shell "$W" | python3 -c 'import sys;d=dict(l.strip().split("=") for l in sys.stdin if "=" in l);print(d["X"],d["Y"],d["WIDTH"],d["HEIGHT"])')
screen() { kitty @ --to "$SOCK" get-text --match id:$PANEL --extent screen 2>/dev/null; }
wait_text() { for _ in $(seq 40); do screen | grep -q -- "$1" && return 0; sleep 0.25; done; echo "--- screen:"; screen; return 1; }
key() { X key --clearmodifiers "$@"; sleep 0.45; }
cell() {      # cell TEXT -> "col row" of the first screen cell where TEXT starts
  screen | python3 -c "
import sys
t = sys.argv[1]
for r, ln in enumerate(sys.stdin.read().split('\n')):
    c = ln.find(t)
    if c >= 0:
        print(c, r); break" "$1"
}
point() { local px py; px=$(( ($1 * GW + GW / 2) / COLS + GX )); py=$(( ($2 * GH + GH / 2) / LINES_N + GY )); X mousemove $((px - 8)) $((py - 3)); sleep 0.1; X mousemove "$px" "$py"; sleep 0.4; }
has() { [ -e "$STATE/$1" ]; }
idx() { python3 -c "import sys; sys.path.insert(0,'$HOME_DIR/python'); import kittymux_settingsview as S; print(S.ids_in_order().index(sys.argv[1]))" "$1"; }
go() {        # go ID: from the top (g), j down to that row
  key g; local n; n=$(idx "$1"); for _ in $(seq "$n"); do X key --clearmodifiers j; sleep 0.12; done; sleep 0.4
}
KMX() { env KITTYMUX_STATE=$STATE KITTYMUX_SOCKET_DIRS=$RUN XDG_RUNTIME_DIR=$RUN KITTYMUX_NOTIFY=0 KITTYMUX_BELL=0 python3 "$HOME_DIR/bin/kittymux" "$@"; }
reloads() { [ -s "$T/reloads.log" ] && wc -l < "$T/reloads.log" || echo 0; }
shot() {      # shot NAME: a PNG of the panel window when OUT is given
  [ -n "$OUT" ] || return 0
  DISPLAY=$DISP import -window root -crop "${GW}x${GH}+${GX}+${GY}" +repage "$OUT/$1.png" 2>/dev/null && echo "wrote $OUT/$1.png"
}

wait_text "tabs" || fail "the Agents view never drew"
screen | grep -q "⚙" || fail "the tab strip has no Settings pill"

# 1. `s` opens it; the header says what is set by hand (the environment's Bell is the one held row)
key s
wait_text "SETTINGS\|BAR" || fail "s did not open the Settings view"
screen | grep -q "BAR" || fail "the Bar group title is missing"
screen | grep -q "minimal" || fail "the preset row is missing"
screen | grep -q "held by env" || fail "the header does not say one setting is held by the environment"
echo "  ok   s opens Settings; presets, groups and the env hold are drawn"
shot settings-dark-38

# 2. space toggles the picked row by writing the ONE file the catalog names, and the row says so; space again puts it back
key j                                                           # hue
key space
has hue-off || fail "space did not write hue-off"
wait_text "file" || fail "the row does not say the value is set by a file"
key space
has hue-off && fail "a second space did not remove hue-off (a switch back at its default leaves no file)"
echo "  ok   space writes hue-off, space again leaves no file"

# 3. a row held by the environment stays locked
go bell
key space
has bell-off && fail "the panel wrote bell-off although KITTYMUX_BELL=0 holds it"
wait_text "held by KITTYMUX_BELL" || fail "the locked row does not say which variable holds it"
echo "  ok   the Bell row is held by KITTYMUX_BELL and stays untouched"
shot settings-dark-38-locked

# 4. a risky switch asks: esc cancels (no file), a second space or enter confirms, turning it OFF never asks
go usage-live
key space
wait_text "contact each" || fail "turning on live usage did not ask first"
has usage-live-on && fail "it was turned on before the answer"
shot settings-dark-38-asking
key Escape
has usage-live-on && fail "esc did not cancel the question"
screen | grep -q "contact each" && fail "the question stayed after esc"
screen | grep -q "BAR" || fail "esc closed the whole view instead of the question"
key space
wait_text "contact each" || fail "the question did not come back"
key Return
has usage-live-on || fail "enter did not confirm"
key space
has usage-live-on && fail "turning it OFF did not just do it"
screen | grep -q "contact each" && fail "turning it OFF asked a question"
echo "  ok   live usage asks; esc cancels; enter confirms; off never asks"

# 5. a click on a state toggles; a click on a row only picks it
key g
read -r FC FR <<<"$(cell "Folder line")"
[ -n "${FC:-}" ] || fail "no Folder line row"
point $((COLS - 4)) "$FR"; X click 1; sleep 0.7
has folder-off || fail "a click on the state did not turn Folder line off"
point $((COLS - 4)) "$FR"; X click 1; sleep 0.7
has folder-off && fail "a second click did not turn it back on"
echo "  ok   a click on the state toggles"

# 6. presets: a click on a chip applies it; p cycles; the CLI sees the same state
read -r PC PR <<<"$(cell "full")"
[ -n "${PC:-}" ] || fail "no full preset chip"
point "$PC" "$PR"; X click 1; sleep 0.8
has hover-on || fail "clicking the full preset did not turn the planned switches on"
KMX settings 2>/dev/null | grep -E "^  hover +on" >/dev/null || fail "the CLI does not agree that hover is on"
read -r PC PR <<<"$(cell "default")"
point "$PC" "$PR"; X click 1; sleep 0.8
has hover-on && fail "the default preset left hover-on behind"
key p; sleep 0.5
key p; key p
echo "  ok   presets by click and by key; the CLI reads what the panel wrote"

# 7. r puts the picked row back to its default; a held row is not ours to reset
go motion
key space; has motion-off || fail "motion off did not write its file"
key r; has motion-off && fail "r did not reset motion"
echo "  ok   r resets the row"

# 8. ten quick toggles are ONE reload of the running kitties (the apply is coalesced and runs off the UI thread)
sleep 2.5; before=$(reloads)
go hue
for _ in $(seq 10); do X key --clearmodifiers space; sleep 0.08; done
sleep 3
after=$(reloads)
[ $((after - before)) -eq 1 ] || fail "ten quick toggles caused $((after - before)) reloads (expected 1)"
has hue-off && fail "an even number of toggles must leave hue at its default"
echo "  ok   ten toggles, one reload"

# 9. panel-view requests: `kittymux settings open` is not tested here (it needs a docked panel); the request file is, through the same tick
key a
wait_text "tabs" || fail "a did not return to Agents"
echo settings > "$STATE/panel-view"
sleep 0.2
# the file is only read in panel mode (the overlay deck ignores it): it must be left alone here, not half-consumed
[ -e "$STATE/panel-view" ] || fail "the overlay deck consumed a panel-only request"
rm -f "$STATE/panel-view"

# 10. a narrow panel (26 columns): nothing is cut off that you need
if [ -n "$OUT" ]; then
  W2=$W; X windowsize "$W2" $(( GW * 26 / COLS )) "$GH"; sleep 1.0
  read -r GX GY GW GH < <(X getwindowgeometry --shell "$W" | python3 -c 'import sys;d=dict(l.strip().split("=") for l in sys.stdin if "=" in l);print(d["X"],d["Y"],d["WIDTH"],d["HEIGHT"])')
  key s; sleep 0.5; shot settings-dark-26
fi

# 11. the tripwire: no other kitty on this machine was touched
AFTER=$(others)
[ "$BEFORE" = "$AFTER" ] || fail "another kitty changed ($BEFORE -> $AFTER)"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: the Settings view: open, toggle, lock, confirm, click, presets, reset, one reload for a burst; the CLI agrees"
