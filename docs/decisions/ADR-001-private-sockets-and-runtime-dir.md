# ADR-001: Private Owned Kitty Sockets and Runtime Directory

## Status
Accepted

## Date
2026-11-21

## Context
kittymux scripts and helpers talk to kitty over remote-control Unix sockets (`listen_on unix:...`) and store runtime scratch files (flags, logs, session state). `/tmp` is world-writable: another local user can plant `/tmp/mykitty-<pid>` or symlink predictable filenames, exposing `kitty @ ls` output or pane text. In addition, background keybind launches receive neither `KITTY_LISTEN_ON` nor `KITTY_WINDOW_ID`, and multiple kitty instances commonly run concurrently (including live user kitties during test runs).

## Decision
- **Owned-socket verification (`lib/socket.sh`)**: Trust a socket path only when it is a real Unix socket owned by the current user (`[[ -S "$1" && -O "$1" ]]`).
- **Private runtime and state directories**: Prefer `$XDG_RUNTIME_DIR/kittymux` (tmpfs, `0700`) for runtime flags/logs, falling back to `$KITTYMUX_STATE/run` (`0700`). When creating nested directories with `mkdir -p -m 700`, pass both parent and child explicitly because `-m` applies only to the deepest directory of each argument.
- **Strict own-kitty resolution**:
  - An explicit target passed to `mux_resolve_socket` never falls back to discovery.
  - A kitten's `fd:N` channel cannot go stale and takes precedence over socket files.
  - Commands launched from inside kitty resolve *that* kitty (`$PPID`, `KITTY_LISTEN_ON`, `KITTY_PID`) and never fall back to "the newest" socket in `mux_own_socket`.
  - Discovery searches `$KITTYMUX_SOCKET_DIRS` (replacing defaults for test isolation) or `$XDG_RUNTIME_DIR` then `/tmp`, deduplicating a socket and its `/tmp` compatibility symlink via `readlink -f`.
  - Failed resolution prints nothing so callers never pass an empty `--to` argument to `kitty @`.
- **Scratch tab identity (`lib/mux.sh`)**: Include the socket inode in scratch tracking paths so a restarted kitty instance cannot inherit stale scratch flags.

## Alternatives Considered

### World-writable `/tmp` sockets without ownership checks
- Pros: Works with legacy defaults without `$XDG_RUNTIME_DIR`.
- Cons: Allows local socket spoofing and symlink attacks on predictable filenames.
- Rejected: Security risk for terminal content and remote-control traffic.

### Always targeting the newest or focused kitty
- Pros: Simpler resolution when background keybinds lack `KITTY_LISTEN_ON`.
- Cons: Misdirects keybinds and tests into unrelated live kitties.
- Rejected: Caused test rigs to spawn windows into the author's live kitty.

## Consequences
- Every smoke rig isolates itself by setting `KITTYMUX_SOCKET_DIRS` to its temporary directory.
- Background keybinds without `KITTY_WINDOW_ID` fall back to `state:focused` inside the resolved kitty process.
- Legacy `/tmp/kitty-$PPID` and `/tmp/mykitty` fallbacks remain skipped whenever `KITTYMUX_SOCKET_DIRS` is set.
