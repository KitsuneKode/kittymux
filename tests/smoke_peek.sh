#!/usr/bin/env bash
# "Quick look" with REAL key events in a real kitty (socket-only, private config/state/socket): ctrl+alt+shift+q opens the peek card of the agent that has waited longest — about
# THAT tab, shown over the pane you are in — ⏎ goes there, esc stays, the chord again closes it (no stacking), and with nothing waiting it opens nothing. The needs-you event is written
# into the rig's private inbox with the real inbox module. Needs Xvfb, xdotool, kitty >= 0.49, python3; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-peek.XXXXXX"); CFG=$T/cfg STATE=$T/state RUN=$T/run
mkdir -p "$CFG" "$STATE" "$RUN" "$T/a" "$T/b" "$T/c" && chmod 700 "$STATE" "$RUN"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -n "${KPID:-}" ] && { echo "--- overlay screen:"; card | head -12; echo "--- tabs:"; tabs; }; [ -s "$T/k.log" ] && tail -5 "$T/k.log"; exit 1; }
for n in $(seq 470 499); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
sed "s|@KITTYMUX_HOME@|$HOME_DIR|g" "$HOME_DIR/kittymux-keys.conf.tpl" > "$CFG/kittymux-keys.conf"
printf 'allow_remote_control socket-only\nlisten_on unix:${XDG_RUNTIME_DIR}/mykitty\nconfirm_os_window_close 0\ninclude %s/kittymux.conf\ninclude %s/kittymux-keys.conf\ngeninclude %s/python/kittymux_layout.py\n' "$HOME_DIR" "$CFG" "$HOME_DIR" > "$CFG/kitty.conf"
cat > "$T/session" <<S
new_tab main
cd $T/a
launch --title shell sh
new_tab api
cd $T/b
launch --title api-shell sh
new_tab web
cd $T/c
launch --title web-shell sh
focus_tab 0
S
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && case "$s" in "$RUN"/*) ;; *) kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))';; esac; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_RUNTIME_DIR=$RUN KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
  KITTYMUX_SOCKET_DIRS=$RUN \
  kitty -o linux_display_server=x11 --class kmx-peek --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 80); do ls "$RUN"/mykitty-* >/dev/null 2>&1 && break; sleep 0.25; done; sleep 3
SOCK=unix:$(ls "$RUN"/mykitty-* | head -1)
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-peek | head -1); X windowsize "$W" 1190 790; sleep 0.4; X windowsize "$W" 1200 800; X windowfocus "$W" 2>/dev/null; sleep 0.8
nwin() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; }
active() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if t["is_active"]: print(t["title"])'; }
tabs() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]: print(" ", t["title"], len(t["windows"]), "(active)" if t["is_active"] else "")'; }
card() { kitty @ --to "$SOCK" get-text --match cmdline:peek-kit --extent screen 2>/dev/null; }
wait_open() { for _ in $(seq 32); do card | grep -q . && return 0; sleep 0.25; done; return 1; }
wait_loaded() { for _ in $(seq 40); do card | grep -q "loading" || return 0; sleep 0.25; done; return 1; }       # the card fetches its data on a worker thread
wait_closed() { for _ in $(seq 16); do [ -z "$(card)" ] && return 0; sleep 0.25; done; return 1; }
win_of_tab() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if t["title"] == sys.argv[1]: print(t["windows"][0]["id"])' "$1"; }
K() { X key --clearmodifiers "$@"; }
CHORD=ctrl+alt+shift+q
base=$(nwin)
[ "$(active)" = main ] || fail "setup: the rig should start on the 'main' tab (active: $(active))"

# 1. nothing needs you: the chord opens nothing (and does not leave a window behind)
K $CHORD; sleep 2.5
card | grep -q . && fail "with nothing waiting the chord must not open a card"
[ "$(nwin)" = "$base" ] || fail "with nothing waiting the window count changed ($(nwin) vs $base)"
echo "  ok   nothing waiting: the chord opens nothing"

# 2. an agent in tab 'web' needs you (a real inbox event for that window, in this kitty): the card opens, about THAT tab, over the pane you are in
WEBW=$(win_of_tab web); APIW=$(win_of_tab api)
[ -n "$WEBW" ] && [ -n "$APIW" ] || fail "could not find the windows of the tabs"
python3 - "$HOME_DIR/python" "$STATE" "$KPID" "$WEBW" "$APIW" <<'PY'
import sys, time
sys.path.insert(0, sys.argv[1])
import kittymux_inbox as I
state, pid, web, api = sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
now = time.time()
# the 'api' agent started waiting later than 'web': the LONGEST waiting one (web) must be the one the quick look shows
I.add(state, I.make_event("permission", "claude", web, "screen", now - 600, pid=pid, tab="web", title="claude needs permission", body="Approve: run the tests?"))
I.add(state, I.make_event("question", "codex", api, "screen", now - 30, pid=pid, tab="api", title="codex asks", body="Which database?"))
PY
K $CHORD; wait_open || fail "$CHORD did not open the peek card"
wait_loaded || fail "the card never finished loading"
out=$(card)
echo "$out" | grep -q "web" || fail "the card should be about the 'web' tab (the agent that has waited longest)"
echo "$out" | grep -q "Which database" && fail "the card must not be about the 'api' tab"
[ "$(active)" = main ] || fail "opening the card must not move you (active: $(active))"
echo "  ok   $CHORD opens the card of the agent that has waited longest ('web'), over the pane you are in; you stay on 'main'"

# 3. the chord again closes it instead of stacking a second card
K $CHORD; wait_closed || fail "pressing $CHORD again did not close the card"
[ "$(nwin)" = "$base" ] || fail "the second $CHORD stacked another card ($(nwin) windows, base $base)"
echo "  ok   the chord again closes it (no stacking)"

# 4. ONE esc closes it and you stay where you were
K $CHORD; wait_open || fail "the card did not reopen"
K Escape; wait_closed || fail "ONE Escape did not close the card"
[ "$(active)" = main ] || fail "esc must leave you where you were (active: $(active))"
[ "$(nwin)" = "$base" ] || fail "window count changed after closing ($(nwin) vs $base)"
echo "  ok   one esc closes it; you stay on 'main'"

# 5. ⏎ goes there
K $CHORD; wait_open || fail "the card did not reopen for the jump"
K Return; wait_closed || fail "Enter did not close the card"
for _ in $(seq 16); do [ "$(active)" = web ] && break; sleep 0.25; done
[ "$(active)" = web ] || fail "Enter should jump to the 'web' tab (active: $(active))"
echo "  ok   ⏎ jumps to the tab the card is about"

[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty (before: $OTHERS_BEFORE after: $(others))"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: quick look — the chord shows the longest-waiting agent's card, esc stays, the chord closes, ⏎ goes there; nothing waiting opens nothing"
