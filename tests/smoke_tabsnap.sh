#!/usr/bin/env bash
# tabs.json from a REAL kitty (socket-only, private config/state/socket, a fake agent): the scanner publishes every tab, the agent's
# tab carries its state and brand, a plain shell tab is listed too, the window carries the theme palette, a new tab appears and a
# closed one goes, and an unchanged scan does not rewrite the file. Then a tripwire: no other kitty touched.
# Needs Xvfb, kitty, python3; else SKIP.
set -u
unset HYPRLAND_INSTANCE_SIGNATURE
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-tabsnap.XXXXXX"); CFG=$T/cfg STATE=$T/state RUN=$T/run
mkdir -p "$CFG" "$STATE" "$RUN" "$T/bin" && chmod 700 "$STATE" "$RUN"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$STATE/tabs.json" ] && head -c 1500 "$STATE/tabs.json"; exit 1; }
for n in $(seq 241 280); do [ -e "/tmp/.X$n-lock" ] || [ -e "/tmp/.X11-unix/X$n" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
printf '#!/bin/sh\nprintf "\\n  * Thinking (esc to interrupt)\\n"\nwhile :; do sleep 1; done\n' > "$T/bin/claude"; chmod +x "$T/bin/claude"
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'allow_remote_control socket-only\nlisten_on unix:${XDG_RUNTIME_DIR}/mykitty\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
cat > "$T/session" <<S
new_tab agent
launch --title agent $T/bin/claude
new_tab plain
launch --title plain sh
focus_tab 0
S
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  XDG_RUNTIME_DIR=$RUN KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_SOCKET_DIRS=$RUN \
  kitty -o linux_display_server=x11 --class kmx-tabsnap --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 80); do ls "$RUN"/mykitty-* >/dev/null 2>&1 && break; sleep 0.25; done; sleep 1
SOCK=unix:$(ls "$RUN"/mykitty-* 2>/dev/null | head -1)
[ "$SOCK" != "unix:" ] || fail "kitty never opened its control socket"
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))' 2>/dev/null; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
q() { python3 - "$STATE/tabs.json" "$@" <<'P'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("none"); sys.exit()
tabs = [t for w in d.get("windows", []) for t in w.get("tabs", [])]
what = sys.argv[2]
if what == "titles":
    print(" ".join(sorted(t["title"] for t in tabs)))
elif what == "state":
    print(next((t["state"] + ":" + t["brand"] for t in tabs if t["title"] == sys.argv[3]), "-"))
elif what == "palette":
    print(",".join(sorted(d["windows"][0].get("palette", {}))))
elif what == "version":
    print(d.get("version"))
P
}
for _ in $(seq 60); do [ "$(q state agent)" = "working:claude" ] && break; sleep 0.3; done
[ "$(q version)" = 1 ] || fail "tabs.json was not written (version: $(q version))"
[ "$(q titles)" = "agent plain" ] || fail "not every tab is listed (titles: $(q titles))"
[ "$(q state agent)" = "working:claude" ] || fail "the agent tab does not carry its state and brand ($(q state agent))"
[ "$(q state plain)" = ":" ] || fail "a shell tab claims an agent ($(q state plain))"
[ "$(q palette)" = "accent,alert,bg,done,faint,fg,muted,waiting,working" ] || fail "the window has no theme palette ($(q palette))"
[ "$(stat -c %a "$STATE/tabs.json")" = 600 ] || fail "tabs.json is not private"
echo "  ok   every tab is listed, the agent's with its state and brand, the window with its palette"
kitty @ --to "$SOCK" launch --type=tab --tab-title third sh >/dev/null
for _ in $(seq 40); do [ "$(q titles)" = "agent plain third" ] && break; sleep 0.3; done
[ "$(q titles)" = "agent plain third" ] || fail "a new tab did not appear ($(q titles))"
kitty @ --to "$SOCK" close-tab --match title:^plain$ >/dev/null
for _ in $(seq 40); do [ "$(q titles)" = "agent third" ] && break; sleep 0.3; done
[ "$(q titles)" = "agent third" ] || fail "a closed tab did not go ($(q titles))"
echo "  ok   a new tab appears and a closed one goes"
M1=$(stat -c %.9Y "$STATE/tabs.json"); sleep 4
M2=$(stat -c %.9Y "$STATE/tabs.json")
[ "$M1" = "$M2" ] || fail "an unchanged scan rewrote tabs.json"
echo "  ok   nothing changed, nothing written"
[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty (before: $OTHERS_BEFORE after: $(others))"
echo "PASS: a real kitty publishes tabs.json: every tab, agent state and brand, the palette, changes in, nothing when idle; no other kitty touched"
