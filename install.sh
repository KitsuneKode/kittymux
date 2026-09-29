#!/usr/bin/env bash
# kittymux install — non-destructive setup.
#
# What it does:
#   1. Verifies deps: kitty >= 0.48, jq, python3, fzf, git
#   2. Renders kittymux-keys.conf (absolute paths baked) into ~/.config/kitty
#   3. Symlinks python/tab_bar.py into ~/.config/kitty (kitty loads it there)
#   4. Adds `include` lines to kitty.conf — AFTER backing it up
#   5. Creates $KITTYMUX_STATE (0700) and the tab-edge include file
#
# What it never does: overwrite kitty.conf, remove options, or touch
# anything outside ~/.config/kitty and the state dir.

set -euo pipefail

KITTYMUX_HOME="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
KITTY_CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/kitty"
KITTY_CONF="$KITTY_CONF_DIR/kitty.conf"
STATE_DIR="${KITTYMUX_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/kittymux}"
KEYS_OUT="$KITTY_CONF_DIR/kittymux-keys.conf"
EDGE_FILE="$KITTY_CONF_DIR/include-tab-edge.conf"

say()  { printf '  %s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

echo "kittymux install — $KITTYMUX_HOME"
echo

# ── deps ────────────────────────────────────────────────────────────────────
missing=()
for dep in jq python3 fzf git; do
    command -v "$dep" >/dev/null 2>&1 || missing+=("$dep")
done
command -v kitty >/dev/null 2>&1 || missing+=("kitty")
if ((${#missing[@]})); then
    die "missing deps: ${missing[*]} — install them and rerun"
fi
kitty_ver="$(kitty --version 2>/dev/null | awk '{print $2}')"
kitty_major="${kitty_ver#*.}"; kitty_major="${kitty_major%%.*}"
kitty_minor="${kitty_ver##*.}"
if [[ "${kitty_ver%%.*}" -eq 0 ]] && (( kitty_major < 48 )); then
    warn "kitty $kitty_ver detected — vertical tabs need >= 0.48, 0.49+ recommended"
fi
ok "deps: jq, python3, fzf, git, kitty ${kitty_ver:-?}"

# ── render keys conf ────────────────────────────────────────────────────────
mkdir -p "$KITTY_CONF_DIR"
sed "s|@KITTYMUX_HOME@|$KITTYMUX_HOME|g" \
    "$KITTYMUX_HOME/kittymux-keys.conf.tpl" > "$KEYS_OUT"
ok "rendered keys → $KEYS_OUT"

# ── tab_bar.py symlink (kitty auto-loads it from the config dir) ────────────
if [[ -L "$KITTY_CONF_DIR/tab_bar.py" ]]; then
    rm -f "$KITTY_CONF_DIR/tab_bar.py"
elif [[ -f "$KITTY_CONF_DIR/tab_bar.py" ]]; then
    mv "$KITTY_CONF_DIR/tab_bar.py" "$KITTY_CONF_DIR/tab_bar.py.bak"
    warn "existing tab_bar.py backed up to tab_bar.py.bak"
fi
ln -s "$KITTYMUX_HOME/python/tab_bar.py" "$KITTY_CONF_DIR/tab_bar.py"
ok "tab_bar.py → symlink"

# ── managed tab-edge file (mux-edge.sh rewrites it) ─────────────────────────
[[ -f "$EDGE_FILE" ]] || printf '# managed by kittymux mux-edge.sh — do not edit\ntab_bar_edge bottom\n' > "$EDGE_FILE"
ok "tab-edge include ready"

# ── include lines in kitty.conf (backup first, never overwrite) ─────────────
touch "$KITTY_CONF"
cp "$KITTY_CONF" "$KITTY_CONF.bak.$(date +%Y%m%d-%H%M%S)"
add_include() {
    local line="$1"
    grep -qxF "$line" "$KITTY_CONF" || printf '\n%s\n' "$line" >> "$KITTY_CONF"
}
add_include "include $KEYS_OUT"
add_include "include $KITTYMUX_HOME/kittymux.conf"
add_include "include $EDGE_FILE"
ok "kitty.conf includes added (backup: kitty.conf.bak.*)"

# ── state dir + exec bits ───────────────────────────────────────────────────
mkdir -p -m 700 "$STATE_DIR/sessions"
chmod +x "$KITTYMUX_HOME"/bin/*
ok "state → $STATE_DIR (0700)"

echo
echo "Done. Reload kitty with ctrl+shift+alt+r (or restart kitty)."
echo
say "Notes:"
say "• remote control: scripts need a listen socket — add e.g."
say "    listen_on unix:/tmp/mykitty"
say "  to kitty.conf if you don't already have one."
say "• live Claude quota is opt-in: export KITTYMUX_USAGE_LIVE=1"
say "• project picker root: export KITTYMUX_PROJECTS=~/code"
say "• uninstall: remove the three include lines, the tab_bar.py symlink,"
say "  and $STATE_DIR"
