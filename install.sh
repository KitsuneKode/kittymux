#!/usr/bin/env bash
# kittymux install — non-destructive setup.
#
# What it does:
#   1. Verifies deps: kitty >= 0.48, jq, python3, fzf, git
#   2. Renders kittymux-keys.conf (absolute paths baked) into ~/.config/kitty
#   3. Symlinks python/tab_bar.py + the kittymux_*.py helper modules into
#      ~/.config/kitty (kitty loads tab_bar.py there; the sidebar kitten finds the
#      helpers there too)
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

# ── python symlinks (kitty auto-loads tab_bar.py from the config dir; the
#    kittymux_*.py helpers are imported by tab_bar.py and the sidebar kitten) ──
link_py() {
    local name="$1" dest="$KITTY_CONF_DIR/$1"
    if [[ -L "$dest" ]]; then
        rm -f "$dest"
    elif [[ -f "$dest" ]]; then
        mv "$dest" "$dest.bak"
        warn "existing $name backed up to $name.bak"
    fi
    ln -s "$KITTYMUX_HOME/python/$name" "$dest"
}
link_py tab_bar.py
for helper in "$KITTYMUX_HOME"/python/kittymux_*.py; do
    link_py "$(basename "$helper")"
done
ok "tab_bar.py + helper modules → symlinks"

# ── managed tab-edge file (mux-edge.sh rewrites it) ─────────────────────────
[[ -f "$EDGE_FILE" ]] || printf '# managed by kittymux mux-edge.sh — do not edit\ntab_bar_edge bottom\n' > "$EDGE_FILE"
ok "tab-edge include ready"

# ── brand icon font (real provider logos via symbol_map) ─────────────────────
FONT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"
mkdir -p "$FONT_DIR"
cp "$KITTYMUX_HOME/assets/kittymux-icons.ttf" "$FONT_DIR/"
command -v fc-cache >/dev/null 2>&1 && fc-cache -f "$FONT_DIR" >/dev/null 2>&1
ok "icon font → $FONT_DIR/kittymux-icons.ttf"

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
