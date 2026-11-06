#!/usr/bin/env bash
# The whole look at once, for the before/after review: a private kitty under Xvfb with the vertical bar, pane title bars and fake agents
# (working, needs you, finished, idle, a question in a background split), and the pixel Agents panel docked beside it in a SECOND private kitty,
# the way `mux-panel` runs it (KITTYMUX_PANEL=1, watching the first one over its socket). Then the CPU of each process at rest.
#   bash tests/shot_premium.sh dark|light OUT_DIR [PANEL_COLS]      writes OUT_DIR/premium-<theme>.png and prints cpu lines
# CPU is sampled twice for CPU_S seconds (default 20) with no input: while one agent works, and after it finishes (nothing moves).
# Needs Xvfb, xdotool, kitty >= 0.49.2, git, ImageMagick (`import`), python3 with cairo/pango/rsvg; else SKIP. Never touches another kitty.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
THEME=${1:-dark}; OUT=${2:-premium-shots}; PCOLS=${3:-38}; CPU_S=${CPU_S:-20}
for dep in Xvfb xdotool kitty git import python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
python3 -c 'import gi; gi.require_version("PangoCairo", "1.0"); gi.require_version("Rsvg", "2.0"); from gi.repository import PangoCairo, Rsvg; import cairo' 2>/dev/null \
  || { echo "SKIP: cairo/pango/rsvg not installed"; exit 0; }
mkdir -p "$OUT"
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-premium.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock BIN=$T/bin
mkdir -p "$CFG" "$STATE" "$BIN" "$T/data/fonts" && chmod 700 "$STATE"
XPID="" KPID="" PPID_K=""
cleanup() { for p in $PPID_K $KPID $XPID; do kill "$p" 2>/dev/null; done; if [ -n "${KEEP:-}" ]; then echo "kept $T"; else rm -rf "$T"; fi; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; for lg in "$T/k.log" "$T/p.log" "$STATE/sidebar-kit-err.log" "$STATE/tab_bar-error.log"; do [ -s "$lg" ] && { echo "--- $lg"; tail -15 "$lg"; }; done; exit 1; }
cp "$HOME_DIR/assets/kittymux-icons.ttf" "$T/data/fonts/" 2>/dev/null

for n in $(seq 380 409); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1640x920x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for _ in $(seq 40); do [ -S "/tmp/.X11-unix/X${DISP#:}" ] && break; sleep 0.25; done
for f in tab_bar.py window_title_bar.py kittymux_*.py; do ln -s "$HOME_DIR/python/$f" "$CFG/$f"; done

if [ "$THEME" = light ]; then cat > "$CFG/theme.conf" <<'C'
foreground #4c4f69
background #eff1f5
selection_foreground #eff1f5
selection_background #4c4f69
active_border_color #1e66f5
inactive_border_color #bcc0cc
active_tab_foreground #4c4f69
active_tab_background #dce0e8
inactive_tab_foreground #6c6f85
inactive_tab_background #e6e9ef
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
active_tab_foreground #c0caf5
active_tab_background #24283b
inactive_tab_foreground #737aa2
inactive_tab_background #1f2030
color9 #f7768e
color10 #9ece6a
color11 #e0af68
color12 #7aa2f7
C
fi
printf 'font_family JetBrainsMono Nerd Font Mono\nfont_size 11\nwindow_padding_width 8\nconfirm_os_window_close 0\nallow_remote_control socket-only\nremember_window_size no\ninclude %s/theme.conf\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\nwindow_title_bar_min_windows 1\nwindow_title_bar_align left\ngeninclude %s/python/kittymux_layout.py\n' \
  "$CFG" "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"

# synthetic repos (a space is a repo + branch); no names or paths from this machine
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
W=$T/work
mkdir -p "$W/website/src/pages" "$W/core"
git -C "$W/website" init -q -b main && git -C "$W/website" -c commit.gpgsign=false commit -q --allow-empty -m init || fail "git init"
git -C "$W/core" init -q -b release/2.4 && git -C "$W/core" -c commit.gpgsign=false commit -q --allow-empty -m init || fail "git init"

# fake agent CLIs: the script's name is what the scanner recognises; each prints what the real one prints in that state
mk() { printf '#!/bin/sh\n%s\nwhile :; do sleep 1; done\n' "$2" > "$BIN/$1"; chmod +x "$BIN/$1"; }
# devin thinks until the file named in $FIN appears, then shows an idle prompt (finished, while you look elsewhere)
printf '#!/bin/sh\nprintf "  Read last 25 lines in ./a.ts\\n\\n  Thinking · 3m 8s (esc twice to interrupt)\\n"\nwhile [ ! -e "$FIN" ]; do sleep 0.3; done\nprintf "\\033[2J\\033[H  all done\\n❯ \\n"\nwhile :; do sleep 1; done\n' > "$BIN/devin"
chmod +x "$BIN/devin"
mk claude "printf ' Bash command\n   rm -rf node_modules\n Do you want to proceed?\n ❯ 1. Yes\n   2. No\n'"
mk codex  "printf '╭──────────╮\n│ >        │\n╰──────────╯\n  ? for shortcuts\n'"
mk opencode "printf ' Allow this command?\n ❯ 1. Yes\n   2. No\n'"
cat > "$T/session" <<S
new_tab og tags
cd $W/website/src/pages
launch --env FIN=$T/never $BIN/devin
new_tab docs nav
cd $W/website
launch $BIN/claude
new_tab pricing review
cd $W/website
launch $BIN/codex
launch --location=vsplit $BIN/opencode
new_tab migrations
cd $W/core
launch --env FIN=$T/finish $BIN/devin
new_tab shell
cd $W/core
launch sh
focus_tab 2
S

# the tripwire, keyed by socket: a kitty you open or close meanwhile is yours, not this rig's; one that was there before and is
# still there must keep its window count
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && printf '%s=%s\n' "$s" "$(kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))')"; done; }
touched() { python3 - "$OTHERS_BEFORE" "$(others)" <<'PY2'
import sys
a, b = (dict(l.split("=", 1) for l in x.splitlines() if "=" in l) for x in sys.argv[1:3])
bad = [f"{k}: {a[k]} -> {b[k]}" for k in a if k in b and a[k] != b[k]]
print("; ".join(bad))
sys.exit(1 if bad else 0)
PY2
}
OTHERS_BEFORE=$(others)
BASE_ENV=(env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID
          __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_DATA_HOME=$T/data KITTYMUX_SOCKET_DIRS=$T/no-sockets
          KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_PANETITLE_DUMP=1)
"${BASE_ENV[@]}" kitty -o linux_display_server=x11 -o initial_window_width=1240 -o initial_window_height=900 --class kmx-main \
  --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done
[ -S "$T/sock" ] || fail "kitty never opened its control socket"
sleep 2
python3 -c "import sys;sys.path.insert(0,'$HOME_DIR/python');import kittymux_layout as L;L.save('$STATE',$KPID,L.Layout('left','full',22))"
kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1; kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 2

printf 'font_family JetBrainsMono Nerd Font Mono\nfont_size 11\ninclude %s/theme.conf\n' "$CFG" > "$CFG/panel.conf"
# the panel: a second private kitty running the sidebar kitten in panel mode against the first one, with the pixel list on
"${BASE_ENV[@]}" KITTYMUX_PANEL=1 KITTYMUX_TARGET="$SOCK" KITTYMUX_TARGET_PID="$KPID" KITTYMUX_DECKPX=1 \
  kitty -o linux_display_server=x11 -o "initial_window_width=${PCOLS}c" -o initial_window_height=900 -o window_padding_width=0 \
  -o tab_bar_style=hidden -o remember_window_size=no -o confirm_os_window_close=0 --class kmx-deck --config "$CFG/panel.conf" \
  kitty +runpy 'from kittens.runner import main; main()' "$CFG" "$HOME_DIR/python/sidebar-kit.py" >"$T/p.log" 2>&1 & PPID_K=$!
X() { DISPLAY=$DISP xdotool "$@"; }
for _ in $(seq 40); do PW=$(X search --class kmx-deck 2>/dev/null | head -1); [ -n "$PW" ] && break; sleep 0.25; done
MW=$(X search --class kmx-main 2>/dev/null | head -1)
[ -n "${PW:-}" ] && [ -n "$MW" ] || fail "no window (panel=${PW:-} main=$MW)"
read -r PWW < <(X getwindowgeometry --shell "$PW" | sed -n 's/^WIDTH=//p')
X windowmove "$PW" 0 0; X windowmove "$MW" "$PWW" 0
X windowsize "$MW" 1230 890; sleep 0.4; X windowsize "$MW" 1240 900; sleep 0.4
X windowsize "$PW" "$PWW" 890; sleep 0.4; X windowsize "$PW" "$PWW" 900

# wait until the scanner has a verdict for every agent, then let the panel catch up
for _ in $(seq 40); do
  python3 - "$STATE" <<'PY' && break
import glob, json, sys
for p in glob.glob(sys.argv[1] + "/scan-*.json"):
    states = {v.get("state") for v in json.load(open(p)).values()}
    sys.exit(0 if {"working", "waiting", "idle"} <= states else 1)
sys.exit(1)
PY
  sleep 0.5
done
touch "$T/finish"                                       # the core migration finishes while you look at another tab: done
sleep 6
DISPLAY=$DISP import -window root -crop "$((PWW + 1240))x900+0+0" +repage "$OUT/premium-$THEME.png" 2>/dev/null || fail "could not capture"
echo "wrote $OUT/premium-$THEME.png"
# the pixel list must really have drawn: a traceback or a fallback note means the shot shows the cell list instead
if grep -q "Traceback" "$STATE/sidebar-kit-err.log" 2>/dev/null; then fail "the panel raised (the shot shows the cell fallback)"; fi
if [ "${KMX_EXPECT_CELLS:-}" != 1 ] && grep -q "deckpx:" "$STATE/sidebar-kit-err.log" 2>/dev/null; then fail "the pixel list fell back: $(grep "deckpx:" "$STATE/sidebar-kit-err.log" | tail -1)"; fi

# the pixel panel lists every tab, so the bar it repeats is hidden while it runs (kittymux_layout.cover)
cols() { kitty @ --to "$SOCK" ls 2>/dev/null | python3 -c 'import sys,json;print(max(w["columns"] for o in json.load(sys.stdin) for t in o["tabs"] if t["is_active"] for w in t["windows"]))'; }
if [ "${KMX_EXPECT_CELLS:-}" != 1 ]; then
  [ "$(cat "$STATE/bar-covered-$KPID" 2>/dev/null)" -gt 0 ] 2>/dev/null || fail "the pixel panel did not cover the bar (no bar-covered-$KPID)"
  COVERED_COLS=$(cols)
fi
# CPU at rest: no input at all; first with one agent working, then after it finishes too
HZ=$(getconf CLK_TCK)
ticks() { local s=0 p; for p in "$@"; do [ -r "/proc/$p/stat" ] && s=$((s + $(awk '{print $14+$15}' "/proc/$p/stat"))); done; echo $s; }
kids() { pgrep -P "$1" 2>/dev/null | tr '\n' ' '; }
cpu() {   # cpu LABEL
  local kten; kten=$(kids "$PPID_K")
  local a0 b0 c0 a1 b1 c1
  a0=$(ticks "$KPID"); b0=$(ticks "$PPID_K"); c0=$(ticks $kten); sleep "$CPU_S"
  a1=$(ticks "$KPID"); b1=$(ticks "$PPID_K"); c1=$(ticks $kten)
  printf 'cpu %-8s main kitty %5.2f%%   panel kitty %5.2f%%   panel kitten %5.2f%%   (%ss)\n' "$1" \
    "$(echo "scale=2; ($a1 - $a0) * 100 / ($HZ * $CPU_S)" | bc)" "$(echo "scale=2; ($b1 - $b0) * 100 / ($HZ * $CPU_S)" | bc)" \
    "$(echo "scale=2; ($c1 - $c0) * 100 / ($HZ * $CPU_S)" | bc)" "$CPU_S"
}
cpu working
touch "$T/never"; sleep 4
cpu rest
if [ "${KMX_EXPECT_CELLS:-}" != 1 ]; then
  # a killed panel cannot give the bar back itself: the scanner in the watched kitty sweeps its cover (every AGE_REFRESH = 20 s)
  for k in $(kids "$PPID_K"); do kill -9 "$k" 2>/dev/null; done          # SIGKILL: the kitten runs no cleanup, as after a crash
  kill "$PPID_K" 2>/dev/null; wait "$PPID_K" 2>/dev/null; PPID_K=
  for _ in $(seq 60); do [ -e "$STATE/bar-covered-$KPID" ] || break; sleep 0.5; done
  [ -e "$STATE/bar-covered-$KPID" ] && fail "a killed panel's cover was never swept"
  sleep 1.5; BACK_COLS=$(cols)
  [ "$BACK_COLS" -lt $((COVERED_COLS - 10)) ] || fail "the bar did not come back after the panel died (pane $COVERED_COLS -> $BACK_COLS columns)"
  echo "  ok   the bar hides under the pixel panel and comes back when it dies (pane $COVERED_COLS -> $BACK_COLS columns)"
fi
diff=$(touched) || fail "this rig changed the windows of ANOTHER kitty ($diff)"
echo "PASS: premium scene captured; no other kitty touched"
