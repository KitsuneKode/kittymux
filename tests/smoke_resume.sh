#!/usr/bin/env bash
# Save → restore with agent resume, in real kitties. Fake agents (runtime-launched scripts, as node-based agents appear) record how they were STARTED:
# after `kittymux sessions save` + a restore in a second kitty, the Claude window must have been started with `--resume <its session id>`, a lone opencode
# with `-c`, two droids sharing a directory as saved (never one conversation opened twice), and no restored hook state. Needs Xvfb, kitty, python3.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-resume.XXXXXX"); CFG=$T/cfg STATE=$T/state; SOCK1=unix:$T/mykitty-5551; SOCK2=unix:$T/mykitty-5552
mkdir -p "$CFG" "$STATE" "$T/bin" "$T/ran" "$T/ch/sessions" "$T/a" "$T/b" "$T/c" && chmod 700 "$STATE"
XPID="" K1="" K2=""
cleanup() { [ -n "$K1" ] && kill "$K1" 2>/dev/null; [ -n "$K2" ] && kill "$K2" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
# fake agents: they answer --help like the real CLIs (so the probe passes) and otherwise record their argv and stay alive
mk() {   # mk <name> <help text>
  cat > "$T/bin/$1" <<PY
#!/usr/bin/env python3
import os, sys, time
if "--help" in sys.argv:
    print("""$2""")
    sys.exit(0)
with open(os.path.join("$T/ran", "$1." + str(os.getpid())), "w") as f:
    f.write(" ".join(sys.argv[1:]))
time.sleep(600)
PY
  chmod +x "$T/bin/$1"
}
mk claude "  -c, --continue   Continue the most recent conversation
  -r, --resume [value]  Resume a conversation by session ID. --resume <session-id>"
mk opencode "  --continue, -c  Continue the last session
  --session, -s string  Session ID"
mk droid "  -r, --resume [sessionId]   Resume a session
  --last   With --resume: skip the picker"
for f in tab_bar.py kittymux_theme.py kittymux_deck.py kittymux_git.py kittymux_layout.py kittymux_barsize.py kittymux_agents.py kittymux_state.py kittymux_scan.py kittymux_inbox.py kittymux_resume.py; do
  ln -s "$HOME_DIR/python/$f" "$CFG/$f"
done
printf 'allow_remote_control yes\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
cat > "$T/session1" <<S
new_tab main
cd $T/a
launch --title cl claude --dangerously-skip-permissions
new_tab other
cd $T/b
launch --title oc opencode
launch --location=vsplit --title shell sh
new_tab twin
cd $T/c
launch --title d1 droid
launch --location=vsplit --title d2 droid
focus_tab 0
S
export PATH="$T/bin:$PATH"
start() {   # start <session file> <socket>
  env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
    kitty -o linux_display_server=x11 --listen-on "$2" --session "$1" >"$T/k.$$.log" 2>&1 &
  echo $!
}
K1=$(start "$T/session1" "$SOCK1")
for _ in $(seq 60); do [ -S "$T/mykitty-5551" ] && break; sleep 0.25; done; sleep 4
ls_json() { kitty @ --to "$1" ls; }
CLPID=$(ls_json $SOCK1 | python3 -c 'import sys,json
for t in json.load(sys.stdin)[0]["tabs"]:
    for w in t["windows"]:
        for p in w["foreground_processes"]:
            if p["cmdline"][-2:-1] and p["cmdline"][1].endswith("/claude"): print(p["pid"]); raise SystemExit')
[ -n "$CLPID" ] || fail "the fake claude is not running in the first kitty"
SID=4d4710c8-de7d-4c89-b7d2-c76a51f6fed7
START=$(python3 -c 'import sys;print(open("/proc/%s/stat"%sys.argv[1]).read().rsplit(")",1)[1].split()[19])' "$CLPID")
printf '{"pid": %s, "sessionId": "%s", "cwd": "%s", "procStart": %s, "status": "idle"}' "$CLPID" "$SID" "$T/a" "$START" > "$T/ch/sessions/$CLPID.json"
KMX() { KITTYMUX_STATE=$STATE KITTYMUX_TARGET=$SOCK1 KITTYMUX_CLAUDE_HOME=$T/ch XDG_CONFIG_HOME=$T/xdg python3 "$HOME_DIR/bin/kittymux" "$@"; }

out=$(KMX sessions list) || fail "sessions list failed: $out"
echo "$out" | grep -q "exact session" && echo "$out" | grep -q "latest in dir" || fail "list does not show an exact and a latest window: $out"
echo "$out" | grep -q "several droid windows" || fail "list does not explain the two droids: $out"
echo "  ok   sessions list: claude exact, opencode latest, the two droids explained"

KMX sessions check >/dev/null 2>&1; true
KMX sessions save test --all >"$T/save.out" 2>&1 || { cat "$T/save.out"; fail "sessions save failed"; }
F=$STATE/sessions/test.kitty-session
[ -s "$F" ] || fail "no session file"
[ "$(stat -c %a "$F")" = 600 ] || fail "the session file is not private"
grep -q -- "--resume $SID" "$F" || { cat "$F"; fail "the saved claude line does not resume its session"; }
grep -q -- "--dangerously-skip-permissions" "$F" || fail "the flags claude was started with were lost"
grep -E "opencode" "$F" | grep -q -- " -c" || fail "the lone opencode is not 'continue latest'"
[ "$(grep -c "bin/droid" "$F")" = 2 ] || { cat "$F"; fail "expected two droid launch lines"; }
! grep "bin/droid" "$F" | grep -qE " (-r|--last)( |'|$)" || { grep "bin/droid" "$F"; fail "the two droids were rewritten (one conversation would open twice)"; }
! grep -q "kittymux_status\|kittymux_msg" "$F" || fail "restored hook state leaked into the saved file"
echo "  ok   saved: claude --resume <id> with its flags, opencode -c, droids as saved, no stale hook state, file is 0600"

# autosave: the same save, silently, to autosave-<pid>.kitty-session, pruned to the newest 5
for i in 1 2 3 4 5 6 7; do : > "$STATE/sessions/autosave-90$i.kitty-session"; touch -d "@$((1000 + i))" "$STATE/sessions/autosave-90$i.kitty-session"; done
KMX sessions autosave || fail "sessions autosave failed"
[ -s "$STATE/sessions/autosave-5551.kitty-session" ] && grep -q -- "--resume $SID" "$STATE/sessions/autosave-5551.kitty-session" || fail "autosave did not write a resumable session"
[ "$(ls "$STATE"/sessions/autosave-*.kitty-session | wc -l)" = 5 ] || fail "autosave did not prune to the newest 5 ($(ls "$STATE"/sessions/autosave-*.kitty-session | wc -l))"
echo "  ok   autosave: resumable file written silently, older autosaves pruned to 5"
ls "$T/ran" > "$T/ran.before"        # what the FIRST kitty started; only what the second one starts counts below
K2=$(start "$F" "$SOCK2")
for _ in $(seq 60); do [ -S "$T/mykitty-5552" ] && break; sleep 0.25; done; sleep 5
ran() { for f in "$T"/ran/*; do grep -qx "$(basename "$f")" "$T/ran.before" || printf '%s: %s\n' "$(basename "$f" | cut -d. -f1)" "$(cat "$f")"; done; }
ran | grep -q "^claude: --dangerously-skip-permissions --resume $SID$" || { ran; fail "the restored claude was not started with --resume $SID"; }
ran | grep -q "^opencode: -c$" || { ran; fail "the restored opencode was not started with -c"; }
[ "$(ran | grep -c '^droid: $')" = 2 ] || { ran; fail "the restored droids were not started as saved (plain, twice)"; }
echo "  ok   restored in a second kitty: claude started with --resume $SID, opencode with -c, both droids plain"
echo "PASS: sessions save/restore resume agents with their conversations"
