# kitty capabilities kittymux does not use yet

Status: research, 2026-10-29, against kitty 0.49.2 (its bundled docs and changelog 0.38–0.49). For maintainers:
what kitty can now do natively that kittymux either reimplements, works around, or would gain from. Ranked by what it
is worth to an agent multiplexer. Each line names the kitty version that added it; check `kitty --version` before
relying on one (kittymux supports older kitties too).

## Replace what we build ourselves

| kitty feature | since | what it replaces or fixes in kittymux |
|---|---|---|
| `kitten @ ls` reports `last_focused_at` per window | 0.47 | our own focus-history bookkeeping for MRU jumps ("back to the agent I was in") |
| `kitten @ ls` reports `neighbors` per window | 0.45 | geometry guessing for directional moves and the deck's pane map |
| global watcher event `on_tab_bar_dirty` | 0.43 | timer-driven tab bar refreshes: redraw only when kitty says the bar changed (less CPU, no stale frame) |
| `inactive_text_alpha` (negative: fade only unfocused OS windows) | 0.47 | the `dim-inactive-windows` custom shader for the common case: cheaper, no shader |
| `launch --next-to` / `--source-window` | 0.40 | "spawn next to the agent I mean, not whatever has focus": the rule we enforce by hand in spawn/fanout |
| `launch --wait-for-child-to-exit` (via `kitty +launch`) | 0.42 | polling for a fanned-out job to finish; we get its exit code directly |
| `kitten @ screenshot` (window, tab or OS window, pixel perfect) | 0.49 | our screenshot path and the rigs' `shot_*` captures |
| `kitten @ set-os-window-title` | 0.49 | per-OS-window titles: makes compositor-side identification exact (see `kittymux_wmfocus`, which tags titles temporarily) |

## Make agents better to work with

| kitty feature | since | use |
|---|---|---|
| `kitten @ get-text --extent alternate / alternate_scrollback` | 0.48 | read full-screen TUI agents (Codex, Gemini, OpenCode) that draw on the alternate screen: more reliable state detection than the visible screen |
| `kitten @ scroll-window` to previous/next prompt | 0.40 | jump between the agent's turns in a long session (with shell integration marks) |
| mappable `copy_last_command_output`, `search_scrollback` | 0.45 | "copy the agent's last answer", "search this agent's session" as kittymux keys |
| `kitten choose-files` (previews: text, images, video, e-books) | 0.45 | attach files to an agent prompt at the speed of thought (`@file` insertion) |
| `kitten dnd` (drag files from the shell to GUI apps, even over SSH) | 0.47 | hand an agent's output files to the browser/editor |
| drag tabs / windows to rearrange, move, detach; drop a single-window tab into another tab's layout | 0.46–0.49 | the deck's rearranging can defer to kitty's own drag and drop with its previews |
| `quick-access-terminal` kitten; `launch --type=os-panel` panels | 0.42 | a dropdown "scratch agent" (Quake-style) and docked panels without a second program |
| sessions: `focus_tab`, multiple layouts per tab saved and restored | 0.44, 0.49 | session restore that lands on the right tab with every layout intact |
| `state:focused_os_window` match | 0.44 | act on "this OS window" without resolving it ourselves |
| watcher `on_color_scheme_preference_change` | 0.39 | follow the desktop's light/dark switch live |

## Visual quality, cheaply

- **Custom shaders** (0.49): kittymux already ships one; kitty now has a supported API for them. Keep shaders for
  effects options can't do.
- `cursor_trail` with `cursor_trail_color` (0.43): the user already runs a trail; colour it from the theme.
- `padding_fill_strategy` (0.49): colour the thin padding strips to match the background, so splits look seamless.
- Window title bars (`toggle_window_title_bars`, 0.46): show per-pane titles only while rearranging.
- `text_fg_override_threshold` perceptual contrast mode (0.41): keep agent output readable on translucent backgrounds.
- Vertical tabs with `tab_bar_edge left|right` (0.48): native, cheaper than a drawn sidebar for the plain case.

## Performance (from kitty's performance guide)

- Latency vs power: `input_delay 0`, `repaint_delay 2`, `sync_to_monitor no` is the lowest-latency setting kitty
  allows: up to ~500 redraws a second and possible tearing. On a laptop the guide's balance is
  `repaint_delay 6–10` with `sync_to_monitor yes`: tear-free, a fraction of the GPU/battery, ~1 frame more latency.
- Remote control is ~20 ms a call: batch reads (one `ls` per tick, memoised; we do) and prefer watchers (events) to
  polling.
- A large `scrollback_pager_history_size` costs memory only when used; `scrollback_lines` is held in RAM per window.

## Found on this machine (2026-10-29)

- `kitty.conf` includes `kittymux.conf` and `geninclude`s `kittymux_layout.py` twice: once via
  `~/Storage/Projects/kittymux` and once via `~/Projects/kittymux`, which are the same directory (a bind mount).
  Harmless but the layout generator runs twice at every kitty start; keep one.
- ~70 `kitty.conf.bak.*` files in `~/.config/kitty`: backups should rotate (keep the last few).

## Suggested order

1. `on_tab_bar_dirty` + `last_focused_at` + `neighbors` (less polling, exact MRU and direction): pure wins.
2. `get-text` alternate extents in the scanner (state detection for TUI agents).
3. `launch --next-to` in spawn/fanout; `--wait-for-child-to-exit` in fanout.
4. Keys: copy the agent's last answer, search the session, jump between prompts.
5. A quick-access "scratch agent"; `choose-files` for attachments.
6. Visual: padding fill, inactive alpha in place of the shader where it suffices.
