#!/usr/bin/env bash
# Confirmed quit captures a layout changed less than the periodic settle time ago.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for d in kitty Xvfb python3; do command -v "$d" >/dev/null || { echo "SKIP: $d missing"; exit 0; }; done
ORIGINAL_RUNTIME=${XDG_RUNTIME_DIR:-/nonexistent}
others() { for socket in /tmp/mykitty-* "$ORIGINAL_RUNTIME"/mykitty-*; do if [ -S "$socket" ] && [ -O "$socket" ]; then kitty @ --to "unix:$socket" ls 2>/dev/null | python3 -c 'import sys,json; print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; fi; done; }
BEFORE=$(others)
RUN=$(mktemp -d /tmp/kmx-exit.XXXXXX); KP= XP=
trap '[ -z "$KP" ] || kill "$KP" 2>/dev/null || true; [ -z "$XP" ] || kill "$XP" 2>/dev/null || true; rm -rf "$RUN"' EXIT
mkdir -p "$RUN/cfg" "$RUN/state" "$RUN/home"
for n in $(seq 480 509); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1000x700x24 >/dev/null 2>&1 & XP=$!; sleep 1
for f in "$ROOT"/python/tab_bar.py "$ROOT"/python/kittymux_*.py; do ln -s "$f" "$RUN/cfg/$(basename "$f")"; done
printf 'allow_remote_control socket-only\nconfirm_os_window_close 0\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' "$ROOT" "$ROOT" "$ROOT" > "$RUN/cfg/kitty.conf"
env -u WAYLAND_DISPLAY -u KITTY_PID -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTYMUX_TARGET HOME="$RUN/home" KITTY_CONFIG_DIRECTORY="$RUN/cfg" KITTYMUX_STATE="$RUN/state" KITTYMUX_SOCKET_DIRS="$RUN" KITTYMUX_NOTIFY=0 KITTYMUX_DEBUG=1 DISPLAY="$DISP" LIBGL_ALWAYS_SOFTWARE=1 __GLX_VENDOR_LIBRARY_NAME=mesa kitty -o linux_display_server=x11 --listen-on "unix:$RUN/sock" sh > "$RUN/log" 2>&1 & KP=$!
RC() { kitty @ --to "unix:$RUN/sock" "$@"; }
for _ in $(seq 60); do [ ! -S "$RUN/sock" ] || break; sleep .2; done
sleep 1
RC load-config; RC load-config
RC goto-layout splits
RC launch --location=hsplit sh
RC launch --location=vsplit sh
RC action quit
wait "$KP" || true
KP=
for _ in $(seq 60); do [ ! -e "$RUN/state/sessions" ] || [ -z "$(find "$RUN/state/sessions" -name '*.kitty-session' -print -quit)" ] || break; sleep .2; done
python3 - "$RUN/state/sessions" <<'PY'
import sys
from pathlib import Path
files=list(Path(sys.argv[1]).glob('autosave-*.kitty-session'))
assert len(files)==1, files
text=files[0].read_text()
assert text.startswith('# kittymux captured_ns: '), text
assert sum(line.startswith('launch ') for line in text.splitlines())==3, text
assert 'layout splits' in text, text
assert files[0].stat().st_mode&0o777==0o600
PY
[ ! -s "$RUN/state/scan-debug.log" ] || { cat "$RUN/state/scan-debug.log"; exit 1; }
# Parse the final file with kitty's own parser, without creating another OS window.
SESSION_FILE=$(find "$RUN/state/sessions" -name '*.kitty-session' -print -quit)
SESSION_FILE="$SESSION_FILE" kitty +runpy 'import os; from kitty.session import parse_session; from kitty.options.types import Options; sessions=list(parse_session(open(os.environ["SESSION_FILE"]).read(), Options())); assert sum(len(t.windows) for s in sessions for t in s.tabs)==3; print("native session parser accepted all three panes")'
echo 'PASS: confirmed quit captured recent layout; offline save parsed after socket teardown'
[ "$(others)" = "$BEFORE" ] || { echo 'FAIL: another kitty changed'; exit 1; }
