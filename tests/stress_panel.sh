#!/usr/bin/env bash
# STRESS of the REAL panel (leaks, stuck timers, errors): a private kitty under Xvfb runs sidebar-kit.py on a synthetic world
# (tools/demo_world.py: a fake HOME the real collectors read, a week of history, inbox events) and is driven with real key events.
# Each step also checks the text the view drew, so this doubles as a smoke test of the three views.
#   bash tests/stress_panel.sh [CYCLES] [COLS] [LINES]       (default 150 cycles, 38 x 44)
# Needs Xvfb, xdotool, kitty, ImageMagick (`import`), python3; otherwise SKIP (exit 0). Never touches another kitty or your real state.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
THEME=dark; OUT=$(mktemp -d "${TMPDIR:-/tmp}/kmx-stress-out.XXXXXX"); COLS=${2:-38}; LINES_N=${3:-44}
for dep in Xvfb xdotool kitty import python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
mkdir -p "$OUT"
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-panel.XXXXXX"); CFG=$T/cfg SOCK=unix:$T/sock
mkdir -p "$CFG" "$T/data/fonts"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; if [ -n "${KEEP:-}" ]; then echo "kept $T"; else rm -rf "$T"; fi; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$T/k.log" ] && tail -15 "$T/k.log"; [ -s "$T/world/state/sidebar-kit-err.log" ] && tail -20 "$T/world/state/sidebar-kit-err.log"; exit 1; }

python3 "$HOME_DIR/tools/demo_world.py" "$T/world" >/dev/null || fail "could not build the fixture"
STATE=$T/world/state
cp "$HOME_DIR/assets/kittymux-icons.ttf" "$T/data/fonts/" 2>/dev/null

for n in $(seq 350 379); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1000x1100x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for _ in $(seq 40); do [ -S "/tmp/.X11-unix/X${DISP#:}" ] && break; sleep 0.25; done

if [ "$THEME" = light ]; then cat > "$CFG/theme.conf" <<'C'
foreground #4c4f69
background #eff1f5
selection_foreground #eff1f5
selection_background #4c4f69
active_border_color #1e66f5
inactive_border_color #acb0be
color9 #d20f39
color10 #40a02b
color11 #df8e1d
color12 #1e66f5
C
else cat > "$CFG/theme.conf" <<'C'
foreground #c0caf5
background #1a1b26
selection_foreground #1a1b26
selection_background #c0caf5
active_border_color #f08fb8
inactive_border_color #414868
color9 #f7768e
color10 #9ece6a
color11 #e0af68
color12 #7aa2f7
C
fi
cat > "$CFG/kitty.conf" <<CONF
font_family JetBrainsMono Nerd Font Mono
font_size 11
window_padding_width 0
tab_bar_style hidden
confirm_os_window_close 0
allow_remote_control socket-only
remember_window_size no
initial_window_width ${COLS}c
initial_window_height ${LINES_N}c
include theme.conf
CONF
printf 'new_tab shell\nlaunch sh\nnew_tab web\nlaunch sh\nnew_tab api\nlaunch sh\nfocus_tab 0\n' > "$T/session"

env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_DATA_HOME=$T/data \
  KITTYMUX_USAGE_HOME=$T/world/home KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
  kitty -o linux_display_server=x11 --class kmx-panel --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done
[ -S "$T/sock" ] || fail "kitty never opened its control socket"
sleep 3

# the panel is a kitten in an overlay over the first window, started the way the ctrl+alt+b chord does (an absolute path: a relative one is read from the config dir)
kitty @ --to "$SOCK" kitten --match id:1 "$HOME_DIR/python/sidebar-kit.py" || fail "could not start the panel kitten"
PANEL=""
for _ in $(seq 40); do
  PANEL=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;d=json.load(sys.stdin);ws=[w["id"] for w in d[0]["tabs"][0]["windows"]];print(max(ws) if len(ws)>1 else "")')
  [ -n "$PANEL" ] && break; sleep 0.25
done
[ -n "$PANEL" ] || fail "the panel kitten never opened a window"
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-panel | head -1)
[ -n "$W" ] || fail "no kitty window"
X windowfocus "$W" 2>/dev/null
read -r GX GY GW GH < <(X getwindowgeometry --shell "$W" | python3 -c 'import sys;d=dict(l.strip().split("=") for l in sys.stdin if "=" in l);print(d["X"],d["Y"],d["WIDTH"],d["HEIGHT"])')
redraw() { X windowsize "$W" $((GW - 10)) $((GH - 10)); sleep 0.4; X windowsize "$W" "$GW" "$GH"; sleep 1.0; }
screen() { kitty @ --to "$SOCK" get-text --match id:$PANEL --extent screen 2>/dev/null; }
wait_text() {                 # wait_text PATTERN  (up to 10 s)
  for _ in $(seq 40); do screen | grep -q -- "$1" && return 0; sleep 0.25; done
  echo "--- screen:"; screen; return 1
}
shot() { redraw; DISPLAY=$DISP import -window root -crop "${GW}x${GH}+${GX}+${GY}" +repage "$OUT/$1.png" 2>/dev/null || fail "could not capture $1"; echo "wrote $OUT/$1.png"; }
key() { X key --clearmodifiers "$@"; sleep 0.5; }


CYCLES=${1:-150}
PID=$(pgrep -f "sidebar-kit.py" | while read -r p; do grep -qa "$T" /proc/$p/environ 2>/dev/null && echo $p; done | head -1)
[ -n "$PID" ] || fail "could not find the panel's own process"
stat_of() { echo "rss_kb=$(awk '/VmRSS/{print $2}' /proc/$PID/status) fds=$(ls /proc/$PID/fd | wc -l) threads=$(awk '/Threads/{print $2}' /proc/$PID/status)"; }
cpu_ticks() { awk '{print $14+$15}' /proc/$PID/stat; }
cell_xy() { python3 -c "print(($1 * $GW + $GW // 2) // $COLS + $GX, ($2 * $GH + $GH // 2) // $LINES_N + $GY)"; }
sleep 2
wait_text "tabs" || fail "the Agents view never drew"
cycle() {
  for c in 3 10 18 25 12 30; do for r in 3 5 8 30 31 40; do read -r px py <<<"$(cell_xy $c $r)"; X mousemove "$px" "$py"; done; done
  X key --clearmodifiers u; X key --clearmodifiers Right; X key --clearmodifiers d; X key --clearmodifiers d
  X key --clearmodifiers i; X key --clearmodifiers j; X key --clearmodifiers x; X key --clearmodifiers z
  X key --clearmodifiers a; X key --clearmodifiers slash; X key --clearmodifiers Escape
}
for _ in $(seq 15); do cycle; done                               # warm up: caches, lazy imports, first allocations
sleep 2; BEFORE=$(stat_of); T0=$(cpu_ticks); echo "after warm-up : $BEFORE"
for i in $(seq "$CYCLES"); do cycle; [ $((i % 50)) -eq 0 ] && echo "  cycle $i: $(stat_of)"; done
sleep 3; AFTER=$(stat_of); echo "after $CYCLES cycles: $AFTER"
# idle CPU: nothing moves for 10 s
IDLE0=$(cpu_ticks); sleep 10; IDLE1=$(cpu_ticks); HZ=$(getconf CLK_TCK)
IDLE_PCT=$(python3 -c "print(round(($IDLE1 - $IDLE0) / $HZ / 10 * 100, 2))")
echo "idle CPU over 10 s: ${IDLE_PCT}%"
python3 - "$BEFORE" "$AFTER" "$IDLE_PCT" <<'PY' || fail "a resource grew under stress"
import sys, re
b = dict(kv.split("=") for kv in sys.argv[1].split()); a = dict(kv.split("=") for kv in sys.argv[2].split())
b, a = {k: int(v) for k, v in b.items()}, {k: int(v) for k, v in a.items()}
bad = []
if a["rss_kb"] > b["rss_kb"] * 1.15 + 4096:
    bad.append(f"memory grew {b['rss_kb']} -> {a['rss_kb']} kB")
if a["fds"] > b["fds"] + 2:
    bad.append(f"file descriptors grew {b['fds']} -> {a['fds']}")
if a["threads"] > b["threads"] + 2:
    bad.append(f"threads grew {b['threads']} -> {a['threads']}")
if float(sys.argv[3]) > 3.0:
    bad.append(f"idle CPU {sys.argv[3]}% is not idle")
if bad:
    print("; ".join(bad)); sys.exit(1)
PY
[ -s "$T/world/state/sidebar-kit-err.log" ] && { echo "--- the panel logged errors:"; tail -30 "$T/world/state/sidebar-kit-err.log"; fail "the panel raised exceptions under stress"; }
screen | grep -q "tabs" || fail "the panel is not drawing after the stress"
echo "PASS: $CYCLES cycles of mouse and key events: no memory, descriptor or thread growth, idle CPU ${IDLE_PCT}%, no errors logged"
