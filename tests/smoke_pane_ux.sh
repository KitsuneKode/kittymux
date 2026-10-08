#!/usr/bin/env bash
# Native actions and persistent Agents/Usage views, using real keys in a private kitty.
set -eu
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null || { echo "SKIP: $dep missing"; exit 0; }; done
RUN=$(mktemp -d /tmp/kmx-paneux.XXXXXX)
CFG=$RUN/cfg STATE=$RUN/state SOCK=unix:$RUN/sock
mkdir -p "$CFG" "$STATE" "$RUN/home"
KPID="" XPID=""
cleanup() { [ -z "$KPID" ] || kill "$KPID" 2>/dev/null || true; [ -z "$XPID" ] || kill "$XPID" 2>/dev/null || true; rm -rf "$RUN"; }
code=0
trap 'code=$?; if [ "$code" -ne 0 ]; then tail -35 "$RUN/kitty.log" 2>/dev/null; cat "$STATE/tab_bar-error.log" "$STATE/sidebar-kit-err.log" 2>/dev/null || true; fi; cleanup' EXIT
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do if [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ]; then kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; fi; done; }
BEFORE=$(others)
for n in $(seq 420 449); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >"$RUN/x.log" 2>&1 & XPID=$!
sleep 1
for f in "$ROOT"/python/tab_bar.py "$ROOT"/python/window_title_bar.py "$ROOT"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
sed "s|@KITTYMUX_HOME@|$ROOT|g" "$ROOT/kittymux-keys.conf.tpl" > "$CFG/keys.conf"
printf 'allow_remote_control socket-only\nconfirm_os_window_close 0\nwindow_padding_width 10\ninclude %s/kittymux.conf\ninclude %s/keys.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\nwindow_title_bar_min_windows 1\ngeninclude %s/python/kittymux_layout.py\n' "$ROOT" "$CFG" "$ROOT" "$ROOT" > "$CFG/kitty.conf"
cat > "$RUN/session" <<'S'
new_tab synthetic-project
layout splits
launch --title pane-one sh
launch --location=hsplit --title pane-two sh
launch --location=hsplit --title pane-three sh
S
# Hold only the private usage refresh so synthetic quota data remains observable.
mkdir -p "$RUN/bin"
PYTHON_REAL=$(command -v python3)
# shellcheck disable=SC2016 # Variables belong to the generated private wrapper.
printf '#!/bin/sh\ncase "$1" in */mux-usage.py) sleep 20; exit 0;; esac\nexec "%s" "$@"\n' "$PYTHON_REAL" > "$RUN/bin/python3"
chmod +x "$RUN/bin/python3"
python3 - "$STATE/agent-usage.json" <<'PY'
import json,sys,time
json.dump({"ts":time.time(),"providers":[{"name":"codex","rows":[{"label":"5h","pct":100,"reset":"resets in 42 minutes"}]},{"name":"claude","rows":[{"label":"week","pct":24,"reset":"resets tomorrow"}],"note":"local snapshot"}]},open(sys.argv[1],'w'))
PY
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_PID -u KITTY_LISTEN_ON -u KITTYMUX_TARGET HOME="$RUN/home" PATH="$RUN/bin:$PATH" KITTYMUX_USAGE_LIVE=0 DISPLAY="$DISP" KITTY_CONFIG_DIRECTORY="$CFG" KITTYMUX_STATE="$STATE" KITTYMUX_HOME="$ROOT" KITTYMUX_SOCKET_DIRS="$RUN" KITTYMUX_NOTIFY=0 KITTYMUX_PANETITLE_DUMP=1 KITTYMUX_BAR_DUMP=1 LIBGL_ALWAYS_SOFTWARE=1 __GLX_VENDOR_LIBRARY_NAME=mesa kitty -o linux_display_server=x11 --class kmx-paneux --listen-on "$SOCK" --session "$RUN/session" > "$RUN/kitty.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ ! -S "$RUN/sock" ] || break; sleep .25; done
[ -S "$RUN/sock" ] || { cat "$RUN/kitty.log"; exit 1; }
sleep 2
X() { DISPLAY="$DISP" xdotool "$@"; }
RC() { kitty @ --to "$SOCK" "$@"; }
W=$(X search --class kmx-paneux | head -1)
X windowsize "$W" 1400 900
X windowfocus "$W"
sleep 1
SNAP() { RC kitten "$ROOT/python/pane-snapshot.py" 1; }
SNAP > "$RUN/before.json"
python3 - "$RUN/before.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]));assert len(s['windows'])==3;assert len(s['rects'])==3
PY
X key ctrl+alt+shift+semicolon
sleep 1.5
RC get-text --match title:kittymux-panes | grep -q 'Pane controls'
X key r
sleep .8
SNAP > "$RUN/rotated.json"
python3 - "$RUN/before.json" "$RUN/rotated.json" <<'PY'
import json,sys
before,after=[json.load(open(p)) for p in sys.argv[1:]]
assert before['rects']!=after['rects'], 'native rotate changed no geometry'
assert {w['id'] for w in before['windows']}=={w['id'] for w in after['windows']}
PY
X key ctrl+alt+shift+semicolon
sleep .4
X key Escape
sleep .4
RC ls | python3 -c 'import json,sys;assert sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"])==3'
# Native tab snapshot must work even with the peek overlay present.
RC kitten --match id:1 "$ROOT/python/peek-kit.py" 1 >/dev/null
sleep 1.4
RC get-text --match cmdline:peek-kit.py > "$RUN/peek.txt"
grep -q '3 panes' "$RUN/peek.txt"
grep -q 'Preview pane' "$RUN/peek.txt"
if [ -n "${SHOT:-}" ]; then RC screenshot "${SHOT}.peek.png" >/dev/null; fi
X key Escape
sleep .5
# Emulate the persistent panel's environment without opening a live desktop panel.
RC launch --type=overlay --allow-remote-control --env KITTYMUX_PANEL=1 --env KITTYMUX_TARGET="$SOCK" --env KITTYMUX_TARGET_PID="$KPID" --env KITTYMUX_STATE="$STATE" --env KITTYMUX_HOME="$ROOT" kitty +runpy 'from kittens.runner import main; main()' "$CFG" "$ROOT/python/sidebar-kit.py" >/dev/null
sleep 1.5
X key u
sleep .25
RC get-text --match cmdline:sidebar-kit.py > "$RUN/usage.txt"
# an old-format cache (no numeric sidecars) still draws: two providers, Codex at 100 %, the reset text parsed into a countdown
grep -q '2 providers' "$RUN/usage.txt"
grep -q '100%' "$RUN/usage.txt"
grep -q '42m' "$RUN/usage.txt"
if [ -n "${SHOT:-}" ]; then RC screenshot "${SHOT}.usage.png" >/dev/null; fi
X key Escape
sleep .3
RC get-text --match cmdline:sidebar-kit.py | grep -q 'Agents'
X key q
sleep .5
RC ls | python3 -c 'import json,sys;assert sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"])==3'
# A screen-derived agent limit updates native pane captions without a title change.
RC send-text --match id:2 "printf '\nUsage limit reached\n'; exec -a codex sleep 60"$'\n'
for _ in $(seq 30); do
    if python3 - "$STATE/scan-$KPID.json" "$STATE/panetitle-dump.json" <<'PYCODE'
import json,sys
try:
    scan,titles=[json.load(open(p)) for p in sys.argv[1:]]
    assert scan['2']['state']=='limited'
    assert '⊘' in titles['2']
except (OSError,KeyError,ValueError,AssertionError):
    sys.exit(1)
PYCODE
    then break; fi
    sleep .3
done
python3 - "$STATE/panetitle-dump.json" <<'PYCODE'
import json,sys
assert '⊘' in json.load(open(sys.argv[1]))['2'], 'native caption did not refresh its limit state'
PYCODE
[ "$(others)" = "$BEFORE" ] || { echo 'FAIL: another kitty was touched'; exit 1; }
[ ! -s "$STATE/tab_bar-error.log" ] || { cat "$STATE/tab_bar-error.log"; exit 1; }
[ ! -s "$STATE/sidebar-kit-err.log" ] || { cat "$STATE/sidebar-kit-err.log"; exit 1; }
echo 'PASS: native pane rotate/cancel, three-pane peek, persistent usage navigation, live limit caption; other kitties untouched'
