#!/usr/bin/env bash
# A waiting agent stays waiting while you scroll its pane: the scanner reads the LIVE screen, not the scrolled view.
# (2026-11-13, measured: scrolled up 100 lines, window.as_text() returns the old output on display, and the prompt vanished.)
#   bash tests/smoke_scroll.sh     # expect: PASS
# Control inside the rig: tests/probe_scroll.py confirms kitty really is scrolled and as_text() shows old output.
# Its own Xvfb, kitty, socket and state dir; ends with a tripwire on every other kitty. Needs Xvfb, kitty, python3.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-scroll.XXXXXX"); CFG=$T/cfg STATE=$T/state BIN=$T/bin
mkdir -p "$CFG" "$STATE" "$BIN" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty*; do [ -S "$s" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
tripwire() { [ "$(others)" = "$OTHERS_BEFORE" ] || { echo "FAIL: this rig changed the windows of ANOTHER kitty on this machine"; return 1; }; }
fail() { echo "FAIL: $*"; tripwire; exit 1; }
for n in $(seq 361 399); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1100x700x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
cat > "$BIN/claude" <<'S'
#!/bin/sh
i=0; while [ $i -lt 300 ]; do echo "earlier output line $i"; i=$((i+1)); done
printf ' Bash command\n   rm -rf node_modules\n Do you want to proceed?\n ❯ 1. Yes\n   2. No\n'
while :; do sleep 1; done
S
chmod +x "$BIN/claude"
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'allow_remote_control socket-only\nlisten_on unix:%s/mykitty\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\n' "$T" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
printf 'new_tab shell\nlaunch\nnew_tab claude\nlaunch %s/claude\nfocus_tab 0\n' "$BIN" > "$T/session"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_SOCKET_DIRS=$T KITTYMUX_NOTIFY=0 \
  kitty -o linux_display_server=x11 --class kmx-scroll --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
SOCK=""; for _ in $(seq 240); do for f in "$T"/mykitty-*; do [ -S "$f" ] && SOCK=$f; done; [ -n "$SOCK" ] && break; sleep 0.25; done
[ -n "$SOCK" ] || fail "kitty never opened its control socket"
SOCK="unix:$SOCK"
WID=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
print(next(w["id"] for o in json.load(sys.stdin) for t in o["tabs"] if t["title"].startswith("claude") for w in t["windows"]))')
state() { python3 -c "import json,sys;d=json.load(open('$STATE/agents.json'));print(next((r['state'] for r in d['agents'] if r['window_id']==$WID),''))" 2>/dev/null; }
until_state() { local i; for i in $(seq 60); do [ "$(state)" = "$1" ] && return 0; sleep 0.25; done; [ "$(state)" = "$1" ]; }
until_state waiting || fail "the fake Claude never read as waiting (state '$(state)')"
echo "  ok   at the bottom, the prompt reads as waiting"
kitty @ --to "$SOCK" scroll-window --match "id:$WID" 100- >/dev/null 2>&1
kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_scroll.py" "$T/p.json" "$WID" >/dev/null 2>&1; sleep 0.3
python3 -c "import json,sys;d=json.load(open('$T/p.json'));sys.exit(0 if d['scrolled_by']>=50 and 'earlier output' in d['shown_last'] else 1)" \
  || fail "control: the pane did not scroll, or as_text() still shows the prompt ($(cat "$T/p.json" 2>/dev/null)): the rig proves nothing"
echo "  ok   control: kitty is scrolled up and as_text() shows old output"
sleep 3                                                   # several scans while scrolled
[ "$(state)" = waiting ] || fail "scrolled up, the waiting agent read as '$(state)': the scan followed the scrolled view"
echo "  ok   scrolled up, it still reads as waiting"
tripwire || exit 1
echo "  ok   no other kitty on this machine was touched"
echo "PASS: the scanner reads the live screen, whatever the scroll position"
