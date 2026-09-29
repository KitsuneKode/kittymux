#!/usr/bin/env bash

# cwd-hud.sh — "where am I" overlay.
#   brief  (default):          pill with project[:worktree]/inner-path + branch
#   detail (--detail, or press the keybind again within 2s): full path,
#          git status, and 'y'/'b' copy path/branch to clipboard via OSC52.
# Invoked via: launch --type=overlay --cwd=current

cols=$(tput cols 2>/dev/null || printf '80')
lines=$(tput lines 2>/dev/null || printf '24')

STATE=/tmp/kittymux-cwd.last
now=$(date +%s)
detail=0
[[ "${1:-}" == "--detail" ]] && detail=1
last=0; [[ -f $STATE ]] && last=$(cat -- "$STATE" 2>/dev/null || printf 0)
(( detail == 0 && now - last < 2 )) && detail=1
printf '%s' "$now" > "$STATE"

path="${PWD/#"$HOME"/~}"
branch=""

# Git-aware label: project[:worktree]/inner-path, else the ~ path
label=""
mapfile -t gi < <(git -C "$PWD" rev-parse --show-toplevel --abbrev-ref HEAD --git-dir --git-common-dir 2>/dev/null)
if (( ${#gi[@]} >= 4 )) && [[ -n "${gi[0]}" ]]; then
    top="${gi[0]}"; branch="${gi[1]}"; gitdir="${gi[2]}"; common="${gi[3]}"
    [[ "$branch" == "HEAD" ]] && branch="detached"
    [[ "$common" != /* ]] && common="$PWD/$common"
    project="$(basename "$(dirname "$common")")"
    [[ "$gitdir" == */worktrees/* ]] && project+=":$(basename "$top")"
    rel="${PWD#"$top"}"; rel="${rel#/}"
    label="$project"; [[ -n "$rel" ]] && label+="/$rel"
else
    label="$path"
fi

# Collapse when too wide
if (( ${#label} + ${#branch} + 14 > cols )); then
    leaf="${label##*/}"
    parent="$(dirname -- "$label")"; parent="${parent##*/}"
    label="…/${parent}/${leaf}"
fi

# Catppuccin Mocha
C_BORDER=45475a; C_PATH=cba6f7; C_BR=a6e3a1; C_SEP=6c7086; C_DIR=89b4fa
C_DIM=6c7086; C_TXT=cdd6f4; C_OK=a6e3a1

FG=$(printf '\xef\x81\xbb')   #  folder
BR=$(printf '\xef\x84\xa6')   #  branch

fg_step() { # hex pct -> truecolor escape
    local h=$1 p=$2
    printf '\033[38;2;%d;%d;%dm' \
        $(( 16#${h:0:2} * p / 100 )) \
        $(( 16#${h:2:2} * p / 100 )) \
        $(( 16#${h:4:2} * p / 100 ))
}

osc52() { # copy $1 to clipboard
    printf '\033]52;c;%s\a' "$(printf %s "$1" | base64 | tr -d '\n')"
}

kitty_rc() { # remote control with socket fallback
    local to="${KITTY_LISTEN_ON:-}"
    if [[ -z "$to" ]]; then
        local s; s=$(ls -t /tmp/mykitty-* 2>/dev/null | head -1)
        [[ -n "$s" ]] && to="unix:$s"
    fi
    [[ -n "$to" ]] && kitty @ --to "$to" "$@" >/dev/null 2>&1
}

printf '\033[?25l'  # hide cursor

if (( detail )); then
    # ---------------- detail mode: the "peek" card ----------------
    git_line=""
    if [[ -n "$branch" ]]; then
        git_line=" $label   $branch"
        dirty=$(timeout 0.4 git -C "$PWD" status --porcelain=v1 2>/dev/null | grep -c . || true)
        ab=$(timeout 0.4 git -C "$PWD" rev-list --left-right --count '@{upstream}...HEAD' 2>/dev/null || true)
        ahead=0; behind=0
        if [[ "$ab" =~ ([0-9]+)[[:space:]]+([0-9]+) ]]; then
            behind=${BASH_REMATCH[1]}; ahead=${BASH_REMATCH[2]}
        fi
        (( dirty > 0 )) && git_line+=" · ${dirty} dirty"
        (( ahead > 0 )) && git_line+=" · ↑${ahead}"
        (( behind > 0 )) && git_line+=" · ↓${behind}"
    else
        git_line="  not a git repo"
    fi

    # Peek at the host pane under this overlay: agent + status + tail.
    # Hover isn't reachable in kitty's tab bar, so this card is the details.
    host_id=""; agent=""; st=""; tail_l=()
    to="${KITTY_LISTEN_ON:-}"
    [[ -z "$to" ]] && { s=$(ls -t /tmp/mykitty-* 2>/dev/null | head -1); [[ -n "$s" ]] && to="unix:$s"; }
    if [[ -n "$to" ]]; then
        mapfile -t hi < <(kitty @ --to "$to" ls 2>/dev/null | python3 - <<'PY'
import json, os, sys
own = os.environ.get("KITTY_WINDOW_ID", "")
AGENTS = {"claude","codex","cursor-agent","cursor","gemini","opencode","amp","devin","aider","crush","grok"}
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit()
for osw in data:
    if not osw.get("is_focused"):
        continue
    for t in osw.get("tabs", []):
        if not t.get("is_active"):
            continue
        wins = {w["id"]: w for w in t.get("windows", [])}
        hist = t.get("active_window_history") or []
        order = [i for i in hist if i in wins] + [w["id"] for w in t.get("windows", []) if w["id"] not in hist]
        for wid in order:
            if str(wid) == own:
                continue
            w = wins[wid]
            agent = ""
            for p in w.get("foreground_processes") or []:
                for a in p.get("cmdline") or []:
                    n = os.path.basename(str(a)).lower()
                    if n in AGENTS:
                        agent = n; break
                if agent:
                    break
            print(wid); print(agent)
            sys.exit()
PY
)
        host_id="${hi[0]:-}"; agent="${hi[1]:-}"
        if [[ -n "$host_id" && -n "$agent" ]]; then
            st=$(python3 - "$host_id" "${to##*-}" <<'PY' 2>/dev/null
import json, os, sys, time
st_dir = os.environ.get("KITTYMUX_STATE") or os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")), "kittymux")
p = os.path.join(st_dir, f"panes-{sys.argv[2]}.json")
try:
    ts = float((json.load(open(p)).get(sys.argv[1]) or {}).get("ts_title") or 0)
except Exception:
    ts = 0
print("waiting" if ts and time.monotonic() - ts > 15 else ("busy" if ts else ""))
PY
)
        fi
        tail_l=()
        if [[ -n "$host_id" ]]; then
            mapfile -t tail_l < <(kitty @ --to "$to" get-text -m "id:$host_id" --extent=screen 2>/dev/null | grep -v '^[[:space:]]*$' | tail -4)
        fi
    fi

    agent_line=""; agent_hex=$C_TXT
    if [[ -n "$agent" ]]; then
        case "$agent" in
            claude)              ag=$'\ue0d8'; agent_hex=d97757 ;;
            codex)               ag=$'\ue0d9'; agent_hex=10a37f ;;
            cursor|cursor-agent) ag=$'\ue0da'; agent_hex=5b8ef4 ;;
            gemini)              ag=$'\ue0db'; agent_hex=4e8cff ;;
            opencode)            ag=$'\ue0dc'; agent_hex=fab283 ;;
            amp)                 ag=$'\ue0dd'; agent_hex=f5c2e7 ;;
            devin)               ag=$'\ue0de'; agent_hex=8b5cf6 ;;
            aider)               ag='✎';       agent_hex=a6e3a1 ;;
            crush)               ag='♥';       agent_hex=f38ba8 ;;
            grok)                ag='✗';       agent_hex=f9e2af ;;
            *)                   ag='⚡';      agent_hex=94e2d5 ;;
        esac
        sttxt=""
        [[ "$st" == "busy" ]] && sttxt="· ● busy"
        [[ "$st" == "waiting" ]] && sttxt="· ! waiting"
        agent_line="$ag $agent $sttxt"
    fi

    # Content rows (text + palette hex). Path/git first, then pane tail.
    rows_txt=(); rows_hex=()
    [[ -n "$agent_line" ]] && { rows_txt+=("$agent_line"); rows_hex+=("$agent_hex"); }
    rows_txt+=("$path");    rows_hex+=("$C_PATH")
    rows_txt+=("$git_line"); rows_hex+=("$C_BR")
    if (( ${#tail_l[@]} )); then
        rows_txt+=("── last output"); rows_hex+=("$C_SEP")
        for l in "${tail_l[@]}"; do rows_txt+=("$l"); rows_hex+=("$C_DIM"); done
    fi

    hint=" y path · b branch · r ↻ · t tab · s split "
    inner=0
    for l in "${rows_txt[@]}" "$hint"; do (( ${#l} > inner )) && inner=${#l}; done
    (( inner > 62 )) && inner=62
    inner=$(( inner + 2 ))
    box_w=$(( inner + 2 ))
    left=$(( (cols - box_w) / 2 )); (( left < 0 )) && left=0
    nrows=${#rows_txt[@]}
    row=$(( lines / 2 - (nrows + 3) / 2 )); (( row < 0 )) && row=0
    note=""

    draw_detail() {
        local p=$1 i
        local b dim ok
        b="$(fg_step "$C_BORDER" "$p")"
        dim="$(fg_step "$C_DIM" "$p")"; ok="$(fg_step "$C_OK" "$p")"
        printf '\033[%d;%dH' "$row" "$left"
        printf '%s╭' "$b"; printf '─%.0s' $(seq "$inner"); printf '╮'
        for i in "${!rows_txt[@]}"; do
            printf '\033[%d;%dH' "$((row + 1 + i))" "$left"
            printf '%s│%s %-*s%s│' "$b" "$(fg_step "${rows_hex[$i]}" "$p")" \
                "$((inner - 1))" "${rows_txt[$i]:0:$((inner - 1))}" "$b"
        done
        printf '\033[%d;%dH' "$((row + 1 + nrows))" "$left"
        if [[ -n "$note" ]]; then
            printf '%s│%s %-*s%s│' "$b" "$ok" "$((inner - 1))" "$note" "$b"
        else
            printf '%s│%s%-*s%s│' "$b" "$dim" "$inner" "$hint" "$b"
        fi
        printf '\033[%d;%dH' "$((row + 2 + nrows))" "$left"
        printf '%s╰' "$b"; printf '─%.0s' $(seq "$inner"); printf '╯'
        printf '\033[0m'
    }

    for p in 18 38 62 84 100; do draw_detail "$p"; sleep 0.03; done

    # key loop: y path, b branch, r re-read git, esc/enter/q/timeout dismiss
    deadline=$(( SECONDS + 5 ))
    while (( SECONDS < deadline )); do
        read -rsn1 -t 0.5 k 2>/dev/null || continue
        case "$k" in
            y) osc52 "$PWD"; note="  copied path" ;;
            b) [[ -n "$branch" ]] && { osc52 "$branch"; note="  copied branch"; } ;;
            t) kitty_rc launch --type=tab --cwd="$PWD" && break ;;
            s) kitty_rc launch --location=hsplit --cwd="$PWD" && break ;;
            r) exec "$0" --detail ;;
            $'\e'|q|$'\n'|$'\r') break ;;
        esac
        draw_detail 100
    done

    for p in 55 20; do draw_detail "$p"; sleep 0.025; done
    printf '\033[?25h\033[0m'
    exit 0
fi

# ---------------- brief pill ----------------
inner_w=$(( ${#label} + 3 ))
[[ -n "$branch" ]] && inner_w=$(( inner_w + ${#branch} + 4 ))
inner_w=$(( inner_w + 1 ))

box_w=$(( inner_w + 2 ))
left=$(( (cols - box_w) / 2 )); (( left < 0 )) && left=0
row=$(( lines / 2 - 1 )); (( row < 0 )) && row=0

draw() {
    local p=$1
    local b dp brp sp
    b="$(fg_step "$C_BORDER" "$p")"
    dp="$(fg_step "$C_PATH" "$p")"
    brp="$(fg_step "$C_BR" "$p")"
    sp="$(fg_step "$C_SEP" "$p")"

    printf '\033[%d;%dH' "$row" "$left"
    printf '%s╭' "$b"; printf '─%.0s' $(seq "$inner_w"); printf '╮'
    printf '\033[%d;%dH' "$((row + 1))" "$left"
    printf '%s│%s %s%s %s%s' "$b" "$sp" "$dp" "$FG" "$dp" "$label"
    if [[ -n "$branch" ]]; then
        printf '%s  %s%s %s%s' "$sp" "$brp" "$BR" "$brp" "$branch"
    fi
    printf '%s %s│' "$sp" "$b"
    printf '\033[%d;%dH' "$((row + 2))" "$left"
    printf '%s╰' "$b"; printf '─%.0s' $(seq "$inner_w"); printf '╯'
    printf '\033[0m'
}

# Fade in
for p in 18 38 62 84 100; do
    draw "$p"
    sleep 0.03
done

# Hold: any key dismisses, else auto-close
read -rsn1 -t 1.4 _ 2>/dev/null || true

# Quick fade out
for p in 55 20; do
    draw "$p"
    sleep 0.025
done

printf '\033[?25h\033[0m'
exit 0
