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
    local s real seen=$'\n'
    while IFS= read -r s; do
        mux_owned_socket "$s" || continue
        # a socket and its /tmp compatibility link are ONE kitty: list the first spelling only
        real=$(readlink -f -- "$s" 2>/dev/null || printf '%s' "$s")
        case "$seen" in *$'\n'"$real"$'\n'*) continue ;; esac
        seen+="$real"$'\n'
        printf '%s\n' "$s"
    done < <(ls -t /tmp/mykitty-* "${XDG_RUNTIME_DIR:-/nonexistent}"/mykitty-* 2>/dev/null)
}

# Where kitty sockets are looked for, one directory per line, in the same order as bin/kittymux's _socket_dirs(): $KITTYMUX_SOCKET_DIRS (':'-separated, existing
# directories only: tests, or a setup that keeps its sockets elsewhere) replaces the defaults; otherwise the private $XDG_RUNTIME_DIR first, then /tmp.
mux_socket_dirs() {
    local d
    if [[ -n "${KITTYMUX_SOCKET_DIRS:-}" ]]; then
        local IFS=:
        for d in $KITTYMUX_SOCKET_DIRS; do [[ -n "$d" && -d "$d" ]] && printf '%s\n' "$d"; done
        return 0
    fi
    [[ -n "${XDG_RUNTIME_DIR:-}" && -d "$XDG_RUNTIME_DIR" ]] && printf '%s\n' "$XDG_RUNTIME_DIR"
    printf '%s\n' /tmp
}

# The socket of the kitty with this pid, in any of those directories. Fails when there is none we own.
mux_socket_for_pid() {
    local pid="${1:-}" d
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    while IFS= read -r d; do
        mux_owned_socket "$d/mykitty-$pid" && { printf 'unix:%s' "$d/mykitty-$pid"; return 0; }
    done < <(mux_socket_dirs)
    return 1
}

# The kitty this process was started FROM (kitty spawns key-bound commands, so its pid is our parent's; a command run through the CLI has it in KITTY_PID),
# or nothing when we were not started inside a kitty at all. Never "the newest": a second kitty must not be mistaken for the one that got the key.
mux_own_socket() {
    mux_socket_for_pid "$PPID" && return 0
    mux_socket_for_pid "${KITTY_PID:-}" && return 0
    return 1
}

# An optional explicit target never falls back. Otherwise prefer the launching
# kitty's socket over inherited env, then owned discovery. fd:N is a kitten handle.
# Failure prints nothing: callers must not pass an empty --to to kitty.
mux_resolve_socket() {
    local s target="${1:-}"
    if (( $# )); then
        if [[ "$target" == unix:* ]]; then
            mux_owned_socket "${target#unix:}" || return 1
        elif [[ ! "$target" =~ ^fd:[0-9]+$ ]]; then
            return 1
        fi
        printf '%s' "$target"; return 0
    fi
    if [[ "${KITTY_LISTEN_ON:-}" =~ ^fd:[0-9]+$ ]]; then
        printf '%s' "$KITTY_LISTEN_ON"; return 0
    fi
    for s in "/tmp/mykitty-${PPID}" "${XDG_RUNTIME_DIR:-/nonexistent}/mykitty-${PPID}" "/tmp/kitty-${PPID}"; do
        mux_owned_socket "$s" && { printf 'unix:%s' "$s"; return 0; }
    done
    if [[ "${KITTY_LISTEN_ON:-}" == unix:* ]]; then
        mux_owned_socket "${KITTY_LISTEN_ON#unix:}" && { printf '%s' "$KITTY_LISTEN_ON"; return 0; }
    fi
    s="$(mux_kitty_sockets | head -n1)"
    if [[ -n "$s" ]] && mux_owned_socket "$s"; then
        printf 'unix:%s' "$s"; return 0
    fi
    if mux_owned_socket /tmp/mykitty; then
        printf 'unix:/tmp/mykitty'; return 0
    fi
    return 1
}
