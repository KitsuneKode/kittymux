#!/usr/bin/env bash
# Pixel Usage/Inbox and optional pane docks, synthetic data and a private Xvfb Kitty only.
# KMX_PANELPX_CONTROL=1 disables graphics and must FAIL. THEME=light COLS=26 OUT=/tmp/shots bash tests/smoke_panelpx.sh
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null || { echo "SKIP: $dep missing"; exit 0; }; done
python3 -c 'import cairo, gi; gi.require_version("Pango", "1.0"); gi.require_version("Rsvg", "2.0")' 2>/dev/null || { echo 'SKIP: cairo/Pango/rsvg missing'; exit 0; }
RUN=$(mktemp -d /tmp/kmx-panelpx.XXXXXX)
OUT=${OUT:-$RUN/shots}; THEME=${THEME:-dark}; COLS=${COLS:-38}; LINES_N=36
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/nonexistent}; XPID='' KPID='' SOCK=''
mkdir -p "$OUT" "$RUN/cfg" "$RUN/home"
others() {
    for s in /tmp/mykitty-* "$REAL_RUNTIME"/mykitty-*; do
        [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] || continue
        kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import json,sys;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'
    done | tr '\n' ' '
}
BEFORE=$(others)
cleanup() {
    rc=$?
    after=$(others)
    if [ "$after" != "$BEFORE" ]; then echo 'FAIL: another Kitty window count changed'; rc=1; fi
    [ -z "$KPID" ] || kill "$KPID" 2>/dev/null || true
    [ -z "$XPID" ] || kill "$XPID" 2>/dev/null || true
    if [ "${KEEP:-0}" = 1 ]; then echo "kept $RUN"; else rm -rf "$RUN"; fi
    exit "$rc"
}
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ ! -s "$RUN/kitty.log" ] || tail -12 "$RUN/kitty.log"; exit 1; }
DISP=${KMX_TEST_DISPLAY:-}
if [ -z "$DISP" ]; then for n in $(seq 620 649); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done; fi
[[ "$DISP" =~ ^:[0-9]+$ ]] && [ ! -e "/tmp/.X${DISP#:}-lock" ] || fail 'private display unavailable'
Xvfb "$DISP" -screen 0 1200x1300x24 >"$RUN/x.log" 2>&1 & XPID=$!
sleep 1
kill -0 "$XPID" 2>/dev/null || fail 'private Xvfb did not start'
python3 "$ROOT/tools/demo_world.py" "$RUN/world" >/dev/null
STATE=$RUN/world/state
SOCK=unix:$RUN/sock
export KITTYMUX_SOCKET_DIRS=$RUN
export PYTHONDONTWRITEBYTECODE=1
python3 - "$RUN/cfg/kitty.conf" "$THEME" "$COLS" "$LINES_N" <<'PY'
import sys
from pathlib import Path
path,theme,cols,rows=sys.argv[1:]
colors=('background #eff1f5\nforeground #4c4f69\ncolor9 #d20f39\ncolor10 #40a02b\ncolor11 #df8e1d\ncolor12 #1e66f5\n' if theme=='light' else 'background #1a1b26\nforeground #c0caf5\ncolor9 #f7768e\ncolor10 #9ece6a\ncolor11 #e0af68\ncolor12 #7aa2f7\n')
Path(path).write_text(f'allow_remote_control socket-only\nconfirm_os_window_close 0\nfont_family JetBrainsMono Nerd Font Mono\nfont_size 11\nwindow_padding_width 0\ntab_bar_style hidden\nremember_window_size no\ninitial_window_width {cols}c\ninitial_window_height {rows}c\n'+colors)
PY
python3 - "$STATE" "$ROOT" <<'PY'
import json,sys,time
from pathlib import Path
state,root=Path(sys.argv[1]),sys.argv[2]
sys.path.insert(0,root+'/python')
import kittymux_inbox as I
I.add(str(state),I.make_event('error','codex',1,'agent',time.time(),pid=42,tab='calm-otter',title='Build failed',body='Compiler missing. Install the compiler, then rerun the build.'))
now=time.time()*1000
cache=state.parent/'rice'/'usage-t3.json';cache.parent.mkdir()
cache.write_text(json.dumps({'cachedAt':now,'providers':[{'driver':'codex','accounts':[{'name':label,'checkedAt':now,'windows':[{'id':'session','label':'5 hour','used':used,'resetsAt':now+9000000,'durationMins':300},{'id':'week','label':'Weekly','used':45,'resetsAt':now+172800000,'durationMins':10080}]} for label,used in [('Personal',30),('Work',100)]]}]}))
PY
env -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID \
    DISPLAY="$DISP" HOME="$RUN/home" ZDOTDIR="$RUN/home" XDG_RUNTIME_DIR="$RUN" KITTY_CONFIG_DIRECTORY="$RUN/cfg" \
    KITTYMUX_STATE="$STATE" KITTYMUX_USAGE_HOME="$RUN/world/home" KITTYMUX_USAGE_LIVE=0 KITTYMUX_NOTIFY=0 KITTYMUX_AUTOSAVE=0 KITTYMUX_DECKPX="$((1 - ${KMX_PANELPX_CONTROL:-0}))" \
    __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 \
    kitty -o linux_display_server=x11 --class kmx-panelpx --listen-on "$SOCK" sh >"$RUN/kitty.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ ! -S "$RUN/sock" ] || break; sleep .2; done
[ -S "$RUN/sock" ] || fail 'private Kitty did not start'
kitty @ --to "$SOCK" kitten --match id:1 "$ROOT/python/sidebar-kit.py"
sleep 2
X() { DISPLAY="$DISP" xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-panelpx | head -1)
[ -n "$W" ] || fail 'private window missing'
X windowfocus "$W"
GEOMETRY=$(X getwindowgeometry --shell "$W")
WIN_H=$(printf '%s\n' "$GEOMETRY" | sed -n 's/^HEIGHT=//p')
key() { X key --clearmodifiers "$@"; sleep .7; }
click() { X mousemove --window "$W" "$1" "$2" click 1; sleep .7; }
screen() { kitty @ --to "$SOCK" get-text; }
shot() { kitty @ --to "$SOCK" screenshot "$OUT/$1.png"; }
unread() { PYTHONPATH="$ROOT/python" python3 - "$STATE" <<'PY'
import sys,kittymux_inbox as I
print(sum(e.get('status')=='unread' for e in I.load(sys.argv[1])))
PY
}
key u; sleep 1
screen | grep -q 'Usage' || fail 'usage tab missing'
if [ -n "$(screen | tail -n +2 | tr -d '[:space:]')" ]; then fail 'pixel Usage fell back to cells (control must fail here)'; fi
shot usage
key d; shot usage-details
cmp -s "$OUT/usage.png" "$OUT/usage-details.png" && fail 'details did not change the graphical view'
key question
screen | grep -q 'Usage keys' || fail 'pixel help key did not open help'
key Escape
key i; sleep 1
shot inbox
BEFORE_UNREAD=$(unread)
click 40 180; shot inbox-expanded
[ "$(unread)" = "$BEFORE_UNREAD" ] || fail 'expanding acknowledged an event'
cmp -s "$OUT/inbox.png" "$OUT/inbox-expanded.png" && fail 'inbox expansion did not draw'
click 160 "$((WIN_H - 16))"; sleep 1.5
[ "$(unread)" = "$((BEFORE_UNREAD - 1))" ] || fail 'dismiss did not target the selected event'
key z; sleep 1.5
[ "$(unread)" = "$BEFORE_UNREAD" ] || fail 'undo did not restore the event'
key Page_Down; shot inbox-scroll
key q
sleep .5
if kitty --version | grep -q '0\.50\.'; then
    KMX() { env -u KITTY_WINDOW_ID -u KITTY_PID -u KITTY_LISTEN_ON KITTYMUX_TARGET="$SOCK" KITTYMUX_STATE="$STATE" python3 "$ROOT/bin/kittymux" pane-controls "$@" --window 1; }
    KMX show
    KMX show
    docks() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(sum("kittymux_pane_controls" in w.get("user_vars",{}) for o in json.load(sys.stdin) for t in o["tabs"] for w in t["windows"]))'; }
    kitty @ --to "$SOCK" ls > "$RUN/docks.json"
    shot pane-controls
    [ "$(docks)" = 1 ] || fail 'pane controls duplicated or failed to open'
    DOCK_ID=$(python3 - "$RUN/docks.json" <<'PY'
import json,sys
print(next(w['id'] for o in json.load(open(sys.argv[1])) for t in o['tabs'] for w in t['windows'] if 'kittymux_pane_controls' in w.get('user_vars',{})))
PY
)
    kitty @ --to "$SOCK" get-text --match "id:$DOCK_ID" | grep -qE 'R (Right|Split)' || fail 'pane controls UI failed to initialize'
    sleep 1; shot pane-controls
    windows() { kitty @ --to "$SOCK" ls | python3 -c 'import json,sys;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; }
    BEFORE_SPLIT=$(windows)
    click 30 30
    [ "$(windows)" = "$((BEFORE_SPLIT + 1))" ] || fail 'pane dock pointer split failed'
    KMX hide
    [ "$(docks)" = 0 ] || fail 'pane controls did not close'
fi
[ ! -s "$STATE/sidebar-kit-err.log" ] || { cat "$STATE/sidebar-kit-err.log"; fail 'panel logged a runtime error'; }
echo "PASS: pixel Usage/Inbox, expansion, dismissal/undo and pane dock; images in $OUT"
