#!/usr/bin/env bash
# project-picker.sh — fzf pick a project dir, create/open its kitty session
# Searches "${KITTYMUX_PROJECTS:-$HOME/Projects}" for directories, hands the selection to kitty-sessionizer.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/mux.sh"
source "$SCRIPT_DIR/fzf-style.sh"

project_roots="$(
    fd -H -t d \
        --exclude node_modules \
        --exclude .pnpm-store \
        --exclude .yarn \
        --exclude .turbo \
        --exclude .next \
        --exclude .nuxt \
        --exclude .svelte-kit \
        --exclude .output \
        --exclude .vercel \
        --exclude .cache \
        --exclude .parcel-cache \
        --exclude .venv \
        --exclude venv \
        --exclude __pycache__ \
        --exclude .pytest_cache \
        --exclude .mypy_cache \
        --exclude .ruff_cache \
        --exclude coverage \
        --exclude build \
        --exclude dist \
        --exclude out \
        --exclude target \
        '^\.git$' "${KITTYMUX_PROJECTS:-$HOME/Projects}" 2>/dev/null \
    | sed -e 's#/.git/$##' -e 's#/.git$##' \
    | sort -u
)"

if [[ -z "$project_roots" ]]; then
    project_roots="$(
        fd -t d -d 3 \
            --exclude node_modules \
            --exclude .pnpm-store \
            --exclude .yarn \
            --exclude .turbo \
            --exclude .next \
            --exclude .nuxt \
            --exclude .svelte-kit \
            --exclude .output \
            --exclude .vercel \
            --exclude .cache \
            --exclude .parcel-cache \
            --exclude .venv \
            --exclude venv \
            --exclude __pycache__ \
            --exclude .pytest_cache \
            --exclude .mypy_cache \
            --exclude .ruff_cache \
            --exclude coverage \
            --exclude build \
            --exclude dist \
            --exclude out \
            --exclude target \
            . "${KITTYMUX_PROJECTS:-$HOME/Projects}" 2>/dev/null
    )"
fi

project_roots="$(
    SESSION_HISTORY_FILE="$SESSION_HISTORY_FILE" python3 -c '
import os
import pathlib
import subprocess
import sys

def sanitize(name: str) -> str:
    name = name.strip().replace("/", "-").replace("\\", "-")
    for suffix in (".kitty-session", ".kitty_session", ".session"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name

history_rank = {}
history_file = os.environ.get("SESSION_HISTORY_FILE", "")
if history_file and os.path.exists(history_file):
    with open(history_file, errors="replace") as handle:
        for rank, line in enumerate(handle):
            name = sanitize(pathlib.Path(line.strip()).name)
            if name and name not in history_rank:
                history_rank[name] = rank

rows = []
for path in [line.strip() for line in sys.stdin if line.strip()]:
    name = sanitize(pathlib.Path(path).name)
    session_rank = history_rank.get(name, 10_000)
    try:
        result = subprocess.run(
            ["git", "-C", path, "log", "-1", "--format=%ct"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=0.25,
            check=False,
        )
        git_time = int((result.stdout or "0").strip() or 0)
    except Exception:
        git_time = 0
    rows.append((session_rank, -git_time, path.lower(), path))

for _, _, _, path in sorted(rows):
    print(path)
'
<<< "$project_roots"
)"

dir=$(
    printf '%s\n' "$project_roots" \
    | fzf \
        "${FZF_KITTY_BASE[@]}" \
        --prompt="  project  " \
        --header=$'enter:open/create session  esc:cancel' \
        --header-first \
        --preview="$SCRIPT_DIR/mux-preview.sh {}" \
        --preview-window=right:55%:wrap:border-left \
        --preview-label=' project '
)

if [[ -n "$dir" ]]; then
    exec "$SCRIPT_DIR/mux-sessionizer" --project-dir "$dir"
fi

exec "${SHELL:-/bin/sh}"
