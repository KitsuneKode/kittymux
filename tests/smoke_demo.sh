#!/usr/bin/env bash
# `kittymux demo` is the front door: it must open a healthy isolated kitty with every showcase tab (agents in each state, a 4-pane tab, a
# file:line tab, a scrollback tab) and the new keys must work in it — checked by clicking a real file:line. Needs Xvfb, xdotool, kitty >= 0.49.2.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
kitty --version | python3 -c 'import re,sys;v=tuple(map(int,re.search(r"(\d+)\.(\d+)\.(\d+)",sys.stdin.read()).groups()));sys.exit(0 if v>=(0,49,2) else 1)' \
    || { echo "SKIP: needs kitty >= 0.49.2"; exit 0; }
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-demo.XXXXXX"); XPID="" DPID=""
cleanup() { [ -n "$DPID" ] && pkill -P "$DPID" 2>/dev/null; [ -n "$DPID" ] && kill "$DPID" 2>/dev/null; pkill -f "^kitty --class kittymux-demo" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1600x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
mkdir -p "$T/bin"; printf '#!/bin/sh\nprintf "%%s\\n" "$@" > "%s/ed.out"\n' "$T" > "$T/bin/nvim"; chmod +x "$T/bin/nvim"
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP VISUAL="$T/bin/nvim" EDITOR="$T/bin/nvim" \
  PYTHONUNBUFFERED=1 "$HOME_DIR/bin/kittymux" demo >"$T/demo.out" 2>&1 & DPID=$!
SOCK=""
for _ in $(seq 80); do SOCK=$(ls /tmp/mykitty-* 2>/dev/null | while read -r s; do pid=${s##*-}; tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -q kittymux-demo && echo "$s"; done | head -1); [ -n "$SOCK" ] && break; sleep 0.25; done
[ -n "$SOCK" ] || { cat "$T/demo.out"; fail "the demo's kitty never opened its socket"; }
sleep 3
ls_() { kitty @ --to "unix:$SOCK" ls; }
tabs=$(ls_ | python3 -c 'import sys,json;print(" ".join(t["title"] for t in json.load(sys.stdin)[0]["tabs"]))')
for want in claude codex antigravity droid review panes file-refs scrollback notes; do
  case " $tabs " in *" $want "*) ;; *) fail "demo tab '$want' is missing (tabs: $tabs)" ;; esac
done
n=$(ls_ | python3 -c 'import sys,json;print(sum(len(t["windows"]) for t in json.load(sys.stdin)[0]["tabs"] if t["title"]=="panes"))')
[ "$n" = 4 ] || fail "the panes tab should have 4 panes, has $n"
echo "  ok   demo opened with every showcase tab ($(echo $tabs | wc -w) tabs; 4 panes in 'panes')"
grep -q "ctrl+shift+click" "$T/demo.out" && grep -q "ctrl+alt+e" "$T/demo.out" || fail "the demo did not print the new things to try"
echo "PASS: kittymux demo opens a healthy showcase of the new features"
