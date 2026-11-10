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
[ "${KMX_SHOT_CARDS:-}" = 1 ] && : > "$STATE/bar-cards"                      # kittymux cards on, through the real geninclude path
[ "${KMX_SHOT_GLASS:-}" = 1 ] && : > "$STATE/bar-cards-glass"                # kittymux cards glass: bar pixels go translucent
[ "${KMX_SHOT_GLASS:-}" = 1 ] && printf 'background_opacity 0.8\n' >> "$CFG/kitty.conf"
[ -n "${KMX_SHOT_CONF:-}" ] && printf '%s\n' "$KMX_SHOT_CONF" >> "$CFG/kitty.conf"     # extra lines, e.g. a custom shader
# synthetic repos (no user data); one tab reports OSC 9;4 progress (64 %): two repos with an `app` folder each, a repo with a linked worktree, a plain folder
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
launch --location=hsplit sh
launch --location=hsplit sh
new_tab
cd $W/web
launch bash -c 'printf "· Pondering… (12s · ↓ 1.2k tokens)\n"; exec -a claude sleep 86400'
new_tab
cd $W/api
launch bash -c 'printf " Bash command\n   rm -rf node_modules\n Do you want to proceed?\n ❯ 1. Yes\n   2. No\n"; exec -a claude sleep 86400'
new_tab
cd $W/web
launch sh -c 'printf "\\033]9;4;1;64\\033\\\\"; exec sh'
new_tab
cd $T/plain/notes
launch sh
focus_tab 1
S
# KMX_SHOT_SCENE=home: two plain shells in a (synthetic) home folder, the bar most people see first
if [ "${KMX_SHOT_SCENE:-}" = home ]; then
  mkdir -p "$T/home"
  # the shells title themselves `~`, the way zsh/fish prompts do
  L="launch sh -c 'printf \"\\\\033]2;~\\\\007\"; exec sh'"
  printf 'new_tab\ncd %s\n%s\nnew_tab\ncd %s\n%s\nfocus_tab 1\n' "$T/home" "$L" "$T/home" "$L" > "$T/session"
  export HOME="$T/home"
fi
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_DATA_HOME=$T/data \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
  kitty -o linux_display_server=x11 --class kmx-shot --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
WID=$(X search --class kmx-shot | head -1)
X windowsize "$WID" 1390 890; sleep 0.4; X windowsize "$WID" 1400 900; sleep 1.2
python3 -c "import sys;sys.path.insert(0,'$HOME_DIR/python');import kittymux_layout as L;L.save('$STATE',$KPID,L.Layout('left','$MODE',$WSTEP))"
kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1; kitty @ --to "$SOCK" load-config >/dev/null 2>&1
sleep 6                                                              # the scanner reads the fake agents' screens
X mousemove --sync ${KMX_SHOT_XY:-900 500}; sleep 0.5                    # KMX_SHOT_XY="x y" puts the pointer over a bar row
[ -n "${KMX_SHOT_XY:-}" ] && X getmouselocation --shell || true
# KMX_SHOT_TAB=N focuses that tab index and grabs a frame of the tab-change animation
if [ -n "${KMX_SHOT_TAB:-}" ]; then
  kitty @ --to "$SOCK" focus-tab --match "index:${KMX_SHOT_TAB}" || true
  sleep "${KMX_SHOT_TAB_SLEEP:-0.08}"
fi
DISPLAY=$DISP import -window root "$T/full.png"
convert "$T/full.png" -crop 380x800+0+0 +repage "$OUT"
# kitty's own framebuffer, which keeps alpha; the root import above composites onto Xvfb and flattens it
[ -n "${KMX_SHOT_ALPHA:-}" ] && kitty @ --to "$SOCK" screenshot "$KMX_SHOT_ALPHA" >/dev/null 2>&1
[ -n "${KMX_SHOT_PIPELINE:-}" ] && cp "$STATE/shaders/kittymux-cards.pipeline" "$KMX_SHOT_PIPELINE" 2>/dev/null || true
[ -n "${KMX_SHOT_LOG:-}" ] && cp "$T/k.log" "$KMX_SHOT_LOG" 2>/dev/null || true
if [ -n "${KMX_SHOT_CPU:-}" ]; then
  _cpu() { awk '{print $14+$15}' "/proc/$KPID/stat"; }
  _a=$(_cpu); sleep 2; _b=$(_cpu)
  for _i in 1 2 3 4 5 6 7 8; do X mousemove $((60 + _i * 15)) 171; sleep 0.2; done
  _c=$(_cpu)
  printf 'idle_ticks %s\nmove_ticks %s\n' "$((_b - _a))" "$((_c - _b))" > "$KMX_SHOT_CPU"
fi
echo "wrote $OUT"
