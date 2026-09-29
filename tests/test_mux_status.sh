#!/usr/bin/env bash
# Plain-bash tests for bin/mux-status (no kitty needed). Exits non-zero on failure.
set -u
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bin="$here/../bin/mux-status"
fail=0
check() { # name expected actual
    if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected [$2] got [$3]"; fail=1; fi
}

esc_working="$(printf '\033]1337;SetUserVar=kittymux_status=%s\007' "$(printf %s working | base64 -w0)")"
esc_done="$(printf '\033]1337;SetUserVar=kittymux_status=%s\007' "$(printf %s done | base64 -w0)")"

# printf/$() would strip nothing important here (BEL and ESC are preserved).
check "print working" "$esc_working" "$("$bin" --print working)"
check "print done"    "$esc_done"    "$("$bin" --print done)"
check "extra args ignored" "$esc_done" "$("$bin" --print done extra '{"json":1}')"

"$bin" bogus >/dev/null 2>&1;  check "bad state exits 2" 2 $?
"$bin" >/dev/null 2>&1;        check "no args exits 2"   2 $?

# runtime failure (no tty, no socket) must still exit 0
( unset KITTY_LISTEN_ON KITTY_WINDOW_ID TMUX; setsid "$bin" working </dev/null >/dev/null 2>&1 ); check "no tty/no socket exits 0" 0 $?

exit $fail
