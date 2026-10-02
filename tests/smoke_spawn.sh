#!/usr/bin/env bash
# Spawn, pick, reopen, mute and snooze in a REAL kitty (socket-only, private config/state/socket; fake agents): `kittymux spawn` puts agents into a new tab (before the scratch
# tab, in the current directory) or a split; the spawn-mode KEYS do the same with real key events; `kittymux pick` lists them and a fake rofi's answer is executed (spawn, jump, ack);
# `kittymux reopen` brings a closed conversation back through the resume prompt; mute/snooze write what the scanner reads. Needs Xvfb, xdotool, kitty, python3.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-spawn.XXXXXX"); CFG=$T/cfg STATE=$T/state RUN=$T/run
mkdir -p "$CFG" "$STATE" "$RUN" "$T/bin" "$T/ran" "$T/a" "$T/b" && chmod 700 "$STATE" "$RUN"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; exit 1; }
for n in $(seq 161 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
# fake agents: answer --help like the real CLIs (resume probe), otherwise record "<cwd> <args>" and stay alive
mk() {
  cat > "$T/bin/$1" <<PY
#!/usr/bin/env python3
import os, sys, time
if "--help" in sys.argv:
    print("""  -r, --resume [value]  Resume a conversation by session ID
  -c, --continue   Continue the most recent conversation
  resume, --last""")
    sys.exit(0)
with open(os.path.join("$T/ran", "$1." + str(os.getpid())), "w") as f:
    f.write(os.getcwd() + " " + " ".join(sys.argv[1:]))
time.sleep(600)
PY
  chmod +x "$T/bin/$1"
}
mk claude; mk codex
# an agent that is genuinely NOT installed on this machine (the host's own agents are on PATH too): chosen at run time so the rig does not depend on the host
ABSENT=$(for a in amp gemini droid grok agy devin cursor-agent opencode; do command -v "$a" >/dev/null 2>&1 || { echo "$a"; break; }; done)
# a fake rofi: logs the rows it was given, answers the index of the first row containing $ROFI_PICK (exit $ROFI_RC, default 0)
cat > "$T/bin/rofi" <<'SH'
#!/usr/bin/env bash
cat > "$ROFI_LOG"
[ -n "${ROFI_PICK:-}" ] || exit 1
i=$(grep -a -n -F -- "$ROFI_PICK" "$ROFI_LOG" | head -1 | cut -d: -f1)
[ -n "$i" ] || exit 1
echo $((i - 1)); exit "${ROFI_RC:-0}"
SH
chmod +x "$T/bin/rofi"
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
sed "s|@KITTYMUX_HOME@|$HOME_DIR|g" "$HOME_DIR/kittymux-keys.conf.tpl" > "$CFG/kittymux-keys.conf"
printf 'allow_remote_control socket-only\nlisten_on unix:${XDG_RUNTIME_DIR}/mykitty\ninclude %s/kittymux.conf\ninclude %s/kittymux-keys.conf\ngeninclude %s/python/kittymux_layout.py\n' "$HOME_DIR" "$CFG" "$HOME_DIR" > "$CFG/kitty.conf"
cat > "$T/session" <<S
new_tab main
cd $T/a
launch --title shell sh
new_tab !scratch
cd $T/b
launch --title scratch sh
focus_tab 0
S
export PATH="$T/bin:$PATH"
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_RUNTIME_DIR=$RUN KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
  KITTYMUX_SOCKET_DIRS=$RUN \
  kitty -o linux_display_server=x11 --class kmx-spawn --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 80); do ls "$RUN"/mykitty-* >/dev/null 2>&1 && break; sleep 0.25; done; sleep 3
SOCK=unix:$(ls "$RUN"/mykitty-* | head -1)
KMX() { env XDG_RUNTIME_DIR=$RUN KITTYMUX_SOCKET_DIRS=$RUN KITTYMUX_STATE=$STATE KITTYMUX_TARGET=$SOCK XDG_CONFIG_HOME=$T/xdg KITTYMUX_NOTIFY=${KMX_NOTIFY:-0} python3 "$HOME_DIR/bin/kittymux" "$@"; }
X() { DISPLAY=$DISP xdotool "$@"; }
ls_json() { kitty @ --to "$SOCK" ls; }
tabs() { ls_json | python3 -c 'import sys,json
d=json.load(sys.stdin)[0]["tabs"]
for t in d: print(t["title"], "|", ",".join(" ".join(p["cmdline"])[:220] for w in t["windows"] for p in w["foreground_processes"]))'; }
ntabs() { ls_json | python3 -c 'import sys,json;print(len(json.load(sys.stdin)[0]["tabs"]))'; }
nwin_active() { ls_json | python3 -c 'import sys,json
for t in json.load(sys.stdin)[0]["tabs"]:
    if t["is_active"]: print(len(t["windows"]))'; }
last_title() { ls_json | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["tabs"][-1]["title"])'; }
ran() { for f in "$T"/ran/*; do [ -e "$f" ] && printf '%s: %s\n' "$(basename "$f" | cut -d. -f1)" "$(cat "$f")"; done; }
wait_ran() { for _ in $(seq 40); do ran | grep -q -- "$1" && return 0; sleep 0.25; done; return 1; }
base=$(ntabs)
# tripwire: this rig must never touch any OTHER kitty (the person running it may be typing in one): count their windows now, compare at the end
others() { for s in /tmp/mykitty-* "${REAL_RUNTIME:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)

# 1. spawn a tab: a new tab, the agent in the CURRENT directory, the scratch tab still last
KMX spawn claude >/dev/null || fail "spawn claude failed"
wait_ran "^claude: $T/a " || { ran; fail "claude did not start in the current directory ($T/a)"; }
[ "$(ntabs)" = $((base + 1)) ] || fail "spawn did not add exactly one tab"
case "$(last_title)" in '!scratch'*) ;; *) tabs; fail "the scratch tab is no longer last";; esac
echo "  ok   spawn claude: a new tab, started in the current directory, scratch tab still last"

# 2. a split of the focused tab
kitty @ --to "$SOCK" focus-tab --match title:claude >/dev/null 2>&1; sleep 0.3
KMX spawn codex --vsplit >/dev/null || fail "spawn codex --vsplit failed"
wait_ran "^codex:" || fail "codex did not start"
[ "$(nwin_active)" = 2 ] || { tabs; fail "--vsplit did not add a pane to the active tab"; }
echo "  ok   spawn codex --vsplit: a second pane in the active tab"

# 3. several at once, and refusals
before=$(ntabs)
KMX spawn claude,codex >/dev/null || fail "spawn claude,codex failed"
sleep 1; [ "$(ntabs)" = $((before + 2)) ] || fail "claude,codex should open two tabs"
KMX spawn nosuch >/dev/null 2>"$T/err"; [ $? = 1 ] && grep -q "not a known agent" "$T/err" || fail "spawn nosuch should be refused"
if [ -n "$ABSENT" ]; then
  KMX spawn "$ABSENT" >/dev/null 2>"$T/err"; [ $? = 1 ] && grep -q "not installed" "$T/err" || fail "an agent that is not installed ($ABSENT) should be refused"
fi
KMX spawn "claude; rm -rf ~" >/dev/null 2>&1; [ $? = 1 ] || fail "a hostile name must be refused"
echo "  ok   spawn claude,codex: two tabs; unknown / not-installed / hostile names refused"

# 4. the spawn-mode keys, with real key events
W=$(X search --onlyvisible --class kmx-spawn | head -1); X windowfocus "$W" 2>/dev/null; sleep 0.5
before=$(ntabs); : > "$T/ran.mark"; ran > "$T/ran.before"
X key --clearmodifiers ctrl+alt+shift+o; sleep 0.4; X key --clearmodifiers c; sleep 2
[ "$(ntabs)" = $((before + 1)) ] || { tabs; fail "ctrl+alt+shift+o then c did not open a tab"; }
[ "$(ran | wc -l)" -gt "$(wc -l < "$T/ran.before")" ] || fail "the key did not start an agent"
before=$(ntabs)
X key --clearmodifiers ctrl+alt+shift+o; sleep 0.4; X key --clearmodifiers q; sleep 1                    # an unknown key cancels the mode and spawns nothing
[ "$(ntabs)" = "$before" ] || fail "an unknown key in spawn mode must spawn nothing"
echo "  ok   keys: ctrl+alt+shift+o then c opens an agent tab; an unknown key cancels"

# 5. pick: the rows
out=$(KMX pick --list) || fail "pick --list failed"
echo "$out" | grep -q "claude" || fail "pick does not list the running agents"
echo "$out" | grep -q "new codex   tab" || fail "pick does not offer a new codex"
[ -z "$ABSENT" ] || { echo "$out" | grep -q "new $ABSENT " && fail "pick offers an agent that is not installed ($ABSENT)"; }
echo "  ok   pick --list: running agents and installed-only new-agent rows"

# 6. pick through a (fake) rofi: choosing a new-agent row spawns it; choosing a running agent jumps to it
export ROFI_LOG=$T/rofi.log
before=$(ntabs)
ROFI_PICK="new codex   tab" KMX pick --menu rofi || fail "pick via rofi failed"
sleep 1; [ "$(ntabs)" = $((before + 1)) ] || fail "choosing 'new codex tab' did not open a tab"
grep -q "claude" "$ROFI_LOG" || fail "rofi was not given the rows"
kitty @ --to "$SOCK" focus-tab --match title:shell >/dev/null 2>&1; sleep 0.3
ROFI_PICK="claude" KMX pick --menu rofi >/dev/null || fail "jump via rofi failed"
sleep 0.5
ls_json | python3 -c 'import sys,json
for t in json.load(sys.stdin)[0]["tabs"]:
    if t["is_active"] and any("claude" in " ".join(p["cmdline"]) for w in t["windows"] for p in w["foreground_processes"]): raise SystemExit(0)
raise SystemExit(1)' || fail "choosing a running claude did not jump to its tab"
echo "  ok   pick via rofi: a spawn row opens a tab; a running-agent row jumps to it"

# 7. needs-you events come first, and alt+a (rofi custom key) marks one read without jumping
CLW=$(ls_json | python3 -c 'import sys,json
for t in json.load(sys.stdin)[0]["tabs"]:
    for w in t["windows"]:
        if any("claude" in " ".join(p["cmdline"]) for p in w["foreground_processes"]): print(w["id"]); raise SystemExit')
PIDK=$(basename "${SOCK#unix:}" | cut -d- -f2)
python3 - "$HOME_DIR" "$STATE" "$CLW" "$PIDK" <<'PY'
import sys, time
sys.path.insert(0, sys.argv[1] + "/python")
import kittymux_inbox as I
ev = I.make_event("permission", "claude", sys.argv[3], "hook", time.time() - 300, pid=int(sys.argv[4]), tab="api", title="claude needs permission", body="Approve: run the tests?")
I.add(sys.argv[2], ev)
PY
KMX pick --list | head -1 | grep -q "^◆" || { KMX pick --list | head -3; fail "a needs-you event is not the first row"; }
ROFI_PICK="Approve: run the tests" ROFI_RC=10 KMX pick --menu rofi >/dev/null || fail "alt+a failed"
KMX inbox --json 2>/dev/null | python3 -c 'import sys,json
d=json.load(sys.stdin)
ev=d if isinstance(d,list) else d.get("events",[])
raise SystemExit(0 if all(e.get("status")!="unread" for e in ev) else 1)' || fail "alt+a did not mark the event read"
echo "  ok   pick: needs-you first; alt+a marks it read"

# 8. reopen: a closed conversation comes back through the resume prompt, in a new tab, in its directory
python3 - "$HOME_DIR" "$STATE" "$T/a" "$T/bin/claude" <<'PY'
import sys, time
sys.path.insert(0, sys.argv[1] + "/python")
import kittymux_journal as J
recs = {}
J.observe(recs, {"agent": "claude", "sid": "0a1b2c3d-0000-4000-8000-000000000009", "cwd": sys.argv[3], "tab": "api work", "argv": [sys.argv[4], "--model", "x"],
                 "state": "idle", "kitty_pid": 2 ** 22 + 7, "wid": 1, "mode": ""}, time.time() - 120)
J.flush(sys.argv[2], recs, time.time())
PY
before=$(ntabs)
KMX reopen >/dev/null 2>"$T/err" || { cat "$T/err"; fail "reopen failed"; }
sleep 2; [ "$(ntabs)" = $((before + 1)) ] || fail "reopen did not open a tab"
tabs | grep -q "resume-prompt" || { tabs; fail "the reopened tab is not asking before resuming"; }
echo "  ok   reopen: the closed conversation is back in a new tab, asking before it resumes"

# 9. mute and snooze write what the scanner reads
KMX notify mute 30m >/dev/null || fail "notify mute failed"
[ "$(stat -c %a "$STATE/notify-mute-until")" = 600 ] || fail "the mute file is not private"
KMX_NOTIFY=1 KMX notify status | grep -q "muted for another" || fail "status does not show the mute"
KMX notify mute banana >/dev/null 2>&1; [ $? = 2 ] || fail "a bad duration must be refused"
KMX notify unmute >/dev/null; [ ! -e "$STATE/notify-mute-until" ] || fail "unmute left the file"
KMX snooze 1h --window "$CLW" >/dev/null || fail "snooze failed"
SF=$(ls "$STATE"/snoozes-*.json 2>/dev/null | head -1)
[ -n "$SF" ] && [ "$(stat -c %a "$SF")" = 600 ] && grep -q "\"$CLW\"" "$SF" || { ls "$STATE"; fail "snooze did not write a private snooze file for window $CLW"; }
ls_json | python3 -c 'import sys,json
for t in json.load(sys.stdin)[0]["tabs"]:
    for w in t["windows"]:
        if "kittymux_snooze_until" in w["user_vars"]: raise SystemExit(1)' || fail "snooze must not be a window variable (a program in the window could set it)"
KMX snooze 1h --window 999999 >/dev/null 2>&1; [ $? = 1 ] || fail "snooze of a window that does not exist must be refused"
KMX snooze --clear --window "$CLW" >/dev/null || fail "snooze --clear failed"
grep -q "\"$CLW\"" "$SF" && fail "snooze --clear left the window in the file"
echo "  ok   notify mute/unmute/status and snooze/--clear"
[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty on this machine (before: $OTHERS_BEFORE after: $(others))"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: spawn, pick, reopen, mute and snooze work in a real kitty (socket-only)"
