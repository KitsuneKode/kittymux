#!/usr/bin/env bash
# Tests for lib/socket.sh — trust only sockets we own; private scratch dir.
set -u
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/socket.sh
source "$here/../lib/socket.sh"
fail=0
check() { if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected [$2] got [$3]"; fail=1; fi; }
yes_no() { "$@" && echo yes || echo no; }

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
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
got="$(XDG_RUNTIME_DIR="$tmp/run" KITTY_LISTEN_ON="fd:7" mux_resolve_socket)"
check "fd: handles (kittens) pass through"  "fd:7" "$got"

# private runtime dir
d="$(XDG_RUNTIME_DIR="$tmp/run" mux_runtime_dir)"
check "runtime dir under XDG_RUNTIME_DIR"   "$tmp/run/kittymux" "$d"
check "runtime dir is 0700"                 700 "$(stat -c %a "$d")"
d="$(XDG_RUNTIME_DIR="" KITTYMUX_STATE="$tmp/state" mux_runtime_dir)"
check "falls back to the private state dir" "$tmp/state/run" "$d"
check "fallback dir is 0700"                700 "$(stat -c %a "$d")"

kill "$srv" "$srv2" 2>/dev/null
exit $fail
