#!/usr/bin/env bash
# Screenshots of the REAL panel (Agents, Usage, Inbox) for looking at it: a private kitty under Xvfb runs sidebar-kit.py on a synthetic world
# (tools/demo_world.py: a fake HOME the real collectors read, a week of history, inbox events) and is driven with real key events.
# Each step also checks the text the view drew, so this doubles as a smoke test of the three views.
#   bash tests/shot_panel.sh dark|light OUT_DIR [COLS] [LINES]       (default 38 x 44: a docked panel's size)
# Writes OUT_DIR/{agents,usage-codex,usage-claude,usage-cursor,usage-devin,inbox,inbox-needs,inbox-ledger}.png.
# Needs Xvfb, xdotool, kitty, ImageMagick (`import`), python3; otherwise SKIP (exit 0). Never touches another kitty or your real state.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
THEME=${1:-dark}; OUT=${2:-panel-shots}; COLS=${3:-38}; LINES_N=${4:-44}
for dep in Xvfb xdotool kitty import python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
mkdir -p "$OUT"
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-panel.XXXXXX"); CFG=$T/cfg SOCK=unix:$T/sock
mkdir -p "$CFG" "$T/data/fonts"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; if [ -n "${KEEP:-}" ]; then echo "kept $T"; else rm -rf "$T"; fi; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$T/k.log" ] && tail -15 "$T/k.log"; [ -s "$T/world/state/sidebar-kit-err.log" ] && tail -20 "$T/world/state/sidebar-kit-err.log"; exit 1; }

python3 "$HOME_DIR/tools/demo_world.py" "$T/world" >/dev/null || fail "could not build the fixture"
STATE=$T/world/state
cp "$HOME_DIR/assets/kittymux-icons.ttf" "$T/data/fonts/" 2>/dev/null

for n in $(seq 350 379); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1000x1100x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for _ in $(seq 40); do [ -S "/tmp/.X11-unix/X${DISP#:}" ] && break; sleep 0.25; done

if [ "$THEME" = light ]; then cat > "$CFG/theme.conf" <<'C'
foreground #4c4f69
background #eff1f5
selection_foreground #eff1f5
selection_background #4c4f69
active_border_color #1e66f5
inactive_border_color #acb0be
color9 #d20f39
color10 #40a02b
color11 #df8e1d
color12 #1e66f5
C
else cat > "$CFG/theme.conf" <<'C'
foreground #c0caf5
background #1a1b26
selection_foreground #1a1b26
selection_background #c0caf5
active_border_color #f08fb8
inactive_border_color #414868
color9 #f7768e
color10 #9ece6a
color11 #e0af68
color12 #7aa2f7
C
fi
cat > "$CFG/kitty.conf" <<CONF
font_family JetBrainsMono Nerd Font Mono
font_size 11
window_padding_width 0
tab_bar_style hidden
confirm_os_window_close 0
allow_remote_control socket-only
remember_window_size no
initial_window_width ${COLS}c
initial_window_height ${LINES_N}c
include theme.conf
CONF
printf 'new_tab shell\nlaunch sh\nnew_tab web\nlaunch sh\nnew_tab api\nlaunch sh\nfocus_tab 0\n' > "$T/session"

env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP XDG_DATA_HOME=$T/data \
  KITTYMUX_USAGE_HOME=$T/world/home KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 \
  kitty -o linux_display_server=x11 --class kmx-panel --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done
[ -S "$T/sock" ] || fail "kitty never opened its control socket"
sleep 3

# the panel is a kitten in an overlay over the first window, started the way the ctrl+alt+b chord does (an absolute path: a relative one is read from the config dir)
kitty @ --to "$SOCK" kitten --match id:1 "$HOME_DIR/python/sidebar-kit.py" || fail "could not start the panel kitten"
PANEL=""
for _ in $(seq 40); do
  PANEL=$(kitty @ --to "$SOCK" ls | python3 -c 'import sys,json;d=json.load(sys.stdin);ws=[w["id"] for w in d[0]["tabs"][0]["windows"]];print(max(ws) if len(ws)>1 else "")')
  [ -n "$PANEL" ] && break; sleep 0.25
done
[ -n "$PANEL" ] || fail "the panel kitten never opened a window"
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --onlyvisible --class kmx-panel | head -1)
[ -n "$W" ] || fail "no kitty window"
X windowfocus "$W" 2>/dev/null
read -r GX GY GW GH < <(X getwindowgeometry --shell "$W" | python3 -c 'import sys;d=dict(l.strip().split("=") for l in sys.stdin if "=" in l);print(d["X"],d["Y"],d["WIDTH"],d["HEIGHT"])')
redraw() { X windowsize "$W" $((GW - 10)) $((GH - 10)); sleep 0.4; X windowsize "$W" "$GW" "$GH"; sleep 1.0; }
screen() { kitty @ --to "$SOCK" get-text --match id:$PANEL --extent screen 2>/dev/null; }
wait_text() {                 # wait_text PATTERN  (up to 10 s)
  for _ in $(seq 40); do screen | grep -q -- "$1" && return 0; sleep 0.25; done
  echo "--- screen:"; screen; return 1
}
shot() { redraw; DISPLAY=$DISP import -window root -crop "${GW}x${GH}+${GX}+${GY}" +repage "$OUT/$1.png" 2>/dev/null || fail "could not capture $1"; echo "wrote $OUT/$1.png"; }
key() { X key --clearmodifiers "$@"; sleep 0.5; }

wait_text "tabs" || fail "the Agents view never drew its header"
screen | grep -q "▦\|Agents" || fail "the Agents view has no tab strip"
shot agents

# buttons are buttons: a keycap lights up under a real pointer and a real click does what its key does
cell() {                      # cell TEXT -> "col row" of the first screen cell where TEXT starts (empty when absent)
  screen | python3 -c "
import sys
t = sys.argv[1]
for r, ln in enumerate(sys.stdin.read().split('\n')):
    c = ln.find(t)
    if c >= 0:
        print(c, r); break" "$1"
}
point() {                     # point COL ROW: the pointer to the middle of that cell (real motion events, a few steps)
  local px py
  px=$(( ($1 * GW + GW / 2) / COLS + GX )); py=$(( ($2 * GH + GH / 2) / LINES_N + GY ))
  X mousemove $((px - 8)) $((py - 3)); sleep 0.15; X mousemove $((px - 3)) $((py - 1)); sleep 0.15; X mousemove "$px" "$py"; sleep 0.6
}
read -r JC JR <<<"$(cell join)"
[ -n "${JC:-}" ] || fail "Agents: the action bar (jump / join / detach / find) is not drawn"
point "$JC" "$JR"
redraw_keep_pointer() { sleep 0.3; }
DISPLAY=$DISP import -window root -crop "${GW}x${GH}+${GX}+${GY}" +repage "$OUT/agents-hover.png" 2>/dev/null
hex=$(convert "$OUT/agents-hover.png" -format '%[hex:u.p{'"$(( ((JC - 1) * GW + GW / 2) / COLS ))"','"$(( (JR * GH + GH / 4) / LINES_N ))"'}]' info: 2>/dev/null)   # the padding cell left of the label: no letter antialiasing in it
echo "hovered keycap pixel: $hex"
[ "$hex" = "F08FB8" ] || fail "Agents: the keycap under the pointer did not light up in the accent (pixel $hex)"
read -r FC FR <<<"$(cell find)"
[ -n "${FC:-}" ] || fail "Agents: no find button"
point "$FC" "$FR"; X click 1; sleep 0.8
screen | grep -q "▏" || fail "Agents: clicking the find button did not open the search"
key Escape
screen | grep -q "▏" && fail "Agents: Esc did not close the search"
X mousemove $((GX + GW - 4)) $((GY + 4)); sleep 0.4        # pointer away: nothing stays lit

key u
wait_text "4 providers" || fail "the Usage view never drew four providers (is the collector reading the fixture?)"
screen | grep -q "Codex" || fail "Usage: the first provider's card is missing"
screen | grep -q "99%" || fail "Usage: Codex 5h share (99%) is missing"
screen | grep -q "63%" || fail "Usage: Codex weekly share (63%) is missing"
if [ "$COLS" -ge 32 ]; then      # narrower panels drop the countdown on purpose: the share is the point of the row
  screen | grep -q "3h 4\|3h 5" || fail "Usage: the reset countdown is missing"
  screen | grep -q "plus" || fail "Usage: the plan chip is missing"
fi
shot usage-codex

read -r DC DR <<<"$(cell details)"                              # the details button
[ -n "${DC:-}" ] || fail "Usage: no details button in the footer"
point "$DC" "$DR"; X click 1; sleep 0.8
screen | grep -q "KITTYMUX_USAGE_LIVE" || fail "Usage: clicking details did not show the source notes"
point "$DC" "$DR"; X click 1; sleep 0.8
screen | grep -q "KITTYMUX_USAGE_LIVE" && fail "Usage: clicking details again did not hide them"
X mousemove $((GX + GW - 4)) $((GY + 4)); sleep 0.3

key Right
wait_text "Claude" || fail "Usage: Right did not pick the second provider"
screen | grep -q "109.0M" || fail "Usage: Claude's week of tokens is missing"
screen | grep -q "12 sess" || fail "Usage: Claude's session chip is missing"
shot usage-claude

key Right; screen | grep -q "Cursor" || fail "Usage: third provider not picked"; screen | grep -q "active" || fail "Usage: Cursor's status chip is missing"
shot usage-cursor
key Right; screen | grep -q "Devin" || fail "Usage: fourth provider not picked"; screen | grep -q "SWE-2 Max" || fail "Usage: Devin's model chip is missing"
shot usage-devin

key i
wait_text "unread" || fail "the Inbox view never drew"
screen | grep -q "need" || fail "Inbox: the needs-you count is missing"
screen | grep -q "Jump" || fail "Inbox: the picked card has no Jump button"
screen | grep -q "rm -rf node_modules" || fail "Inbox: the permission command is missing"
shot inbox

key Tab
wait_text "Needs" || true
shot inbox-needs
key Tab; key Tab; key Tab                                       # back to All
key shift+g                                                     # the last card: the wait ledger shows under it
wait_text "waited" || fail "Inbox: the wait ledger never showed under the last card"
screen | grep -q "median" || fail "Inbox: the ledger has no median"
shot inbox-ledger

# dismiss is reversible: x hides the card and the footer offers z for a few seconds; z brings it back; the offer expires by itself
key g
screen | grep -q "4 unread" || fail "Inbox: expected 4 unread before dismissing"
read -r XC XR <<<"$(cell dismiss)"                              # the footer's dismiss button (the card's own button says Dismiss with a capital)
[ -n "${XC:-}" ] || fail "Inbox: no dismiss button in the footer"
point "$XC" "$XR"; X click 1
wait_text "3 unread" || fail "Inbox: clicking the dismiss keycap did not dismiss the picked card"
screen | grep -q "z .*undo" || fail "Inbox: the footer does not offer z to undo a dismissal"
shot inbox-undo
key z
wait_text "4 unread" || fail "Inbox: z did not bring the dismissed card back"
screen | grep -q "z .*undo" && fail "Inbox: the undo offer stayed after it was used"
key x; wait_text "3 unread" || fail "Inbox: second dismissal failed"
sleep 9                                                         # no key: the offer must go away on its own timer
screen | grep -q "z .*undo" && fail "Inbox: the undo offer never expired (the timed redraw did not run)"
key z                                                           # too late: nothing comes back
screen | grep -q "3 unread" || fail "Inbox: z after the offer expired changed something"
KITTYMUX_STATE=$STATE python3 -c "
import sys; sys.path.insert(0, '$HOME_DIR/python')
import kittymux_inbox as I, time
ev = [e for e in I.load('$STATE') if e['status'] == 'dismissed']
I.restore('$STATE', time.time(), [e['id'] for e in ev])" && key r   # put the fixture back as it was found

key a
wait_text "tabs" || fail "a did not return to the Agents view"
echo "PASS: Agents, Usage (four providers) and Inbox views drew from the synthetic world; PNGs in $OUT"
