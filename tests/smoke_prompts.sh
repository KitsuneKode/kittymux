#!/usr/bin/env bash
# A plain terminal waiting on YOU, in a real kitty: a script that prints sudo's prompt (leading the pty as `bash`, the way a
# `bash update.sh` does), a pacman look-alike asking [Y/n], and an ssh look-alike. Each becomes one typed inbox event, with FIXED text
# (the user name on the prompt is never stored); answering the prompt clears it; a prompt in the pane you are looking at pops nothing;
# the per-kind switch silences it. Needs Xvfb, kitty; else SKIP. Only ever talks to its own kitty.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty python3 bash; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-prompts.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" "$T/bin" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -f "$T/k.log" ] && tail -6 "$T/k.log"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'allow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"

# the programs: a script prompting like sudo does, a copy of bash NAMED pacman / ssh (so the program leading the pty is the real name)
printf '%s\n' '#!/bin/bash' 'printf "[sudo] password for zork-private: "' 'read -rs x; echo; echo answered' > "$T/sudo-ish.sh"
printf '%s\n' 'printf ":: Proceed with installation? [Y/n] "' 'read -r x; echo answered' > "$T/pacman.sh"
printf '%s\n' 'printf "zork-private@box'"'"'s password: "' 'read -rs x; echo; echo answered' > "$T/ssh.sh"
cp "$(command -v bash)" "$T/bin/pacman"; cp "$(command -v bash)" "$T/bin/ssh"

printf 'new_tab one\nlaunch bash --norc\nnew_tab two\nlaunch bash --norc\nfocus_tab 0\n' > "$T/session"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_DEBUG=1 \
  kitty -o linux_display_server=x11 --class kmx-prompts --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 4

win_of() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for t in json.load(sys.stdin)[0]["tabs"]:
    if t["title"].startswith(sys.argv[1]) or any(w["title"].startswith(sys.argv[1]) for w in t["windows"]): print(t["windows"][0]["id"]); break' "$1"; }
W2=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;ts=json.load(sys.stdin)[0]["tabs"];print(ts[1]["windows"][0]["id"])')
W1=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;ts=json.load(sys.stdin)[0]["tabs"];print(ts[0]["windows"][0]["id"])')
[ -n "$W1" ] && [ -n "$W2" ] || fail "could not find the two windows"
run() { kitty @ --to "$SOCK" send-text --match "id:$1" "$2"$'\r'; }
events() { KITTYMUX_STATE=$STATE python3 "$HOME_DIR/bin/kittymux" inbox --all --json | python3 -c 'import sys,json;[print(json.dumps(e)) for e in json.load(sys.stdin)["events"]]'; }
wait_for() {   # wait_for <python expr over e> → 0 when an event matches
  for _ in $(seq 40); do events | python3 -c 'import sys,json
expr=sys.argv[1]
for l in sys.stdin:
    e=json.loads(l)
    if eval(expr): raise SystemExit(0)
raise SystemExit(1)' "$1" && return 0; sleep 0.25; done; return 1
}
sleep 3     # every window is "seen" once before it can announce (a restart must not replay old prompts)

# 1. a sudo-style prompt in the tab you are NOT looking at (tab two): bash leads the pty, so only sudo's own wording identifies it
run "$W2" "bash $T/sudo-ish.sh"
wait_for 'e["kind"]=="permission" and e["agent"]=="sudo" and e["status"]=="unread" and e["severity"]=="needs-you"' || fail "the sudo prompt never became a needs-you event"
echo "  ok   a sudo prompt in another tab → one permission event (agent sudo)"
raw=$(cat "$STATE/inbox.jsonl")
case "$raw" in *zork-private*) fail "the user name on the prompt reached the inbox" ;; esac
case "$raw" in *"asking for your password"*) ;; *) fail "the event text is not the fixed sentence" ;; esac
echo "  ok   the text is fixed: the name on the prompt was never stored"

# 2. answering it clears it
run "$W2" "pw"
wait_for 'e["kind"]=="permission" and e["agent"]=="sudo" and e["status"]!="unread"' || fail "answering the prompt did not clear the event"
echo "  ok   answering the prompt cleared it"

# 3. pacman's [Y/n]: only counts with pacman leading the pty
run "$W2" "$T/bin/pacman $T/pacman.sh"
wait_for 'e["kind"]=="question" and e["agent"]=="pacman" and e["status"]=="unread"' || fail "the pacman [Y/n] prompt never became a question event"
run "$W2" "y"
echo "  ok   pacman's [Y/n] → a question event"
# the same [Y/n] under a program that is not a package manager means nothing
n_before=$(events | wc -l)
run "$W2" "printf 'Delete everything? [Y/n] '; read x"
sleep 4
[ "$(events | wc -l)" = "$n_before" ] || fail "a [Y/n] question in a random program became an event"
run "$W2" "y"
echo "  ok   a [Y/n] in some other program is not ours"

# 4. ssh's login prompt
run "$W2" "$T/bin/ssh $T/ssh.sh"
wait_for 'e["kind"]=="permission" and e["agent"]=="ssh" and e["status"]=="unread"' || fail "the ssh password prompt never became an event"
run "$W2" "pw"
echo "  ok   ssh's password prompt → a permission event (agent ssh)"

# 5. the pane you are looking at pops nothing and is acknowledged
kitty @ --to "$SOCK" focus-tab --match title:one >/dev/null 2>&1; sleep 1
run "$W1" "bash $T/sudo-ish.sh"
sleep 4
events | python3 -c 'import sys,json
rows=[json.loads(l) for l in sys.stdin]
mine=[e for e in rows if e["kind"]=="permission" and e["agent"]=="sudo"]
assert len(mine)>=2, "the focused prompt was not recorded at all"
assert mine[-1]["status"]!="unread", "a prompt in the pane you are looking at stayed unread"' || fail "a prompt in the pane you are looking at was left unread"
run "$W1" "pw"
echo "  ok   a prompt in the pane you are looking at is acknowledged at once"

# 6. the switch
KITTYMUX_STATE=$STATE python3 "$HOME_DIR/bin/kittymux" features off sudo >/dev/null || fail "kittymux features off sudo failed"
sleep 3
n_before=$(events | wc -l)
kitty @ --to "$SOCK" focus-tab --match title:two >/dev/null 2>&1; sleep 1
run "$W2" "bash $T/sudo-ish.sh"
sleep 5
[ "$(events | wc -l)" = "$n_before" ] || fail "the sudo prompt still produced an event with the switch off"
run "$W2" "pw"
echo "  ok   kittymux features off sudo silences it"
[ "$(stat -c %a "$STATE/inbox.jsonl")" = 600 ] || fail "the inbox is not private"
echo "PASS: sudo / pacman / ssh prompts → one fixed-text event each, cleared by answering, acknowledged when looked at, switchable"
