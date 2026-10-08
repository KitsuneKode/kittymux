#!/usr/bin/env bash
# kitty's timer dispatcher copies every due timer into a table and then runs them one by one; a callback that REMOVES another timer due in the same batch
# leaves the table pointing at a Python function that kitty has just released. If nothing else holds that function it is freed and kitty calls a dead object:
# libpython SIGSEGV in python_timer_callback (the 2026-10-07 22:57 coredump). kittymux_timers hands kitty a callable that can never be freed.
#   1. control   a raw timer pair: A removes B in the same batch → kitty DIES (this proves the rig can see the crash; if kitty no longer dies the premise is gone — said, not failed)
#   2. stable    the same pair through kittymux_timers → kitty lives, the stale B tick is harmless
#   3. soak      the real scanner (a working fake agent: scan + spin timers) while 40 config reloads fire from one-shot timers
#   bash tests/smoke_timers.sh [TREE]      TREE defaults to this checkout. Needs Xvfb, kitty; else SKIP.
set -u
ulimit -c 0          # the control phase kills a kitty ON PURPOSE: no 70 MB core file for it
HOME_DIR=$(cd "${1:-$(dirname "${BASH_SOURCE[0]}")/..}" && pwd)
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-timers.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
for n in $(seq 490 519); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done

# a kitten whose handle_result runs INSIDE kitty. Mode "raw": timer A removes timer B (due in the same batch) and B's function has no other reference.
# Mode "stable": the same through kittymux_timers. Mode "storm N": N config reloads, each fired from a one-shot timer.
cat > "$CFG/probe.py" <<PROBE
from kittens.tui.handler import result_handler


def main(args):
    pass


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    import gc
    import sys
    from kitty.fast_data_types import add_timer, remove_timer
    mode = args[1]
    log = open("$T/probe.log", "a")
    ids = {}

    def a(tid):
        remove_timer(ids["b"])
        log.write("A ran and removed B\n")
        log.flush()

    def make_b():
        def b(tid):
            log.write("B ran after being removed (stale tick)\n")
            log.flush()
        return b

    if mode == "raw":
        ids["a"] = add_timer(a, 0.3, False)
        ids["b"] = add_timer(make_b(), 0.3, False)            # the only reference to B's function is kitty's timer table
    elif mode == "stable":
        import types
        import kittymux_timers
        mod = types.ModuleType("kmx_probe_mod")
        mod.b = make_b()
        sys.modules["kmx_probe_mod"] = mod
        ids["a"] = add_timer(a, 0.3, False)
        ids["b"] = kittymux_timers.add("kmx_probe_mod", "b", 0.3, False)
        mod.b = make_b()                                      # the module was "reloaded": the first function object is gone, the stable callable is not
    elif mode == "storm":
        left = [int(args[2])]

        def fire(timer_id):
            left[0] -= 1
            if left[0] > 0:
                add_timer(fire, 0.5, False)
            boss.load_config_file()

        add_timer(fire, 0.01, False)
    gc.collect()
PROBE

start() {   # start <session file> : a kitty with the kittymux modules; the config is the same for every phase
  printf 'allow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
    "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
  rm -f "$T/sock" "$T/probe.log"
  env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
    KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_DEBUG=1 \
    kitty -o linux_display_server=x11 --class kmx-timers --listen-on "$SOCK" --session "$1" >"$T/k.log" 2>&1 & KPID=$!
  for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
  kill -0 "$KPID" 2>/dev/null || { echo "FAIL: kitty did not start"; tail -5 "$T/k.log"; exit 1; }
}
stop() { kill "$KPID" 2>/dev/null; wait "$KPID" 2>/dev/null; KPID=""; }
alive() { kill -0 "$KPID" 2>/dev/null; }
printf 'new_tab one\nlaunch sh\n' > "$T/plain.session"

# 1. control
start "$T/plain.session"
kitty @ --to "$SOCK" kitten "$CFG/probe.py" raw >/dev/null 2>&1; sleep 3
if alive; then echo "  note kitty did NOT die when a timer callback removed a due timer: its dispatcher no longer has the flaw (the fix below is then only a precaution)"
else echo "  ok   control: a raw timer removed in the same batch killed kitty (the premise of the 22:57 crash, reproduced)"; fi
stop

# 2. stable
start "$T/plain.session"
kitty @ --to "$SOCK" kitten "$CFG/probe.py" stable >/dev/null 2>&1; sleep 3
alive || { echo "FAIL: kitty died with the stable-callable pair ($HOME_DIR)"; tail -5 "$T/k.log"; exit 1; }
grep -q "A ran" "$T/probe.log" || { echo "FAIL: the probe never ran"; exit 1; }
echo "  ok   the same pair through kittymux_timers: kitty lives ($(grep -c 'B ran' "$T/probe.log" 2>/dev/null || true) stale tick(s) of the removed timer, harmless)"
stop

# 3. soak with the real scanner
printf '%s\n' 'printf "· Pondering… (12s · ↓ 1.2k tokens · esc to interrupt)\n"; exec -a claude sleep 86400' > "$T/agent.sh"
printf 'new_tab agent\nlaunch bash %s/agent.sh\nnew_tab other\nlaunch sh\nfocus_tab 0\n' "$T" > "$T/agent.session"
start "$T/agent.session"; sleep 3
working=$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(sum(1 for v in d.values() if v.get("state")=="working"))' "$STATE/scan-$KPID.json" 2>/dev/null || echo 0)
[ "${working:-0}" -ge 1 ] || { echo "FAIL: the fake agent is not seen as working (no spin timer): $working"; exit 1; }
echo "  ok   a working agent is seen: the spinner timer (10 fps) and the scan timer both run"
kitty @ --to "$SOCK" kitten "$CFG/probe.py" storm 40 >/dev/null 2>&1
for _ in $(seq 80); do alive || break; sleep 0.5; done
alive || { echo "FAIL: kitty DIED during 40 reloads fired from timers ($HOME_DIR)"; tail -5 "$T/k.log"; exit 1; }
kitty @ --to "$SOCK" ls >/dev/null 2>&1 || { echo "FAIL: kitty is up but no longer answers"; exit 1; }
[ -s "$STATE/tab_bar-error.log" ] && { echo "FAIL: the tab bar logged errors:"; tail -5 "$STATE/tab_bar-error.log"; exit 1; }
age=$(python3 -c 'import os,sys,time;print(int(time.time()-os.stat(sys.argv[1]).st_mtime))' "$STATE/scan-$KPID.json")
[ "$age" -le 6 ] || { echo "FAIL: the scanner's verdict file is $age s old: its timer is gone after the reloads"; exit 1; }
echo "  ok   40 reloads fired from timer callbacks: kitty is up and the scanner still ticks (verdicts $age s old)"
echo "PASS: removing a timer inside a timer callback cannot crash kitty through kittymux's timers"
