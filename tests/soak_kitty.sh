#!/usr/bin/env bash
# A soak of everything kittymux runs inside kitty: windows come and go (agents that work, ask, hit a limit, plain shells with a password prompt), the config is
# reloaded now and then, and the process is measured the whole time: resident memory, open file descriptors, threads, zombie children. The scanner lives as long as
# kitty does, so anything it keeps per window or per tick must stop growing. Not part of CI (minutes); run it after changing kittymux_scan, kittymux_barsize or tab_bar.
#   bash tests/soak_kitty.sh [CYCLES]      (default 40 cycles of 6 windows, ~4 minutes)    Needs Xvfb, kitty; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CYCLES=${1:-40}
ulimit -c 0
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-soak.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -f "$T/k.log" ] && tail -5 "$T/k.log"; exit 1; }
for n in $(seq 550 579); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'allow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
printf 'new_tab base\nlaunch sh\n' > "$T/session"
# the little programs the windows run: an agent that works, one that asks, one at its limit (argv[0] makes the scanner see an agent), a password prompt
printf '%s\n' 'printf "· Pondering… (12s · ↓ 1k tokens · esc to interrupt)\n"; exec -a claude sleep 4' > "$T/work.sh"
printf '%s\n' 'printf " Do you want to proceed?\n ❯ 1. Yes\n   2. No\n"; exec -a claude sleep 4' > "$T/ask.sh"
printf '%s\n' 'printf "You have hit your usage limit. Try again at 9:21 PM.\n"; exec -a codex sleep 4' > "$T/limit.sh"
printf '%s\n' 'printf "[sudo] password for someone: "; sleep 4' > "$T/pw.sh"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_LEGACY_SOCKET_DIR=$T \
  kitty -o linux_display_server=x11 --class kmx-soak --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 4
kill -0 "$KPID" 2>/dev/null || fail "kitty did not start"

rss() { awk '/^VmRSS/ {print $2}' /proc/$KPID/status; }
fds() { ls /proc/$KPID/fd 2>/dev/null | wc -l; }
thr() { awk '/^Threads/ {print $2}' /proc/$KPID/status; }
zom() { ps --ppid "$KPID" -o stat= 2>/dev/null | grep -c '^Z'; }
sample() { echo "$(rss) $(fds) $(thr) $(zom)"; }

# warm up: one full cycle first, so one-time costs (imports, caches, fonts) are not counted as growth
cycle() {
  for prog in work ask limit pw; do
    kitty @ --to "$SOCK" launch --type=tab --tab-title "$prog" bash "$T/$prog.sh" >/dev/null 2>&1
  done
  kitty @ --to "$SOCK" launch --type=window --keep-focus sh -c 'sleep 3' >/dev/null 2>&1
  sleep 3
  if [ $(( $1 % 7 )) = 0 ]; then kitty @ --to "$SOCK" load-config >/dev/null 2>&1; fi
  sleep 3
  # close every tab but the base
  kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if t["title"] != "base": print(t["id"])' | while read -r id; do kitty @ --to "$SOCK" close-tab --match "id:$id" >/dev/null 2>&1; done
  sleep 1
}
cycle 0; cycle 1
read -r R0 F0 T0 Z0 <<<"$(sample)"
echo "  start: rss=${R0}kB fds=$F0 threads=$T0 zombies=$Z0"
for i in $(seq 2 $((CYCLES + 1))); do
  kill -0 "$KPID" 2>/dev/null || fail "kitty DIED during cycle $i"
  cycle "$i"
  [ $(( i % 10 )) = 0 ] && echo "  cycle $i: $(sample)   (rss fds threads zombies)"
done
read -r R1 F1 T1 Z1 <<<"$(sample)"
echo "  end:   rss=${R1}kB fds=$F1 threads=$T1 zombies=$Z1"
[ "$F1" -le $((F0 + 6)) ] || fail "open file descriptors grew from $F0 to $F1: something is not closed"
[ "$T1" -le $((T0 + 2)) ] || fail "threads grew from $T0 to $T1"
[ "$Z1" -le 2 ] || fail "$Z1 zombie children: a Popen is never waited for"
growth=$(( (R1 - R0) / 1024 ))
[ "$growth" -le 60 ] || fail "resident memory grew by ${growth} MB over $CYCLES cycles"
age=$(python3 -c 'import os,sys,time;print(int(time.time()-os.stat(sys.argv[1]).st_mtime))' "$STATE/scan-$KPID.json" 2>/dev/null || echo 999)
[ "$age" -le 6 ] || fail "the scanner stopped publishing ($age s old)"
[ -s "$STATE/tab_bar-error.log" ] && fail "the tab bar logged errors: $(tail -3 "$STATE/tab_bar-error.log")"
bytes=$(du -sb "$STATE" 2>/dev/null | cut -f1)
[ "${bytes:-0}" -le $((2 * 1024 * 1024)) ] || fail "the state directory grew to ${bytes} bytes: something logs or caches without a cap ($(ls -S "$STATE" | head -3 | tr '\n' ' '))"
echo "PASS: $CYCLES cycles of windows opening, asking, hitting limits, prompting and closing: fds, threads, zombies and memory stayed flat (memory change ${growth} MB, state dir ${bytes} bytes)"
