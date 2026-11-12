#!/usr/bin/env bash
# Upgrade smoke test: a kitty started on an OLDER RELEASE of the whole tree (every module, kittymux.conf, the
# assets) is upgraded in place to this checkout, the way `git pull` + `kittymux upgrade` reaches a live kitty that
# has run for days. The bar must keep drawing kittymux's rows, not kitty's plain fallback.
# (2026-11-12: a kitty started on e415a52 kept that release's kittymux_reload in memory; the new tab_bar.py called
# prefer_own on it, failed to load, and kitty drew bare titles. smoke_reload.sh swaps one helper and never saw it.)
#
# Needs Xvfb, xdotool, kitty and git history; otherwise SKIP. Its own X display, config, state and socket only.
#   bash tests/smoke_upgrade.sh                             # expect: PASS
#   SMOKE_UPGRADE_TO=7601482 bash tests/smoke_upgrade.sh    # control, the release before the fix: expect FAIL
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OLD_REV=${SMOKE_UPGRADE_FROM:-e415a52}
for dep in Xvfb xdotool kitty git python3 tar; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
git -C "$HOME_DIR" cat-file -e "$OLD_REV^{commit}" 2>/dev/null || { echo "SKIP: git history does not include $OLD_REV (shallow clone?)"; exit 0; }

T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-upgrade.XXXXXX")
CFG=$T/cfg STATE=$T/state TREE=$T/tree SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" "$TREE" "$T/new" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; grep -E "tab_bar|Traceback|Error" "$T/kitty.log" 2>/dev/null | sed 's/^/  | /' | tail -8; exit 1; }

# the old release, laid out like an install: the config dir links each module into the checkout
git -C "$HOME_DIR" archive "$OLD_REV" python assets kittymux.conf | tar -x -C "$TREE"
if [ -n "${SMOKE_UPGRADE_TO:-}" ]; then
  git -C "$HOME_DIR" archive "$SMOKE_UPGRADE_TO" python assets kittymux.conf | tar -x -C "$T/new"
else
  cp -a "$HOME_DIR/python" "$HOME_DIR/assets" "$HOME_DIR/kittymux.conf" "$T/new/"
fi
for f in "$TREE"/python/tab_bar.py "$TREE"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'allow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$TREE" "$TREE" "$TREE" > "$CFG/kitty.conf"
printf 'new_tab api\nlaunch\nnew_tab claude\nlaunch bash -c %s\nnew_tab notes\nlaunch\nfocus_tab 0\n' "'exec -a claude sleep 300'" > "$T/session.kitty"

for n in $(seq 121 150); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1300x820x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_SOCKET_DIRS=$T KITTYMUX_NOTIFY=0 \
  kitty -o linux_display_server=x11 --class kmx-upgrade --listen-on "$SOCK" --session "$T/session.kitty" >"$T/kitty.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done
[ -S "$T/sock" ] || fail "kitty never opened its control socket"
redraw() {   # kitty lays the bar out again after a resize
  W=$(DISPLAY=$DISP xdotool search --class kmx-upgrade 2>/dev/null | head -1); [ -n "$W" ] || return 0
  DISPLAY=$DISP xdotool windowsize "$W" 1290 810; sleep 0.4; DISPLAY=$DISP xdotool windowsize "$W" 1300 820; sleep 0.8
}
tabs() { kitty @ --to "$SOCK" ls 2>/dev/null | python3 -c 'import sys,json; print(sum(len(o["tabs"]) for o in json.load(sys.stdin)))'; }
sleep 2; redraw
for _ in $(seq 40); do [ "$(tabs)" = "3" ] && break; sleep 0.5; done
[ "$(tabs)" = "3" ] || fail "expected 3 tabs at start, got $(tabs)"
grep -qE "Failed to load custom tab_bar|Custom draw tab function failed" "$T/kitty.log" && fail "the OLD release does not draw its own bar (precondition)"

# the upgrade: the files change under the running kitty, then kittymux upgrade's reload (twice, as it does)
rm -rf "$TREE/python" "$TREE/assets" "$TREE/kittymux.conf"; cp -a "$T/new/." "$TREE/"
for i in 1 2; do kitty @ --to "$SOCK" load-config >/dev/null 2>&1 || fail "load-config #$i failed"; sleep 1; redraw; done
sleep 1; redraw

[ "$(tabs)" = "3" ] || fail "tabs changed across the upgrade: $(tabs)"
kill -0 "$KPID" 2>/dev/null || fail "kitty died"
if grep -qE "Failed to load custom tab_bar|Custom draw tab function failed" "$T/kitty.log"; then
  fail "after the upgrade kitty draws its plain bar: kittymux's tab_bar.py did not load"
fi

# Clicks after the upgrade: with the pixel bar on, a click on a row activates the tab DRAWN there. (2026-11-12: the hooks
# into kitty were kept from the first load, so the old release's hit test answered with its text cells: wrong tab.)
PXDEPS=1; python3 -c "import cairo, gi; gi.require_version('Pango', '1.0'); gi.require_version('Rsvg', '2.0')" 2>/dev/null || PXDEPS=0
[ $PXDEPS = 0 ] && echo "  skip the pixel-bar click after the upgrade: cairo/pango/rsvg not installed (as smoke_pxbar)"
if [ $PXDEPS = 1 ] && [ -e "$TREE/python/kittymux_pxbar.py" ] && [ -e "$HOME_DIR/tests/probe_pxbar.py" ]; then
  : > "$STATE/pxbar-on"
  kitty @ --to "$SOCK" load-config >/dev/null 2>&1 || fail "load-config with pxbar on failed"; sleep 1; redraw
  W=$(DISPLAY=$DISP xdotool search --class kmx-upgrade 2>/dev/null | head -1)
  kitty @ --to "$SOCK" focus-tab --match title:notes >/dev/null 2>&1
  band() {   # "y0 y1" of the row drawn for the tab titled $1; fails while no picture is up
    kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_pxbar.py" "$T/px.json" >/dev/null 2>&1 || return 1
    kitty @ --to "$SOCK" ls > "$T/ls.json" 2>/dev/null || return 1
    python3 - "$T/px.json" "$T/ls.json" "$1" <<'P'
import json, sys
px, ls, title = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3]
tid = next(t["id"] for t in ls[0]["tabs"] if t["title"] == title)
w = next(iter(px["windows"].values()))
print(*next(h[1:3] for h in w["hits"] if h[0] == "tab" and h[3] == tid))
P
  }
  B=""; for _ in $(seq 60); do B=$(band api 2>/dev/null) && [ -n "$B" ] && break; sleep 0.25; done
  [ -n "$B" ] || fail "no pixel bar picture after switching pxbar on (the new code did not take over)"
  set -- $B
  active() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
print(next(t["title"] for t in json.load(sys.stdin)[0]["tabs"] if t["is_active"]))'; }
  [ "$(active)" = notes ] || fail "precondition: 'notes' should be active, '$(active)' is"
  DISPLAY=$DISP xdotool mousemove --window "$W" 90 $(( ($1 + $2) / 2 )) click 1
  for _ in $(seq 40); do [ "$(active)" = api ] && break; sleep 0.125; done
  [ "$(active)" = api ] || fail "after the upgrade a click on the row drawn for 'api' activated '$(active)': the hit test is the old release's"
  echo "  ok   after the upgrade a click on a pixel-bar row activates the tab drawn there"
fi
echo "PASS: a kitty started on $OLD_REV upgrades in place to ${SMOKE_UPGRADE_TO:-this checkout} and keeps drawing kittymux's bar (3 tabs intact)"
