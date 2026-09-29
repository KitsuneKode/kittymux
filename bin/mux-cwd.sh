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
    # ---------------- detail mode ----------------
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

    hint=" y path · b branch · t tab · s split "
    inner=$(( ${#path} > ${#git_line} ? ${#path} : ${#git_line} ))
    (( inner < ${#hint} )) && inner=${#hint}
    inner=$(( inner + 2 ))
    box_w=$(( inner + 2 ))
    left=$(( (cols - box_w) / 2 )); (( left < 0 )) && left=0
    nrows=4
    row=$(( lines / 2 - 2 )); (( row < 0 )) && row=0
    note=""

    draw_detail() {
        local p=$1
        local b dp brp sp dim ok
        b="$(fg_step "$C_BORDER" "$p")"; dp="$(fg_step "$C_PATH" "$p")"
        brp="$(fg_step "$C_BR" "$p")"; sp="$(fg_step "$C_SEP" "$p")"
        dim="$(fg_step "$C_DIM" "$p")"; ok="$(fg_step "$C_OK" "$p")"
        local txttp; txttp="$(fg_step "$C_TXT" "$p")"

        printf '\033[%d;%dH' "$row" "$left"
        printf '%s╭' "$b"; printf '─%.0s' $(seq "$inner"); printf '╮'
        printf '\033[%d;%dH' "$((row + 1))" "$left"
        printf '%s│%s %s%-*s %s│' "$b" "$dp" "$txttp" "$((inner - 2))" "$path" "$b"
        printf '\033[%d;%dH' "$((row + 2))" "$left"
        printf '%s│%s%-*s%s│' "$b" "$brp" "$inner" "${git_line:0:$inner}" "$b"
        printf '\033[%d;%dH' "$((row + 3))" "$left"
        if [[ -n "$note" ]]; then
            printf '%s│%s %-*s%s│' "$b" "$ok" "$((inner - 1))" "$note" "$b"
        else
            printf '%s│%s%-*s%s│' "$b" "$dim" "$inner" "$hint" "$b"
        fi
        printf '\033[%d;%dH' "$((row + 4))" "$left"
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
