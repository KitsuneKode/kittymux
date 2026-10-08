#!/usr/bin/env bash
# "What did the agent change?" in a real kitty: a fake agent idles, then works — editing files in a real git repository — then idles. The scanner takes a baseline when the run starts and the
# summary when it ends (a detached `kittymux checkpoint`); `kittymux changes` and `kittymux pick` report it. A file that was already dirty before the run must NOT be counted, ignored files
# must not be, and the repository itself must not be written to. Private kitty/state/socket; ends with the cross-kitty tripwire. Needs Xvfb, kitty, git, python3.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty git python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-chg.XXXXXX"); CFG=$T/cfg STATE=$T/state RUN=$T/run REPO=$T/repo
mkdir -p "$CFG" "$STATE" "$RUN" "$T/bin" "$REPO" && chmod 700 "$STATE" "$RUN"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; exit 1; }
for n in $(seq 171 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
# git starts a DETACHED `maintenance run --auto` after a commit; while it runs it keeps objects/maintenance.lock in the repository, and a listing of every file under
# objects/ then differed by that one transient file: the check below failed once in a while on CI. Maintenance is off for the rig's own git, and the check
# looks at real objects and packs only (a lock or a temp file is not an object), so it can only fail on a write that matters.
G="git -c maintenance.auto=false -c gc.auto=0 -c user.email=t@t -c user.name=t -c commit.gpgsign=false"
repo_objects() { ( cd "$REPO/.git/objects" && find . -type f | grep -E '^\./([0-9a-f]{2}/[0-9a-f]{38}|pack/[^/]+)$' | sort | md5sum ); }
( cd "$REPO" && git init -q && printf 'one\ntwo\n' > a.txt && printf 'build/\n' > .gitignore && git add . && $G commit -qm init )
printf 'dirty before the run\n' > "$REPO/earlier.txt"                       # uncommitted BEFORE the run: not the agent's work
objs_before=$(repo_objects)
cat > "$T/bin/claude" <<PY
#!/usr/bin/env python3
import os, sys, time
IDLE = "╭────╮\n│ >  │\n╰────╯\n? for shortcuts\n"
def screen(text): sys.stdout.write("\x1bc" + text); sys.stdout.flush()
screen(IDLE); time.sleep(7)                                           # the scanner sees it idle first: then a run START is real
screen("✻ Cogitating… (12s · esc to interrupt)\n")
time.sleep(5)                                                          # a real run works for a while: the scanner takes the baseline on its next tick, BEFORE the edits
os.chdir("$REPO")
with open("a.txt", "a") as f: f.write("three\nfour\nfive\n")           # +3
with open("new.py", "w") as f: f.write("x = 1\n" * 10)                 # +10, untracked
os.makedirs("build", exist_ok=True)
with open("build/out.bin", "w") as f: f.write("junk\n" * 50)           # ignored
time.sleep(5)
screen(IDLE)
while True: time.sleep(1)
PY
chmod +x "$T/bin/claude"
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'allow_remote_control socket-only\nlisten_on unix:${XDG_RUNTIME_DIR}/mykitty\ninclude %s/kittymux.conf\ngeninclude %s/python/kittymux_layout.py\ntab_bar_edge left\ntab_bar_min_tabs 1\n' "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
printf 'new_tab agent\ncd %s\nlaunch %s/bin/claude\nnew_tab other\nlaunch\nfocus_tab 1\n' "$REPO" "$T" > "$T/session"      # focus is on ANOTHER tab: the finished run is "done, unseen" and the bar draws its summary
export PATH="$T/bin:$PATH"
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_RUNTIME_DIR=$RUN KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
  KITTYMUX_SOCKET_DIRS=$RUN kitty -o linux_display_server=x11 --class kmx-chg --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 80); do ls "$RUN"/mykitty-* >/dev/null 2>&1 && break; sleep 0.25; done
SOCK=unix:$(ls "$RUN"/mykitty-* | head -1); KP=${SOCK##*-}
KMX() { env XDG_RUNTIME_DIR=$RUN KITTYMUX_SOCKET_DIRS=$RUN KITTYMUX_STATE=$STATE KITTYMUX_TARGET=$SOCK KITTYMUX_NOTIFY=0 python3 "$HOME_DIR/bin/kittymux" "$@"; }
others() { for s in /tmp/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
# wait for the run to start, work and finish (7 s idle + 5 s work + scan + helper)
CACHE=$STATE/changes-$KP.json
for _ in $(seq 80); do python3 - "$CACHE" <<'PY' && break
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if any(v.get("summary") for v in d.values()) else 1)
PY
  sleep 0.5; done
[ -s "$CACHE" ] || { ls "$STATE"; tail -5 "$T/k.log"; fail "no changes cache was written (the scanner never ran the checkpoint helper?)"; }
[ "$(stat -c %a "$CACHE")" = 600 ] || fail "the changes cache is not private"
python3 - "$CACHE" <<'PY' || fail "the summary is wrong (expected 2 files +13 −0 relative to the run START: a.txt +3, new.py +10; earlier.txt and build/ excluded)"
import json, sys
v = next(iter(json.load(open(sys.argv[1])).values()))
s = v["summary"]
print("   cached:", s["files"], "files", "+%d" % s["add"], "−%d" % s["del"], "vs", v["vs"])
raise SystemExit(0 if (s["files"], s["add"], s["del"], v["vs"]) == (2, 13, 0, "run") else 1)
PY
echo "  ok   baseline at run start, summary at run end: 2 files +13 (the dirty-before file and the ignored build/ are not the agent's)"
WID=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["tabs"][0]["windows"][0]["id"])')
out=$(KMX changes --window "$WID") || fail "kittymux changes failed"
echo "$out" | head -1 | grep -q "2 files +13" || { echo "$out"; fail "kittymux changes does not report 2 files +13"; }
echo "$out" | grep -q "new.py" || fail "kittymux changes does not list the changed files"
echo "$out" | grep -q "earlier.txt" && fail "a file that was dirty before the run is listed as the agent's work"
KMX changes --all | grep -q "2 files +13" || fail "changes --all does not show the cached summary"
KMX changes --bogus >/dev/null 2>&1; [ $? = 2 ] || fail "unknown options must be refused"
KMX pick --list | grep -q "Δ 2 files +13" || { KMX pick --list; fail "pick does not show the change summary on the agent's row"; }
echo "  ok   kittymux changes (live) / --all / pick rows agree"
python3 - "$STATE/scan-$KP.json" <<'PY' || fail "the agent's verdict is not done (the bar's finished-tab summary path was not exercised)"
import json, sys
d = json.load(open(sys.argv[1]))
raise SystemExit(0 if any(v.get("state") == "done" for v in d.values()) else 1)
PY
[ ! -s "$STATE/tab_bar-error.log" ] || { sed 's/^/  | /' "$STATE/tab_bar-error.log" | tail -8; fail "the tab bar logged an error drawing a finished tab with a change summary"; }
echo "  ok   a finished tab with a summary draws without a tab bar error"
[ "$(repo_objects)" = "$objs_before" ] || fail "the repository's object store was written to (an object or a pack was added or removed)"
[ ! -e "$REPO/.git/index.lock" ] || fail "an index lock was left behind"
echo "  ok   the repository was not written to (no new objects, no lock)"
[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty on this machine"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: what the agent changed is recorded at run start/end, reported, and never touches the repository"
