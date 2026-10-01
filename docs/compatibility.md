# Compatibility

What has actually been run, and what is only expected to work. "Tested" means exercised by the
author or by a test in this repo; everything else is an educated guess and is labelled as one.

| Area | Status |
|---|---|
| **kitty 0.49.1** | Tested — the version used day to day. `kittymux doctor` refuses < 0.48 (vertical tabs). |
| **kitty 0.49.2** | Tested (released 2026-10-01): the install test and all three real-kitty smoke tests (states, sidebar buttons/drag/peek/absorb, upgrade-under-a-running-kitty) pass. CI runs both versions. |
| kitty 0.48.x | Untested. Vertical tab bar exists; native tab/window drag-and-drop (used for splits ↔ tabs) is newer and may be missing. |
| **Arch Linux, Hyprland (Wayland)** | Tested — daily driver, incl. the docked panel (`kitten panel`, layer-shell). |
| Other Wayland compositors | Panel needs `wlr-layer-shell`; sway/river/niri are expected to work, **untested**. GNOME/Mutter has no layer-shell → no docked panel (everything else works). |
| X11 | Tab bar, scanner, deck: **tested under Xvfb** (see `tests/smoke_*.sh`). Panel: not available. |
| macOS | Untested. `/proc`-based foreground-process reads (`tcgetpgrp` + `/proc/<pgrp>/cmdline`) are Linux-only, so agent detection will not work as written. |
| Windows | Not supported (kitty has no Windows build). |

## Agent CLIs

Status is read from each agent's screen (see README → *Agent status*), so it depends on what the TUI prints.
Markers were verified against real sessions of the tools below on the author's machine; versions drift,
and a TUI that rewords its prompts needs a one-line change in `python/kittymux_state.py`.

| Agent | Screen markers | Hooks |
|---|---|---|
| Claude Code | tested (working — both the `esc to interrupt` form and the newer `· Verb… (6m 52s · ↓ 35k tokens)` line, permission prompt, usage limit) | `kittymux hooks --install` |
| Codex CLI | tested (working, usage limit) | `notify` → `mux-status` |
| Devin | tested (working; idle prompt; "N subagents" footers are not read as work) | — |
| OpenCode | idle screen checked live; its working marker (`esc interrupt`) follows the documented hint | — |
| Gemini CLI, Cursor Agent, Amp, Antigravity (`agy`) | patterns follow each tool's documented hints; **not verified against live sessions** | — |
| Factory `droid` | "No active subscription found" read as `limited` (seen live); working/permission markers not verified; its `⛬` title icon is stripped | — |
| grok, qwen, kimi, goose, kilo, vibe (Mistral), junie, auggie | logo + hooks/title activity only | — |
| aider, crush | no readable TUI markers → hooks or title activity only | — |

## Things that depend on the environment

- **Remote control socket** (`allow_remote_control` + `listen_on`) is required by the pickers and CLI.
  Prefer `listen_on unix:${XDG_RUNTIME_DIR}/mykitty` (private directory). `/tmp` works but any local user
  can create files there; kittymux only talks to sockets owned by you, and `doctor` warns.
- **Fonts**: brand logos live in a bundled icon font installed to `~/.local/share/fonts`. After the first
  install, restart kitty once (kitty caches loaded font faces; a config reload does not re-read a font file
  that gained glyphs).
- **Tools** used when present: `fzf`, `jq`, `git`, `notify-send`, `gh` (PR numbers), `ss` (listening ports).
- `pane-state.py` is cached by kitty for the life of the process; it only holds hook state now, so an upgrade
  never needs a restart for it. New *helper modules* are picked up by `kittymux upgrade` (two reloads).
