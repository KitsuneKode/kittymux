#!/usr/bin/env bash
# End-to-end status smoke test: a real kitty under Xvfb, three fake agent CLIs that print what the
# real ones print, and the question "does each tab get the right state?" — read from the verdict
# file the scanner publishes (scan-<pid>.json), which is what the tab bar, deck and panel consume.
#
#   devin  → "Thinking · 37m 8s (esc twice to interrupt)"      expect: working   (was shown as "waiting")
#   claude → "Do you want to proceed? ❯ 1. Yes"                expect: waiting
#   codex  → an idle prompt                                    expect: idle
# Then the devin pane "finishes" while another tab has focus   expect: done, and idle after focusing it.
#
# Needs Xvfb, xdotool, kitty; otherwise SKIP (exit 0). Private display/config/socket; touches nothing of yours.
set -u

HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do
  command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }
done

T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-state.XXXXXX")
CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock BIN=$T/bin
mkdir -p "$CFG" "$STATE" "$BIN" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "${SMOKE_KEEP:-}" ] && { cp -r "$STATE" "$SMOKE_KEEP" 2>/dev/null; cp "$T/kitty.log" "$SMOKE_KEEP/" 2>/dev/null; };  [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$STATE/tab_bar-error.log" ] && sed 's/^/  | /' "$STATE/tab_bar-error.log" | tail -12
         for f in "$STATE"/scan-*.json; do [ -f "$f" ] && { echo "  scan verdicts:"; cat "$f"; echo; }; done; exit 1; }

for n in $(seq 121 150); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1300x820x24 >/dev/null 2>&1 &
XPID=$!
sleep 1
kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }

# fake agent CLIs — the script's own name is what the scanner recognises
mk() { printf '#!/bin/sh\n%s\nwhile :; do sleep 1; done\n' "$2" > "$BIN/$1"; chmod +x "$BIN/$1"; }
# devin thinks until $T/finish appears, then clears the screen and shows an idle prompt
printf '#!/bin/sh\nprintf "  Read last 25 lines in ./a.ts\\n\\n  Thinking · 37m 8s (esc twice to interrupt)\\n"\nwhile [ ! -e "%s" ]; do sleep 0.3; done\nprintf "\\033[2J\\033[H  all done\\n❯ \\n"\nwhile :; do sleep 1; done\n' "$T/finish" > "$BIN/devin"
chmod +x "$BIN/devin"
mk claude "printf ' Bash command\n   rm -rf node_modules\n Do you want to proceed?\n ❯ 1. Yes\n   2. No\n'"
mk codex  "printf '╭──────────╮\n│ >        │\n╰──────────╯\n  ? for shortcuts\n'"
mk opencode "printf ' Allow this command?\n ❯ 1. Yes\n   2. No\n'"      # lives in a split nobody is looking at

for f in tab_bar.py kittymux_theme.py kittymux_deck.py kittymux_git.py kittymux_layout.py kittymux_barsize.py \
         kittymux_agents.py kittymux_state.py kittymux_scan.py; do
  ln -s "$HOME_DIR/python/$f" "$CFG/$f"
done
cat > "$CFG/kitty.conf" <<CONF
allow_remote_control yes
include $HOME_DIR/kittymux.conf
watcher $HOME_DIR/python/pane-state.py
tab_bar_edge left
tab_bar_min_tabs 1
CONF
cat > "$T/session.kitty" <<SESS
new_tab devin
launch $BIN/devin
new_tab claude
launch $BIN/claude
new_tab codex
launch $BIN/codex
new_tab shell
launch
new_tab split
launch
launch --location=vsplit $BIN/opencode
focus_tab 4
SESS

env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
  kitty ${SMOKE_KITTY_ARGS:-} -o linux_display_server=x11 --class kmx-state --listen-on "$SOCK" --session "$T/session.kitty" \
  >"$T/kitty.log" 2>&1 &
KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done
[ -S "$T/sock" ] || fail "kitty never opened its control socket"

redraw() {
  W=$(DISPLAY=$DISP xdotool search --class kmx-state 2>/dev/null | head -1)
  [ -n "$W" ] || return 0
  DISPLAY=$DISP xdotool windowsize "$W" 1290 810; sleep 0.4
  DISPLAY=$DISP xdotool windowsize "$W" 1300 820; sleep 0.8
}
sleep 2; redraw

# title → window id (so we can map verdicts to tabs)
wid_of() { kitty @ --to "$SOCK" ls 2>/dev/null | python3 -c '
import sys, json
want = sys.argv[1]
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if t["title"].startswith(want) or any(want in (w.get("title") or "") for w in t["windows"]):
            print(t["windows"][0]["id"]); raise SystemExit' "$1"; }
verdict() {   # verdict <window id> → state, from the published file
  python3 - "$STATE" "$1" <<'PY'
import glob, json, sys
for p in glob.glob(sys.argv[1] + "/scan-*.json"):
    v = json.load(open(p)).get(sys.argv[2]) or {}
    print(v.get("state", "?")); break
else:
    print("nofile")
PY
}
expect() {    # expect <name> <wid> <state> — poll up to 8 s (the scanner ticks twice a second)
  for _ in $(seq 16); do [ "$(verdict "$2")" = "$3" ] && { echo "  ok   $1 → $3"; return 0; }; sleep 0.5; done
  fail "$1: expected $3, got $(verdict "$2")"
}

ID_D=$(wid_of devin); ID_C=$(wid_of claude); ID_X=$(wid_of codex)
[ -n "$ID_D" ] && [ -n "$ID_C" ] && [ -n "$ID_X" ] || fail "could not find the agent windows (devin=$ID_D claude=$ID_C codex=$ID_X)"

expect "devin thinking"        "$ID_D" working
expect "claude permission"     "$ID_C" waiting
expect "codex idle prompt"     "$ID_X" idle

# a question in a split the user is not looking at: the scanner must still see it (the tab bar rolls
# every pane of the tab up — kittymux_agents.tab_verdict — so the tab lights up too)
read -r ID_S ID_SH < <(kitty @ --to "$SOCK" ls | python3 -c '
import sys, json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        for w in t["windows"]:
            if any("opencode" in " ".join(p["cmdline"]) for p in w["foreground_processes"]):
                other = [x["id"] for x in t["windows"] if x["id"] != w["id"]]
                print(w["id"], other[0] if other else ""); raise SystemExit')
[ -n "${ID_S:-}" ] && [ -n "${ID_SH:-}" ] || fail "could not find the split tab (opencode=${ID_S:-} shell=${ID_SH:-})"
kitty @ --to "$SOCK" focus-window --match "id:$ID_SH" >/dev/null 2>&1        # the shell pane is the active one
expect "question in a background split" "$ID_S" waiting
kitty @ --to "$SOCK" focus-tab --match "title:codex" >/dev/null 2>&1

if [ -n "${SMOKE_SHOT:-}" ] && command -v import >/dev/null 2>&1; then
  DISPLAY=$DISP import -window root "$SMOKE_SHOT" 2>/dev/null && echo "  screenshot: $SMOKE_SHOT"
fi
# the spinner must keep animating on its own (devin has no hooks, so this is the screen-detected
# path that used to stutter): sample the bar region and require several distinct frames
if command -v import >/dev/null 2>&1 && command -v md5sum >/dev/null 2>&1 && command -v bc >/dev/null 2>&1; then
  # Count distinct frames of a screen region over 3 s, sampling every ~50 ms (a short, odd pause
  # cannot alias with the spinner's 1 s period).
  distinct() {   # distinct <WxH+X+Y>
    local t0; t0=$(date +%s.%N)
    while [ "$(echo "$(date +%s.%N) - $t0 < 3" | bc)" = 1 ]; do
      DISPLAY=$DISP import -window root -crop "$1" png:- 2>/dev/null | md5sum; sleep 0.03
    done | sort -u | wc -l
  }
  # The regression this guards: marking the tab bar dirty alone does not make kitty RENDER, so on an
  # otherwise idle window the spinner advanced ~1 frame/s (it only moved when the cursor blinked).
  # A 10 fps spinner must show ~10 distinct frames in 3 s with nothing else going on.
  spinner=$(distinct 420x60+0+20)
  [ "$spinner" -ge 7 ] || fail "spinner is not animating continuously: $spinner distinct frames in 3 s on an idle window (expect ~10)"
  echo "  ok   spinner animates continuously on an idle window ($spinner distinct frames in 3 s)"
fi
sleep 1
A=$(ls -l --time-style=+%s%N "$STATE"/scan-*.json | awk '{print $6}')
sleep 4
B=$(ls -l --time-style=+%s%N "$STATE"/scan-*.json | awk '{print $6}')
[ "$A" != "$B" ] || fail "scan file never refreshed (heartbeat/scanner stopped)"
echo "  ok   scanner heartbeat alive"

# devin finishes while the user is looking at the shell tab → unseen completion; focusing it clears it
touch "$T/finish"
expect "devin finished unseen" "$ID_D" done
sleep 2
expect "…and it stays done"    "$ID_D" done
kitty @ --to "$SOCK" focus-tab --match "id:$(kitty @ --to "$SOCK" ls | python3 -c '
import sys, json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if any(w["id"] == int(sys.argv[1]) for w in t["windows"]): print(t["id"])' "$ID_D")" >/dev/null 2>&1
expect "devin seen → idle"     "$ID_D" idle

# vertical-bar hit testing: the blank spacer line between two tabs used to belong to no tab (so a tab
# dragged over it was thrown to the end of the list, and a click there did nothing). It must resolve
# to the nearer tab (a tie goes to the lower one). Rows are 22 px below a 10 px top margin; the first tab owns the
# 2-row header (rows 0-3), claude = rows 5-6, the spacer after it = row 7 (y≈175), codex = rows 8-9 (so the click lands on codex).
active_tab() { kitty @ --to "$SOCK" ls | python3 -c '
import sys, json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if t["is_active"]: print(t["title"]); raise SystemExit'; }
W=$(DISPLAY=$DISP xdotool search --class kmx-state 2>/dev/null | head -1)
before=$(active_tab)
DISPLAY=$DISP xdotool mousemove 120 175 click 1; sleep 0.6
after=$(active_tab)
[ "$after" != "$before" ] && [ -n "$after" ] || fail "a click on the spacer row between two tabs hit no tab (active stayed '$before')"
echo "  ok   click on the spacer row between tabs activates the nearer tab ('$before' → '$after')"

[ -s "$STATE/tab_bar-error.log" ] && fail "tab bar logged an error"
kill -0 "$KPID" 2>/dev/null || fail "kitty died"
echo "PASS: states come from the screen — working/waiting/idle/done(unseen→cleared) all correct; no tab bar errors"
