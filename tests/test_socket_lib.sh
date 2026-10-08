#!/usr/bin/env bash
# Tests for lib/socket.sh — trust only sockets we own; private scratch dir.
set -u
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/socket.sh
source "$here/../lib/socket.sh"
fail=0
check() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected [$2] got [$3]"; fail=1; fi; }
yes_no() { "$@" && echo yes || echo no; }

tmp="$(mktemp -d)"; srv=""; srv2=""
trap 'kill "$srv" "$srv2" 2>/dev/null || true; rm -rf "$tmp"' EXIT
python3 - "$tmp/mine.sock" <<'PY' &
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); time.sleep(30)
PY
srv=$!
for _ in $(seq 1 30); do [[ -S "$tmp/mine.sock" ]] && break; sleep 0.1; done

check "own socket is trusted"        yes "$(yes_no mux_owned_socket "$tmp/mine.sock")"
: > "$tmp/plain"
check "regular file is not a socket" no  "$(yes_no mux_owned_socket "$tmp/plain")"
check "missing path is rejected"     no  "$(yes_no mux_owned_socket "$tmp/nope")"
# a socket owned by someone else (root): the journal socket exists on systemd machines
for foreign in /run/systemd/journal/socket /dev/log /run/systemd/private; do
    if [[ -S "$foreign" && ! -O "$foreign" ]]; then
        check "root-owned socket ($foreign) is rejected" no "$(yes_no mux_owned_socket "$foreign")"; break
    fi
done

# PPID rule: a socket named after our parent wins over a stale env var
mkdir -p "$tmp/run"
python3 - "$tmp/run/mykitty-$PPID" <<'PY' &
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); time.sleep(30)
PY
srv2=$!
for _ in $(seq 1 30); do [[ -S "$tmp/run/mykitty-$PPID" ]] && break; sleep 0.1; done
got="$(XDG_RUNTIME_DIR="$tmp/run" KITTY_LISTEN_ON="unix:$tmp/plain" mux_resolve_socket)"
check "stale env socket is ignored, parent's socket used" "unix:$tmp/run/mykitty-$PPID" "$got"
got="$(XDG_RUNTIME_DIR="$tmp/run" KITTY_LISTEN_ON="unix:$tmp/mine.sock" mux_resolve_socket)"
check "parent wins over an owned but stale inherited socket" "unix:$tmp/run/mykitty-$PPID" "$got"
got="$(XDG_RUNTIME_DIR="$tmp/run" mux_resolve_socket "unix:$tmp/mine.sock")"
check "explicit owned target wins over parent" "unix:$tmp/mine.sock" "$got"
got="$(mux_resolve_socket "unix:$tmp/plain" || printf rejected)"
check "explicit regular-file target fails closed" rejected "$got"
got="$(XDG_RUNTIME_DIR="$tmp/run" KITTY_LISTEN_ON="fd:7" mux_resolve_socket)"
check "fd: handles (kittens) pass through"  "fd:7" "$got"

# Isolate discovery: never inspect or contact live kitty for absence cases.
got="$(
    # Resolver calls these overrides indirectly.
    # shellcheck disable=SC2329
    mux_owned_socket() { return 1; }
    # shellcheck disable=SC2329
    mux_kitty_sockets() { :; }
    unset KITTY_LISTEN_ON
    socket="$(mux_resolve_socket)"; rc=$?
    printf '%s:%s' "$rc" "$socket"
)"
check "no trusted socket returns failure and no fallback address" '1:' "$got"

# a socket and its /tmp compatibility link are ONE kitty
mkdir -p "$tmp/leg"; ln -sf "$tmp/run/mykitty-$PPID" "$tmp/leg/mykitty-$PPID"
listed="$(
    ls() { command ls "$@" 2>/dev/null; }
    # shellcheck disable=SC2329
    mux_kitty_sockets_probe() { :; }
    for s in "$tmp/leg/mykitty-$PPID" "$tmp/run/mykitty-$PPID"; do mux_owned_socket "$s" && printf '%s\n' "$s"; done | while IFS= read -r s; do readlink -f -- "$s"; done | sort -u | wc -l
)"
check "the link and the socket resolve to one kitty" 1 "$listed"

# the kitty a command was started FROM comes before any "newest" one (the panel used to watch the newest kitty and act on the wrong one)
mkdir -p "$tmp/run2"
python3 - "$tmp/run2/mykitty-4242" "$tmp/run2/mykitty-4243" <<'PY' &
import socket, sys, time
socks = []
for path in sys.argv[1:]:
    s = socket.socket(socket.AF_UNIX); s.bind(path); socks.append(s); time.sleep(0.2)   # the second one is the newest
time.sleep(30)
PY
srv3=$!
for _ in $(seq 1 30); do [[ -S "$tmp/run2/mykitty-4243" ]] && break; sleep 0.1; done
got="$(XDG_RUNTIME_DIR="$tmp/run2" mux_socket_for_pid 4242)"
check "a socket is found by its kitty's pid in the runtime dir"  "unix:$tmp/run2/mykitty-4242" "$got"
got="$(XDG_RUNTIME_DIR="$tmp/run2" mux_socket_for_pid 4244 || printf none)"
check "a pid with no socket finds nothing"                        none "$got"
for bad in "" 0 -1 "../x" "4242 " "4242/../4243"; do
    got="$(XDG_RUNTIME_DIR="$tmp/run2" mux_socket_for_pid "$bad" || printf none)"
    check "pid [$bad] is not a pid"                              none "$got"
done
got="$(XDG_RUNTIME_DIR="$tmp/run2" KITTY_PID=4242 mux_own_socket)"
check "the launching kitty (KITTY_PID) beats the newest socket"  "unix:$tmp/run2/mykitty-4242" "$got"
got="$(XDG_RUNTIME_DIR="$tmp/run2" KITTY_PID="" mux_own_socket || printf none)"
check "not started inside a kitty: no own socket, never 'newest'" none "$got"
got="$(XDG_RUNTIME_DIR="$tmp/run" KITTY_PID=4242 mux_own_socket)"
check "the parent's socket wins over KITTY_PID"                  "unix:$tmp/run/mykitty-$PPID" "$got"
# the panel itself (a stand-in hyprctl that knows no focused window, so a live desktop cannot change the answer): started from kitty 4242 while kitty 4243 is newer, it must watch 4242
mkdir -p "$tmp/fakebin"; printf '#!/bin/sh\necho {}\n' > "$tmp/fakebin/hyprctl"; chmod +x "$tmp/fakebin/hyprctl"
env -u KITTYMUX_TARGET XDG_RUNTIME_DIR="$tmp/run2" KITTY_PID=4242 PATH="$tmp/fakebin:$PATH" "$here/../bin/mux-panel" target > "$tmp/target.out" 2>/dev/null
check "mux-panel watches the kitty it was started from, not the newest" "unix:$tmp/run2/mykitty-4242" "$(cat "$tmp/target.out")"
env -u KITTYMUX_TARGET -u KITTY_PID KITTYMUX_TARGET="" XDG_RUNTIME_DIR="$tmp/run2" PATH="$tmp/fakebin:$PATH" "$here/../bin/mux-panel" target > "$tmp/target2.out" 2>/dev/null
check "started from outside every kitty it falls back to the newest" "unix:$tmp/run2/mykitty-4243" "$(cat "$tmp/target2.out")"
kill "$srv3" 2>/dev/null || true

# private runtime dir
d="$(XDG_RUNTIME_DIR="$tmp/run" mux_runtime_dir)"
check "runtime dir under XDG_RUNTIME_DIR"   "$tmp/run/kittymux" "$d"
check "runtime dir is 0700"                 700 "$(stat -c %a "$d")"
d="$(XDG_RUNTIME_DIR="" KITTYMUX_STATE="$tmp/state" mux_runtime_dir)"
check "falls back to the private state dir" "$tmp/state/run" "$d"
check "fallback dir is 0700"                700 "$(stat -c %a "$d")"

exit $fail
