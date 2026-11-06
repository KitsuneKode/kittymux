#!/usr/bin/env bash
# Confirm closing a busy agent, with REAL key events in a REAL kitty (socket-only, private config/state/socket, a fake agent):
#   a working agent's pane does not close on the first ctrl+shift+w: its tab's row in the bar asks ("Close? ctrl+shift+w again"; a pane title
#   bar, when kitty draws one, says it in full); then, with pane title bars forced on, the full question on the pane's own title bar;
#   the question lapses after ~4 s and the pane is still there; the key twice closes it; an idle pane closes at once (the control);
#   ctrl+shift+q on a tab with a working agent asks the same way; `closeguard` off closes at once. Then a tripwire: no other kitty touched.
# Needs Xvfb, xdotool, kitty >= 0.49.2 (pane title bars), python3; else SKIP.
set -u
unset HYPRLAND_INSTANCE_SIGNATURE
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-close.XXXXXX"); CFG=$T/cfg STATE=$T/state RUN=$T/run
mkdir -p "$CFG" "$STATE" "$RUN" "$T/bin" && chmod 700 "$STATE" "$RUN"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; [ -n "${KEEP:-}" ] && cp -r "$T" "$KEEP" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$STATE/tab_bar-error.log" ] && tail -12 "$STATE/tab_bar-error.log"; exit 1; }
for n in $(seq 201 240); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1300x820x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
# a fake claude that is always mid-turn: the scanner reads "esc to interrupt" as working
printf '#!/bin/sh\nprintf "\\n  * Thinking (esc to interrupt)\\n"\nwhile :; do sleep 1; done\n' > "$T/bin/claude"
chmod +x "$T/bin/claude"
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/window_title_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
sed "s|@KITTYMUX_HOME@|$HOME_DIR|g" "$HOME_DIR/kittymux-keys.conf.tpl" > "$CFG/kittymux-keys.conf"
printf 'allow_remote_control socket-only\nlisten_on unix:${XDG_RUNTIME_DIR}/mykitty\ninclude %s/kittymux.conf\ninclude %s/kittymux-keys.conf\nwatcher %s/python/pane-state.py\ngeninclude %s/python/kittymux_layout.py\ncursor_blink_interval 0\n' \
  "$HOME_DIR" "$CFG" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
# CLOSE_EDGE=left: the vertical bar (the question takes the tab's alert row); default: kitty's own bottom bar (it takes the title's place)
[ "${CLOSE_EDGE:-}" = left ] && printf 'tab_bar_edge left\ntab_bar_min_tabs 1\n' >> "$CFG/kitty.conf"
cat > "$T/session" <<S
new_tab busy
launch --title busy $T/bin/claude
new_tab idle
launch --title idle sh
new_tab busytab
launch --title busytab $T/bin/claude
new_tab offguard
launch --title offguard $T/bin/claude
new_tab keeper
launch --title keeper sh
focus_tab 0
S
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  XDG_RUNTIME_DIR=$RUN KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_SOCKET_DIRS=$RUN KITTYMUX_PANETITLE_DUMP=1 KITTYMUX_BAR_DUMP=1 \
  kitty -o linux_display_server=x11 -o initial_window_width=1240 -o initial_window_height=780 -o remember_window_size=no --class kmx-close --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 80); do ls "$RUN"/mykitty-* >/dev/null 2>&1 && break; sleep 0.25; done; sleep 2
SOCK=unix:$(ls "$RUN"/mykitty-* 2>/dev/null | head -1)
[ "$SOCK" != "unix:" ] || fail "kitty never opened its control socket"
# tripwire: count every OTHER kitty's windows now, compare at the end
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))' 2>/dev/null; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
X() { DISPLAY=$DISP xdotool "$@"; }
RC() { kitty @ --to "$SOCK" "$@"; }
titles() {   # the tab titles; retries a busy socket, and never answers "nothing" for an ls that failed (a closed-check would pass vacuously)
  local out
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    out=$(RC ls 2>>"$T/ls.err" | python3 -c 'import sys,json;print(" ".join(t["title"] for o in json.load(sys.stdin) for t in o["tabs"]) or "-")' 2>/dev/null) && [ -n "$out" ] && { echo "$out"; return 0; }
    sleep 0.3
  done
  echo "kitty @ ls did not answer: $(tail -3 "$T/ls.err")" >&2; return 1; }
has_tab() { local t; t=$(titles) || fail "kitty @ ls did not answer"; [[ " $t " == *" $1 "* ]]; }
wid_of() { RC ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if t["title"] == sys.argv[1]: print(t["windows"][0]["id"])' "$1"; }
state_of() { python3 -c 'import sys,json,glob
for p in glob.glob(sys.argv[1] + "/scan-*.json"):
    print((json.load(open(p)).get(sys.argv[2]) or {}).get("state", ""))' "$STATE" "$1" 2>/dev/null; }
tab_id() { RC ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if t["title"] == sys.argv[1]: print(t["id"])' "$1"; }
alert() { python3 -c 'import sys,json;print((json.load(open(sys.argv[1])).get(sys.argv[2]) or {}).get("alert",""))' "$STATE/bar-dump.json" "$1" 2>/dev/null; }
caption() { python3 -c 'import sys,json,re;print(re.sub(r"\x1b\[[0-9;]*m","",json.load(open(sys.argv[1])).get(sys.argv[2],"")))' "$STATE/panetitle-dump.json" "$1" 2>/dev/null; }
focus_tab() { RC focus-tab --match "title:^$1\$" >/dev/null 2>&1; sleep 0.6; W=$(X search --onlyvisible --class kmx-close | head -1); X windowfocus "$W" 2>/dev/null; sleep 0.4; }
key() { X key --clearmodifiers "$1"; }
wait_state() { for _ in $(seq 60); do [ "$(state_of "$1")" = "$2" ] && return 0; sleep 0.3; done; return 1; }

BUSY=$(wid_of busy); IDLE=$(wid_of idle); BT=$(wid_of busytab); OFF=$(wid_of offguard); TB=$(tab_id busy); TB2=$(tab_id busytab)
[ -n "$BUSY" ] && [ -n "$IDLE" ] && [ -n "$BT" ] && [ -n "$OFF" ] || fail "the session did not open (tabs: $(titles))"
wait_state "$BUSY" working || fail "the fake agent never read as working (state: $(state_of "$BUSY"))"

# 1. one press on a working agent: still open, and its title bar asks
focus_tab busy
key ctrl+shift+w; sleep 0.8
has_tab busy || fail "ctrl+shift+w closed a WORKING agent without asking"
alert "$TB" | grep -q "Close? Press again" || fail "the tab's row did not ask (alert: $(alert "$TB"))"
echo "  ok   a working agent asks on its tab's row: $(alert "$TB")"
[ -n "${CLOSE_SHOT:-}" ] && DISPLAY=$DISP import -window root "$CLOSE_SHOT" 2>/dev/null
# 2. the question lapses on its own; the pane stays
sleep 4.5
has_tab busy || fail "the pane closed while nobody answered"
alert "$TB" | grep -q "Close?" && fail "the question did not lapse after ~4 s"
echo "  ok   the question lapses after ~4 s and the pane stays"
# 3. the key twice closes it
key ctrl+shift+w; sleep 0.7; key ctrl+shift+w; sleep 1.2
has_tab busy && fail "the key twice did not close the busy agent"
echo "  ok   the same key again closes it"
# 4. control: an idle shell closes on one press, as kitty always did
focus_tab idle
key ctrl+shift+w; sleep 1.2
has_tab idle && fail "an idle pane did not close on one press (the guard asked when nothing was busy)"
echo "  ok   an idle pane closes at once"
# 5. a tab with a working agent asks the same way
wait_state "$BT" working || fail "the second fake agent never read as working"
focus_tab busytab
key ctrl+shift+q; sleep 0.8
has_tab busytab || fail "ctrl+shift+q closed a tab with a WORKING agent without asking"
alert "$TB2" | grep -q "Close? Press again" || fail "the tab close did not ask (alert: $(alert "$TB2"))"
key ctrl+shift+q; sleep 1.2
has_tab busytab && fail "ctrl+shift+q twice did not close the tab"
echo "  ok   a tab with a working agent asks, then closes on the second press"
# 6. with pane title bars on, the pane's own title bar says it in full
RC load-config --override window_title_bar_min_windows=1 >/dev/null 2>&1; sleep 1
P7=$(RC launch --type=tab --tab-title titled "$T/bin/claude" 2>/dev/null); sleep 0.5
wait_state "$P7" working || fail "the fourth fake agent never read as working"
focus_tab titled
key ctrl+shift+w; sleep 0.8
caption "$P7" | grep -q "Close Claude Code? It is working · ctrl+shift+w again" || fail "the pane title bar did not ask in full (caption: $(caption "$P7"))"
echo "  ok   with pane title bars on, the pane's own bar asks in full: $(caption "$P7" | sed 's/^ *//')"
key ctrl+shift+w; sleep 1.2
has_tab titled && fail "the second press did not close the titled pane"
# 7. the switch off: no question
touch "$STATE/closeguard-off"
wait_state "$OFF" working || fail "the third fake agent never read as working"
focus_tab offguard
key ctrl+shift+w; sleep 1.2
has_tab offguard && fail "with closeguard off the pane still asked"
echo "  ok   closeguard off: the key closes at once"

has_tab keeper || fail "the tab nobody closed is gone"
[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty (before: $OTHERS_BEFORE after: $(others))"
[ ! -s "$STATE/tab_bar-error.log" ] || fail "the tab bar logged errors"
echo "PASS: a busy agent asks on its title bar before it closes; idle panes and the switch off close at once; no other kitty touched"
