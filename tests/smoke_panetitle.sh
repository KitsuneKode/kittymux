#!/usr/bin/env bash
# The pane header row in kitty's per-pane title bars, in a real kitty (kitty >= 0.49.2): window_title_template + the window_title_bar.py trampoline →
# kittymux_panetitle. Pane title bars are forced on; KITTYMUX_PANETITLE_DUMP=1 records what was drawn per window (escape sequences and all).
#   SHOT=out.png bash tests/smoke_panetitle.sh      also saves a screenshot of the window, for looking at.
# Needs Xvfb, xdotool, kitty >= 0.49.2, git; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
THEME=${THEME:-dark}
for dep in Xvfb xdotool kitty git python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
kitty --version | python3 -c 'import re,sys;v=tuple(int(x) for x in re.search(r"(\d+)\.(\d+)\.(\d+)",sys.stdin.read()).groups());sys.exit(0 if v>=(0,49,2) else 1)' || { echo "SKIP: kitty older than 0.49.2"; exit 0; }
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-ptitle.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -f "$STATE/panetitle-dump.json" ] && cat "$STATE/panetitle-dump.json" | cut -c1-1500; [ -s "$T/k.log" ] && tail -5 "$T/k.log"; exit 1; }
for n in $(seq 350 379); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for _ in $(seq 40); do [ -S "/tmp/.X11-unix/X${DISP#:}" ] && break; sleep 0.25; done
for f in tab_bar.py window_title_bar.py kittymux_*.py; do ln -s "$HOME_DIR/python/$f" "$CFG/$f"; done
# a themed kitty (Gruvbox-like dark or Catppuccin-like light): kitty's un-themed title bars are white blocks, which is not what anyone sees
if [ "$THEME" = light ]; then
cat > "$CFG/theme.conf" <<'C'
foreground #4c4f69
background #eff1f5
active_border_color #1e66f5
inactive_border_color #bcc0cc
active_tab_foreground #4c4f69
active_tab_background #dce0e8
inactive_tab_foreground #6c6f85
inactive_tab_background #ccd0da
color0 #5c5f77
color1 #d20f39
color2 #40a02b
color3 #df8e1d
color4 #1e66f5
color5 #8839ef
color6 #179299
color7 #6c6f85
color8 #8c8fa1
color9 #d20f39
color10 #40a02b
color11 #df8e1d
color12 #1e66f5
color13 #8839ef
color14 #179299
color15 #4c4f69
C
else
cat > "$CFG/theme.conf" <<'C'
foreground #ebdbb2
background #272727
active_border_color #d3869b
inactive_border_color #504945
active_tab_foreground #fbf1c7
active_tab_background #665c54
inactive_tab_foreground #a89984
inactive_tab_background #3c3836
color0 #282828
color1 #cc241d
color2 #98971a
color3 #d79921
color4 #458588
color5 #b16286
color6 #689d6a
color7 #a89984
color8 #928374
color9 #fb4934
color10 #b8bb26
color11 #fabd2f
color12 #83a598
color13 #d3869b
color14 #8ec07c
color15 #ebdbb2
C
fi
printf 'font_family JetBrainsMono Nerd Font Mono\nfont_size 11\nwindow_padding_width 10\nconfirm_os_window_close 0\nallow_remote_control socket-only\ninclude %s/theme.conf\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\nwindow_title_bar_min_windows 1\nwindow_title_bar_align left\ngeninclude %s/python/kittymux_layout.py\n' \
  "$CFG" "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
W=$T/work
mkdir -p "$W/alpha/src/ui" "$W/bravo" "$T/plain/notes"
for r in alpha bravo; do git -C "$W/$r" init -q -b main && git -C "$W/$r" -c commit.gpgsign=false commit -q --allow-empty -m init || fail "git init"; done
git -C "$W/alpha" worktree add -q -b feat-wt "$W/alpha-wt" || fail "git worktree add"
cat > "$T/session" <<S
new_tab alpha
cd $W/alpha/src/ui
launch sh
cd $W/alpha
launch --location=vsplit sh
new_tab bravo
cd $W/bravo
launch sh
new_tab notes
cd $T/plain/notes
launch sh
new_tab wt
cd $W/alpha-wt
launch sh
focus_tab 0
S
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_PANETITLE_DUMP=1 \
  kitty -o linux_display_server=x11 --class kmx-ptitle --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
WID=$(X search --class kmx-ptitle | head -1)
X windowsize "$WID" 1390 890; sleep 0.4; X windowsize "$WID" 1400 900; sleep 1.5
python3 -c "import sys;sys.path.insert(0,'$HOME_DIR/python');import kittymux_layout as L;L.save('$STATE',$KPID,L.Layout('left','full',22))"
kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1; kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 2
FEAT() { env -u KITTY_LISTEN_ON KITTYMUX_SOCKET_DIRS="$T/no-sockets" KITTYMUX_STATE=$STATE "$HOME_DIR/bin/kittymux" features "$@" >/dev/null 2>&1; }

# window id → its directory, from kitty itself
wid_of() { kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
want = sys.argv[1]
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        for w in t["windows"]:
            if w["cwd"].endswith(want): print(w["id"]); sys.exit()' "$1"; }
# what was last drawn for window $1: plain text, with all escape sequences removed (or RAW)
drawn() { python3 - "$STATE/panetitle-dump.json" "$1" "${2:-plain}" <<'PY'
import json, re, sys
rows = json.load(open(sys.argv[1])); s = rows.get(sys.argv[2], "<none>")
print(s if sys.argv[3] == "raw" else re.sub(r"\x1b\[[0-9;:]*m", "", s))
PY
}
for _ in $(seq 60); do [ -s "$STATE/panetitle-dump.json" ] && break; sleep 0.25; done
[ -s "$STATE/panetitle-dump.json" ] || fail "no pane title bar was ever drawn through the hook (is window_title_template in effect?)"
sleep 1
A=$(wid_of "/work/alpha/src/ui"); B=$(wid_of "/work/bravo"); N=$(wid_of "/plain/notes"); WT=$(wid_of "/work/alpha-wt")
[ -n "$A" ] && [ -n "$B" ] && [ -n "$N" ] && [ -n "$WT" ] || fail "could not map the windows (A=$A B=$B N=$N WT=$WT)"

# 1. the place uses the bar's grammar: project-relative (no leading slash), the branch kept, the name not repeated
python3 - "$STATE/panetitle-dump.json" "$A" "$B" "$N" "$WT" <<'PY' || fail "place grammar"
import json, re, sys
rows = json.load(open(sys.argv[1]))
def plain(wid):
    return re.sub(r"\x1b\[[0-9;:]*m", "", rows.get(str(wid), ""))
def mentions(text, word):
    return len(re.findall(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", text))
A, B, N, WT = (plain(w) for w in sys.argv[2:])
def need(ok, msg, out):
    if not ok:
        sys.stderr.write(msg + "\n drew: " + out + "\n")
        sys.exit(1)
need("/alpha" not in A and "src/ui" in A and "main" in A and mentions(A, "alpha") == 1,
     "alpha/src/ui should be the project name, then src/ui and the branch, once", A)
need(mentions(B, "bravo") == 1 and "main" in B and "bravo  bravo" not in B,
     "a shell at the repo root must not repeat its name", B)
need(mentions(N, "notes") == 1, "the notes pane should name its folder once", N)
need("alpha-wt" in WT and "feat-wt" in WT and mentions(WT, "alpha") == 1 and "alpha:alpha-wt" not in WT,
     "a worktree shell keeps the worktree and the branch without repeating the project", WT)
PY
echo "  ok   each pane header keeps the branch, drops a leading slash, and does not repeat its name"

# 2. the active pane's name is bold; an inactive pane's is not
ACTIVE=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if t["is_active"]:
            for w in t["windows"]:
                if w["is_focused"]: print(w["id"])')
OTHER=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if t["is_active"]:
            for w in t["windows"]:
                if not w["is_focused"]: print(w["id"])')
[ -n "$ACTIVE" ] && [ -n "$OTHER" ] || fail "no split tab found"
case "$(drawn "$ACTIVE" raw)" in *$'\x1b[1m'*) ;; *) fail "the focused pane's name should be bold: $(drawn "$ACTIVE" raw)" ;; esac
case "$(drawn "$OTHER" raw)" in *$'\x1b[1m'*) fail "an unfocused pane's name should not be bold" ;; esac
echo "  ok   the focused pane's name is bold, the other pane's is not"

# 3. the pane's own title becomes the bold name when it adds something, and a repeated product name is left out
kitty @ --to "$SOCK" set-window-title --match "id:$B" "nvim README.md" >/dev/null 2>&1; sleep 1.5
case "$(drawn "$B")" in *"nvim README.md"*) ;; *) fail "the pane's task should be the bold name: $(drawn "$B")" ;; esac
kitty @ --to "$SOCK" set-window-title --match "id:$B" "bravo" >/dev/null 2>&1; sleep 1.5
plain_b=$(drawn "$B")
case "$plain_b" in *"nvim README"*) fail "a title that only repeats the folder must be left out: $plain_b" ;; esac
kitty @ --to "$SOCK" set-window-title --match "id:$B" "" >/dev/null 2>&1; sleep 1.5
case "$(drawn "$B")" in *bravo*) ;; *) fail "an EMPTY window title must still show the folder caption: $(drawn "$B")" ;; esac
echo "  ok   the bold name is the task when it says something new (empty and repeated titles included)"

# 4. renaming the TAB does not touch the pane header (the tab name and the pane title are different things)
before=$(drawn "$A")
TAB=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if any(w["id"] == int(sys.argv[1]) for w in t["windows"]): print(t["id"])' "$A")
kitty @ --to "$SOCK" set-tab-title --match "id:$TAB" "my renamed tab" >/dev/null 2>&1; sleep 1.5
[ "$(drawn "$A")" = "$before" ] || fail "renaming the tab changed the pane's line: '$before' → '$(drawn "$A")'"
echo "  ok   renaming a tab leaves the pane headers alone"

# 5. the switch: off → nothing is drawn through the hook (kitty shows its own title)
FEAT off panetitle; kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1
kitty @ --to "$SOCK" set-window-title --match "id:$B" "after off" >/dev/null 2>&1; sleep 2
[ -z "$(drawn "$B")" ] || fail "with panetitle off the hook must return nothing, it drew: $(drawn "$B")"
FEAT on panetitle; kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1
kitty @ --to "$SOCK" set-window-title --match "id:$B" "back on" >/dev/null 2>&1; sleep 2
case "$(drawn "$B")" in *bravo*) ;; *) fail "after turning panetitle on again the line should be back: $(drawn "$B")" ;; esac
echo "  ok   features off panetitle hands the bar back to kitty's own title; on brings the line back"

if [ -n "${SHOT:-}" ]; then
  kitty @ --to "$SOCK" focus-tab --match title:alpha >/dev/null 2>&1; kitty @ --to "$SOCK" set-window-title --match "id:$A" "nvim src/main.rs" >/dev/null 2>&1; sleep 2
  DISPLAY=$DISP import -window root "$SHOT" && echo "  shot $SHOT ($THEME)"
  X windowsize "$WID" 520 890; sleep 1.5
  DISPLAY=$DISP import -window root "${SHOT%.png}-narrow.png" && echo "  shot ${SHOT%.png}-narrow.png ($THEME)"
  X windowsize "$WID" 1400 900; sleep 0.5
fi
[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty (before: $OTHERS_BEFORE after: $(others))"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: pane title bars show the pane header row, fall back to kitty's own title when off, and survive renames"
