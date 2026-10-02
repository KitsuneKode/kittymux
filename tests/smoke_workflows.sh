#!/usr/bin/env bash
# Two real kitties, overlapping local IDs, private display/config/state/sockets.
# Exercises scratch isolation, unnamed-session attention jumps and target-owner lookup.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty python3; do
    command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }
done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-workflows.XXXXXX")
XPID="" APID="" BPID=""
cleanup() {
    for pid in "$APID" "$BPID" "$XPID"; do
        [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
    done
    rm -rf "$T"
}
trap cleanup EXIT
mkdir -p "$T/cfg" "$T/state" "$T/bin" "$T/run"
chmod 700 "$T/state" "$T/run"
# Let Xvfb choose a display atomically rather than racing another smoke rig.
Xvfb -displayfd 3 -screen 0 1200x800x24 3>"$T/display" >"$T/x.log" 2>&1 &
XPID=$!
for _ in $(seq 40); do [[ -s "$T/display" ]] && break; sleep 0.1; done
[[ -s "$T/display" ]] || { echo "FAIL: private X display did not start"; exit 1; }
export DISPLAY=":$(cat "$T/display")"
unset WAYLAND_DISPLAY KITTY_WINDOW_ID KITTY_LISTEN_ON KITTY_PID KITTYMUX_TARGET KITTYMUX_TARGET_PID
export __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1
export KITTY_CONFIG_DIRECTORY="$T/cfg" KITTYMUX_STATE="$T/state" KITTYMUX_NOTIFY=0 KITTYMUX_BELL=0
export XDG_RUNTIME_DIR="$T/run"
for f in "$ROOT"/python/*.py; do cp "$f" "$T/cfg/"; done
cat >"$T/cfg/kitty.conf" <<CONF
allow_remote_control socket-only
include $ROOT/kittymux.conf
watcher $T/cfg/pane-state.py
tab_bar_edge left
tab_bar_min_tabs 1
geninclude $T/cfg/kittymux_layout.py
CONF
cat >"$T/bin/claude" <<'AGENT'
#!/bin/sh
printf 'Do you want to proceed?\n❯ 1. Yes\n'
while :; do sleep 1; done
AGENT
# The attention CLI must never manipulate the user's compositor during this rig.
printf '#!/bin/sh\nprintf "[]\\n"\n' >"$T/bin/hyprctl"
chmod +x "$T/bin/claude" "$T/bin/hyprctl"
export PATH="$T/bin:$PATH"
kitty -o linux_display_server=x11 --class kmx-workflows-a --listen-on "unix:$T/a" /bin/sh >"$T/a.log" 2>&1 &
APID=$!
kitty -o linux_display_server=x11 --class kmx-workflows-b --listen-on "unix:$T/b" /bin/sh >"$T/b.log" 2>&1 &
BPID=$!
for _ in $(seq 60); do [[ -S "$T/a" && -S "$T/b" ]] && break; sleep 0.2; done
[[ -S "$T/a" && -S "$T/b" ]] || { echo "FAIL: private control sockets did not start"; exit 1; }
# The attention CLI's established discovery convention uses PID-suffixed socket names.
ln -s "$T/a" "$T/mykitty-$APID"
ln -s "$T/b" "$T/mykitty-$BPID"
export KITTYMUX_SOCKET_GLOB="$T/mykitty-*"
python3 - "$ROOT" "$T" "$APID" "$BPID" <<'PY'
import json, os, pathlib, subprocess, sys, time
root, tmp = map(pathlib.Path, sys.argv[1:3])
apid, bpid = map(int, sys.argv[3:5])
sys.path.insert(0, str(root / "python"))
import kittymux_deck as deck

def rc(sock, *args):
    return subprocess.check_output(["kitty", "@", "--to", "unix:" + str(sock), *args], text=True, timeout=8)

def snapshot(sock):
    return json.loads(rc(sock, "ls"))

a, b = tmp / "a", tmp / "b"
for sock in (a, b):
    rc(sock, "set-tab-title", "regular")
rc(a, "launch", "--type=tab", "--tab-title", "agent", "--", str(tmp / "bin/claude"))
rc(b, "launch", "--type=tab", "--tab-title", "second", "--", "/bin/sh")
for sock, expected in ((a, apid), (b, bpid)):
    assert deck.target_pid(snapshot(sock)) == expected, "custom socket owner mismatch"
print("  ok   custom socket ownership verified from real pane processes")
assert snapshot(a)[0]["id"] == snapshot(b)[0]["id"], "rig must overlap OS-window IDs"
assert snapshot(a)[0]["tabs"][0]["id"] == snapshot(b)[0]["tabs"][0]["id"], "rig must overlap tab IDs"
for sock in (a, b, a):
    source = snapshot(sock)[0]["tabs"][0]["windows"][0]["id"]
    env = dict(os.environ, KITTY_LISTEN_ON="unix:" + str(sock), KITTY_WINDOW_ID=str(source))
    result = subprocess.run(["bash", str(root / "bin/mux-scratch.sh"), "--cwd", str(tmp), "--", "/bin/sh"],
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, "scratch failed: " + result.stderr
    for target in (a, b):
        assert any(t["title"] == "regular" for t in snapshot(target)[0]["tabs"]), "regular tab closed"
for sock in (a, b):
    titles = [t["title"] for t in snapshot(sock)[0]["tabs"]]
    assert len(titles) == 3 and titles.count("!scratch") == 1, titles
print("  ok   repeated scratch launches preserve regular tabs in both instances")
# Refocus a plain pane in the source; the agent's session columns are deliberately empty.
plain = snapshot(a)[0]["tabs"][0]["windows"][0]["id"]
rc(a, "focus-window", "--match", "id:" + str(plain))
agent = next(t["windows"][0]["id"] for t in snapshot(a)[0]["tabs"] if t["title"] == "agent")
for _ in range(40):
    path = tmp / "state" / f"scan-{apid}.json"
    try:
        verdict = json.loads(path.read_text()).get(str(agent), {})
        if verdict.get("state") == "waiting": break
    except (OSError, ValueError): pass
    time.sleep(0.2)
else:
    raise AssertionError("agent never reached waiting")
env = dict(os.environ, KITTY_LISTEN_ON="unix:" + str(a), KITTY_WINDOW_ID=str(plain))
rows = subprocess.check_output(["bash", str(root / "bin/mux-agents.sh"), "--list"], env=env, text=True, timeout=15)
assert rows.strip().split("\t")[4:6] == ["", ""], "rig must exercise empty session columns"
result = subprocess.run(["bash", str(root / "bin/mux-agents.sh"), "--next-waiting"], env=env,
                        check=True, capture_output=True, text=True, timeout=15)
for _ in range(20):
    active = next(t for t in snapshot(a)[0]["tabs"] if t["is_active"])
    if any(w["id"] == agent for w in active["windows"]):
        break
    time.sleep(0.1)
else:
    raise AssertionError("unnamed-session jump failed: " + repr((rows, result.stdout, result.stderr,
        [(t["title"], t["is_active"]) for t in snapshot(a)[0]["tabs"]])))
# Xvfb has no WM, so OS focus flags are not reliable; this one-pane tab must be active.
print("  ok   unnamed-session attention jump focuses the real waiting pane")
for pid in (apid, bpid):
    os.kill(pid, 0)
error = tmp / "state" / "tab_bar-error.log"
assert not error.exists() or not error.stat().st_size, "tab bar reported errors"
print("PASS: two-instance scratch safety, target identity and attention jump (real kitty)")
PY
