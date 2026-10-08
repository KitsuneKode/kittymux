#!/usr/bin/env bash
# Save → restore with agent resume, in real kitties (default: the restored window ASKS; --direct writes the resume command itself). Fake agents (runtime-launched scripts, as node-based agents appear) record how they were STARTED:
# after `kittymux sessions save` + a restore in a second kitty, the Claude window must have been started with `--resume <its session id>`, a lone opencode
# with `-c`, two droids sharing a directory as saved (never one conversation opened twice), and no restored hook state. Needs Xvfb, kitty, python3.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-resume.XXXXXX"); CFG=$T/cfg STATE=$T/state; SOCK1=unix:$T/mykitty-5551; SOCK2=unix:$T/mykitty-5552; SOCK3=unix:$T/mykitty-5553
mkdir -p "$CFG" "$STATE" "$T/bin" "$T/ran" "$T/ch/sessions" "$T/a" "$T/b" "$T/c" && chmod 700 "$STATE"
XPID="" K1="" K2="" K3=""
cleanup() { [ -n "$K1" ] && kill "$K1" 2>/dev/null; [ -n "$K2" ] && kill "$K2" 2>/dev/null; [ -n "$K3" ] && kill "$K3" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
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
mk_oc() {   # a fake opencode: answers `session list --format json` for its directory, otherwise records its argv and stays alive
  cat > "$T/bin/opencode" <<PY
#!/usr/bin/env python3
import json, os, sys, time
if "--help" in sys.argv:
    print("""  --continue, -c  Continue the last session
  --session, -s string  Session ID""")
    sys.exit(0)
if sys.argv[1:3] == ["session", "list"]:
    print(json.dumps([{"id": "ses_smoke1", "title": "t", "updated": int(time.time() * 1000), "created": 1, "directory": os.getcwd()}]))
    sys.exit(0)
with open(os.path.join("$T/ran", "opencode." + str(os.getpid())), "w") as f:
    f.write(" ".join(sys.argv[1:]))
time.sleep(600)
PY
  chmod +x "$T/bin/opencode"
}
mk claude "  -c, --continue   Continue the most recent conversation
  -r, --resume [value]  Resume a conversation by session ID. --resume <session-id>"
mk_oc
mk droid "  -r, --resume [sessionId]   Resume a session
  --last   With --resume: skip the picker"
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do
  ln -s "$f" "$CFG/$(basename "$f")"
done
printf 'allow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
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
  env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
    kitty -o linux_display_server=x11 --listen-on "$2" --session "$1" >"$T/k.$$.log" 2>&1 &
  echo $!
}
K1=$(start "$T/session1" "$SOCK1")
for _ in $(seq 240); do [ -S "$T/mykitty-5551" ] && break; sleep 0.25; done; sleep 4
ls_json() { kitty @ --to "$1" ls; }
CLPID=$(ls_json $SOCK1 | python3 -c 'import sys,json
for t in json.load(sys.stdin)[0]["tabs"]:
    for w in t["windows"]:
        for p in w["foreground_processes"]:
            if p["cmdline"][-2:-1] and p["cmdline"][1].endswith("/claude"): print(p["pid"]); raise SystemExit')
[ -n "$CLPID" ] || fail "the fake claude is not running in the first kitty"
SID=0a1b2c3d-0000-4000-8000-000000000001
START=$(python3 -c 'import sys;print(open("/proc/%s/stat"%sys.argv[1]).read().rsplit(")",1)[1].split()[19])' "$CLPID")
printf '{"pid": %s, "sessionId": "%s", "cwd": "%s", "procStart": %s, "status": "idle"}' "$CLPID" "$SID" "$T/a" "$START" > "$T/ch/sessions/$CLPID.json"
KMX() { KITTYMUX_STATE=$STATE KITTYMUX_TARGET=$SOCK1 KITTYMUX_CLAUDE_HOME=$T/ch XDG_CONFIG_HOME=$T/xdg python3 "$HOME_DIR/bin/kittymux" "$@"; }

out=$(KMX sessions list) || fail "sessions list failed: $out"
echo "$out" | grep -q "opencode .*exact session.*-s ses_smoke1" || fail "the lone opencode is not resolved to its own conversation (touched since it started): $out"
echo "$out" | grep -q "several droid windows" || fail "list does not explain the two droids: $out"
echo "  ok   sessions list: claude exact, opencode exact via its own session list, the two droids explained"

KMX sessions check >/dev/null 2>&1; true
KMX sessions save test --all --direct >"$T/save.out" 2>&1 || { cat "$T/save.out"; fail "sessions save failed"; }
F=$STATE/sessions/test.kitty-session
[ -s "$F" ] || fail "no session file"
[ "$(stat -c %a "$F")" = 600 ] || fail "the session file is not private"
grep -q -- "--resume $SID" "$F" || { cat "$F"; fail "the saved claude line does not resume its session"; }
grep -q -- "--dangerously-skip-permissions" "$F" || fail "the flags claude was started with were lost"
grep -E "opencode" "$F" | grep -q -- "-s ses_smoke1" || { cat "$F"; fail "the lone opencode did not resolve to -s ses_smoke1"; }
[ "$(grep -c "bin/droid" "$F")" = 2 ] || { cat "$F"; fail "expected two droid launch lines"; }
! grep "bin/droid" "$F" | grep -qE " (-r|--last)( |'|$)" || { grep "bin/droid" "$F"; fail "the two droids were rewritten (one conversation would open twice)"; }
! grep -q "kittymux_status\|kittymux_msg" "$F" || fail "restored hook state leaked into the saved file"
echo "  ok   saved: claude --resume <id> with its flags, opencode -s <its id>, droids as saved, no stale hook state, file is 0600"

# autosave: the same save, silently, to autosave-<pid>.kitty-session, pruned to the newest 5
for i in 1 2 3 4 5 6 7; do : > "$STATE/sessions/autosave-90$i.kitty-session"; touch -d "@$((1000 + i))" "$STATE/sessions/autosave-90$i.kitty-session"; done
KMX sessions autosave || fail "sessions autosave failed"
[ -s "$STATE/sessions/autosave-5551.kitty-session" ] && grep -q "resume-prompt.*$SID" "$STATE/sessions/autosave-5551.kitty-session" || fail "autosave did not write a resumable session"
[ "$(ls "$STATE"/sessions/autosave-*.kitty-session | wc -l)" = 5 ] || fail "autosave did not prune to the newest 5 ($(ls "$STATE"/sessions/autosave-*.kitty-session | wc -l))"
echo "  ok   autosave: resumable file written silently, older autosaves pruned to 5"
ls "$T/ran" > "$T/ran.before"        # what the FIRST kitty started; only what the second one starts counts below
K2=$(start "$F" "$SOCK2")
for _ in $(seq 240); do [ -S "$T/mykitty-5552" ] && break; sleep 0.25; done; sleep 5
ran() { for f in "$T"/ran/*; do grep -qx "$(basename "$f")" "$T/ran.before" || printf '%s: %s\n' "$(basename "$f" | cut -d. -f1)" "$(cat "$f")"; done; }
ran | grep -q "^claude: --dangerously-skip-permissions --resume $SID$" || { ran; fail "the restored claude was not started with --resume $SID"; }
ran | grep -q "^opencode: -s ses_smoke1$" || { ran; fail "the restored opencode was not started with -s ses_smoke1"; }
[ "$(ran | grep -c '^droid: $')" = 2 ] || { ran; fail "the restored droids were not started as saved (plain, twice)"; }
echo "  ok   restored in a second kitty: claude started with --resume $SID, opencode with -s ses_smoke1, both droids plain"
echo "  ok   --direct restore: agents resumed without asking"

# default save: the same windows come back ASKING. Nothing runs until answered; Enter resumes (all flags), n starts new, a window with nothing to resume is untouched.
KMX sessions save ask --all >"$T/save2.out" 2>&1 || { cat "$T/save2.out"; fail "sessions save (prompt mode) failed"; }
F2=$STATE/sessions/ask.kitty-session
[ "$(grep -c "resume-prompt" "$F2")" = 2 ] || { cat "$F2"; fail "expected the claude and opencode windows to ask (2 resume-prompt lines)"; }
! grep "bin/droid" "$F2" | grep -q "resume-prompt" || fail "the ambiguous droids must not get a prompt"
ls "$T/ran" > "$T/ran.before"
K3=$(start "$F2" "$SOCK3")
for _ in $(seq 240); do [ -S "$T/mykitty-5553" ] && break; sleep 0.25; done; sleep 5
ran | grep -q "^claude:" && { ran; fail "claude started before the prompt was answered"; }
ran | grep -q "^opencode:" && { ran; fail "opencode started before the prompt was answered"; }
WINS=$(kitty @ --to $SOCK3 ls | python3 -c 'import sys,json
for t in json.load(sys.stdin)[0]["tabs"]:
    for w in t["windows"]:
        c = " ".join(p["cmdline"][-1] for p in w["foreground_processes"] if p["cmdline"])
        for p in w["foreground_processes"]:
            if "resume-prompt" in " ".join(p["cmdline"]):
                info = p["cmdline"][-1]
                print(w["id"], "claude" if "\"agent\":\"claude\"" in info else "opencode")')
[ "$(echo "$WINS" | wc -l)" = 2 ] || { echo "$WINS"; fail "the two prompts are not waiting in the restored kitty"; }
CW=$(echo "$WINS" | awk '$2=="claude"{print $1}'); OW=$(echo "$WINS" | awk '$2=="opencode"{print $1}')
kitty @ --to $SOCK3 get-text --match id:$CW | grep -q "resume session 0a1b2c3d" || { kitty @ --to $SOCK3 get-text --match id:$CW; fail "the claude prompt does not name its session"; }
echo "  ok   restore asks: two prompts waiting, nothing started, the session named on screen"
kitty @ --to $SOCK3 send-text --match id:$CW '\r'
kitty @ --to $SOCK3 send-text --match id:$OW 'n'
sleep 3
ran | grep -q "^claude: --dangerously-skip-permissions --resume $SID$" || { ran; fail "Enter did not resume claude with its flags"; }
ran | grep -qx "opencode: " || { ran; fail "n did not start opencode as a new conversation (its original command)"; }
echo "  ok   Enter resumes claude --resume <id> with its flags; n starts opencode as saved"

# the journal: the scanner recorded the live agents, so history and recovery know them
for _ in $(seq 20); do [ -s "$STATE/agent-sessions.json" ] && break; sleep 1; done
[ -s "$STATE/agent-sessions.json" ] && [ "$(stat -c %a "$STATE/agent-sessions.json")" = 600 ] || fail "the scanner did not write the private agent journal"
KMX sessions history | grep -q "claude" || { KMX sessions history; fail "history does not list the claude session"; }
echo "  ok   journal: the live agents are recorded (0600) and 'sessions history' lists them"
echo "PASS: sessions save/restore resume agents with their conversations"
