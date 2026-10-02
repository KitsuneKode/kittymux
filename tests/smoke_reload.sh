#!/usr/bin/env bash
# Render smoke test: does the real tab bar survive a config reload after its helper
# modules change underneath a RUNNING kitty? (This is the regression that once made a live
# kitty draw the new tab bar with a stale kittymux_agents and fall back to kitty's default.)
#
# Needs Xvfb, xdotool and kitty; otherwise it prints SKIP and exits 0. Uses its own private
# X display, config and control socket — it never touches your kitty or your config.
#
#   bash tests/smoke_reload.sh                 # expect: PASS
#   SMOKE_KEEP_STALE=1 bash tests/smoke_reload.sh   # sanity check of the detector: expect FAIL
set -u

HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do
  command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }
done

T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-smoke.XXXXXX")
CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "${SMOKE_KEEP:-}" ] && { cp -r "$STATE" "$SMOKE_KEEP" 2>/dev/null; cp "$T/kitty.log" "$SMOKE_KEEP/" 2>/dev/null; }; 
  [ -n "$KPID" ] && kill "$KPID" 2>/dev/null
  [ -n "$XPID" ] && kill "$XPID" 2>/dev/null
  rm -rf "$T"
}
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$STATE/tab_bar-error.log" ] && sed 's/^/  | /' "$STATE/tab_bar-error.log" | tail -12; exit 1; }

# a private X display: first free number from :90
for n in $(seq 90 120); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1300x820x24 >/dev/null 2>&1 &
XPID=$!
sleep 1
kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }

# config: helper modules linked from the repo — except kittymux_agents.py, which starts life as the
# PREVIOUS release's copy (valid, just older), like a kitty that was started before `git pull`.
# Against the current tab bar that old copy is missing newer names, so the tab bar logs errors until
# the module is refreshed — which is exactly what a reload must do.
for f in "$HOME_DIR"/python/pane-state.py "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do
  cp "$f" "$CFG/$(basename "$f")"         # real copies of EVERY helper (a module resolves its siblings from its OWN directory; a hand-kept list silently goes stale when tab_bar imports a new one)
done
OLD_REV=331a40f
if ! git -C "$HOME_DIR" show "$OLD_REV:python/kittymux_agents.py" > "$CFG/kittymux_agents.py" 2>/dev/null; then
  echo "SKIP: git history does not include $OLD_REV (shallow clone?)"; exit 0
fi
cat > "$CFG/kitty.conf" <<CONF
allow_remote_control socket-only
include $HOME_DIR/kittymux.conf
watcher $CFG/pane-state.py
tab_bar_edge left
tab_bar_min_tabs 1
CONF
cat > "$T/session.kitty" <<SESS
new_tab api
launch
new_tab claude
launch bash -c 'exec -a claude sleep 300'
new_tab notes
launch
focus_tab 1
SESS

env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_ERR_DEDUPE=0 \
  kitty -o linux_display_server=x11 --class kmx-smoke --listen-on "$SOCK" --session "$T/session.kitty" \
  >"$T/kitty.log" 2>&1 &
KPID=$!

for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done
[ -S "$T/sock" ] || fail "kitty never opened its control socket ($(tail -3 "$T/kitty.log" 2>/dev/null))"

tabs() { kitty @ --to "$SOCK" ls 2>/dev/null | python3 -c 'import sys,json; print(sum(len(o["tabs"]) for o in json.load(sys.stdin)))'; }
redraw() {   # kitty only lays the bar out after a resize — force one
  W=$(DISPLAY=$DISP xdotool search --class kmx-smoke 2>/dev/null | head -1)
  [ -n "$W" ] || return 0
  DISPLAY=$DISP xdotool windowsize "$W" 1290 810; sleep 0.4
  DISPLAY=$DISP xdotool windowsize "$W" 1300 820; sleep 0.8
}

sleep 2; redraw
for _ in $(seq 40); do [ "$(tabs)" = "3" ] && break; sleep 0.5; done      # a slow machine (CI) builds the session more slowly
[ "$(tabs)" = "3" ] || fail "expected 3 tabs at start, got $(tabs)"
# precondition: the old module really does break the current tab bar (otherwise this test proves nothing)
if [ ! -s "$STATE/tab_bar-error.log" ]; then
  echo "SKIP: the old helper module no longer breaks the tab bar — pick a newer OLD_REV in this script"; exit 0
fi
: > "$STATE/tab_bar-error.log"

if [ -z "${SMOKE_KEEP_STALE:-}" ]; then
  # `git pull` happened: the current module replaces the old one on disk, kitty is still running
  cp "$HOME_DIR/python/kittymux_agents.py" "$CFG/kittymux_agents.py"
fi

for i in 1 2; do
  kitty @ --to "$SOCK" load-config >/dev/null 2>&1 || fail "load-config #$i failed"
  sleep 1; redraw
done
# errors logged WHILE upgrading (the old module still drawing before the first reload finished) do not
# count; what matters is that once reloaded the bar draws cleanly — so start counting from here
: > "$STATE/tab_bar-error.log"
sleep 1; redraw; sleep 1; redraw

if [ -n "${SMOKE_SHOT:-}" ] && command -v import >/dev/null 2>&1; then
  DISPLAY=$DISP import -window root "$SMOKE_SHOT" 2>/dev/null && echo "screenshot: $SMOKE_SHOT"
fi
[ "$(tabs)" = "3" ] || fail "tabs changed across reloads: $(tabs)"
kill -0 "$KPID" 2>/dev/null || fail "kitty died"
if [ -s "$STATE/tab_bar-error.log" ]; then
  fail "tab bar logged an error after reload"
fi
echo "PASS: after two reloads the running kitty draws with the upgraded helper modules, no errors (3 tabs intact)"
