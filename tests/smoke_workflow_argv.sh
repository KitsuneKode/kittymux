#!/usr/bin/env bash
# Private native argv, scratch placement and stale-identity regression checks.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for d in kitty Xvfb python3; do command -v "$d" >/dev/null || { echo "SKIP: $d missing"; exit 0; }; done
ORIGINAL_RUNTIME=${XDG_RUNTIME_DIR:-/nonexistent}
others() { for socket in /tmp/mykitty-* "$ORIGINAL_RUNTIME"/mykitty-*; do if [ -S "$socket" ] && [ -O "$socket" ]; then kitty @ --to "unix:$socket" ls 2>/dev/null | python3 -c 'import sys,json; print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; fi; done; }
BEFORE=$(others)
RUN=$(mktemp -d /tmp/kmx-exit.XXXXXX); KP= XP=
trap '[ -z "$KP" ] || kill "$KP" 2>/dev/null || true; [ -z "$XP" ] || kill "$XP" 2>/dev/null || true; rm -rf "$RUN"' EXIT
mkdir -p "$RUN/cfg" "$RUN/state" "$RUN/home" "$RUN/runtime"
export XDG_RUNTIME_DIR="$RUN/runtime"
for n in $(seq 480 509); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1000x700x24 >/dev/null 2>&1 & XP=$!; sleep 1
for f in "$ROOT"/python/tab_bar.py "$ROOT"/python/kittymux_*.py; do ln -s "$f" "$RUN/cfg/$(basename "$f")"; done
printf 'allow_remote_control socket-only\nconfirm_os_window_close 0\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' "$ROOT" "$ROOT" "$ROOT" > "$RUN/cfg/kitty.conf"
env -u WAYLAND_DISPLAY -u KITTY_PID -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTYMUX_TARGET HOME="$RUN/home" KITTY_CONFIG_DIRECTORY="$RUN/cfg" KITTYMUX_STATE="$RUN/state" KITTYMUX_SOCKET_DIRS="$RUN" KITTYMUX_NOTIFY=0 KITTYMUX_DEBUG=1 DISPLAY="$DISP" LIBGL_ALWAYS_SOFTWARE=1 __GLX_VENDOR_LIBRARY_NAME=mesa kitty -o linux_display_server=x11 --listen-on "unix:$RUN/sock" sh > "$RUN/log" 2>&1 & KP=$!
RC() { kitty @ --to "unix:$RUN/sock" "$@"; }
for _ in $(seq 60); do [ ! -S "$RUN/sock" ] || break; sleep .2; done
sleep 1
WORKFLOW() { env -u KITTY_PID -u KITTY_LISTEN_ON KITTYMUX_TARGET="unix:$RUN/sock" KITTYMUX_STATE="$RUN/state" KITTYMUX_SOCKET_DIRS="$RUN" KITTY_WINDOW_ID=1 "$ROOT/bin/kittymux" workflow "$@"; }
WORKFLOW scratch --cwd "$RUN/home" -- sh
WORKFLOW newtab
WORKFLOW newtab --next
WORKFLOW scratch --cwd "$RUN/home" -- sh
RC ls > "$RUN/result.json"
python3 - "$RUN/result.json" <<'PY'
import json,sys
hosts=json.load(open(sys.argv[1]));tabs=hosts[0]['tabs']
assert len(tabs)==4, [(t['id'],t['title']) for t in tabs]
assert tabs[-1]['title']=='!scratch', [(t['id'],t['title']) for t in tabs]
assert sum(t['title']=='!scratch' for t in tabs)==1
PY
WORKFLOW nav next
mkdir -p "$RUN/state/sessions"
FILE="$RUN/state/sessions/quote'"$'\n'"path.kitty-session"
WORKFLOW save-session 1 "$FILE"
for _ in $(seq 30); do [ ! -s "$FILE" ] || break; sleep .2; done
[ -s "$FILE" ] || { echo 'FAIL: exact path was not saved'; exit 1; }
# A stale record naming an unrelated tab must not close it.
find "$RUN/runtime/kittymux" "$RUN/state/run" -name 'scratch-*' -type f 2>/dev/null | while read -r f; do printf '1\t1\t%s\n' aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa > "$f"; done || true
WORKFLOW scratch --cwd "$RUN/home" -- sh
RC ls | python3 -c 'import json,sys;d=json.load(sys.stdin);assert any(w["id"]==1 for o in d for t in o["tabs"] for w in t["windows"])'
cat > "$RUN/state/sessions/parked-bird.kitty-session" <<'SESSION'
new_tab parked-bird
launch sh
SESSION
cat > "$RUN/state/sessions/calm-otter.kitty-session" <<'SESSION'
new_tab calm-one
launch sh
new_tab calm-two
launch sh
focus_tab 0
SESSION
RC action --match id:1 goto_session "$RUN/state/sessions/parked-bird.kitty-session"
RC action --match id:1 goto_session "$RUN/state/sessions/calm-otter.kitty-session"
RC ls > "$RUN/named.json"
NAMED_PANE=$(python3 - "$RUN/named.json" <<'PY'
import json,sys
print(next(w['id'] for o in json.load(open(sys.argv[1])) for t in o['tabs'] if t['is_active'] for w in t['windows']))
PY
)
WORKFLOW save-session "$NAMED_PANE" "$RUN/state/sessions/calm-capture.kitty-session"
python3 - "$RUN/state/sessions/calm-capture.kitty-session" <<'PY'
import sys
text=open(sys.argv[1]).read()
assert 'parked-bird' not in text, text
assert 'calm-one' in text and 'calm-two' in text, text
assert sum(s.startswith('launch ') for s in text.splitlines())==2,text
assert 'focus_tab 0' in text,text
PY
echo 'PASS: scratch stays last, exact newline path saves, stale record cannot close another tab, named save excludes parked sessions'
[ "$(others)" = "$BEFORE" ] || { echo 'FAIL: another kitty changed'; exit 1; }
