#!/usr/bin/env bash

# Shared Catppuccin-ish fzf styling for kitty overlays.

FZF_KITTY_COLORS=(
    --color=bg:#1e1e2e,bg+:#313244,fg:#cdd6f4,fg+:#f5e0dc
    --color=hl:#f38ba8,hl+:#f38ba8
    --color=info:#cba6f7,prompt:#89b4fa,pointer:#f5c2e7,marker:#a6e3a1
    --color=spinner:#f9e2af,header:#6c7086,border:#45475a,label:#89b4fa
    --color=preview-bg:#181825,preview-border:#45475a
)

FZF_KITTY_BASE=(
    --ansi
    --cycle
    --height=100%
    --layout=reverse
    --border=rounded
    --margin=1,2
    --padding=1,2
    --marker='✓'
    --pointer='▸'
    --separator='─'
    "${FZF_KITTY_COLORS[@]}"
)

# Full-content application shell used by Kitty Home. Later options override
# the inset defaults above without changing smaller project/rename pickers.
FZF_KITTY_HOME=(
    "${FZF_KITTY_BASE[@]}"
    --margin=0
    --padding=0
    --border=none
    --input-border=bottom
    --input-label=' search '
    --input-label-pos=2
    --header-border=bottom
    --header-label=' Kitty Home '
    --header-label-pos=2
    --footer-border=top
    --footer-label=' shortcuts '
    --footer-label-pos=2
    --info=inline-right
    --ghost='Search sessions and actions'
)
