#!/usr/bin/env bash
# `kittymux answer` in a real kitty: a fake Claude draws its permission menu and reads one key. The answer types into THAT pane
# only while the same prompt is on screen: a different --expect is refused, and so is any answer once the prompt has gone.
#   bash tests/smoke_answer.sh          # expect: PASS
# Its own Xvfb, kitty, socket and state dir; it ends by checking that no other kitty was touched. Needs Xvfb, kitty, python3.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-answer.XXXXXX"); CFG=$T/cfg STATE=$T/state BIN=$T/bin
mkdir -p "$CFG" "$STATE" "$BIN" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty*; do [ -S "$s" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
tripwire() { [ "$(others)" = "$OTHERS_BEFORE" ] || { echo "FAIL: this rig changed the windows of ANOTHER kitty on this machine (before: $OTHERS_BEFORE after: $(others))"; return 1; }; }
fail() { echo "FAIL: $*"; tripwire; exit 1; }
for n in $(seq 281 319); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1300x820x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
# the fake Claude: its real permission menu, then one key read raw; it prints what it got and draws a plain screen
cat > "$BIN/claude" <<'S'
#!/usr/bin/env bash
printf ' Bash command\n   rm -rf node_modules\n Do you want to proceed?\n ❯ 1. Yes\n   2. Yes, and don'"'"'t ask again for rm commands\n   3. No, and tell Claude what to do differently (esc)\n'
IFS= read -rsn1 k
printf '\033[2J\033[HGOT:%q\n' "$k"
while :; do sleep 1; done
S
chmod +x "$BIN/claude"
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'allow_remote_control socket-only\nlisten_on unix:%s/mykitty\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\n' "$T" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"   # listen_on in the conf: kitty names it mykitty-<pid>
printf 'new_tab claude\nlaunch %s/claude\nnew_tab shell\nlaunch\nfocus_tab 1\n' "$BIN" > "$T/session"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_SOCKET_DIRS=$T KITTYMUX_NOTIFY=0 \
  kitty -o linux_display_server=x11 --class kmx-answer --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
SOCK=""; for _ in $(seq 240); do SOCK=$(ls "$T"/mykitty-* 2>/dev/null | head -1); [ -S "$SOCK" ] && break; sleep 0.25; done
[ -S "$SOCK" ] || fail "kitty never opened its control socket"
SOCK="unix:$SOCK"
ans() { env -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID KITTYMUX_STATE=$STATE KITTYMUX_SOCKET_DIRS=$T "$HOME_DIR/bin/kittymux" answer "$@" 2>&1; }
pane() { kitty @ --to "$SOCK" get-text --match "id:$WID" 2>/dev/null; }
WID=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
print(next(w["id"] for o in json.load(sys.stdin) for t in o["tabs"] if t["title"].startswith("claude") for w in t["windows"]))')
# the scanner publishes the waiting row (control: without it nothing below proves anything)
KEY=""; for _ in $(seq 80); do KEY=$(python3 -c "import json,sys;d=json.load(open('$STATE/agents.json'));print(next((r['key'] for r in d['agents'] if r['state']=='waiting' and r['window_id']==$WID),''))" 2>/dev/null); [ -n "$KEY" ] && break; sleep 0.25; done
[ -n "$KEY" ] || fail "the fake Claude never read as waiting in agents.json"
echo "  ok   $KEY reads as waiting"
out=$(ans "$KEY" allow --expect "Delete the database?"); rc=$?
[ $rc = 3 ] || fail "a different question was not refused (rc $rc: $out)"
pane | grep -q "GOT:" && fail "a refused answer still typed into the pane"
echo "  ok   a changed question is refused and nothing is typed"
out=$(ans "$KEY" allow --expect "Do you want to proceed?"); rc=$?
[ $rc = 0 ] || fail "allow on the same prompt failed (rc $rc: $out)"
for _ in $(seq 40); do pane | grep -q "GOT:1" && break; sleep 0.125; done
pane | grep -q "GOT:1" || fail "allow did not type 1 into the pane ($(pane | head -3))"
echo "  ok   allow typed 1 into that pane"
out=$(ans "$KEY" allow); rc=$?
[ $rc = 3 ] || [ $rc = 1 ] || fail "an answer with no prompt on screen was not refused (rc $rc: $out)"
echo "  ok   with the prompt gone, an answer is refused"
tripwire || exit 1
echo "  ok   no other kitty on this machine was touched"
echo "PASS: kittymux answer types into the one pane, and only while that prompt is on screen"
