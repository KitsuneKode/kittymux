#!/usr/bin/env bash
# mux-panel's focus commands against a fake `kitten` that records its arguments: summon/dock send the right focus_policy to the
# panel's own socket, `toggle` summons a docked panel and removes a summoned one, the mode file follows, garbage means docked.
# The layer-shell grab itself cannot run here (no compositor): that is checked by hand on Hyprland (docs/testing.md).
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-pf.XXXXXX"); trap 'kill $SPID $LPID 2>/dev/null; rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/run" "$T/state"; chmod 700 "$T/run"
cat > "$T/bin/kitten" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$T/calls"
EOF
chmod +x "$T/bin/kitten"
export PATH="$T/bin:$PATH" XDG_RUNTIME_DIR="$T/run" KITTYMUX_STATE="$T/state" KITTYMUX_TARGET=unix:/nonexistent
SOCK="$T/run/kittymux-panel-$(id -u).sock"
python3 - "$SOCK" <<'PY' & LPID=$!
import socket, sys, time, os
s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); s.listen(1); time.sleep(60)
PY
sleep 30 & SPID=$!
for _ in $(seq 40); do [ -S "$SOCK" ] && break; sleep 0.05; done
echo $SPID > "$T/state/panel.pid"
P="$HOME_DIR/bin/mux-panel"
fail() { echo "FAIL: $*"; [ -f "$T/calls" ] && sed 's/^/  call: /' "$T/calls"; exit 1; }
last() { tail -n1 "$T/calls" 2>/dev/null; }

printf docked > "$T/state/panel-mode"
"$P" summon >/dev/null || fail "summon failed"
last | grep -q -- "--to unix:$SOCK resize-os-window --action=os-panel --incremental focus-policy=exclusive" || fail "summon sent: $(last)"
[ "$(cat "$T/state/panel-mode")" = summoned ] || fail "mode file after summon: $(cat "$T/state/panel-mode")"

"$P" dock >/dev/null || fail "dock failed"
last | grep -q "focus-policy=on-demand" || fail "dock sent: $(last)"
[ "$(cat "$T/state/panel-mode")" = docked ] || fail "mode file after dock"

# toggle on a docked panel summons it (does not remove it)
: > "$T/calls"
"$P" toggle >/dev/null || fail "toggle (docked) failed"
last | grep -q "focus-policy=exclusive" || fail "toggle on a docked panel sent: $(last)"
kill -0 "$SPID" 2>/dev/null || fail "toggle on a docked panel stopped it"

# toggle on a summoned panel removes it
"$P" toggle >/dev/null
[ -f "$T/state/panel.pid" ] && fail "toggle on a summoned panel left the pidfile"
[ -f "$T/state/panel-mode" ] && fail "stop left the mode file"

# garbage in the mode file reads as docked: a toggle summons rather than removes (stop removed the socket and killed the stand-in: make new ones)
wait "$SPID" 2>/dev/null; kill $LPID 2>/dev/null; rm -f "$SOCK"
python3 - "$SOCK" <<'PY' & LPID=$!
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); s.listen(1); time.sleep(60)
PY
sleep 30 & SPID=$!; echo $SPID > "$T/state/panel.pid"
for _ in $(seq 40); do [ -S "$SOCK" ] && break; sleep 0.05; done
printf 'exclusive-ish' > "$T/state/panel-mode"; : > "$T/calls"
"$P" toggle >/dev/null
last | grep -q "focus-policy=exclusive" || fail "garbage mode did not read as docked: $(last)"

# a panel that is not running cannot be summoned
rm -f "$T/state/panel.pid"
"$P" summon >/dev/null 2>&1 && fail "summon of a missing panel claimed success"
# the option NAME is kitty's own: the fake kitten above accepted `focus_policy` once while the real panel answered "Unknown flag" and the keyboard
# was never given back. Ask the real kitten what it calls the flag (skipped without one).
REAL=$(PATH="${PATH#$T/bin:}" command -v kitten || true)
if [ -n "$REAL" ]; then
  "$REAL" panel --help 2>/dev/null | grep -q -- '--focus-policy' || fail "this kitten has no --focus-policy: summon/dock cannot work here"
fi
echo "PASS: summon/dock/toggle send the right focus_policy to the panel's socket and keep the mode file"
