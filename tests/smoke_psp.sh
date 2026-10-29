#!/usr/bin/env bash
# OSC 7501 through bin/mux-pty in a real kitty: a private kitty on a virtual display (its own socket, nothing else
# touched) runs a fake agent that reports `blocked` behind the relay, and the same agent WITHOUT it (the control:
# kitty drops OSC 7501, so that window must have no status). Checks kitty's own `ls`: the relayed window carries the
# `kittymux_psp` user variable with the report, the control does not.
#   bash tests/smoke_psp.sh            (needs Xvfb and kitty; else SKIP)
set -u
HOME_DIR=$(cd "$(dirname "$0")/.." && pwd)
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-psp.XXXXXX"); SOCK=unix:$T/sock
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
for n in $(seq 350 379); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1000x700x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
MSG=$(printf 'Run the tests?' | base64 | tr -d '=')
cat > "$T/agent" <<A
#!/bin/sh
printf '\033]7501;state=blocked:kind=question:app=claude:msg=$MSG\033\\\\'
exec sleep 600
A
chmod +x "$T/agent"
cat > "$T/session" <<S
new_tab relayed
launch --title relayed $HOME_DIR/bin/mux-pty -- $T/agent
new_tab control
launch --title control $T/agent
S
printf 'allow_remote_control socket-only\nconfirm_os_window_close 0\n' > "$T/kitty.conf"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  kitty --config "$T/kitty.conf" -o linux_display_server=x11 --class kmx-psp --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 120); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 2
kitty @ --to "$SOCK" ls > "$T/ls.json" 2>/dev/null || { echo "FAIL: kitty @ ls"; exit 1; }
python3 - "$T/ls.json" <<'P'
import json, sys
wins = {w["title"]: w for o in json.load(open(sys.argv[1])) for t in o["tabs"] for w in t["windows"]}
relayed = wins["relayed"]["user_vars"].get("kittymux_psp", "")
control = wins["control"]["user_vars"].get("kittymux_psp", "")
ok = '"state":"blocked"' in relayed and "Run the tests?" in relayed and control == ""
print(("PASS" if ok else "FAIL") + f": relayed={relayed!r} control={control!r}")
sys.exit(0 if ok else 1)
P
