#!/usr/bin/env bash
# The kittymux client ATTACHED to a real kitty's own vertical bar: a private kitty (X11 under Xvfb, socket-only, private everything, fake
# agents in several states), first with its own cell bar (the "before"), then with the client laid over the bar the way attach mode
# lays it on Hyprland. Under Xvfb with no window manager both windows sit at 0,0, so the client's preview window (KITTYMUX_CLIENT_MODE=
# attach, KITTYMUX_CLIENT_FLOAT=1: sized to kitty's bar minus its divider, kitty's bar colour) lands exactly on the bar. Checks:
#   - tabs.json carries the bar's geometry; the client runs `kittymux client attach <kitty> <itself>`, and kitty's bar stops drawing tabs;
#   - the picture: the client in kitty's bar, kitty's divider and panes beside it (READ IT);
#   - the client stops: the record dies with it and the bar draws its tabs again. Tripwire: no other kitty touched.
# Usage: shot_attach.sh [dark|light] [OUTDIR]     Needs Xvfb, xdotool, import, kitty, qs; else SKIP.
set -u
unset HYPRLAND_INSTANCE_SIGNATURE
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
THEME=${1:-dark}; OUT=${2:-/tmp/kmx-attach-shots}
for dep in Xvfb xdotool import kitty qs python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
mkdir -p "$OUT"
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-attach.XXXXXX"); CFG=$T/cfg STATE=$T/state RUN=$T/run
mkdir -p "$CFG" "$STATE" "$RUN" "$T/bin" "$T/work/calm-otter" "$T/work/quiet-heron" && chmod 700 "$STATE" "$RUN"
XPID="" KPID="" QPID=""
cleanup() { for p in $QPID $KPID $XPID; do kill "$p" 2>/dev/null; done; wait 2>/dev/null; [ -n "${KEEP:-}" ] && cp -r "$T" "$KEEP"; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; tail -15 "$T/qs.log" 2>/dev/null; [ -s "$STATE/tab_bar-error.log" ] && tail -12 "$STATE/tab_bar-error.log"; exit 1; }
for n in $(seq 281 320); do [ -e "/tmp/.X$n-lock" ] || [ -e "/tmp/.X11-unix/X$n" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1180x720x24 >/dev/null 2>&1 & XPID=$!
for _ in $(seq 50); do [ -e "/tmp/.X11-unix/X${DISP#:}" ] && break; sleep 0.1; done
kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
# fake agents: one mid-turn, one asking, one finished
printf '#!/bin/sh\nprintf "\\n  * Thinking (esc to interrupt)\\n"\nwhile :; do sleep 1; done\n' > "$T/bin/claude"
printf '#!/bin/sh\nprintf "\\n  Allow edit to parser.rs?\\n  1. Yes\\n  2. No\\n\\n  Do you want to proceed?\\n"\nwhile :; do sleep 1; done\n' > "$T/bin/codex"
chmod +x "$T/bin/"*
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
if [ "$THEME" = light ]; then COLORS='background #f6f6f4\nforeground #2a2a2e\nactive_border_color #7c4dff\ncolor9 #d32f2f\ncolor10 #2e7d32\ncolor11 #b26a00\ncolor12 #1565c0\n'
else COLORS='background #101014\nforeground #e6e6ea\nactive_border_color #c792ea\ncolor9 #f07178\ncolor10 #c3e88d\ncolor11 #ffcb6b\ncolor12 #82aaff\n'; fi
printf "allow_remote_control socket-only\nlisten_on unix:\${XDG_RUNTIME_DIR}/mykitty\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ngeninclude %s/python/kittymux_layout.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ncursor_blink_interval 0\nfont_size 11\n$COLORS" \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
cat > "$T/session" <<S
new_tab Port the config loader
cd $T/work/calm-otter
launch --title "Port the config loader" $T/bin/claude
new_tab Review the parser
cd $T/work/calm-otter
launch --title "Review the parser" $T/bin/codex
new_tab api dev server
cd $T/work/quiet-heron
launch --title "api dev server" sh
focus_tab 0
S
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  XDG_RUNTIME_DIR=$RUN KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_SOCKET_DIRS=$RUN KITTYMUX_BAR_DUMP=1 HOME=$T/work \
  kitty -o linux_display_server=x11 -o initial_window_width=1180 -o initial_window_height=720 -o remember_window_size=no --class kmx-attach --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 80); do ls "$RUN"/mykitty-* >/dev/null 2>&1 && break; sleep 0.25; done
SOCK=unix:$(ls "$RUN"/mykitty-* 2>/dev/null | head -1)
[ "$SOCK" != "unix:" ] || fail "kitty never opened its control socket"
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))' 2>/dev/null; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
geo() { python3 -c 'import json,sys;g=json.load(open(sys.argv[1]))["windows"][0].get("geometry") or {};print(g.get("edge",""))' "$STATE/tabs.json" 2>/dev/null; }
for _ in $(seq 60); do [ "$(geo)" = left ] && break; sleep 0.3; done
[ "$(geo)" = left ] || fail "tabs.json has no left bar geometry"
sleep 3      # let the agents' states settle
DISPLAY=$DISP xdotool mousemove 1170 700
DISPLAY=$DISP import -window root "$OUT/attach-$THEME-before.png"; echo "  shot $OUT/attach-$THEME-before.png"
attached() { python3 -c 'import json,sys
d = json.load(open(sys.argv[1])); live = {str(t["tab_id"]) for w in json.load(open(sys.argv[2]))["windows"] for t in w["tabs"]}
print(",".join(sorted({str(r.get("attached")) for k, r in d.items() if k in live and "attached" in r})))' "$STATE/bar-dump.json" "$STATE/tabs.json" 2>/dev/null; }
env -u WAYLAND_DISPLAY DISPLAY=$DISP QT_QPA_PLATFORM=xcb QT_QUICK_BACKEND=software KITTYMUX_STATE=$STATE KITTYMUX_ICONS=$HOME_DIR/assets/icons \
  KITTYMUX_BIN=$HOME_DIR/bin/kittymux KITTYMUX_CLIENT_FLOAT=1 KITTYMUX_CLIENT_MODE=attach \
  qs -p "$HOME_DIR/client" >"$T/qs.log" 2>&1 & QPID=$!
# the preview is not attach mode proper (no Hyprland): attach the way the client does, with the client as the owner
for _ in $(seq 40); do DISPLAY=$DISP xdotool search --name "kittymux client" >/dev/null 2>&1 && break; sleep 0.2; done
KITTYMUX_STATE=$STATE python3 "$HOME_DIR/bin/kittymux" client attach "$KPID" "$QPID" || fail "client attach refused"
for _ in $(seq 40); do [ "$(attached)" = True ] && break; sleep 0.3; done
[ "$(attached)" = True ] || fail "kitty's bar still draws tabs under the client (dump: $(attached))"
echo "  ok   attached: kitty's bar keeps its place and draws no tabs"
DISPLAY=$DISP xdotool mousemove 1170 700; sleep 2.5
DISPLAY=$DISP import -window root "$OUT/attach-$THEME-after.png"; echo "  shot $OUT/attach-$THEME-after.png"
DISPLAY=$DISP xdotool mousemove 90 160; sleep 0.8
DISPLAY=$DISP import -window root "$OUT/attach-$THEME-hover.png"; echo "  shot $OUT/attach-$THEME-hover.png"
kitty @ --to "$SOCK" focus-tab --match 'title:^Review' >/dev/null 2>&1
DISPLAY=$DISP xdotool mousemove 1170 700; sleep 2.5
DISPLAY=$DISP import -window root "$OUT/attach-$THEME-switched.png"; echo "  shot $OUT/attach-$THEME-switched.png   (where you are: the accent mark moved with the tab)"
errs=$(grep -E "ERROR|WARN" "$T/qs.log" | grep -v "Saving logs\|X11 connection\|xcb-cursor" || true)
[ -z "$errs" ] || fail "QML reported: $errs"
kill "$QPID"; wait "$QPID" 2>/dev/null; QPID=""
for _ in $(seq 60); do [ "$(attached)" = False ] && break; sleep 0.3; done
[ "$(attached)" = False ] || fail "the client stopped but the bar did not draw its tabs again"
echo "  ok   the client stopped: kitty's bar draws its own tabs again"
[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty"
echo "PASS: the client sits in kitty's own bar; kitty draws nothing under it, and its bar comes back when the client goes (read $OUT)"
