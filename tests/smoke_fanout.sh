#!/usr/bin/env bash
# `kittymux fanout` in a real kitty: one prompt to three fake agents, each started in its OWN git worktree/branch in its own tab, with the prompt in that CLI's own form (claude positional,
# devin after `--`, opencode via --prompt). Then `fanout compare` sees what each did (committed or not) relative to the base, `clean` keeps a worktree with uncommitted work, and the main
# checkout is never touched. Private kitty/state/socket; ends with the cross-kitty tripwire. Needs Xvfb, kitty, git, python3.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb kitty git python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-fan.XXXXXX"); CFG=$T/cfg STATE=$T/state RUN=$T/run REPO=$T/repo
mkdir -p "$CFG" "$STATE" "$RUN" "$T/bin" "$T/ran" "$REPO" && chmod 700 "$STATE" "$RUN"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; exit 1; }
for n in $(seq 171 199); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
G="git -c user.email=t@t -c user.name=t -c commit.gpgsign=false"
( cd "$REPO" && git init -q -b main && git config gc.auto 0 && printf 'one\n' > a.txt && git add . && $G commit -qm init )
for a in claude devin opencode; do
  cat > "$T/bin/$a" <<PY
#!/usr/bin/env python3
import os, sys, time
with open(os.path.join("$T/ran", "$a." + str(os.getpid())), "w") as f:
    f.write(os.getcwd() + "\n" + "\x1f".join(sys.argv[1:]))
time.sleep(600)
PY
  chmod +x "$T/bin/$a"
done
printf 'allow_remote_control socket-only\nlisten_on unix:${XDG_RUNTIME_DIR}/mykitty\ninclude %s/kittymux.conf\ngeninclude %s/python/kittymux_layout.py\n' "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'new_tab main\ncd %s\nlaunch --title shell sh\nnew_tab !scratch\nlaunch sh\nfocus_tab 0\n' "$REPO" > "$T/session"
export PATH="$T/bin:$PATH"
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_RUNTIME_DIR=$RUN KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
  KITTYMUX_SOCKET_DIRS=$RUN kitty -o linux_display_server=x11 --class kmx-fan --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 80); do ls "$RUN"/mykitty-* >/dev/null 2>&1 && break; sleep 0.25; done; sleep 2
SOCK=unix:$(ls "$RUN"/mykitty-* | head -1)
KMX() { env XDG_RUNTIME_DIR=$RUN KITTYMUX_SOCKET_DIRS=$RUN KITTYMUX_STATE=$STATE KITTYMUX_TARGET=$SOCK KITTYMUX_NOTIFY=0 python3 "$HOME_DIR/bin/kittymux" "$@"; }
others() { for s in /tmp/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
ntabs() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;print(len(json.load(sys.stdin)[0]["tabs"]))'; }
before=$(ntabs)
PROMPT='refactor the parser; keep `tests` green'
KMX fanout "$PROMPT" claude,devin,opencode --name t1 --cwd "$REPO" >"$T/out" 2>&1 || { cat "$T/out"; fail "fanout failed"; }
for _ in $(seq 40); do [ "$(ls "$T/ran" | wc -l)" -ge 3 ] && break; sleep 0.25; done
[ "$(ls "$T/ran" | wc -l)" = 3 ] || { cat "$T/out"; ls "$T/ran"; fail "three agents did not start"; }
[ "$(ntabs)" = $((before + 3)) ] || fail "expected three new tabs"
kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
t=[x["title"] for x in json.load(sys.stdin)[0]["tabs"]]
raise SystemExit(0 if t[-1].startswith("!scratch") and "claude · t1" in t and "devin · t1" in t and "opencode · t1" in t else 1)' || fail "the tabs are not titled '<agent> · t1' with scratch still last"
for a in claude devin opencode; do
  f=$(ls "$T"/ran/$a.*); cwd=$(sed -n 1p "$f"); args=$(sed -n 2p "$f")
  [ "$cwd" = "$REPO/.worktrees/t1-$a" ] || fail "$a did not start in its own worktree (started in $cwd)"
  case $a in
    claude)   want="$PROMPT" ;;
    devin)    want="--"$'\x1f'"$PROMPT" ;;
    opencode) want="--prompt"$'\x1f'"$PROMPT" ;;
  esac
  [ "$args" = "$want" ] || fail "$a got the wrong arguments: [$args] (wanted [$want])"
done
echo "  ok   three agents, three worktrees, three tabs; the prompt in each CLI's own form (backticks stayed text)"
[ -z "$(cd "$REPO" && git status --porcelain)" ] || fail "the main checkout was touched (git status is not clean)"
for a in claude devin opencode; do ( cd "$REPO" && git rev-parse --verify -q "refs/heads/t1-$a" >/dev/null ) || fail "branch t1-$a is missing"; done
echo "  ok   the main checkout is untouched; one branch per agent"
printf 'x\ny\n' >> "$REPO/.worktrees/t1-claude/a.txt"                                                 # claude: uncommitted +2
( cd "$REPO/.worktrees/t1-devin" && printf 'z\n' > n.py && git add . && $G commit -qm devin )        # devin: committed +1
out=$(KMX fanout compare t1) || fail "compare failed"
echo "$out" | grep -E "^ +claude +1 file \+2" >/dev/null || { echo "$out"; fail "compare does not show claude's uncommitted +2"; }
echo "$out" | grep -E "^ +devin +1 file \+1" >/dev/null || { echo "$out"; fail "compare does not show devin's committed +1"; }
echo "$out" | grep -E "^ +opencode +no changes" >/dev/null || { echo "$out"; fail "compare does not show opencode as unchanged"; }
KMX fanout list | grep -q "^  t1 " || fail "fanout list does not show t1"
KMX fanout clean t1 | grep -q "dry run" || fail "clean without --yes must be a dry run"
KMX fanout clean t1 --yes | grep -q "kept claude" || fail "clean removed a worktree with uncommitted work"
[ -d "$REPO/.worktrees/t1-claude" ] && [ ! -d "$REPO/.worktrees/t1-opencode" ] || fail "clean did not keep exactly the dirty worktree"
KMX fanout clean t1 --yes --force >/dev/null && [ ! -d "$REPO/.worktrees/t1-claude" ] || fail "clean --force did not remove the rest"
KMX fanout "p" claude --name t2 --base nosuchref --cwd "$REPO" >/dev/null 2>&1; [ $? = 1 ] || fail "a bad --base must be refused"
echo "  ok   compare sees uncommitted and committed work; clean is a dry run, keeps dirty worktrees, --force removes them"
[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty on this machine"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: fanout starts one agent per worktree with its prompt, compares and cleans them, and never touches the main checkout"
