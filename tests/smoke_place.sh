#!/usr/bin/env bash
# The folder line of vertical tabs, in a real kitty. Four tabs: two in DIFFERENT repos whose shells show the SAME title ("app"),
# one at a repo root (the title already says the project) and one plain folder outside any repo. Reads what the bar drew from the
# KITTYMUX_BAR_DUMP hook, then flips the switches (`kittymux features`) and checks each piece goes away on its own and that with
# everything off the bar draws the line it always did. Needs Xvfb, xdotool, kitty, git, python3; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty git python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-place.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$STATE/tab_bar-error.log" ] && sed 's/^/  | /' "$STATE/tab_bar-error.log" | tail -12; [ -f "$STATE/bar-dump.json" ] && cat "$STATE/bar-dump.json"; exit 1; }
for n in $(seq 201 229); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in tab_bar.py kittymux_theme.py kittymux_deck.py kittymux_git.py kittymux_features.py kittymux_place.py kittymux_layout.py kittymux_barsize.py kittymux_agents.py kittymux_state.py kittymux_scan.py; do
  ln -s "$HOME_DIR/python/$f" "$CFG/$f"
done
printf 'window_padding_width 10\nconfirm_os_window_close 0\nallow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
mkdir -p "$T/work/alpha/app" "$T/work/bravo/app" "$T/plain/notes"
for r in alpha bravo; do git -C "$T/work/$r" init -q -b main || fail "git init"; done
cat > "$T/session" <<S
new_tab
cd $T/work/alpha/app
launch sh
new_tab
cd $T/work/bravo/app
launch sh
new_tab
cd $T/work/alpha
launch sh
new_tab
cd $T/plain/notes
launch sh
focus_tab 0
S
others() { for s in /tmp/mykitty-* "${REAL_RUNTIME:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_BAR_DUMP=1 \
  kitty -o linux_display_server=x11 --class kmx-place --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --class kmx-place | head -1)
X windowsize "$W" 1390 890; sleep 0.4; X windowsize "$W" 1400 900; sleep 1.2       # a real size (and a first redraw), as the other rigs do
# a known bar width (30 columns): without a saved layout kitty's own, narrower width applies (same trick as smoke_resize.sh)
python3 -c "import sys;sys.path.insert(0,'$HOME_DIR/python');import kittymux_layout as L;L.save('$STATE',$KPID,L.Layout('left','full',22))"
kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1; kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1.5
reload() { kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 2.5; }
# `kittymux features` reloads every kitty it can find: confine its discovery to NOTHING (and drop KITTY_LISTEN_ON, which points at the kitty this rig was started from),
# so only this rig's own `reload` below touches a kitty
FEAT() { env -u KITTY_LISTEN_ON KITTYMUX_SOCKET_DIRS="$T/no-sockets" KITTYMUX_STATE=$STATE "$HOME_DIR/bin/kittymux" features "$@" >/dev/null 2>&1; }
# check KIND — prints the rows as one line per tab:  text|roles|emphasised|hue|legacy|hidden
rows() { python3 - "$STATE/bar-dump.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for k in sorted(d, key=int):
    r = d[k]
    print("%s|%s|%s|%s|%s|%s" % ("".join(t for t, _ in r["pieces"]), ",".join(role for _, role in r["pieces"]),
          r.get("emphasised"), "none" if r.get("hue") is None else "hue", r["legacy"], r.get("hidden")))
PY
}
for _ in $(seq 80); do [ -s "$STATE/bar-dump.json" ] && [ "$(rows 2>/dev/null | wc -l)" -ge 4 ] && break; sleep 0.25; done
[ "$(rows | wc -l)" -ge 4 ] || fail "the bar drew fewer than 4 folder lines"

# 1. defaults: project highlighted, the twins ("app" in alpha and bravo) emphasised, hue on
R=$(rows)
echo "$R" | grep -q "^[^|]*alpha/app[^|]*|icon,project,inner,branch|True|hue|False|False$" || fail "alpha/app line wrong:
$R"
echo "$R" | grep -q "^[^|]*bravo/app[^|]*|icon,project,inner,branch|True|hue|False|False$" || fail "bravo/app line wrong:
$R"
echo "  ok   two tabs titled 'app' show their projects, both emphasised, with a hue"
# the repo-root tab and the plain folder: the title already says the project, so the line shows the rest
echo "$R" | grep -q "|branch|False|hue|False|True$" || fail "the repo-root tab should hide the project and show only the branch:
$R"
echo "$R" | grep -q "|where|False|hue|False|True$" || fail "the plain-folder tab should hide the project and show where it lives:
$R"
echo "  ok   a title that already says the project is not repeated (branch / location shown instead)"

# 2. collide off: the twins lose their emphasis, everything else stays
FEAT off collide; reload
R=$(rows)
echo "$R" | grep "alpha/app" | grep -q "|False|hue|False|False$" || fail "collide off should clear the emphasis:
$R"
echo "  ok   features off collide: no emphasis, the rest unchanged"
FEAT on collide

# 3. hue off: no hue anywhere
FEAT off hue; reload
R=$(rows)
echo "$R" | grep -q "|hue|" && fail "hue off left a hue in a row:
$R"
echo "  ok   features off hue: no hue"
FEAT on hue

# 4. minimal preset = folder only
FEAT preset minimal; reload
R=$(rows)
echo "$R" | grep "alpha/app" | grep -q "|False|none|False|False$" || fail "preset minimal should leave the folder line without hue or emphasis:
$R"
echo "  ok   preset minimal: the folder line alone"

# 5. everything off: the line this bar always drew (branch, or folder outside a repo) — no project, no roles
FEAT preset default; FEAT off folder; reload
R=$(rows)
[ "$(echo "$R" | grep -c '^[^|]*|legacy|None|none|True|None$')" -ge 4 ] || fail "folder off should draw the legacy line on every tab:
$R"
echo "$R" | grep -q "alpha" && fail "folder off still shows a project name:
$R"
echo "  ok   features off folder: the original branch / folder line, nothing new"

# 6. no other kitty on this machine was touched
[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty (before: $OTHERS_BEFORE after: $(others))"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: tabs say where they are; every piece switches off on its own; all off is the old line"
