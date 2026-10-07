#!/usr/bin/env bash
# Draw cost of the vertical bar. A private kitty with N tabs (default 23, every one in the git checkout $1) and one fake working agent (its spinner
# redraws the whole bar ~10x/s) runs the tab_bar.py of that tree with KITTYMUX_PROFILE=1 for ~20 s; prints the profile lines and their mean.
# Compare two trees:   bash tests/profile_bar.sh /path/to/main    then    bash tests/profile_bar.sh .
# Needs Xvfb, xdotool, kitty; else SKIP. Touches only its own kitty.
set -u
TREE=$(cd "${1:-$(dirname "${BASH_SOURCE[0]}")/..}" && pwd); N=${N:-23}
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-prof.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
for n in $(seq 290 319); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in "$TREE"/python/tab_bar.py "$TREE"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'window_padding_width 10\nconfirm_os_window_close 0\nallow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$TREE" "$TREE" "$TREE" > "$CFG/kitty.conf"
{ echo "new_tab agent"; echo "cd $TREE"
  echo "launch bash -c 'printf \"· Pondering… (12s · ↓ 1.2k tokens)\\n\"; exec -a claude sleep 86400'"
  for i in $(seq 2 "$N"); do echo "new_tab t$i"; echo "cd $TREE"; echo "launch sh"; done
  echo "focus_tab 0"; } > "$T/session"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_PROFILE=1 \
  kitty -o linux_display_server=x11 --class kmx-prof --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --class kmx-prof | head -1)
X windowsize "$W" 1390 890; sleep 0.4; X windowsize "$W" 1400 900; sleep 1.2
python3 -c "import sys;sys.path.insert(0,'$TREE/python');import kittymux_layout as L;L.save('$STATE',$KPID,L.Layout('left','full',22))"
kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1; kitty @ --to "$SOCK" load-config >/dev/null 2>&1
sleep 20
LOG=$STATE/tab_bar-profile.log
[ -s "$LOG" ] || { echo "no profile lines were written (tree: $TREE) — is the bar drawing?"; tail -5 "$STATE/tab_bar-error.log" 2>/dev/null; exit 1; }
echo "tree: $TREE   tabs: $N"
tail -6 "$LOG"
python3 - "$LOG" <<'PY'
import re, sys
rows = [l for l in open(sys.argv[1]) if "avg_ms=" in l][-6:]
avg = [float(re.search(r"avg_ms=([\d.]+)", l).group(1)) for l in rows]
mx = [float(re.search(r"max_ms=([\d.]+)", l).group(1)) for l in rows]
print("MEAN avg_ms=%.3f  worst max_ms=%.3f  (%d samples)" % (sum(avg) / len(avg), max(mx), len(avg)))
PY
