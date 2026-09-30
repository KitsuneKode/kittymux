# shellcheck shell=bash
# lib/socket.sh — finding *our* kitty, and keeping scratch files private.
#
# /tmp is world-writable: anyone can create /tmp/mykitty-1234. Sending `ls` output or
# window text to a socket we did not create would hand it to whoever planted it. So a
# socket is trusted only if it is a real socket OWNED BY THE CURRENT USER. Likewise
# predictable /tmp file names (flags, logs) are a symlink-attack surface: those live in a
# private (0700) runtime directory instead.

# Private per-user directory for flags/logs. Prefers $XDG_RUNTIME_DIR (tmpfs, 0700).
mux_runtime_dir() {
    local base="${XDG_RUNTIME_DIR:-}" d
    if [[ -d "$base" && -O "$base" ]]; then
        d="$base/kittymux"
    else
        d="${KITTYMUX_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/kittymux}/run"
    fi
    mkdir -p "$d" 2>/dev/null && chmod 700 "$d" 2>/dev/null
    printf '%s' "$d"
}

# A real socket owned by us.
mux_owned_socket() { [[ -S "$1" && -O "$1" ]]; }

# Owned kitty sockets, newest first (kitty appends its pid: listen_on unix:/tmp/mykitty →
# /tmp/mykitty-<pid>). Also looks in $XDG_RUNTIME_DIR, the safer place for listen_on.
mux_kitty_sockets() {
    local s
    while IFS= read -r s; do
        mux_owned_socket "$s" && printf '%s\n' "$s"
    done < <(ls -t /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-* 2>/dev/null)
}

# The kitty that launched us: env → our parent (kitty spawns key-bound scripts) → newest
# owned socket → a conventional default. Prints a `--to` value.
mux_resolve_socket() {
    local s
    if [[ "${KITTY_LISTEN_ON:-}" == unix:* ]]; then
        mux_owned_socket "${KITTY_LISTEN_ON#unix:}" && { printf '%s' "$KITTY_LISTEN_ON"; return; }
    elif [[ -n "${KITTY_LISTEN_ON:-}" ]]; then          # fd:N handed to kittens — not a path
        printf '%s' "$KITTY_LISTEN_ON"; return
    fi
    for s in "/tmp/mykitty-${PPID}" "${XDG_RUNTIME_DIR:-/nonexistent}/mykitty-${PPID}" "/tmp/kitty-${PPID}"; do
        mux_owned_socket "$s" && { printf 'unix:%s' "$s"; return; }
    done
    s="$(mux_kitty_sockets | head -n1)"
    if [[ -n "$s" ]]; then printf 'unix:%s' "$s"; else printf 'unix:/tmp/mykitty'; fi
}
