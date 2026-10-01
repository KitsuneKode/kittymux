#!/usr/bin/env bash
# Fresh-machine install test, in a throw-away $HOME (your real config is never touched):
#   install.sh → idempotent → kitty accepts the generated config → doctor runs → uninstall leaves no trace.
# kitty is optional: without it only the file-level checks run.
set -u

HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in jq python3 fzf git; do
  command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }
done
command -v kitty >/dev/null 2>&1 || { echo "SKIP: kitty not installed"; exit 0; }

T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-install.XXXXXX")
trap 'rm -rf "$T"' EXIT
export HOME=$T/home XDG_CONFIG_HOME=$T/home/.config XDG_DATA_HOME=$T/home/.local/share XDG_STATE_HOME=$T/home/.local/state
unset KITTY_CONFIG_DIRECTORY KITTYMUX_STATE KITTY_LISTEN_ON KITTY_PID
mkdir -p "$HOME"
CONF=$XDG_CONFIG_HOME/kitty
fail() { echo "FAIL: $*"; exit 1; }
ok()   { echo "  ok   $*"; }

mkdir -p "$CONF" && printf 'font_size 12\n' > "$CONF/kitty.conf"       # a user who already has a config

"$HOME_DIR/install.sh" --leader >"$T/install.out" 2>&1 || { cat "$T/install.out"; fail "install.sh failed"; }
[ -L "$CONF/tab_bar.py" ] && [ -L "$CONF/kittymux_state.py" ] && [ -L "$CONF/kittymux_scan.py" ] || fail "helper modules were not linked"
[ -f "$CONF/kittymux-keys.conf" ] && [ -f "$XDG_DATA_HOME/fonts/kittymux-icons.ttf" ] || fail "keys conf / icon font missing"
[ "$(stat -c %a "$XDG_STATE_HOME/kittymux")" = 700 ] || fail "state dir is not 0700"
grep -q '^font_size 12$' "$CONF/kitty.conf" || fail "the user's own kitty.conf line was lost"
ok "fresh install: links, keys, font, 0700 state dir; the existing kitty.conf line is kept"

[ -f "$CONF/open-actions.conf" ] && ! grep -q '@KITTYMUX_HOME@' "$CONF/open-actions.conf" \
  && grep -q "$HOME_DIR/bin/mux-open-ref" "$CONF/open-actions.conf" || fail "open-actions.conf was not rendered"
ok "open-actions.conf rendered with this checkout's mux-open-ref"

before=$(cat "$CONF/kitty.conf")
"$HOME_DIR/install.sh" --leader >/dev/null 2>&1 || fail "second install failed"
[ "$before" = "$(cat "$CONF/kitty.conf")" ] || fail "a second install changed kitty.conf (it must be idempotent)"
ok "second install is a no-op for kitty.conf"

# kitty must accept the generated config without a single complaint. (`kitty --debug-config` reports
# none of these, so ask kitty's own loader: bad lines are returned, warnings go to stderr.)
check_config() {
  kitty +runpy "
from kitty.config import load_config
bad = []
load_config('$CONF/kitty.conf', accumulate_bad_lines=bad)
print('BAD LINES:', len(bad))
for b in bad: print('  line', b.number, b.line[:70], '|', str(b.exception)[:80])" 2>&1
}
out=$(check_config)
if printf '%s' "$out" | grep -qE "BAD LINES: [1-9]|Could not find included|unknown config key|Traceback"; then
  printf '%s\n' "$out" | head -20
  fail "kitty complains about the generated config"
fi
printf '%s' "$out" | grep -q "BAD LINES: 0" || { printf '%s\n' "$out" | head; fail "could not load the config"; }
ok "kitty's config loader: 0 bad lines, no warnings"

"$HOME_DIR/bin/kittymux" doctor >"$T/doctor.out" 2>&1
grep -q "Traceback" "$T/doctor.out" && { cat "$T/doctor.out"; fail "doctor crashed"; }
ok "doctor runs without crashing"

"$HOME_DIR/bin/kittymux" uninstall >"$T/dry.out" 2>&1
[ -L "$CONF/tab_bar.py" ] || fail "the dry run removed something"
"$HOME_DIR/bin/kittymux" uninstall --yes --purge >"$T/un.out" 2>&1 || { cat "$T/un.out"; fail "uninstall failed"; }
left=$(grep -c kittymux "$CONF/kitty.conf" || true)
[ "$left" = 0 ] || fail "uninstall left $left kittymux lines in kitty.conf"
[ ! -e "$CONF/tab_bar.py" ] && [ ! -e "$CONF/kittymux_state.py" ] && [ ! -e "$CONF/kittymux-keys.conf" ] \
  && [ ! -e "$XDG_DATA_HOME/fonts/kittymux-icons.ttf" ] && [ ! -e "$XDG_STATE_HOME/kittymux" ] || fail "uninstall left files behind"
grep -q '^font_size 12$' "$CONF/kitty.conf" || fail "uninstall damaged the user's own config"
ls "$CONF"/kitty.conf.bak.kittymux-uninstall-* >/dev/null 2>&1 || fail "no kitty.conf backup from uninstall"
ok "uninstall: dry run touched nothing; --yes --purge removed everything it added and kept the user's lines"
out=$(check_config)
printf '%s' "$out" | grep -q "BAD LINES: 0" && ! printf '%s' "$out" | grep -qE "Could not find included|unknown config key" \
  || { printf '%s\n' "$out" | head; fail "kitty complains after uninstall (a dangling include?)"; }
ok "kitty is happy after uninstall too"
# a user's OWN open-actions.conf is never overwritten and never removed
printf 'protocol file\nmime text/*\naction launch --type=overlay less ${FILE_PATH}\n' > "$CONF/open-actions.conf"
"$HOME_DIR/install.sh" >"$T/install2.out" 2>&1 || fail "install over a user's open-actions failed"
grep -q 'mime text/\*' "$CONF/open-actions.conf" && ! grep -q mux-open-ref "$CONF/open-actions.conf" || fail "install overwrote the user's open-actions.conf"
grep -q "open-actions" "$T/install2.out" || fail "install did not tell the user how to add the file:line lines"
"$HOME_DIR/bin/kittymux" uninstall --yes >/dev/null 2>&1
grep -q 'mime text/\*' "$CONF/open-actions.conf" || fail "uninstall deleted the user's open-actions.conf"
ok "a user's own open-actions.conf is kept by install and uninstall"
echo "PASS: install → reinstall → config valid → doctor → uninstall, in a fresh \$HOME"
