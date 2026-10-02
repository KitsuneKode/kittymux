#!/usr/bin/env bash
# The security posture we recommend, proven in a real kitty: with `allow_remote_control socket-only` a program in a terminal CANNOT control kitty by printing an escape
# sequence (with `yes` it can — the positive control, so this test would notice if kitty ever changed), while the socket in a private $XDG_RUNTIME_DIR still works and
# kittymux finds it there. Needs Xvfb, kitty, python3.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-sock.XXXXXX"); STATE=$T/state RUN=$T/run
mkdir -p "$STATE" "$RUN" "$T/cfg" && chmod 700 "$STATE" "$RUN"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 800x600x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
# what any program in the terminal could do: print kitty's remote-control escape sequence and read the answer from the tty
cat > "$T/probe.py" <<'PY'
import os, select, sys, termios, time, tty
out = sys.argv[1]
fd = sys.stdin.fileno()
old = termios.tcgetattr(fd)
tty.setraw(fd)
sys.stdout.write('\x1bP@kitty-cmd{"cmd":"ls","version":[0,14,2],"no_response":false}\x1b\\')
sys.stdout.flush()
buf, end = b"", time.time() + 4
while time.time() < end:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        buf += os.read(fd, 65536)
termios.tcsetattr(fd, termios.TCSADRAIN, old)
with open(out, "wb") as f:
    f.write(buf)
time.sleep(60)
PY
run_mode() {   # run_mode <allow_remote_control value>
  mode=$1; rm -f "$RUN"/mykitty-*
  printf 'allow_remote_control %s\nlisten_on unix:${XDG_RUNTIME_DIR}/mykitty\n' "$mode" > "$T/cfg/kitty.conf"
  env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_RUNTIME_DIR=$RUN KITTY_CONFIG_DIRECTORY=$T/cfg \
    kitty -o linux_display_server=x11 python3 "$T/probe.py" "$T/inband.$mode" >"$T/k.$mode.log" 2>&1 & KPID=$!
  for _ in $(seq 80); do [ -s "$T/inband.$mode" ] || [ -e "$T/inband.$mode" ] && break; sleep 0.25; done
  [ -e "$T/inband.$mode" ] || fail "the probe did not finish under $mode"
}
run_mode yes
grep -q '"ok": *true' "$T/inband.yes" || fail "positive control: with allow_remote_control yes the escape sequence should have worked (kitty changed?): $(cat "$T/inband.yes")"
echo "  ok   control: allow_remote_control yes obeys an escape sequence printed by a program"
kill "$KPID" 2>/dev/null; wait "$KPID" 2>/dev/null; KPID=""
run_mode socket-only
grep -q '"ok": *true' "$T/inband.socket-only" && fail "socket-only still obeyed an in-band escape sequence: $(cat "$T/inband.socket-only")"
echo "  ok   allow_remote_control socket-only: the same escape sequence is refused"
SOCK=$(ls "$RUN"/mykitty-* 2>/dev/null | head -1)
[ -S "$SOCK" ] || fail "no socket in the private runtime dir"
[ "$(stat -c %a "$RUN")" = 700 ] || fail "runtime dir is not private"
kitty @ --to "unix:$SOCK" ls >/dev/null 2>&1 || fail "the socket in \$XDG_RUNTIME_DIR does not accept remote control under socket-only"
out=$(env -u KITTY_LISTEN_ON XDG_RUNTIME_DIR=$RUN KITTYMUX_STATE=$STATE python3 "$HOME_DIR/bin/kittymux" doctor 2>&1)
echo "$out" | grep -q "connected (unix:$RUN/mykitty-" || { echo "$out" | sed -n '/live kitty/,/^$/p'; fail "kittymux did not find the socket in \$XDG_RUNTIME_DIR"; }
echo "  ok   the \$XDG_RUNTIME_DIR socket works under socket-only and kittymux discovers it"
echo "PASS: socket-only blocks in-band control; the private-socket setup works end to end"
