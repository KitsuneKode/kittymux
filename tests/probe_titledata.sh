#!/usr/bin/env bash
# P0-c: what does kitty hand a custom window_title_bar.py's draw_window_title(data)? Dumps the keys; no pass/fail.
set -u
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-title.XXXXXX"); SOCK=unix:$T/sock; XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
for n in $(seq 260 289); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1000x700x24 >/dev/null 2>&1 & XPID=$!; sleep 1
kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for _ in $(seq 40); do [ -S "/tmp/.X11-unix/X${DISP#:}" ] && break; sleep 0.25; done      # Xvfb accepts connections a moment after it starts
mkdir -p "$T/cfg"
cat > "$T/cfg/window_title_bar.py" <<PY
import json

def draw_window_title(data):
    try:
        fields = data._asdict() if hasattr(data, "_asdict") else (dict(data) if hasattr(data, "items") else vars(data))
        with open("$T/title-data.json", "w") as f:
            json.dump({k: repr(v)[:80] for k, v in fields.items()}, f)
    except Exception as e:
        with open("$T/title-data.json", "w") as f:
            f.write(repr(type(data)) + " " + repr(dir(data)) + " " + repr(e))
    return "probe"
PY
printf 'allow_remote_control socket-only\nwindow_title_bar_min_windows 1\nwindow_title_template "{custom}"\nconfirm_os_window_close 0\n' > "$T/cfg/kitty.conf"
printf 'new_tab one\nlaunch sh\nlaunch --location=vsplit sh\n' > "$T/session"
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP KITTY_CONFIG_DIRECTORY=$T/cfg \
  kitty -o linux_display_server=x11 --class kmx-title --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
if [ -s "$T/title-data.json" ]; then echo "draw_window_title(data) received:"; cat "$T/title-data.json"; echo
  python3 - "$T/title-data.json" <<'PY'
import json, sys
try:
    keys = set(json.load(open(sys.argv[1])))
    ident = sorted(keys & {"cwd", "wd", "active_wd", "window_id", "id"})
    print("RESULT: a directory or window id is available:", bool(ident), ident, "| all fields:", sorted(keys))
except ValueError:
    print("RESULT: data was not a mapping — see the dump above")
PY
else echo "RESULT: draw_window_title was never called (see $T/k.log: $(tail -3 "$T/k.log" 2>/dev/null))"; fi
