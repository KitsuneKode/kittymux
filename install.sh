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

# ── options ──────────────────────────────────────────────────────────────────
#   --leader[=KEY]   also install leader mode (tap KEY, then one key; default KEY: ctrl+space)
LEADER=0; LEADER_KEY="ctrl+space"
for arg in "$@"; do
    case "$arg" in
        --leader)       LEADER=1 ;;
        --leader=*)     LEADER=1; LEADER_KEY="${arg#--leader=}" ;;
        -h|--help)      sed -n '2,13p;' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; echo "options: --leader[=KEY]"; exit 0 ;;
        *) echo "install.sh: unknown option $arg" >&2; exit 2 ;;
    esac
done

KITTYMUX_HOME="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
KITTY_CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/kitty"
KITTY_CONF="$KITTY_CONF_DIR/kitty.conf"
STATE_DIR="${KITTYMUX_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/kittymux}"
KEYS_OUT="$KITTY_CONF_DIR/kittymux-keys.conf"
EDGE_FILE="$KITTY_CONF_DIR/include-tab-edge.conf"

say()  { printf '  %s\n' "$*"; }
# escape a value for use as a sed replacement (paths may contain & | \ /)
sed_esc() { printf '%s' "$1" | sed -e 's/[\\/&|]/\\&/g'; }
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
if [[ "${kitty_ver%%.*}" -eq 0 ]] && (( kitty_major < 48 )); then
    warn "kitty $kitty_ver detected — vertical tabs need >= 0.48, 0.49+ recommended"
fi
ok "deps: jq, python3, fzf, git, kitty ${kitty_ver:-?}"

# ── render keys conf ────────────────────────────────────────────────────────
mkdir -p "$KITTY_CONF_DIR"
case "$KITTYMUX_HOME" in *$'\n'*) die "install path contains a newline" ;; esac
sed "s|@KITTYMUX_HOME@|$(sed_esc "$KITTYMUX_HOME")|g" \
    "$KITTYMUX_HOME/kittymux-keys.conf.tpl" > "$KEYS_OUT"
ok "rendered keys → $KEYS_OUT"

# ── leader mode (opt-in) ─────────────────────────────────────────────────────
LEADER_OUT="$KITTY_CONF_DIR/kittymux-leader.conf"
if (( LEADER )); then
    [[ "$LEADER_KEY" =~ ^[A-Za-z0-9+_.,-]+$ ]] || die "invalid leader key '$LEADER_KEY'"
    sed -e "s|@KITTYMUX_HOME@|$(sed_esc "$KITTYMUX_HOME")|g" -e "s|@KITTYMUX_LEADER@|$(sed_esc "$LEADER_KEY")|g" \
        "$KITTYMUX_HOME/kittymux-leader.conf.tpl" > "$LEADER_OUT"
    ok "rendered leader mode (leader: $LEADER_KEY) → $LEADER_OUT"
fi

# ── open-actions: click `file.py:42` → editor at that line (needs kitty ≥ 0.49.2 for detect_url_regex) ──
OPEN_OUT="$KITTY_CONF_DIR/open-actions.conf"
if [[ ! -e "$OPEN_OUT" ]] || grep -q '^# kittymux — click a file reference' "$OPEN_OUT" 2>/dev/null; then
    sed "s|@KITTYMUX_HOME@|$(sed_esc "$KITTYMUX_HOME")|g" "$KITTYMUX_HOME/open-actions.conf.tpl" > "$OPEN_OUT"
    ok "rendered open-actions → $OPEN_OUT (click src/app.py:42 to open it in \$EDITOR)"
else
    warn "you already have $OPEN_OUT — add kittymux's two lines from open-actions.conf.tpl to use file:line clicks"
fi

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
link_py window_title_bar.py      # kitty's per-pane title bar loads this by name (it hands over to kittymux_panetitle)
for helper in "$KITTYMUX_HOME"/python/kittymux_*.py; do
    link_py "$(basename "$helper")"
done
ok "tab_bar.py, window_title_bar.py + helper modules → symlinks"

# ── legacy tab-edge default (per-instance layout state now wins) ─────────────────────────
[[ -f "$EDGE_FILE" ]] || printf '# kittymux legacy default — per-instance layout state overrides this\ntab_bar_edge bottom\n' > "$EDGE_FILE"
ok "tab-edge include ready"

# ── brand icon font (real provider logos via symbol_map) ─────────────────────
FONT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"
mkdir -p "$FONT_DIR"
# Copy only when the font actually differs. Rewriting an identical file bumps its timestamp, and a running kitty would then wonder whether it has loaded it.
if cmp -s "$KITTYMUX_HOME/assets/kittymux-icons.ttf" "$FONT_DIR/kittymux-icons.ttf"; then
    ok "icon font up to date → $FONT_DIR/kittymux-icons.ttf"
else
    cp "$KITTYMUX_HOME/assets/kittymux-icons.ttf" "$FONT_DIR/"
    command -v fc-cache >/dev/null 2>&1 && fc-cache -f "$FONT_DIR" >/dev/null 2>&1
    ok "icon font → $FONT_DIR/kittymux-icons.ttf (a kitty started before this needs a restart to draw new glyphs)"
fi

# ── include lines in kitty.conf (backup first, never overwrite) ─────────────
touch "$KITTY_CONF"
cp "$KITTY_CONF" "$KITTY_CONF.bak.$(date +%Y%m%d-%H%M%S)"
add_include() {
    local line="$1"
    grep -qxF "$line" "$KITTY_CONF" || printf '\n%s\n' "$line" >> "$KITTY_CONF"
}
add_include "include $KEYS_OUT"
(( LEADER )) && add_include "include $LEADER_OUT"
add_include "include $KITTYMUX_HOME/kittymux.conf"
# kitty rejects a file included twice (and pops an error at every start). If your
# config already includes the edge file (e.g. via another conf), leave it be — but it
# must come AFTER kittymux.conf, or kittymux.conf's tab_bar_edge wins over the toggle.
if grep -rqs "include-tab-edge.conf" "$KITTY_CONF_DIR"/*.conf 2>/dev/null; then
    warn "include-tab-edge.conf is already included by your config — make sure it comes after kittymux.conf"
else
    add_include "include $EDGE_FILE"
fi
# Per-window bar layout (kittymux layout …): kitty runs this on every (re)load and takes
# its output as config. It must come LAST so a saved layout wins; with none saved it prints
# nothing and your own tab_bar_* settings stay in charge.
chmod +x "$KITTYMUX_HOME/python/kittymux_layout.py" 2>/dev/null || true
add_include "geninclude $KITTYMUX_HOME/python/kittymux_layout.py"
ok "kitty.conf includes added (backup: kitty.conf.bak.*)"

# ── the `kittymux` command on your PATH ─────────────────────────────────────
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
mkdir -p "$BIN_DIR"
if [[ -e "$BIN_DIR/kittymux" && ! -L "$BIN_DIR/kittymux" ]]; then
    warn "$BIN_DIR/kittymux exists and is not a link — left alone (use $KITTYMUX_HOME/bin/kittymux)"
else
    ln -sfn "$KITTYMUX_HOME/bin/kittymux" "$BIN_DIR/kittymux"
    ok "kittymux command → $BIN_DIR/kittymux"
fi
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR is not on your PATH — add  export PATH=\"$BIN_DIR:\$PATH\"  to your shell profile (then: kittymux doctor)" ;;
esac

# ── state dir + exec bits ───────────────────────────────────────────────────
mkdir -p "$STATE_DIR/sessions" && chmod 700 "$STATE_DIR" "$STATE_DIR/sessions"
chmod +x "$KITTYMUX_HOME"/bin/* 2>/dev/null || true
ok "state → $STATE_DIR (0700)"

echo
echo "Done. Reload kitty with ctrl+shift+alt+r (or restart kitty)."
echo
say "Notes:"
say "• remote control: scripts need a listen socket — add (private directory, no in-band control)"
say "    allow_remote_control socket-only"
say "    listen_on unix:\${XDG_RUNTIME_DIR}/mykitty"
say "  to kitty.conf if you don't already have one."
say "• live Claude quota is opt-in: export KITTYMUX_USAGE_LIVE=1"
say "• project picker root: export KITTYMUX_PROJECTS=~/code"
say "• try it:  kittymux doctor   ·   kittymux screenshot   ·   kittymux dim on   ·   kittymux demo"
say "• uninstall: kittymux uninstall --yes   (removes the include lines, symlinks and the command; --purge also $STATE_DIR)"
