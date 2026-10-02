#!/usr/bin/env bash
# A screenshot of the vertical bar, for looking at it (the look-and-feel review, the README): a private kitty with a dozen tabs in synthetic
# repos — twins, a worktree, a split, a plain folder, two fake agents — drawn with a dark or a light theme.
#   bash tests/shot_bar.sh dark|light OUT.png [WIDTH_STEP] [MODE]      (WIDTH_STEP: kittymux layout width, default 22 → a 30-column bar;
#                                                                      MODE: full|compact — compact is the slim icon rail)
# Switches go in the environment, e.g.  KITTYMUX_HUE=off bash tests/shot_bar.sh dark /tmp/a.png.  Needs Xvfb, xdotool, kitty, git, ImageMagick; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
THEME=${1:-dark}; OUT=${2:-bar-$THEME.png}; WSTEP=${3:-22}; MODE=${4:-full}
for dep in Xvfb xdotool kitty git import convert python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-shot.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" "$T/data/fonts" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
for n in $(seq 320 349); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for _ in $(seq 40); do [ -S "/tmp/.X11-unix/X${DISP#:}" ] && break; sleep 0.25; done
for f in tab_bar.py kittymux_*.py; do ln -s "$HOME_DIR/python/$f" "$CFG/$f"; done
cp "$HOME_DIR/assets/kittymux-icons.ttf" "$T/data/fonts/" 2>/dev/null
if [ "$THEME" = light ]; then
cat > "$CFG/theme.conf" <<'C'
foreground #4c4f69
background #eff1f5
selection_foreground #eff1f5
selection_background #4c4f69
cursor #4c4f69
active_border_color #1e66f5
inactive_border_color #acb0be
color0 #5c5f77
color1 #d20f39
color2 #40a02b
color3 #df8e1d
color4 #1e66f5
color5 #8839ef
color6 #179299
color7 #acb0be
color8 #6c6f85
color9 #d20f39
color10 #40a02b
color11 #df8e1d
color12 #1e66f5
color13 #8839ef
color14 #179299
color15 #bcc0cc
C
else
cat > "$CFG/theme.conf" <<'C'
foreground #c0caf5
background #1a1b26
selection_foreground #1a1b26
selection_background #c0caf5
cursor #c0caf5
active_border_color #bb9af7
inactive_border_color #414868
color0 #15161e
color1 #f7768e
color2 #9ece6a
color3 #e0af68
color4 #7aa2f7
color5 #bb9af7
color6 #7dcfff
color7 #a9b1d6
color8 #414868
color9 #f7768e
color10 #9ece6a
color11 #e0af68
color12 #7aa2f7
color13 #bb9af7
color14 #7dcfff
color15 #c0caf5
C
fi
printf 'font_family JetBrainsMono Nerd Font Mono\nfont_size 11\nwindow_padding_width 10\nconfirm_os_window_close 0\nallow_remote_control socket-only\ninclude %s/theme.conf\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$CFG" "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
# synthetic repos (no user data): two repos with an `app` folder each, a repo with a linked worktree, a plain folder
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
W=$T/work
mkdir -p "$W/kittymux/python" "$W/web/app" "$W/api/app" "$W/docs" "$T/plain/notes"
for r in kittymux web api docs; do git -C "$W/$r" init -q -b main && git -C "$W/$r" -c commit.gpgsign=false commit -q --allow-empty -m init; done
git -C "$W/kittymux" checkout -q -b feat/side-sheet && git -C "$W/kittymux" -c commit.gpgsign=false worktree add -q -b feat/hue "$W/kittymux/.worktrees/hue" 2>/dev/null
git -C "$W/web" checkout -q -b fix/login-redirect
cat > "$T/session" <<S
new_tab
cd $W/kittymux
launch sh
new_tab
cd $W/kittymux/python
launch sh
new_tab
cd $W/web/app
launch sh
new_tab
cd $W/api/app
launch sh
new_tab
cd $W/kittymux/.worktrees/hue
launch sh
new_tab
cd $W/docs
launch sh
launch --location=vsplit sh
new_tab
cd $W/web
launch bash -c 'printf "· Pondering… (12s · ↓ 1.2k tokens)\n"; exec -a claude sleep 86400'
new_tab
cd $W/api
launch bash -c 'printf " Bash command\n   rm -rf node_modules\n Do you want to proceed?\n ❯ 1. Yes\n   2. No\n"; exec -a claude sleep 86400'
new_tab
cd $T/plain/notes
launch sh
focus_tab 1
S
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_DATA_HOME=$T/data \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
  kitty -o linux_display_server=x11 --class kmx-shot --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
WID=$(X search --class kmx-shot | head -1)
X windowsize "$WID" 1390 890; sleep 0.4; X windowsize "$WID" 1400 900; sleep 1.2
python3 -c "import sys;sys.path.insert(0,'$HOME_DIR/python');import kittymux_layout as L;L.save('$STATE',$KPID,L.Layout('left','$MODE',$WSTEP))"
kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1; kitty @ --to "$SOCK" load-config >/dev/null 2>&1
sleep 6                                                              # the scanner reads the fake agents' screens
X mousemove 900 500; sleep 0.5
DISPLAY=$DISP import -window root "$T/full.png"
convert "$T/full.png" -crop 380x700+0+0 +repage "$OUT"
echo "wrote $OUT"
