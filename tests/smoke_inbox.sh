#!/usr/bin/env bash
# The inbox, end to end in a real kitty: an agent pane sends real OSC 99 desktop notifications (what Claude Code / Codex do), kitty's own
# notification pipeline hands them to kittymux, and they become typed events — permission, usage limit (with its reset time), completion —
# the completion also drives the pane's state like a Stop hook, and focusing the tab acknowledges what it reported. Needs Xvfb, kitty; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-inbox.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -f "$T/k.log" ] && tail -6 "$T/k.log"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do
  ln -s "$f" "$CFG/$(basename "$f")"
done
printf 'allow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
# the "agent": argv[0] is claude, shows a busy marker, and sends real OSC 99 notifications when told to (files appear)
cat > "$T/agent.sh" <<AG
printf '· Pondering… (12s · ↓ 1.2k tokens)\n'
osc() { printf '\033]99;i=%s:d=0:p=title;Claude Code\033\\\\\033]99;i=%s:d=1:p=body;%s\033\\\\' "\$1" "\$1" "\$2"; }
while true; do
  [ -f "$T/go1" ] && { rm "$T/go1"; osc 1 'Claude needs your permission to use Bash'; }
  [ -f "$T/go2" ] && { rm "$T/go2"; osc 2 "You've hit your usage limit. Resets in 2h 30m"; }
  [ -f "$T/go3" ] && { rm "$T/go3"; printf '\033[2J\033[H> '; osc 3 'Agent turn complete'; }
  sleep 0.2
done
AG
printf 'new_tab other\nlaunch sh\nnew_tab agent\nlaunch bash -c '"'"'exec -a claude bash %s/agent.sh'"'"'\nfocus_tab 0\n' "$T" > "$T/session"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_DEBUG=1 \
  kitty -o linux_display_server=x11 --class kmx-inbox --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 4
ibx() { KITTYMUX_STATE=$STATE python3 "$HOME_DIR/bin/kittymux" inbox "$@"; }
events() { KITTYMUX_STATE=$STATE python3 "$HOME_DIR/bin/kittymux" inbox --all --json | python3 -c 'import sys,json;[print(json.dumps(e)) for e in json.load(sys.stdin)["events"]]'; }
wait_for() {   # wait_for <python expr over e (an event dict)> → exits 0 when some event matches
  for _ in $(seq 40); do events | python3 -c 'import sys,json
expr=sys.argv[1]
for l in sys.stdin:
    e=json.loads(l)
    if eval(expr): raise SystemExit(0)
raise SystemExit(1)' "$1" && return 0; sleep 0.25; done; return 1
}
verdict() { python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(*[v.get("state","")+"|"+v.get("why","") for v in d.values() if v.get("agent")==sys.argv[2]])' "$STATE/scan-$KPID.json" claude 2>/dev/null; }
sleep 2

touch "$T/go1"
wait_for 'e["kind"]=="permission" and "agent" in e["sources"] and e["severity"]=="needs-you"' || fail "the agent's own permission notification never reached the inbox"
echo "  ok   OSC 99 'needs your permission' → a permission event from the agent (needs-you)"

touch "$T/go2"
wait_for 'e["kind"]=="limit" and e.get("reset_at") and 2.4*3600 < e["reset_at"]-e["t"] < 2.6*3600' || fail "the usage-limit notification did not become a limit event with its reset time"
echo "  ok   OSC 99 usage limit → a limit event carrying its reset time (≈ 2h 30m)"

touch "$T/go3"
wait_for 'e["kind"]=="done" and e["confidence"]=="high" and e["sources"]==["agent"]' || fail "the completion notification did not become a high-confidence done event"
for _ in $(seq 20); do case "$(verdict)" in done\|*) break ;; esac; sleep 0.25; done
case "$(verdict)" in done\|*) ;; *) fail "the pane's state did not follow the agent's completion ($(verdict))" ;; esac
echo "  ok   OSC 99 'turn complete' → a done event (agent, high confidence) and the pane's state became done"

ibx | grep -q "permission" || fail "kittymux inbox does not list the permission event"
ibx | grep -q "resets in" || fail "kittymux inbox does not show the reset countdown"
echo "  ok   kittymux inbox lists them (with the reset countdown)"

# the agent's own popups are still suppressed (our filter rule), so the inbox is the only record of them
grep -qi "filtered out" "$T/k.log" 2>/dev/null; true

kitty @ --to "$SOCK" focus-tab --match title:agent >/dev/null 2>&1; sleep 2.5
unread=$(ibx | grep -c . || true)
ibx | grep -q "inbox is empty" || fail "focusing the agent's tab did not acknowledge its events (unread: $(ibx | head -3))"
echo "  ok   focusing the tab acknowledged what it reported"
for p in "$STATE/inbox.jsonl" "$STATE/inbox-snapshot.json"; do [ "$(stat -c %a "$p")" = 600 ] || fail "$p is not private"; done
python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));assert d["version"]==1 and "events" in d' "$STATE/inbox-snapshot.json" || fail "the snapshot is not the documented shape"
echo "PASS: agent notifications → typed inbox events, the pane follows, focus acknowledges, files are private"
