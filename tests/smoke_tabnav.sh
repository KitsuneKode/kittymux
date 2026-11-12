#!/usr/bin/env bash
# ctrl+tab / ctrl+shift+tab with the pixel tab bar, pressed as real keys: they walk the tabs in the order the bar DRAWS them
# (by project), not kitty's order. Tabs alternate between two projects, so the two orders differ on the first press.
# (2026-11-12, the owner: "the order doesn't match the bar", it "lands on hidden tabs" and the highlight jumps.)
#   bash tests/smoke_tabnav.sh                        # expect: PASS
#   SMOKE_TABNAV_CONTROL=1 bash tests/smoke_tabnav.sh # control, kitty's own next_tab (the maps left out): expect FAIL
# Its own Xvfb, kitty, socket and state dir; it ends by checking that no other kitty was touched. Needs Xvfb, xdotool, kitty, git,
# python3 with cairo/pango/rsvg (gi); else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty git python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
python3 -c "import cairo, gi; gi.require_version('Pango', '1.0'); gi.require_version('Rsvg', '2.0')" 2>/dev/null || { echo "SKIP: cairo/pango/rsvg not installed"; exit 0; }
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-tabnav.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" "$T/apple" "$T/berry" && chmod 700 "$STATE"
for r in apple berry; do git -C "$T/$r" init -q && git -C "$T/$r" -c user.name=t -c user.email=t@example.invalid -c commit.gpgsign=false commit -q --allow-empty -m init; done
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
# tripwire: every OTHER kitty's window count, taken before this rig's kitty exists; checked on PASS and on FAIL alike
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
tripwire() { [ "$(others)" = "$OTHERS_BEFORE" ] || { echo "FAIL: this rig changed the windows of ANOTHER kitty on this machine (before: $OTHERS_BEFORE after: $(others))"; return 1; }; }
fail() { echo "FAIL: $*"; [ -s "$STATE/tab_bar-error.log" ] && tail -20 "$STATE/tab_bar-error.log"; tripwire; exit 1; }
for n in $(seq 241 279); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'window_padding_width 10\nconfirm_os_window_close 0\nallow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
if [ -z "${SMOKE_TABNAV_CONTROL:-}" ]; then          # the template's own lines, so the rig tests what ships
  grep -E '^map (ctrl\+tab|ctrl\+shift\+tab) ' "$HOME_DIR/kittymux-keys.conf.tpl" | sed "s|@KITTYMUX_HOME@|$HOME_DIR|g" >> "$CFG/kitty.conf"
  [ "$(grep -c '^map ctrl+\(shift+\)\?tab ' "$CFG/kitty.conf")" = 2 ] || fail "the template does not map ctrl+tab and ctrl+shift+tab"
fi
cat > "$T/session" <<S
new_tab alpha
cd $T/apple
launch sh
new_tab bravo
cd $T/berry
launch sh
new_tab charlie
cd $T/apple
launch sh
new_tab delta
cd $T/berry
launch sh
focus_tab 0
S
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_SOCKET_DIRS=$T KITTYMUX_NOTIFY=0 KITTYMUX_PXBAR=on \
  kitty -o linux_display_server=x11 --class kmx-tabnav --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done
[ -S "$T/sock" ] || fail "kitty never opened its control socket ($(tail -3 "$T/k.log" 2>/dev/null))"
X() { DISPLAY=$DISP xdotool "$@"; }
W=""; for _ in $(seq 80); do W=$(X search --class kmx-tabnav 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.25; done
[ -n "$W" ] || fail "kitty's window never appeared"
X windowsize "$W" 1390 890; sleep 0.4; X windowsize "$W" 1400 900
active() { kitty @ --to "$SOCK" ls 2>/dev/null | python3 -c 'import sys,json
print(next(t["title"] for t in json.load(sys.stdin)[0]["tabs"] if t["is_active"]))'; }
until_active() { local i; for i in $(seq 40); do [ "$(active)" = "$1" ] && return 0; sleep 0.125; done; [ "$(active)" = "$1" ]; }
# the picture is up with both projects drawn as groups (control: without it the rest proves nothing)
drawn() { kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_pxbar.py" "$T/px.json" >/dev/null 2>&1 &&
  python3 -c "import json,sys;d=json.load(open('$T/px.json'));w=list(d['windows'].values());sys.exit(0 if w and sum(h[0]=='group' for h in w[0]['hits'])==2 and sum(h[0]=='tab' for h in w[0]['hits'])==4 else 1)" 2>/dev/null; }
for _ in $(seq 120); do drawn && break; sleep 0.25; done
drawn || fail "no pixel bar picture with two groups and four rows within 30 s"
until_active alpha || fail "precondition: alpha should be active, '$(active)' is"
X windowactivate --sync "$W" 2>/dev/null; X windowfocus --sync "$W" 2>/dev/null
press() { X key --clearmodifiers "$1"; }
press ctrl+Tab
until_active charlie || fail "ctrl+tab from 'alpha' went to '$(active)': the bar draws apple (alpha, charlie) then berry (bravo, delta)"
press ctrl+Tab
until_active bravo || fail "ctrl+tab from 'charlie' went to '$(active)', not 'bravo' (the next group's first row)"
press ctrl+shift+Tab
until_active charlie || fail "ctrl+shift+tab from 'bravo' went to '$(active)', not back to 'charlie'"
press ctrl+shift+Tab; press ctrl+shift+Tab
until_active delta || fail "ctrl+shift+tab from 'alpha' did not wrap to the last row 'delta' ('$(active)')"
echo "  ok   ctrl+tab / ctrl+shift+tab walk the rows in the order the bar draws them, and wrap"
tripwire || exit 1
echo "  ok   no other kitty on this machine was touched"
echo "PASS: ctrl+tab follows the pixel tab bar's drawn order (real key events)"
