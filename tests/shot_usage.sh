#!/usr/bin/env bash
# A private dashboard render. Synthetic usage only, no provider calls or live kitty.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
THEME=${1:-dark}; OUT=${2:-/tmp/usage.png}; COLS=${3:-32}
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null || { echo "SKIP: $dep missing"; exit 0; }; done
RUN=$(mktemp -d /tmp/kmx-usage-shot.XXXXXX)
KPID= XPID=
trap '[ -z "$KPID" ] || kill "$KPID" 2>/dev/null || true; [ -z "$XPID" ] || kill "$XPID" 2>/dev/null || true; rm -rf "$RUN"' EXIT
mkdir -p "$RUN/cfg" "$RUN/state" "$RUN/home" "$RUN/bin"
SOCK=unix:$RUN/sock
for n in $(seq 450 479); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x1200x24 > "$RUN/x.log" 2>&1 & XPID=$!
sleep 1
printf 'allow_remote_control socket-only\nconfirm_os_window_close 0\nfont_family JetBrainsMono Nerd Font Mono\nfont_size 11\nremember_window_size no\nwindow_padding_width 8\ntab_bar_min_tabs 9999\ninitial_window_width %sc\ninitial_window_height 58c\n' "$COLS" > "$RUN/cfg/kitty.conf"
if [ "$THEME" = light ]; then printf 'background #eff1f5\nforeground #4c4f69\ncolor1 #d20f39\ncolor2 #40a02b\ncolor3 #df8e1d\ncolor4 #1e66f5\ncolor5 #8839ef\ncolor6 #179299\ncolor8 #6c6f85\nactive_border_color #8839ef\ncolor9 #d20f39\ncolor10 #40a02b\ncolor11 #df8e1d\ncolor12 #1e66f5\n' >> "$RUN/cfg/kitty.conf"; else printf 'background #1a1b26\nforeground #c0caf5\ncolor1 #f7768e\ncolor2 #9ece6a\ncolor3 #e0af68\ncolor4 #7aa2f7\ncolor5 #bb9af7\ncolor6 #7dcfff\ncolor8 #414868\nactive_border_color #bb9af7\ncolor9 #f7768e\ncolor10 #9ece6a\ncolor11 #e0af68\ncolor12 #7aa2f7\n' >> "$RUN/cfg/kitty.conf"; fi
PYREAL=$(command -v python3)
printf '#!/bin/sh\ncase "$1" in */mux-usage.py) sleep 60; exit 0;; esac\nexec "%s" "$@"\n' "$PYREAL" > "$RUN/bin/python3"
chmod +x "$RUN/bin/python3"
python3 - "$RUN/state" <<'PY'
import sys,json,time,datetime
from pathlib import Path
p=Path(sys.argv[1]);now=time.time();hour=int(now//3600)*3600
providers=[{'name':'codex','rows':[{'label':'5h','pct':99,'reset':'resets in 3h 50m'},{'label':'week','pct':63,'reset':'resets in 4d 19h'}],'note':'Plan Plus · local quota snapshot'}, {'name':'claude','rows':[{'label':'week','text':'109M tokens · 12 sessions'}],'note':'Local usage; no quota percentage available'}, {'name':'cursor','rows':[{'label':'Plan','text':'Pro · active'}]}, {'name':'devin','rows':[{'label':'today','text':'5 sessions · 37.6M tokens'},{'label':'model','text':'SWE-2 Max'}]}]
(p/'agent-usage.json').write_text(json.dumps({'ts':now,'providers':providers}))
(p/'agent-usage-trends.json').write_text(json.dumps({'version':1,'samples':[{'provider':'codex','row':0,'at':hour-i*3600,'pct':max(0,99-i*2)} for i in range(48) if i not in (20,21,22,23)]}))
(p/'agent-usage-history.json').write_text(json.dumps({(datetime.date.today()-datetime.timedelta(days=i)).isoformat():{'_daily_version':2,'claude_fresh':n} for i,n in ((0,1000000),(1,8000000),(2,3000000),(4,2000000),(6,4000000))}))
PY
env -u WAYLAND_DISPLAY -u KITTY_PID -u KITTY_WINDOW_ID -u KITTY_LISTEN_ON -u KITTYMUX_TARGET DISPLAY="$DISP" HOME="$RUN/home" PATH="$RUN/bin:$PATH" KITTYMUX_USAGE_LIVE=0 KITTYMUX_AUTOSAVE=0 KITTYMUX_PANEL=1 KITTYMUX_TARGET="$SOCK" KITTYMUX_STATE="$RUN/state" KITTYMUX_HOME="$ROOT" KITTY_CONFIG_DIRECTORY="$RUN/cfg" KITTYMUX_SOCKET_DIRS="$RUN" LIBGL_ALWAYS_SOFTWARE=1 __GLX_VENDOR_LIBRARY_NAME=mesa kitty -o linux_display_server=x11 --class kmx-usage-shot --listen-on "$SOCK" kitty +runpy 'from kittens.runner import main; main()' "$RUN/cfg" "$ROOT/python/sidebar-kit.py" > "$RUN/log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ ! -S "$RUN/sock" ] || break; sleep .2; done
sleep 1.5
kitty @ --to "$SOCK" send-key u >/dev/null
sleep 1.5
kitty @ --to "$SOCK" screenshot "$OUT" >/dev/null
kitty @ --to "$SOCK" get-text > "${OUT%.png}.txt"
[ ! -s "$RUN/state/sidebar-kit-err.log" ] || { cat "$RUN/state/sidebar-kit-err.log"; exit 1; }
echo "wrote $OUT"
