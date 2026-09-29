#!/usr/bin/env bash

set -euo pipefail

DIR="${1:-}"
[[ -d "$DIR" ]] || { echo "  (missing project)"; exit 0; }

hr() { printf '%.0s─' $(seq 1 "${COLUMNS:-72}"); printf '\n'; }

run_limited() {
    if command -v timeout >/dev/null 2>&1; then
        timeout 1s "$@"
    else
        "$@"
    fi
}

echo "  PROJECT"
echo "  $(basename "$DIR")"
echo "  $DIR"

if git -C "$DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    branch="$(run_limited git -C "$DIR" branch --show-current 2>/dev/null || true)"
    branch="${branch:-detached}"
    status="$(run_limited git -C "$DIR" status --short 2>/dev/null | wc -l | tr -d ' ')"
    echo "  git: ${branch}  ${status} changed"
fi

if [[ -f "$DIR/package.json" ]] && command -v jq >/dev/null 2>&1; then
    pkg_name="$(jq -r '.name // empty' "$DIR/package.json" 2>/dev/null || true)"
    pkg_manager=""
    [[ -f "$DIR/bun.lockb" || -f "$DIR/bun.lock" ]] && pkg_manager="bun"
    [[ -f "$DIR/pnpm-lock.yaml" ]] && pkg_manager="pnpm"
    [[ -f "$DIR/yarn.lock" ]] && pkg_manager="yarn"
    [[ -f "$DIR/package-lock.json" ]] && pkg_manager="npm"
    [[ -n "$pkg_name" ]] && echo "  package: $pkg_name${pkg_manager:+  ($pkg_manager)}"
fi

if [[ -f "$DIR/pyproject.toml" ]]; then
    echo "  python: pyproject.toml"
elif [[ -f "$DIR/Cargo.toml" ]]; then
    echo "  rust: Cargo.toml"
elif [[ -f "$DIR/go.mod" ]]; then
    echo "  go: go.mod"
fi

hr
echo "  files"
ignore_glob='node_modules|.pnpm-store|.yarn|.git|.turbo|.next|.nuxt|.svelte-kit|.output|.vercel|.cache|.parcel-cache|.venv|venv|__pycache__|.pytest_cache|.mypy_cache|.ruff_cache|coverage|build|dist|out|target'
if command -v eza >/dev/null 2>&1; then
    run_limited eza --color=always --icons=auto --group-directories-first --git-ignore --ignore-glob="$ignore_glob" --level=2 --tree "$DIR" 2>/dev/null | head -34
else
    run_limited tree -C -L 2 -I "$ignore_glob" "$DIR" 2>/dev/null | head -34
fi

if git -C "$DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    recent="$(run_limited git -C "$DIR" log -1 --pretty='format:%cr  %s' 2>/dev/null || true)"
    if [[ -n "$recent" ]]; then
        hr
        echo "  last commit"
        echo "  $recent"
    fi
fi
