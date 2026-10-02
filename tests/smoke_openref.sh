#!/usr/bin/env bash
# Clicking `src/app.py:42` in a pane opens $EDITOR at that line (kitty >= 0.49.2: detect_url_regex + open-actions),
# with a REAL ctrl+shift+click. Also: a made-up path opens nothing. Needs Xvfb, xdotool, kitty >= 0.49.2; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
kitty --version | python3 -c 'import re,sys;v=tuple(map(int,re.search(r"(\d+)\.(\d+)\.(\d+)",sys.stdin.read()).groups()));sys.exit(0 if v>=(0,49,2) else 1)' \
    || { echo "SKIP: detect_url_regex needs kitty >= 0.49.2"; exit 0; }
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-ref.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock PROJ=$T/proj
mkdir -p "$CFG" "$STATE" "$PROJ/src" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -f "$T/k.log" ] && tail -5 "$T/k.log"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
: > "$PROJ/src/app.py"
mkdir -p "$T/bin"; printf '#!/bin/sh\nprintf "%%s\\n" "$@" > "%s/ed.out"\n' "$T" > "$T/bin/nvim"; chmod +x "$T/bin/nvim"   # named like nvim: kittymux passes +LINE to it
sed "s|@KITTYMUX_HOME@|$HOME_DIR|g" "$HOME_DIR/open-actions.conf.tpl" > "$CFG/open-actions.conf"
cp "$HOME_DIR/python/kittymux_layout.py" "$CFG/"
cat > "$CFG/kitty.conf" <<CONF
allow_remote_control socket-only
geninclude $CFG/kittymux_layout.py
CONF
printf 'launch --cwd=%s sh -c "printf \\"see src/app.py:42:7 and nowhere/none.py:3 ok\\\\n\\"; exec sleep 600"\n' "$PROJ" > "$T/session"
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE VISUAL="$T/bin/nvim" EDITOR="$T/bin/nvim" \
  kitty -o linux_display_server=x11 --class kmx-ref --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 2
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-ref | head -1); X windowfocus "$W" 2>/dev/null; sleep 0.5
read -r GW GH < <(X getwindowgeometry --shell "$W" | python3 -c 'import sys;d=dict(l.strip().split("=") for l in sys.stdin if "=" in l);print(d["WIDTH"],d["HEIGHT"])')
read -r COLS LINES < <(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;w=json.load(sys.stdin)[0]["tabs"][0]["windows"][0];print(w["columns"],w["lines"])')
click() {   # click at text column $1 on line 0 with ctrl+shift held
    local x y; x=$(python3 -c "print(int(($1 + .5) * $GW / $COLS))"); y=$(python3 -c "print(int(.5 * $GH / $LINES))")
    X mousemove "$x" "$y"; sleep 0.3
    X keydown ctrl keydown shift; sleep 0.1; X click 1; sleep 0.1; X keyup shift keyup ctrl
}
click 8                                   # inside "src/app.py:42:7" (text starts at column 4)
for _ in $(seq 20); do [ -s "$T/ed.out" ] && break; sleep 0.25; done
[ -s "$T/ed.out" ] || fail "clicking src/app.py:42:7 did not start the editor"
grep -qx "+42" "$T/ed.out" && grep -qx "$PROJ/src/app.py" "$T/ed.out" || fail "editor got: $(tr '\n' ' ' < "$T/ed.out")"
rm -f "$T/ed.out"
click 30                                   # "nowhere/none.py:3": no such file
sleep 4
[ ! -e "$T/ed.out" ] || fail "a reference to a missing file started the editor"
echo "PASS: ctrl+shift+click on src/app.py:42:7 opens \$EDITOR at the line; a missing file opens nothing"
