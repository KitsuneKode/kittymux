#!/usr/bin/env bash
# The day kitty's control socket moved to $XDG_RUNTIME_DIR, every older script that looks for /tmp/mykitty-<pid> silently found no kitty — and the keys bound to
# them seemed dead. A real kitty here has its socket in a PRIVATE runtime dir; a key runs a script written the old way (it looks ONLY at <legacy dir>/mykitty-$PPID)
# and must open a tab. With the switch off the same key must do nothing (the control: it proves this rig can see the failure). Needs Xvfb, xdotool, kitty; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-legacy.XXXXXX"); CFG=$T/cfg STATE=$T/state RUN=$T/run LEGACY=$T/tmp
mkdir -p "$CFG" "$STATE" "$RUN" "$LEGACY" && chmod 700 "$STATE" "$RUN"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -f "$T/k.log" ] && tail -6 "$T/k.log"; exit 1; }
for n in $(seq 460 489); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done

# a script written the OLD way: the socket is /tmp/mykitty-<kitty's pid> and nowhere else (the legacy dir stands in for /tmp)
cat > "$T/old-script.sh" <<SH
#!/usr/bin/env bash
SOCKET="unix:$LEGACY/mykitty-\${PPID}"
[[ -S "$LEGACY/mykitty-\${PPID}" ]] || exit 3
kitty @ --to "\$SOCKET" launch --type=tab --tab-title legacy-ok sleep 600 >/dev/null 2>&1
SH
chmod +x "$T/old-script.sh"
printf 'allow_remote_control socket-only\nlisten_on unix:%s/mykitty\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\nmap f9 launch --type=background %s/old-script.sh\n' \
  "$RUN" "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" "$T" > "$CFG/kitty.conf"

start() {   # start <extra env...>: a kitty whose socket is in $RUN
  env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
    XDG_RUNTIME_DIR=$RUN KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_LEGACY_SOCKET_DIR=$LEGACY KITTYMUX_NOTIFY=0 "$@" \
    kitty -o linux_display_server=x11 --class kmx-legacy >"$T/k.log" 2>&1 & KPID=$!
  SOCK=""
  for _ in $(seq 60); do SOCK=$(ls "$RUN"/mykitty-* 2>/dev/null | head -1); [ -n "$SOCK" ] && break; sleep 0.25; done
  [ -n "$SOCK" ] || fail "kitty never opened its control socket"
  sleep 3
}
tabs() { kitty @ --to "unix:$SOCK" ls | python3 -c 'import sys,json;print(" ".join(t["title"] for o in json.load(sys.stdin) for t in o["tabs"]))'; }
press() { local w; w=$(DISPLAY=$DISP xdotool search --onlyvisible --class kmx-legacy | head -1); DISPLAY=$DISP xdotool windowfocus "$w" 2>/dev/null; sleep 0.5; DISPLAY=$DISP xdotool key --clearmodifiers F9; sleep 3; }
stop() { kill "$KPID" 2>/dev/null; wait "$KPID" 2>/dev/null; KPID=""; rm -f "$LEGACY"/mykitty-* "$RUN"/mykitty-*; }

# 1. with the link (the default): the old script finds kitty
start
PID=${SOCK##*-}
[ -L "$LEGACY/mykitty-$PID" ] || fail "no compatibility link at $LEGACY/mykitty-$PID (socket: $SOCK)"
[ "$(readlink "$LEGACY/mykitty-$PID")" = "$SOCK" ] || fail "the link does not point at kitty's real socket"
echo "  ok   a link at the old path points at the socket in the private runtime dir"
press
case "$(tabs)" in *legacy-ok*) echo "  ok   the key bound to an old-style script opens its tab" ;; *) fail "the old-style script found no kitty (tabs: $(tabs))" ;; esac
stop

# 2. the control: with the switch off the same key does nothing, so this rig can tell working from broken
touch "$STATE/socketlink-off"
start
[ ! -e "$LEGACY/mykitty-${SOCK##*-}" ] || fail "the switch is off but a link was made"
press
case "$(tabs)" in *legacy-ok*) fail "the old-style script worked WITHOUT the link: the rig cannot tell working from broken" ;; *) echo "  ok   control: with 'socketlink' off the same key does nothing (the failure this fixes)" ;; esac
stop

# 3. a link left by a kitty that exited is cleaned up by the next one
rm -f "$STATE/socketlink-off"
ln -s "$RUN/mykitty-1" "$LEGACY/mykitty-1"
start
[ ! -e "$LEGACY/mykitty-1" ] && [ ! -L "$LEGACY/mykitty-1" ] || fail "a link whose kitty exited was left behind"
echo "  ok   the dead link of an exited kitty is removed"
echo "PASS: scripts written for /tmp/mykitty-<pid> keep finding kitty when its socket lives in a private directory"
