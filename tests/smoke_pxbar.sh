#!/usr/bin/env bash
# The pixel tab bar (pxbar switch) in a real kitty: the picture is up, a click on a row activates the tab DRAWN there (the
# picture's rows don't line up with kitty's cells), the empty space under the rows activates nothing, the close cross closes a
# plain tab, and a busy agent's cross asks first (a second click closes). Clicks wobble, as hands do (tests/smoke_click.sh).
# Its own Xvfb, kitty, socket and state dir; it ends by checking that no other kitty was touched. Needs Xvfb, xdotool, kitty,
# python3 with cairo/pango/rsvg (gi); else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
python3 -c "import cairo, gi; gi.require_version('Pango', '1.0'); gi.require_version('Rsvg', '2.0')" 2>/dev/null || { echo "SKIP: cairo/pango/rsvg not installed"; exit 0; }
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-pxbar.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" "$T/work" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
# tripwire: every OTHER kitty's window count, taken before this rig's kitty exists; checked on PASS and on FAIL alike
others() { for s in /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
tripwire() { [ "$(others)" = "$OTHERS_BEFORE" ] || { echo "FAIL: this rig changed the windows of ANOTHER kitty on this machine (before: $OTHERS_BEFORE after: $(others))"; return 1; }; }
fail() { echo "FAIL: $*"; [ -s "$STATE/tab_bar-error.log" ] && tail -20 "$STATE/tab_bar-error.log"; tripwire; exit 1; }
for n in $(seq 201 239); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in "$HOME_DIR"/python/tab_bar.py "$HOME_DIR"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'window_padding_width 10\nconfirm_os_window_close 0\nallow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
cat > "$T/session" <<S
new_tab alpha
cd $T/work
launch sh
new_tab bravo
cd $T/work
launch sh
new_tab agent
cd $T/work
launch bash -c 'printf "· Pondering… (12s · ↓ 1.2k tokens)\n"; exec -a claude sleep 86400'
new_tab delta
cd $T/work
launch sh
new_tab echo
cd $T/work
launch sh
focus_tab 0
S
env -u WAYLAND_DISPLAY -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTY_PID -u KITTYMUX_TARGET -u KITTYMUX_TARGET_PID __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_SOCKET_DIRS=$T KITTYMUX_NOTIFY=0 KITTYMUX_PXBAR=on \
  kitty -o linux_display_server=x11 --class kmx-pxbar --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 240); do [ -S "$T/sock" ] && break; sleep 0.25; done
[ -S "$T/sock" ] || fail "kitty never opened its control socket ($(tail -3 "$T/k.log" 2>/dev/null))"
X() { DISPLAY=$DISP xdotool "$@"; }
W=""; for _ in $(seq 80); do W=$(X search --class kmx-pxbar 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.25; done
[ -n "$W" ] || fail "kitty's window never appeared"
X windowsize "$W" 1390 890; sleep 0.4; X windowsize "$W" 1400 900

probe() { kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_pxbar.py" "$T/px.json" >/dev/null 2>&1; }
ls_json() { kitty @ --to "$SOCK" ls; }
active() { ls_json | python3 -c 'import sys,json
for t in json.load(sys.stdin)[0]["tabs"]:
    if t["is_active"]: print(t["title"])'; }
titles() {   # the tab titles; FAILS (no output) when kitty can't be asked, so a crash never reads as "the tab is gone"
  local j; j=$(ls_json 2>/dev/null) || return 1
  printf '%s' "$j" | python3 -c 'import sys,json;print(" ".join(t["title"] for t in json.load(sys.stdin)[0]["tabs"]))'
}
has_tabs() {   # has_tabs "present…" -- "absent…": true when every present title is there and no absent one is
  local now; now=$(titles) || fail "kitty did not answer 'ls' (did it crash?)"
  local want=1 t
  for t in "$@"; do
    [ "$t" = -- ] && { want=0; continue; }
    case " $now " in *" $t "*) [ $want = 1 ] || return 1 ;; *) [ $want = 0 ] || return 1 ;; esac
  done
}
band() {   # "y0 y1 right" of the row drawn for the tab with this TITLE
  probe
  ls_json > "$T/ls.json"
  python3 - "$T/px.json" "$T/ls.json" "$1" <<'P'
import json, sys
px, ls, title = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3]
tid = next(t["id"] for t in ls[0]["tabs"] if t["title"] == title)
w = next(iter(px["windows"].values()))
h = next(h for h in w["hits"] if h[0] == "tab" and h[3] == tid)
print(h[1], h[2], w["right"])
P
}
wobble_click() {   # press, drift 8 px, release: a hand's click, past kitty's own 5 px click tolerance and under a drag
  X mousemove --window "$W" "$1" "$2"; sleep 0.1; X mousedown 1; X mousemove --window "$W" $(( $1 + 7 )) $(( $2 + 3 )); sleep 0.08; X mouseup 1; sleep 0.8
}

# 0. the picture is up and has a band per tab (control: no picture would mean every check below proved nothing). A slow
# runner renders later: poll for it with a deadline, never a sleep that happened to be long enough
rows5() { probe && python3 -c "import json,sys;d=json.load(open('$T/px.json'));w=list(d['windows'].values());sys.exit(0 if w and sum(h[0]=='tab' for h in w[0]['hits'])==5 else 1)" 2>/dev/null; }
for _ in $(seq 120); do rows5 && break; sleep 0.25; done
rows5 || fail "no pixel bar picture with 5 tab rows within 30 s (probe: $(cat "$T/px.json" 2>/dev/null))"
echo "  ok   the picture is up with a row per tab (render $(python3 -c "import json;print(round(list(json.load(open('$T/px.json'))['windows'].values())[0]['ms'],1))" "$T/px.json") ms)"

# 1. a click on a row activates the tab drawn there
read -r y0 y1 right < <(band bravo)
wobble_click 90 $(( (y0 + y1) / 2 ))
[ "$(active)" = bravo ] || fail "a click on the row drawn for 'bravo' left '$(active)' active"
echo "  ok   a click on a row activates that tab"

# 2. the empty space under the rows activates nothing (kitty's blank cells there belong to some tab)
read -r y0 y1 right < <(band echo)
wobble_click 90 $(( y1 + 120 ))
[ "$(active)" = bravo ] || fail "a click below the rows activated '$(active)'"
echo "  ok   the space under the rows activates nothing"

# 3. the close cross closes a plain tab
read -r y0 y1 right < <(band delta)
wobble_click $(( right - 16 )) $(( y0 + 16 ))
has_tabs alpha bravo agent echo -- delta || fail "the close cross did not close 'delta' alone (tabs: $(titles))"
echo "  ok   the close cross closes a plain tab"

# 4. a busy agent's cross asks first; a second click inside the guard's window closes it
sleep 2
read -r y0 y1 right < <(band agent)
wobble_click $(( right - 16 )) $(( y0 + 16 ))
has_tabs alpha bravo agent echo || fail "one click on a working agent's cross closed it without asking (tabs: $(titles))"
read -r y0 y1 right < <(band agent)
wobble_click $(( right - 16 )) $(( y0 + 16 ))
has_tabs alpha bravo echo -- agent || fail "a second click on the working agent's cross did not close it alone (tabs: $(titles))"
echo "  ok   a busy agent's cross asks first, a second click closes it"

tripwire || exit 1
echo "  ok   no other kitty on this machine was touched"
echo "PASS: the pixel tab bar maps clicks to the rows it draws, and its close cross closes (busy agents ask first)"
