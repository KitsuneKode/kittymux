#!/usr/bin/env bash
# The folder line in kitty's per-pane title bars, in a real kitty (kitty >= 0.49.2): window_title_template + the window_title_bar.py trampoline →
# kittymux_panetitle. Pane title bars are forced on; KITTYMUX_PANETITLE_DUMP=1 records what was drawn per window (escape sequences and all).
#   SHOT=out.png bash tests/smoke_panetitle.sh      also saves a screenshot of the window, for looking at.
# Needs Xvfb, xdotool, kitty >= 0.49.2, git; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
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
# a themed kitty (Gruvbox-like, the tab colours a real theme sets): kitty's un-themed title bars are white blocks, which is not what anyone sees
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
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
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

# 1. every pane says where it is, in the tab bar's grammar
for want in "$A|alpha/src/ui|main" "$B|bravo|main" "$N|notes|" "$WT|alpha:alpha-wt|feat-wt"; do
  id=${want%%|*}; rest=${want#*|}; proj=${rest%%|*}; extra=${rest#*|}
  out=$(drawn "$id")
  case "$out" in *"$proj"*) ;; *) fail "window $id should show '$proj', drew: $out" ;; esac
  [ -z "$extra" ] || case "$out" in *"$extra"*) ;; *) fail "window $id should show '$extra', drew: $out" ;; esac
done
echo "  ok   each pane's title bar shows its project / path / branch / worktree"

# 2. the active pane's project is bold; an inactive pane's is not
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
case "$(drawn "$ACTIVE" raw)" in *$'\x1b[1m'*) ;; *) fail "the focused pane's project should be bold: $(drawn "$ACTIVE" raw)" ;; esac
case "$(drawn "$OTHER" raw)" in *$'\x1b[1m'*) fail "an unfocused pane's project should not be bold" ;; esac
echo "  ok   the focused pane's project is bold, the other pane's is not"

# 3. the pane's own title follows when it adds something, and is left out when it does not
kitty @ --to "$SOCK" set-window-title --match "id:$B" "nvim README.md" >/dev/null 2>&1; sleep 1.5
case "$(drawn "$B")" in *"bravo"*"nvim README.md") ;; *) fail "the pane's own title should follow the folder line: $(drawn "$B")" ;; esac
kitty @ --to "$SOCK" set-window-title --match "id:$B" "bravo" >/dev/null 2>&1; sleep 1.5
case "$(drawn "$B")" in *"·"*) fail "a title that only repeats the project must be left out: $(drawn "$B")" ;; esac
kitty @ --to "$SOCK" set-window-title --match "id:$B" "" >/dev/null 2>&1; sleep 1.5
case "$(drawn "$B")" in *bravo*) ;; *) fail "an EMPTY window title (a session that was just resumed) must still show the folder line: $(drawn "$B")" ;; esac
echo "  ok   the pane's own title is appended only when it says something new (empty and repeated titles included)"

# 4. renaming the TAB does not touch the pane's folder line (the tab name and the pane title are different things)
before=$(drawn "$A")
TAB=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json
for o in json.load(sys.stdin):
    for t in o["tabs"]:
        if any(w["id"] == int(sys.argv[1]) for w in t["windows"]): print(t["id"])' "$A")
kitty @ --to "$SOCK" set-tab-title --match "id:$TAB" "my renamed tab" >/dev/null 2>&1; sleep 1.5
[ "$(drawn "$A")" = "$before" ] || fail "renaming the tab changed the pane's line: '$before' → '$(drawn "$A")'"
echo "  ok   renaming a tab leaves the panes' folder lines alone"

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
  DISPLAY=$DISP import -window root "$SHOT" && echo "  shot $SHOT"
fi
[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty (before: $OTHERS_BEFORE after: $(others))"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: pane title bars carry the folder line, fall back to kitty's own title when off, and survive renames"
