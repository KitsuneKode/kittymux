#!/usr/bin/env bash

# Shared helpers for kitty session scripts.
#
# Model:
#   Session  = named kitty session group (goto_session / session: match)
#   OS window = host; can hold multiple session groups, one visible at a time
#   Tab      = tmux window equivalent
#   Split    = tmux pane equivalent
#
# Multiple sessions can coexist in one OS window (parked/visible).
# Cross-OS-window: if a session is live in a different OS window, focus that window.
# No "clean window" guardrail — create/restore always targets the current OS window.

set -o pipefail

# All kittymux state (sessions, history) lives under one private state home.
# Override with KITTYMUX_STATE for custom layouts or testing.
KITTYMUX_STATE="${KITTYMUX_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/kittymux}"
SESSIONS_DIR="${KITTYMUX_STATE}/sessions"
SESSION_EXT=".kitty-session"
SESSION_HISTORY_FILE="${SESSIONS_DIR}/.history"
LIVE_HISTORY_PREFIX="${SESSIONS_DIR}/.live-history"

ensure_sessions_dir() {
    # shellcheck disable=SC2174  # both arguments are named, so each gets the mode
    mkdir -p -m 700 "$KITTYMUX_STATE" "$SESSIONS_DIR"      # -m only applies to the deepest directory of each argument: name the parent too, or it gets the default umask
}

trim_whitespace() {
    local value="$1"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s\n' "$value"
}

sanitize_session_name() {
    local name
    name="$(trim_whitespace "$1")"
    name="${name//\//-}"
    name="${name//\\/-}"
    name="${name%.kitty-session}"
    name="${name%.kitty_session}"
    name="${name%.session}"
    [[ -n "$name" ]] || return 1
    printf '%s\n' "$name"
}

session_display_name() {
    local file_name
    file_name="$(basename "$1")"
    file_name="${file_name%.kitty-session}"
    file_name="${file_name%.kitty_session}"
    file_name="${file_name%.session}"
    printf '%s\n' "$file_name"
}

session_name_from_file() {
    session_display_name "$1"
}

session_path() {
    local session_name
    session_name="$(sanitize_session_name "$1")" || return 1
    printf '%s/%s%s\n' "$SESSIONS_DIR" "$session_name" "$SESSION_EXT"
}

session_exists() {
    local session_file
    session_file="$(session_path "$1")" || return 1
    [[ -s "$session_file" ]]
}

regex_escape() {
    python3 -c "import re, sys; print(re.escape(sys.argv[1]))" "$1"
}

is_inside_kitty() {
    [[ -n "${KITTY_WINDOW_ID:-}" || -n "${KITTY_LISTEN_ON:-}" ]]
}

# KITTY_LISTEN_ON/KITTY_WINDOW_ID are only set for real window launches
# (tab/window/overlay). Background keybind launches get neither — resolve
# context via socket fallback here and state:focused in source_context_json.
# kitty appends its PID to listen_on path (e.g. /tmp/mykitty -> /tmp/mykitty-<pid>).
# Prefer the parent's socket over inherited env; all path fallbacks must be owned.
# shellcheck source=socket.sh
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/socket.sh"
KITTY_SOCKET="$(mux_resolve_socket)" || KITTY_SOCKET=""

kitty_remote() {
    [[ -n "$KITTY_SOCKET" ]] || { printf '%s\n' 'kittymux: no trusted kitty socket' >&2; return 1; }
    kitty @ --to "$KITTY_SOCKET" "$@"
}

kitty_action() {
    local action_name="$1"
    shift
    kitty_remote action "$action_name" "$@"
}

kitty_action_for_window() {
    local match="$1"
    local action_name="$2"
    shift 2
    kitty_remote action --match "$match" "$action_name" "$@"
}

notify_kitty() {
    local message="$1"
    notify-send -t 1600 "Kitty" "$message" 2>/dev/null || true
}

join_shell_words() {
    local joined=""
    local arg
    for arg in "$@"; do
        joined+=$(printf '%q ' "$arg")
    done
    printf '%s\n' "${joined% }"
}

quote_session_value() {
    local value="${1//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '"%s"' "$value"
}

# Write a session file template. Includes session_name directive so kitty
# tags the created tabs with the session group.
write_session_template() {
    # The default new-session layout comes from a template file (assets/templates/plain.kitty-session, or ~/.config/kittymux/templates/plain.kitty-session
    # if you made your own); `kittymux sessions new NAME --template agent|duo|review|…` renders the agent-aware ones.
    local session_file="$1"
    local project_dir="$2"
    local session_name="$3"
    local tpl_dir="${XDG_CONFIG_HOME:-$HOME/.config}/kittymux/templates"
    local tpl="$tpl_dir/plain.kitty-session"
    [[ -f "$tpl" ]] || tpl="$(dirname "${BASH_SOURCE[0]}")/../assets/templates/plain.kitty-session"
    SESSION_NAME_FOR_TEMPLATE="$session_name" SESSION_DIR_FOR_TEMPLATE="$project_dir" SESSION_SHELL_FOR_TEMPLATE="${SHELL:-/bin/sh}" \
        python3 - "$tpl" "$(dirname "${BASH_SOURCE[0]}")/../python" > "$session_file" <<'PY'
import os, sys
sys.path.insert(0, sys.argv[2])
import kittymux_resume as R
text = open(sys.argv[1], encoding="utf-8").read()
sys.stdout.write(R.render_template(text, {"NAME": os.environ["SESSION_NAME_FOR_TEMPLATE"], "CWD": os.environ["SESSION_DIR_FOR_TEMPLATE"],
                                          "SHELL": os.environ["SESSION_SHELL_FOR_TEMPLATE"]}))
PY
}

# ── JSON helpers ──────────────────────────────────────────────────────────────

json_has_windows() {
    python3 -c '
import json, sys
text = sys.stdin.read().strip()
if not text:
    raise SystemExit(1)
try:
    data = json.loads(text)
except Exception:
    raise SystemExit(1)
for os_window in data:
    for tab in os_window.get("tabs", []):
        if tab.get("windows"):
            raise SystemExit(0)
raise SystemExit(1)
'
}

count_tabs_from_json() {
    python3 -c '
import json, sys
text = sys.stdin.read().strip()
if not text:
    print(0); raise SystemExit(0)
try:
    data = json.loads(text)
except Exception:
    print(0); raise SystemExit(0)
count = sum(len(ow.get("tabs", [])) for ow in data)
print(count)
'
}

first_ids_from_json() {
    python3 -c '
import json, sys
text = sys.stdin.read().strip()
if not text:
    raise SystemExit(1)
try:
    data = json.loads(text)
except Exception:
    raise SystemExit(1)
for os_window in data:
    for tab in os_window.get("tabs", []):
        for window in tab.get("windows", []):
            print(os_window["id"], tab["id"], window["id"])
            raise SystemExit(0)
raise SystemExit(1)
'
}

# ── Context helpers ───────────────────────────────────────────────────────────

kitty_ls_json() {
    kitty_remote ls
}

self_context_json() {
    kitty_remote ls --self 2>/dev/null || true
}

overlay_parent_context_json() {
    kitty_remote ls --match 'state:overlay_parent' 2>/dev/null || true
}

# Background keybind launches get no KITTY_WINDOW_ID and resolve to nothing
# under --self, so the focused window is the only reliable context there.
focused_context_json() {
    kitty_remote ls --match 'state:focused' 2>/dev/null || true
}

source_context_json() {
    local json
    json="$(overlay_parent_context_json)"
    if printf '%s' "$json" | json_has_windows; then
        printf '%s\n' "$json"
        return 0
    fi
    json="$(self_context_json)"
    if printf '%s' "$json" | json_has_windows; then
        printf '%s\n' "$json"
        return 0
    fi
    focused_context_json
}

self_context_ids()   { self_context_json   | first_ids_from_json; }
source_context_ids() { source_context_json | first_ids_from_json; }

window_context_ids() {
    local window_id="$1"
    kitty_remote ls --match "id:${window_id}" 2>/dev/null | first_ids_from_json
}

self_window_id() {
    local _os _tab win
    read -r _os _tab win < <(self_context_ids)
    printf '%s\n' "$win"
}

source_window_id() {
    local _os _tab win
    read -r _os _tab win < <(source_context_ids)
    printf '%s\n' "$win"
}

source_tab_id() {
    local _os tab _win
    read -r _os tab _win < <(source_context_ids)
    printf '%s\n' "$tab"
}

source_os_window_id() {
    local os _tab _win
    read -r os _tab _win < <(source_context_ids)
    printf '%s\n' "$os"
}

is_overlay_invocation() {
    local self_id source_id
    self_id="$(self_window_id 2>/dev/null || true)"
    source_id="$(source_window_id 2>/dev/null || true)"
    [[ -n "$self_id" && -n "$source_id" && "$self_id" != "$source_id" ]]
}

# ── Tab / window operations ───────────────────────────────────────────────────

set_tab_title_by_id() {
    kitty_remote set-tab-title --match "id:${1}" "$2"
}

focus_tab_by_id() {
    kitty_remote focus-tab --match "id:${1}"
}

goto_layout_for_tab() {
    kitty_remote goto-layout --match "id:${1}" "$2"
}

window_tab_id() {
    local _os tab _win
    read -r _os tab _win < <(window_context_ids "$1")
    printf '%s\n' "$tab"
}

win_id_for_tab() {
    local tab_id="$1"
    kitty_remote ls --match-tab "id:${tab_id}" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for ow in data:
    for tab in ow.get('tabs', []):
        for w in tab.get('windows', []):
            print(w['id']); sys.exit(0)
sys.exit(1)
"
}

launch_new_tab() {
    local source_window="$1" tab_title="$2" cwd="$3"
    shift 3
    kitty_remote launch \
        --source-window "id:${source_window}" \
        --type=tab \
        --tab-title "$tab_title" \
        --cwd "$cwd" \
        -- "$@"
}

launch_split_in_tab() {
    local source_window="$1" tab_id="$2" cwd="$3" location="$4"
    shift 4
    kitty_remote launch \
        --source-window "id:${source_window}" \
        --match "id:${tab_id}" \
        --cwd "$cwd" \
        --location="$location" \
        -- "$@"
}

window_belongs_to_session() {
    local window_id="$1"
    local json
    json="$(kitty_remote ls --match "id:${window_id} and not session:^$" 2>/dev/null || true)"
    printf '%s' "$json" | json_has_windows
}

# kitty 0.49: reflect the active session in the OS window title; empty
# title restores automatic app-driven tracking for anonymous workspaces.
set_os_window_title_for_session() {
    local name="${1:-}"
    if [[ -n "$name" ]]; then
        kitty_remote set-os-window-title --match state:focused_os_window "$name" >/dev/null 2>&1 || true
    else
        kitty_remote set-os-window-title --match state:focused_os_window >/dev/null 2>&1 || true
    fi
}

goto_session_for_window() {
    local window_id="$1"
    local session_target="$2"
    kitty_action_for_window "id:${window_id}" goto_session "$session_target"
    set_os_window_title_for_session "$(session_display_name "$session_target")"
}

save_session_file_for_window() {
    local window_id="$1"
    local session_file="$2"
    local save_args
    save_args="$(join_shell_words \
        --save-only \
        --use-foreground-process \
        --match=state:focused_os_window \
        "$session_file"
    )"
    kitty_action_for_window "id:${window_id}" save_as_session "$save_args"
}

# ── Cross-OS-window session lookup ────────────────────────────────────────────

# Returns the OS window ID that currently hosts <session_name>, or exits 1.
find_os_window_for_session() {
    local session_name="$1"
    local escaped
    escaped="$(regex_escape "$session_name")"
    kitty_remote ls --match-tab "session:^${escaped}$" 2>/dev/null \
    | python3 -c "
import json, sys
data = json.load(sys.stdin)
for ow in data:
    if ow.get('tabs'):
        print(ow['id'])
        sys.exit(0)
sys.exit(1)
"
}

# Active-tab title for an OS window (used for Hyprland focus matching).
os_window_active_title() {
    local os_window_id="$1"
    kitty_remote ls 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
target = int(sys.argv[1])
for ow in data:
    if ow['id'] != target:
        continue
    for tab in ow.get('tabs', []):
        if tab.get('is_active'):
            print(tab.get('title') or '')
            raise SystemExit(0)
    tabs = ow.get('tabs') or []
    if tabs:
        print(tabs[0].get('title') or '')
        raise SystemExit(0)
raise SystemExit(1)
" "$os_window_id"
}

# Prefer a specific window in the OS window; fall back to first window found.
first_window_id_in_os_window() {
    local os_window_id="$1"
    local prefer_window_id="${2:-}"
    kitty_remote ls 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
target = int(sys.argv[1])
prefer = sys.argv[2]
for ow in data:
    if ow['id'] != target:
        continue
    if prefer:
        prefer_id = int(prefer)
        for tab in ow.get('tabs', []):
            for w in tab.get('windows', []):
                if w.get('id') == prefer_id:
                    print(prefer_id)
                    raise SystemExit(0)
    for tab in ow.get('tabs', []):
        for w in tab.get('windows', []):
            print(w['id'])
            raise SystemExit(0)
raise SystemExit(1)
" "$os_window_id" "$prefer_window_id"
}

# OS window id that currently hosts the given kitty window id.
os_window_id_for_window() {
    local window_id="$1"
    kitty_remote ls --match "id:${window_id}" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for ow in data:
    print(ow['id'])
    raise SystemExit(0)
raise SystemExit(1)
"
}

# Hyprland assist: focus the desktop client whose title matches exactly.
# Kitty remote focus alone can leave you on the source workspace under Wayland.
focus_hyprland_by_title() {
    local title="$1"
    [[ -n "$title" ]] || return 1
    command -v hyprctl >/dev/null 2>&1 || return 1

    local address
    address="$(hyprctl clients -j 2>/dev/null | python3 -c "
import json, sys
title = sys.argv[1]
clients = json.load(sys.stdin)
# Exact title first (Kitty and Hyprland share the active tab title).
for c in clients:
    if c.get('class') != 'kitty':
        continue
    if c.get('title') == title:
        print(c.get('address') or '')
        raise SystemExit(0)
# Soft fallback: unique substring match when titles truncate differently.
matches = []
for c in clients:
    if c.get('class') != 'kitty':
        continue
    ct = c.get('title') or ''
    if title and (title in ct or ct in title):
        matches.append(c.get('address') or '')
if len(matches) == 1 and matches[0]:
    print(matches[0])
    raise SystemExit(0)
raise SystemExit(1)
" "$title" 2>/dev/null || true)"
    [[ -n "$address" ]] || return 1
    hyprctl dispatch focuswindow "address:${address}" >/dev/null 2>&1
}

# Focus an OS window by its ID (Kitty first, then Hyprland by title).
focus_os_window_by_id() {
    local os_window_id="$1"
    local prefer_window_id="${2:-}"
    local win_id title
    win_id="$(first_window_id_in_os_window "$os_window_id" "$prefer_window_id" 2>/dev/null || true)"
    [[ -n "$win_id" ]] || return 1
    kitty_remote focus-window --match "id:${win_id}" 2>/dev/null || true
    title="$(os_window_active_title "$os_window_id" 2>/dev/null || true)"
    focus_hyprland_by_title "$title" 2>/dev/null || true
}

# Focus the window that was moved (follows it into the destination OS window).
focus_moved_window() {
    local window_id="$1"
    local title os_id
    [[ -n "$window_id" ]] || return 1
    kitty_remote focus-window --match "id:${window_id}" 2>/dev/null || true
    os_id="$(os_window_id_for_window "$window_id" 2>/dev/null || true)"
    if [[ -n "$os_id" ]]; then
        title="$(os_window_active_title "$os_id" 2>/dev/null || true)"
    fi
    if [[ -z "${title:-}" ]]; then
        title="$(kitty_remote ls --match "id:${window_id}" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for ow in data:
    for tab in ow.get('tabs', []):
        for w in tab.get('windows', []):
            if w.get('id') == int(sys.argv[1]):
                print(w.get('title') or tab.get('title') or '')
                raise SystemExit(0)
raise SystemExit(1)
" "$window_id" 2>/dev/null || true)"
    fi
    focus_hyprland_by_title "${title:-}" 2>/dev/null || true
}

# TSV rows for the move-tab fzf picker (excludes the source OS window).
# Columns: label \t kind \t os_window_id \t target_tab_id \t tab_count \t sessions \t title
list_move_tab_targets() {
    local source_os_window_id="$1"
    kitty_remote ls 2>/dev/null | python3 -c "
import json, sys, os

source = int(sys.argv[1])
data = json.load(sys.stdin)

# Optional Hyprland workspace map: title -> workspace name
ws_by_title = {}
try:
    import subprocess
    raw = subprocess.check_output(['hyprctl', 'clients', '-j'], text=True, stderr=subprocess.DEVNULL)
    for c in json.loads(raw):
        if c.get('class') != 'kitty':
            continue
        title = c.get('title') or ''
        ws = (c.get('workspace') or {}).get('name') or ''
        if title and ws:
            ws_by_title[title] = str(ws)
except Exception:
    pass

def abbreviate_path(path: str) -> str:
    home = os.path.expanduser('~')
    if path == home:
        return '~'
    if path.startswith(home + '/'):
        path = '~/' + path[len(home)+1:]
    parts = path.split('/')
    if len(parts) <= 3:
        return path
    return '…/' + '/'.join(parts[-2:])

for ow in data:
    oid = ow.get('id')
    if oid == source:
        continue
    tabs = ow.get('tabs') or []
    if not tabs:
        continue
    active = None
    sessions = []
    cwd = ''
    for tab in tabs:
        if tab.get('is_active'):
            active = tab
        for w in tab.get('windows') or []:
            sn = (w.get('session_name') or '').strip()
            if sn and sn not in sessions:
                sessions.append(sn)
            if not cwd and w.get('cwd'):
                cwd = w['cwd']
    if active is None:
        active = tabs[0]
    title = (active.get('title') or '~').replace('\t', ' ')
    target_tab = active.get('id')
    ntabs = len(tabs)
    sess = ', '.join(sessions[:3])
    if len(sessions) > 3:
        sess += f' +{len(sessions)-3}'
    ws = ws_by_title.get(title, '')
    meta_bits = [f'{ntabs} tab' + ('s' if ntabs != 1 else '')]
    if ws:
        meta_bits.append(f'ws {ws}')
    if sess:
        meta_bits.append(sess)
    elif cwd:
        meta_bits.append(abbreviate_path(cwd))
    meta = ' · '.join(meta_bits)
    label = f'● win {oid:<3} {title}  ({meta})'
    print(f'{label}\tos_window\t{oid}\t{target_tab}\t{ntabs}\t{sess}\t{title}')
" "$source_os_window_id"
}

# Move the tab containing <window_id> to another OS window (or a new one).
# target_kind: os_window | new
# target_tab_id: required when kind=os_window (any tab in destination OS window)
move_tab_for_window() {
    local window_id="$1"
    local target_kind="$2"
    local target_tab_id="${3:-}"

    [[ -n "$window_id" ]] || return 1

    case "$target_kind" in
        new)
            kitty_remote detach-tab --match "window_id:${window_id}" \
                || return 1
            ;;
        os_window)
            [[ -n "$target_tab_id" ]] || return 1
            kitty_remote detach-tab \
                --match "window_id:${window_id}" \
                --target-tab "id:${target_tab_id}" \
                || return 1
            ;;
        *)
            return 1
            ;;
    esac

    # Follow the moved tab into its destination OS window / Hyprland workspace.
    focus_moved_window "$window_id"
}

# ── Scratch tab tracking ──────────────────────────────────────────────────────

scratch_tab_file_for_os_window() {
    local namespace
    [[ "$1" =~ ^[1-9][0-9]*$ && "$KITTY_SOCKET" == unix:* ]] || return 1
    mux_owned_socket "${KITTY_SOCKET#unix:}" || return 1
    # Include the socket inode so a restarted instance cannot inherit old flags.
    namespace="$(python3 -c '
import hashlib, os, sys
s = os.stat(sys.argv[1])
print(hashlib.sha256(f"{sys.argv[1]}:{s.st_dev}:{s.st_ino}".encode()).hexdigest())
' "${KITTY_SOCKET#unix:}")" || return 1
    printf '%s/scratch-%s-%s\n' "$(mux_runtime_dir)" "$namespace" "$1"
}

# Validate the OS owner, title, window and per-launch identity against live ls.
# Prints a tab/window/token record. Legacy tab-id-only flags are never accepted.
scratch_record_for_os_window() {
    local os_win_id="$1" tab_id="$2" expected="${3:-}"
    kitty_remote ls 2>/dev/null | python3 -c '
import json, sys
osid, tabid = map(int, sys.argv[1:3])
for ow in json.load(sys.stdin):
    if ow.get("id") != osid:
        continue
    for tab in ow.get("tabs", []):
        if tab.get("id") != tabid or tab.get("title") != "!scratch":
            continue
        for w in tab.get("windows", []):
            token = (w.get("user_vars") or {}).get("kittymux_scratch", "")
            if not token or not all(c in "0123456789abcdef" for c in token):
                continue
            record = "%s\t%s\t%s" % (tabid, w["id"], token)
            if not sys.argv[3] or record == sys.argv[3]:
                print(record); sys.exit(0)
sys.exit(1)
' "$os_win_id" "$tab_id" "$expected"
}

get_scratch_tab_id() {
    local f record tab_id
    f="$(scratch_tab_file_for_os_window "$1")" || return 1
    [[ -f "$f" && ! -L "$f" && -O "$f" ]] || return 1
    record="$(cat "$f")"
    tab_id="${record%%$'\t'*}"
    [[ "$tab_id" =~ ^[1-9][0-9]*$ && "$record" == *$'\t'* ]] || return 1
    scratch_record_for_os_window "$1" "$tab_id" "$record" >/dev/null || return 1
    printf '%s\n' "$tab_id"
}

set_scratch_tab_id() {
    local f record
    f="$(scratch_tab_file_for_os_window "$1")" || return 1
    [[ ! -L "$f" ]] || return 1
    record="$(scratch_record_for_os_window "$1" "$2")" || return 1
    (umask 077; printf '%s\n' "$record" > "$f")
}

clear_scratch_tab_id() {
    local f
    f="$(scratch_tab_file_for_os_window "$1")" || return 1
    rm -f "$f"
}

# Returns the validated scratch window ID, not a tab in another OS window.
scratch_win_id_for_os_window() {
    local tab_id record
    tab_id="$(get_scratch_tab_id "$1")" || return 1
    record="$(scratch_record_for_os_window "$1" "$tab_id")" || return 1
    printf '%s\n' "$record" | cut -f2
}

# ── Session history ───────────────────────────────────────────────────────────

session_files_sorted() {
    ensure_sessions_dir
    find "$SESSIONS_DIR" -maxdepth 1 -type f \
        \( -name "*.kitty-session" -o -name "*.kitty_session" -o -name "*.session" \) \
        -size +0c -print | sort
}

history_session_files() {
    local file
    declare -A seen=()
    [[ -f "$SESSION_HISTORY_FILE" ]] || return 0
    while IFS= read -r file; do
        [[ -n "$file" && -f "$file" ]] || continue
        [[ -n "${seen[$file]:-}" ]] && continue
        seen["$file"]=1
        printf '%s\n' "$file"
    done < "$SESSION_HISTORY_FILE"
}

record_session() {
    local session_file="$1"
    local temp_file
    [[ -f "$session_file" ]] || return 1
    ensure_sessions_dir
    temp_file="$(mktemp)"
    {
        printf '%s\n' "$session_file"
        history_session_files | awk -v current="$session_file" '$0 != current'
    } | awk '!seen[$0]++' | head -n 50 > "$temp_file"
    mv "$temp_file" "$SESSION_HISTORY_FILE"
}

remove_session_from_saved_history() {
    local session_file="$1"
    local temp_file
    ensure_sessions_dir
    temp_file="$(mktemp)"
    history_session_files | awk -v doomed="$session_file" '$0 != doomed' > "$temp_file"
    mv "$temp_file" "$SESSION_HISTORY_FILE"
}

ordered_session_files() {
    local file
    declare -A seen=()
    while IFS= read -r file; do
        [[ -n "$file" ]] || continue
        [[ -n "${seen[$file]:-}" ]] && continue
        seen["$file"]=1
        printf '%s\n' "$file"
    done < <(history_session_files)
    while IFS= read -r file; do
        [[ -n "$file" ]] || continue
        [[ -n "${seen[$file]:-}" ]] && continue
        seen["$file"]=1
        printf '%s\n' "$file"
    done < <(session_files_sorted)
}

# ── Live session helpers (within current OS window) ───────────────────────────

session_is_live_in_focused_window() {
    local session_name="$1"
    local escaped json
    escaped="$(regex_escape "$session_name")"
    json="$(kitty_remote ls --match-tab "state:focused_os_window and session:^${escaped}$" 2>/dev/null || true)"
    printf '%s' "$json" | count_tabs_from_json | grep -q '^[1-9]'
}

session_is_active_in_focused_window() {
    local session_name="$1"
    local escaped json
    escaped="$(regex_escape "$session_name")"
    json="$(kitty_remote ls --match-tab "state:focused_os_window and state:active and session:^${escaped}$" 2>/dev/null || true)"
    printf '%s' "$json" | count_tabs_from_json | grep -q '^[1-9]'
}

live_session_names_for_window() {
    local window_id="$1"
    local session_name
    declare -A seen=()

    while IFS= read -r session_name; do
        [[ -n "$session_name" ]] || continue
        session_is_live_in_focused_window "$session_name" || continue
        [[ -n "${seen[$session_name]:-}" ]] && continue
        seen["$session_name"]=1
        printf '%s\n' "$session_name"
    done < <(read_live_history_names_for_window "$window_id")

    while IFS= read -r file; do
        session_name="$(session_name_from_file "$file")"
        session_is_live_in_focused_window "$session_name" || continue
        [[ -n "${seen[$session_name]:-}" ]] && continue
        seen["$session_name"]=1
        printf '%s\n' "$session_name"
    done < <(session_files_sorted)
}

current_live_session_name_for_window() {
    local window_id="$1"
    local session_name
    while IFS= read -r session_name; do
        [[ -n "$session_name" ]] || continue
        if session_is_active_in_focused_window "$session_name"; then
            printf '%s\n' "$session_name"
            return 0
        fi
    done < <(live_session_names_for_window "$window_id")
    live_session_names_for_window "$window_id" | head -n 1
}

# Like current_live_session_name_for_window, but NO fallback — prints a name
# only when a saved session is verified active. Used by autosave, where
# guessing would overwrite the wrong file.
active_named_session_for_window() {
    local window_id="$1"
    local session_name
    while IFS= read -r session_name; do
        [[ -n "$session_name" ]] || continue
        if session_is_active_in_focused_window "$session_name"; then
            printf '%s\n' "$session_name"
            return 0
        fi
    done < <(live_session_names_for_window "$window_id")
    return 0
}

# Checkpoint the departing session before it is parked. Anonymous workspaces
# are skipped — autosave never invents a filename. Run BEFORE goto_session
# while the departing session is still the visible one; save_as_session's
# focused_os_window match already serializes only the visible session group.
autosave_active_session_for_window() {
    local window_id="$1"
    local session_name session_file
    session_name="$(active_named_session_for_window "$window_id")"
    [[ -n "$session_name" ]] || return 0
    session_file="$(session_path "$session_name")" || return 0
    [[ -s "$session_file" ]] || return 0
    save_session_file_for_window "$window_id" "$session_file" || true
}

last_live_session_name_for_window() {
    local window_id="$1"
    local current_name session_name
    current_name="$(current_live_session_name_for_window "$window_id")"
    while IFS= read -r session_name; do
        [[ -n "$session_name" ]] || continue
        [[ "$session_name" == "$current_name" ]] && continue
        session_is_live_in_focused_window "$session_name" || continue
        printf '%s\n' "$session_name"
        return 0
    done < <(read_live_history_names_for_window "$window_id")
}

cycle_live_session_name_for_window() {
    local window_id="$1"
    local direction="$2"
    local current_name index target_index
    local -a session_names=()

    mapfile -t session_names < <(live_session_names_for_window "$window_id")
    [[ "${#session_names[@]}" -gt 0 ]] || return 1

    current_name="$(current_live_session_name_for_window "$window_id")"
    if [[ -z "$current_name" ]]; then
        printf '%s\n' "${session_names[0]}"; return 0
    fi

    for index in "${!session_names[@]}"; do
        if [[ "${session_names[$index]}" == "$current_name" ]]; then
            if [[ "$direction" == "prev" ]]; then
                target_index=$(( (index - 1 + ${#session_names[@]}) % ${#session_names[@]} ))
            else
                target_index=$(( (index + 1) % ${#session_names[@]} ))
            fi
            printf '%s\n' "${session_names[$target_index]}"
            return 0
        fi
    done
    printf '%s\n' "${session_names[0]}"
}

focus_live_session_name() {
    local window_id="$1"
    local session_name="$2"
    session_is_live_in_focused_window "$session_name" || return 1
    autosave_active_session_for_window "$window_id"
    goto_session_for_window "$window_id" "$session_name"
    record_live_session_for_window "$window_id" "$session_name"
}

# ── Live history per OS window ────────────────────────────────────────────────

live_history_file_for_window() {
    local window_id="$1"
    local os_window_id _tab_id _win_id
    read -r os_window_id _tab_id _win_id < <(window_context_ids "$window_id")
    printf '%s-%s\n' "$LIVE_HISTORY_PREFIX" "$os_window_id"
}

read_live_history_names_for_window() {
    local window_id="$1"
    local history_file name
    declare -A seen=()
    history_file="$(live_history_file_for_window "$window_id")"
    [[ -f "$history_file" ]] || return 0
    while IFS= read -r name; do
        [[ -n "$name" ]] || continue
        [[ -n "${seen[$name]:-}" ]] && continue
        seen["$name"]=1
        printf '%s\n' "$name"
    done < "$history_file"
}

record_live_session_for_window() {
    local window_id="$1"
    local session_name="$2"
    local history_file temp_file
    history_file="$(live_history_file_for_window "$window_id")"
    temp_file="$(mktemp)"
    {
        printf '%s\n' "$session_name"
        read_live_history_names_for_window "$window_id" \
            | awk -v current="$session_name" '$0 != current'
    } | awk '!seen[$0]++' | head -n 50 > "$temp_file"
    mv "$temp_file" "$history_file"
}

# ── Create / restore sessions ─────────────────────────────────────────────────

# Load a session file (create or restore) into the current OS window.
# The existing active session is parked — not destroyed.
load_session_into_window() {
    local source_window="$1"
    local session_file="$2"
    local session_name
    session_name="$(session_name_from_file "$session_file")"
    autosave_active_session_for_window "$source_window"
    goto_session_for_window "$source_window" "$session_file"
    record_session "$session_file"
    record_live_session_for_window "$source_window" "$session_name"
}

# Create a brand-new session from a project directory.
# Writes a template and loads it — current session is parked, not destroyed.
create_new_session_in_window() {
    local source_window="$1"
    local project_dir="$2"
    local session_name="$3"
    local session_file="$4"

    write_session_template "$session_file" "$project_dir" "$session_name"
    load_session_into_window "$source_window" "$session_file"
}

# Returns the cwd of the first window inside a given kitty window ID.
# Used to inherit the user's real working directory into the overlay.
source_window_cwd() {
    local window_id="$1"
    kitty_remote ls --match "id:${window_id}" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for ow in data:
    for tab in ow.get('tabs', []):
        for w in tab.get('windows', []):
            cwd = w.get('cwd', '')
            if cwd:
                print(cwd)
                sys.exit(0)
sys.exit(1)
" || true
}

# ── Detached helper ───────────────────────────────────────────────────────────

spawn_detached_helper() {
    local log_file
    log_file="$(mux_runtime_dir)/session-helper.log"
    nohup env \
        HOME="$HOME" \
        PATH="$PATH" \
        KITTY_LISTEN_ON="${KITTY_LISTEN_ON:-}" \
        "$@" >"$log_file" 2>&1 &
}
