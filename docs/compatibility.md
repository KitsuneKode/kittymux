# Compatibility

What has actually been run, and what is only expected to work. "Tested" means exercised by the
author or by a test in this repo; everything else is an educated guess and is labelled as one.

| Area | Status |
|---|---|
| **kitty 0.49.1** | Tested — the version used day to day. `kittymux doctor` refuses < 0.48 (vertical tabs). |
| **Updating kitty under a running kitty** | kitty keeps running its old binary but loads Python files from the new install on demand and at every config reload — an unsupported mixed state (after the 0.49.1 → 0.49.2 update, tab clicks/drags and reloads in still-running kitties are suspect). `kittymux doctor` now warns when a running kitty's binary was replaced; restart it. |
| **Tab drag on 0.49.1 vs 0.49.2** | 0.49.1 swaps the dragged tab with whatever it touches (kittymux patches that: no jump on grab, no cascades); 0.49.2 reorders by insertion with a drop marker and lets a pane dropped on a tab gap/edge become a new tab, so kittymux's patches stand down there. Both are covered by `tests/smoke_drag.sh`. |
| **kitty 0.49.2** | Tested (released 2026-10-01): the install test and all three real-kitty smoke tests (states, sidebar buttons/drag/peek/absorb, upgrade-under-a-running-kitty) pass. CI runs both versions. |
| **kitty-only options (0.49.2)** | `detect_url_regex` (clickable `file:line`) and `custom_shaders dim-inactive-windows` are emitted by the layout geninclude only when the asking kitty is ≥ 0.49.2 (and, for the shader, `slangc` is installed). Click test: `tests/smoke_openref.sh`. `tests/smoke_extras.sh` verifies the dim render with `slangc` present (≈65k pixels change on, restored off; the test skips that half without `slangc`) and the clean refusal without it. |
| **Window-manager keys** | Hyprland (HyDE scrolling layout) takes `ctrl+alt` + `a s f c x p w m ←→↑↓ = -`; kittymux avoids them (pinned by a unit test; `kittymux doctor` checks your live binds). |
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
| Codex CLI | tested (working incl. `• Working (… • esc to interrupt)`, usage limit; status lines without the esc hint, like `• Reviewing approval request (3s)`, match by shape — not yet seen live) | `notify` → `mux-status` |
| Devin | tested (working via `esc twice to interrupt` and its busy input placeholder `Guide Devin while it works`; idle prompt (its composer reads `Ask Devin to build features` only when idle, so a busy line above it is stale); "N subagents" footers are not read as work — whether they mean running subagents is unverified) | — |
| OpenCode | idle screen checked live; its working marker (`esc interrupt`) follows the documented hint | — |
| Gemini CLI, Cursor Agent, Amp, Antigravity (`agy`) | patterns follow each tool's documented hints; **not verified against live sessions** | — |
| Factory `droid` | "No active subscription found" read as `limited` (seen live); working/permission markers not verified; its `⛬` title icon is stripped | — |
| grok, qwen, kimi, goose, kilo, vibe (Mistral), junie, auggie | logo + hooks/title activity only | — |
| aider, crush | no readable TUI markers → hooks or title activity only | — |

## Things that depend on the environment

- **Remote control socket** (`allow_remote_control` + `listen_on`) is required by the pickers and CLI. Use
  `allow_remote_control socket-only` (no in-band control from program output; every smoke test runs under it) and
  `listen_on unix:${XDG_RUNTIME_DIR}/mykitty` (private directory; kitty expands environment variables there). `/tmp` works but any local user
  can create files there; kittymux only talks to sockets owned by you, and `doctor` warns.
- **Fonts**: brand logos live in a bundled icon font installed to `~/.local/share/fonts`. After the first
  install, restart kitty once (kitty caches loaded font faces; a config reload does not re-read a font file
  that gained glyphs).
- **Tools** used when present: `fzf`, `jq`, `git`, `notify-send`, `gh` (PR numbers), `ss` (listening ports).
- `pane-state.py` is cached by kitty for the life of the process; it only holds hook state now, so an upgrade
  never needs a restart for it. New *helper modules* are picked up by `kittymux upgrade` (two reloads).

## Side-sheet probes (kitty 0.49.2)

| Question | How checked | Answer |
|---|---|---|
| Does idle mouse motion over the tab bar reach Python? | `tests/probe_motion.sh` (Xvfb, real pointer events) | **No.** 0 of 8 idle moves reached `TabManager.handle_tab_bar_mouse`; only press/release arrive (2 calls). Hover cannot open anything from the bar itself; it can live inside the sheet and the docked panel. |
| What does `draw_window_title(data)` receive? | `tests/probe_titledata.sh` (Xvfb) | `WindowTitleData(has_activity_since_last_focus, is_active, needs_attention, tab_id, title, window_id)` — no directory, but `window_id` resolves it (`get_boss().window_id_map[window_id].child.current_cwd`). |
| Does an os-panel land flush beside the bar, and how fast does it start? | `tests/probe_panel.sh` — **manual, Hyprland** | **Not yet run.** Needs a person on the real compositor; an Xvfb run would say nothing about layer-shell. |
