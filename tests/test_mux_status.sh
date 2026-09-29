#!/usr/bin/env bash
# Plain-bash tests for bin/mux-status (no kitty needed). Exits non-zero on failure.
set -u
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bin="$here/../bin/mux-status"
fail=0
check() { # name expected actual
    if [[ "$2" == "$3" ]]; then echo "ok   $1"; else echo "FAIL $1: expected [$2] got [$3]"; fail=1; fi
}
b64() { printf %s "$1" | base64 -w0; }
esc() { printf '\033]1337;SetUserVar=%s=%s\007' "$1" "$(b64 "$2")"; }
# NB: $(...) keeps ESC/BEL bytes; only trailing newlines are stripped.

check "working clears msg"   "$(esc kittymux_msg '')$(esc kittymux_status working)" "$("$bin" --print working </dev/null)"
check "idle clears msg"      "$(esc kittymux_msg '')$(esc kittymux_status idle)"    "$("$bin" --print idle </dev/null)"
check "done, no msg"         "$(esc kittymux_msg '')$(esc kittymux_status done)"    "$("$bin" --print done </dev/null)"
check "--msg flag"           "$(esc kittymux_msg 'needs approval')$(esc kittymux_status waiting)" \
                             "$("$bin" --print --msg 'needs approval' waiting </dev/null)"
check "--msg ignored for working" "$(esc kittymux_msg '')$(esc kittymux_status working)" \
                             "$("$bin" --print --msg 'nope' working </dev/null)"

if command -v jq >/dev/null 2>&1; then
    check "stdin JSON .message" "$(esc kittymux_msg 'Claude needs your permission')$(esc kittymux_status waiting)" \
        "$(printf '%s' '{"message":"Claude needs your permission","hook_event_name":"Notification"}' | "$bin" --print waiting)"
    check "argv JSON (codex)" "$(esc kittymux_msg 'all done')$(esc kittymux_status done)" \
        "$("$bin" --print done '{"type":"agent-turn-complete","last-assistant-message":"all done"}' </dev/null)"
    check "stdin JSON without message" "$(esc kittymux_msg '')$(esc kittymux_status waiting)" \
        "$(printf '%s' '{"hook_event_name":"Notification"}' | "$bin" --print waiting)"
fi

long="$(printf 'x%.0s' $(seq 1 200))"
check "msg bounded to 120" "$(esc kittymux_msg "$(printf 'x%.0s' $(seq 1 120))")$(esc kittymux_status waiting)" \
    "$("$bin" --print --msg "$long" waiting </dev/null)"
check "msg newlines flattened" "$(esc kittymux_msg 'a b')$(esc kittymux_status waiting)" \
    "$("$bin" --print --msg $'a\nb' waiting </dev/null)"
check "msg control chars stripped" "$(esc kittymux_msg 'ab')$(esc kittymux_status waiting)" \
    "$("$bin" --print --msg $'a\001b' waiting </dev/null)"
# an embedded escape must never survive into the payload as a raw ESC inside the value
inj="$("$bin" --print --msg $'a\033]0;evil\007b' waiting </dev/null)"
check "no injected OSC in msg (exactly our 2)" 2 "$(printf '%s' "$inj" | grep -o $'\033\]' | wc -l)"

"$bin" bogus >/dev/null 2>&1;  check "bad state exits 2" 2 $?
"$bin" >/dev/null 2>&1;        check "no args exits 2"   2 $?

# runtime failure (no tty, no socket) must still exit 0
( unset KITTY_LISTEN_ON KITTY_WINDOW_ID TMUX; setsid "$bin" working </dev/null >/dev/null 2>&1 ); check "no tty/no socket exits 0" 0 $?

exit $fail
