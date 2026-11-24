"""Agent skill installer for kittymux (pure Python, no kitty imports).

Gives coding agents (Claude Code, Codex, OpenCode, Antigravity) a concise,
token-efficient guide to inspect and orchestrate kitty panes safely via the
kittymux CLI and `kitty @`, without stealing focus or closing user panes.
"""
from __future__ import annotations

import os
from pathlib import Path

MARKER = "<!-- kittymux-managed-skill -->"

SKILL_MD = f"""---
name: kittymux
description: Inspect and orchestrate kitty tabs, split panes, agent statuses, diffs, and companion shells using kittymux without stealing focus.
---
{MARKER}

# kittymux Workspace Control

Use `kittymux` and `kitty @` when the user asks you to run commands in companion panes, check sibling agents, inspect diffs, or manage splits inside kitty.

## Read workspace state (safe, read-only)

```sh
kittymux tabs --json          # every tab and pane across running kitties, with state, repo, branch, and title
kittymux inbox --json         # pending questions, permissions, errors, limits, and completions
kittymux changes --json       # git files and line counts changed since this agent run started
kittymux explain --json       # why each agent pane is in its current state
```

## Open companion panes without stealing focus

Always pass `--keep-focus` and tag panes you create with `--var kittymux_owner=$KITTY_WINDOW_ID` so you can identify and clean up only what you opened:

```sh
kitty @ launch --location=vsplit --cwd=current --keep-focus \\
  --var kittymux_owner="$KITTY_WINDOW_ID" \\
  --title "tests" -- sh -lc 'pytest -q'
```

## Read output from a companion pane

```sh
kitty @ get-text --match id:<WINDOW_ID> --extent=screen
```

## Clean up only panes you created

```sh
kitty @ close-window --match "var:kittymux_owner=$KITTY_WINDOW_ID"
```

## Spawn parallel agents or fan out tasks

```sh
kittymux spawn codex --vsplit                 # start a sibling agent beside this pane
kittymux fanout "fix flaky test" claude,codex # isolated worktrees + tabs per agent
```

## Rules

- Never focus or switch OS windows unasked; always pass `--keep-focus` on background launches.
- Never close panes that do not carry your `kittymux_owner` tag unless the user explicitly names them.
- Never paste secrets or environment dumps into remote-control commands or commit messages.
"""

TARGETS = (
    (".claude", "skills", "kittymux", "SKILL.md"),
    (".codex", "skills", "kittymux", "SKILL.md"),
    (".agents", "skills", "kittymux", "SKILL.md"),
)


def skill_paths(home: str | Path | None = None) -> list[Path]:
    root = Path(home) if home is not None else Path.home()
    return [root.joinpath(*parts) for parts in TARGETS]


def install(home: str | Path | None = None) -> tuple[list[Path], list[Path]]:
    """Write SKILL.md to each agent skill dir. Returns (written, skipped_unowned)."""
    written: list[Path] = []
    skipped: list[Path] = []
    for path in skill_paths(home):
        if path.exists():
            try:
                existing = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                skipped.append(path)
                continue
            if MARKER not in existing:
                skipped.append(path)
                continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SKILL_MD, encoding="utf-8")
        written.append(path)
    return written, skipped


def remove(home: str | Path | None = None) -> tuple[list[Path], list[Path]]:
    """Remove only kittymux-managed SKILL.md files. Returns (removed, skipped_unowned)."""
    removed: list[Path] = []
    skipped: list[Path] = []
    for path in skill_paths(home):
        if not path.exists():
            continue
        try:
            existing = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            skipped.append(path)
            continue
        if MARKER not in existing:
            skipped.append(path)
            continue
        path.unlink()
        try:
            if not any(path.parent.iterdir()):
                path.parent.rmdir()
        except OSError:
            pass
        removed.append(path)
    return removed, skipped


def load_live_tabs(state_dir: str | Path) -> list[dict]:
    """Read `$KITTYMUX_STATE/tabs.json` and return only rows whose kitty pid is still alive."""
    import json

    path = Path(state_dir) / "tabs.json"
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    windows = doc.get("windows") if isinstance(doc, dict) else None
    if not isinstance(windows, list):
        return []
    live: list[dict] = []
    for win in windows:
        if not isinstance(win, dict):
            continue
        pid = win.get("kitty_pid")
        if isinstance(pid, int) and pid > 0 and not os.path.exists(f"/proc/{pid}"):
            continue
        live.append(win)
    return live
