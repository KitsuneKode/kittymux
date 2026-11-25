# ADR-002: Per-Instance Layout and Version-Gated Config via `geninclude`

## Status
Accepted

## Date
2026-11-21

## Context
Kitty options belong to a kitty *process* (shared across its OS windows), and reloading `kitty.conf` overwrites any runtime option changes not represented in config. Furthermore:
- Options introduced in newer kitty releases (`detect_url_regex`, `{custom}` in `window_title_template`, `custom_shaders`) cause config errors on older or already-running kitty processes upgraded underneath a live session.
- Emitting multiple `custom_shaders` lines causes the last line to replace earlier ones.
- Under Wayland compositors with focus-on-activate enabled (such as Hyprland's `misc:focus_on_activate`), kitty's `window_alert_on_bell` triggers `xdg-activation` requests that forcibly steal focus and switch workspaces.
- `geninclude` Python scripts execute inside kitty's own embedded interpreter during config parsing.

## Decision
- **Per-instance layout via last-loaded `geninclude` (`python/kittymux_layout.py`)**: Store per-process layout (`edge`, `mode`, `width`) in `$KITTYMUX_STATE/layout-<pid>.json` (with `layout-default.json` for new instances) and emit kitty config via `geninclude python/kittymux_layout.py` placed *last* in `kitty.conf`. If no layout is saved, emit nothing so the user's own `tab_bar_*` settings remain in charge.
- **Embedded-interpreter safety**: `kittymux_layout.py` never raises `SystemExit` (`main()` returns cleanly) and catches helper-import failures so config loading can never crash or abort kitty.
- **Process-version gating**: Gate newer options on `kitty.constants.version` of the *asking* process (`DETECT_URL_MIN = (0, 49, 2)`, `PANE_TITLE_MIN = (0, 49, 2)`, `DIM_SHADER_MIN = (0, 49, 2)`, `CARDS_SHADER_MIN = (0, 49, 0)`), and gate shaders on `have_slangc()`. Combine all active shaders into a single `custom_shaders` line, where `PXBAR_PIPELINE` replaces `CARDS_PIPELINE`.
- **Pane title fallback**: Set `window_title_template` to `{custom or title}` so a missing/disabled hook or empty custom output falls back to kitty's standard title instead of a blank bar.
- **Focus-steal prevention**: When `hypr_focus_on_activate()` is true and the `attention` switch is not explicitly forced on, emit `window_alert_on_bell no`.
- **PID-reuse-safe cover and attach records**: Panel bar hiding (`bar-covered-<kitty_pid>`, emitting `tab_bar_min_tabs 9999` after layout lines) and client attach suppression (`bar-attached-<kitty_pid>`) store `(owner_pid, owner_start, kitty_start)` using `/proc/<pid>/stat` field 22 start ticks so a dead or reused PID never leaves a kitty without its bar. Stale cleanup removes records only when the kitty process itself is gone; a live kitty's scanner sweeps dead-owner records and triggers a redraw.
- **Vertical bar geometry constants**: Measured kitty vertical bar width is `tab_title_max_length + 8` columns (`BAR_PADDING_COLS = 8`), capped by kitty at `1/3` of the window width (`MAX_WINDOW_FRACTION = 1/3`). `COMPACT_WIDTH = 1` yields a 9-column rail; `DEFAULT_WIDTH = 20` yields 28 columns; `tab_bar_min_tabs 9999` hides the bar. The resize grab zone spans `GRAB_CELLS = 1.0` each side of `DIVIDER_CELLS = 1.0` (minimum `GRAB_MIN_PX = 12.0`), while the native divider (verified against kitty `0.49.2`) sits inside the pane's side padding when `pad_px >= 10`.
- **Installer safety (`install.sh`)**: Backup `kitty.conf` before appending includes; skip re-adding `include-tab-edge.conf` if already included (kitty errors on duplicate includes); copy `kittymux-icons.ttf` only when `cmp -s` detects a real difference so mtime does not bump for running kitties; omit leader-covered chords in `kittymux-keys.conf` when leader mode is active (`# kittymux:leader-covers KEY`).

## Alternatives Considered

### Writing static config files into `~/.config/kitty`
- Pros: No runtime script execution during config reload.
- Cons: Cannot vary per kitty PID, breaks live kitties running older versions after a package upgrade, and loses runtime overrides on reload.
- Rejected: `geninclude` is the only mechanism that evaluates per-process state and running version on every reload.

## Consequences
- `kittymux_layout.py` remains pure Python with no unconditional kitty imports so it is unit-testable under system `python3`.
- Resizing a hidden or compact bar automatically transitions `mode` to `"full"`.
- Running kitties started before a font update rely on `kittymux-icons.ttf` mtime staying stable until an actual glyph change ships.
