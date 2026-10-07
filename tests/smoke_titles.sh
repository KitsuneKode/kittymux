#!/usr/bin/env bash
# What a tab is CALLED, in every awkward situation around renames, restores and resumes — in a real kitty, reading the title the bar actually drew
# (KITTYMUX_BAR_DUMP=1). A session restore leaves tabs unnamed, titled by whatever the windows say, with a prompt where the agent was; a resumed agent
# sets (or never sets) its own title; a renamed tab is cleared again; a program can title its window with anything, escape sequences included.
# Needs Xvfb, xdotool, kitty, python3; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-titles.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -f "$STATE/bar-dump.json" ] && python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print({k:v.get("title") for k,v in d.items()})' "$STATE/bar-dump.json"; exit 1; }
for n in $(seq 380 409); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for _ in $(seq 40); do [ -S "/tmp/.X11-unix/X${DISP#:}" ] && break; sleep 0.25; done
for f in tab_bar.py window_title_bar.py kittymux_*.py; do ln -s "$HOME_DIR/python/$f" "$CFG/$f"; done
printf 'window_padding_width 10\nconfirm_os_window_close 0\nallow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
W=$T/work
for d in s1 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 s12; do mkdir -p "$W/$d"; done
INFO=$(python3 -c 'import sys;sys.path.insert(0,sys.argv[1]);import kittymux_resume as R;print(R.prompt_info("claude","exact","0a1b2c3d-0000-4000-8000-000000000001",["claude"],["claude","--resume","0a1b2c3d-0000-4000-8000-000000000001"]))' "$HOME_DIR/python")
cat > "$T/session" <<S
new_tab
cd $W/s1
launch sh
new_tab restored-name
cd $W/s2
launch sh
new_tab
cd $W/s3
launch sh
new_tab
cd $W/s4
launch sh
new_tab
cd $W/s5
launch bash -c 'exec -a claude sleep 86400'
new_tab
cd $W/s6
launch bash -c 'exec -a claude sleep 86400'
new_tab
cd $W/s7
launch sh
new_tab
cd $W/s8
launch $HOME_DIR/bin/kittymux resume-prompt --info '$INFO'
new_tab
cd $W/s9
launch sh
new_tab
cd $W/s10
launch sh
new_tab
cd $W/s11
launch sh
new_tab
cd $W/s12
launch sh
focus_tab 0
S
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_BAR_DUMP=1 \
  kitty -o linux_display_server=x11 --class kmx-titles --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
WID=$(X search --class kmx-titles | head -1)
X windowsize "$WID" 1390 890; sleep 0.4; X windowsize "$WID" 1400 900; sleep 1.5
python3 -c "import sys;sys.path.insert(0,'$HOME_DIR/python');import kittymux_layout as L;L.save('$STATE',$KPID,L.Layout('left','full',22))"
kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1; kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 4

win() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        for w in t["windows"]:
            if w["cwd"].endswith("/" + sys.argv[1]): print(w["id"], t["id"]); sys.exit()' "$1"; }
wid() { win "$1" | cut -d' ' -f1; }
tid() { win "$1" | cut -d' ' -f2; }
# the title drawn for the tab whose window lives in directory $1
drawn() { python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get(sys.argv[2],{}).get("title","<none>"))' "$STATE/bar-dump.json" "$(tid "$1")"; }
settitle() { kitty @ --to "$SOCK" set-window-title --match "id:$(wid "$1")" "$2" >/dev/null 2>&1; sleep 1.6; }
expect() {      # expect DIR WANT WHAT
  got=$(drawn "$1"); [ "$got" = "$2" ] || fail "$3: wanted '$2', the bar drew '$got'"; }

# 1. a fresh shell with no title of its own: the folder it is in
expect s1 "s1" "a fresh shell"
# 2. a tab a restored session gave a NAME: that name, not whatever its window says
settitle s2 "something the shell set"; expect s2 "restored-name" "a named tab (as a restored session leaves it)"
# 3. renaming by hand, then clearing the name: back to automatic — never stuck on the old name
kitty @ --to "$SOCK" set-tab-title --match "id:$(tid s3)" "tmp-name" >/dev/null 2>&1; sleep 1.6; expect s3 "tmp-name" "a renamed tab"
kitty @ --to "$SOCK" set-tab-title --match "id:$(tid s3)" "" >/dev/null 2>&1; sleep 1.6; expect s3 "s3" "a tab whose name was cleared again"
echo "  ok   a fresh shell is its folder; a named tab keeps its name; a cleared name returns to automatic"
# 4. a program titles its window (a shell prompt, an editor): that title, without the spinner glyph
settitle s4 "✳ Fix login bug"; expect s4 "Fix login bug" "a program-set title"
# 5. an agent with a conversation title: the title, without the agent's name in front
settitle s5 "✳ Fix login bug"; expect s5 "Fix login bug" "a running agent with a conversation title"
# 6. an agent whose title says nothing (a freshly resumed one, or one that never sets any): the project, not 'Claude Code'
settitle s6 "Claude Code"; expect s6 "s6" "an agent with a generic title"
# 7. the agent exited, its title stayed behind (no shell integration): the folder again
settitle s7 "✳ Claude Code"; expect s7 "s7" "a stale agent title after the agent exited"
echo "  ok   titled windows, agents with and without a conversation title, a stale title left behind"
# 8. a restored agent window waiting on its resume prompt: said plainly, never 'python'
got=$(drawn s8); case "$got" in *resume*) ;; *) fail "a restored window waiting on its resume prompt should say so, the bar drew '$got'" ;; esac
echo "  ok   a restored window waiting for an answer says so ('$got')"
# 9. a hostile title: no control character reaches the bar
settitle s9 $'ev\x1b[31mil\x07\x1b]0;pwned\x07 name'
got=$(drawn s9); python3 -c 'import sys;sys.exit(0 if not any(ord(c)<32 or 127<=ord(c)<160 for c in sys.argv[1]) else 1)' "$got" || fail "control characters reached the bar: $(printf %q "$got")"
# 10. a very long title: cut with an ellipsis to the room it has
settitle s10 "$(python3 -c 'print("a very long conversation title " * 8)')"
got=$(drawn s10); [ "${#got}" -le 30 ] && case "$got" in *…) ;; *) fail "a long title should end in an ellipsis: '$got'" ;; esac
# 11. a title of nothing but whitespace: the folder
settitle s11 "     "; expect s11 "s11" "a whitespace-only title"
# 12. a shell that titles its window with the directory path: the last component
settitle s12 "/home/someone/projects/proj/"; expect s12 "proj" "a path as the title"
echo "  ok   a hostile title, a very long one, a blank one and a path all come out clean"

[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty (before: $OTHERS_BEFORE after: $(others))"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: tab titles hold up through renames, restores, resumes, stale and hostile titles"
