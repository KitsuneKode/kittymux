# Plan 006 spike report — persistent `kitten panel` sidebar

**Verdict: GO — shipped.** `bin/mux-panel` (`ctrl+alt+shift+b`, leader `B`) runs the sidebar
deck as a persistent, docked, space-reserving panel on Hyprland. Measured 2026-09-30 on
Hyprland 0.56.2, kitty 0.49.1, 1920×1080 monitor.

## Answers (each observed, not assumed)

| # | Question | Answer | Evidence |
|---|---|---|---|
| 1 | Does `kitten panel --edge=left` run, and how does it run a python kitten? | Yes. `kitten panel … kitten /abs/path/sidebar-kit.py` works. **The path must be canonical** — a `..` segment (e.g. `bin/../python/…`) makes the inner `kitten` exit silently and the panel vanishes with no log. | bisected: same command with `$PWD/python/…` → panel present; with `bin/../python/…` → 0 layers |
| 2 | Is space reserved? | **Yes, automatically** (no `--exclusive-zone` flags needed for `--edge=left`): the monitor's reserved area became `[407, 38, 0, 0]` and the tiled window shrank 1900 → 1493 px wide and shifted right. | `hyprctl monitors -j` reserved; `hyprctl clients -j` before/after |
| 3 | Layer / visibility | One layer-shell surface, namespace **`kitty-panel`**, level 2 (`top`), x=1600 y=38 w=427 h=1042 at `--columns=32`. Per-monitor, so it shows on every workspace of that monitor. Use `layerrule … kitty-panel` for blur etc. | `hyprctl layers -j` |
| 4 | Hover/click in the panel | Deck logic verified: hover selects rows and click jumps (real X11 pointer events in the offscreen rig; a click on the third row focused that tab). In-panel input on Hyprland itself was not injected (that would move the operator's real pointer). `--focus-policy=on-demand` lets the panel take keys when clicked. | offscreen rig; code path identical (`MouseTracking.full`) |
| 5 | Can the deck read the main kitty from inside the panel? | Yes, via `kitty @ --to <socket>`: `KITTYMUX_TARGET` (default: the kitty you are in, from `hyprctl activewindow` pid → `/tmp/mykitty-<pid>`, else the newest socket). A standalone (non-overlay) kitten must not request the kitten_ui RC fd → `kitten_ui(allow_remote_control=not KITTYMUX_PANEL)`. | live panel rendered a real instance's tabs |
| 6 | Cost | Idle CPU **0.9% of one core** (deck refresh every 1.5 s), RSS **~247 MB** for the 4-process tree (a full kitty instance + GPU context). Teardown restores the reserved area to `[0, 38, 0, 0]` and removes the layer. | /proc/stat sampled over 10 s |

## Gotchas found (handled in `bin/mux-panel`)

- `--class` is not a `kitten panel` option; passing it makes the panel fail to appear.
- `kitten_ui(allow_remote_control=True)` raises when run outside a kitty-launched kitten unless
  `KITTY_LISTEN_ON=fd:N`; a panel inherits a socket-style `KITTY_LISTEN_ON` from its launcher.
- Never `pkill -f` panel processes from a shell whose own command line contains the pattern.

## Not done / follow-ups

- One panel watches **one** kitty instance. With several instances a global deck would enumerate
  all `/tmp/mykitty-*` sockets and jump across them with the existing `focus_hyprland_by_title`.
- Multi-monitor: `--output-name` can pin the panel to one output.
- X11/i3: the exclusive zone is ignored there; the panel still runs as a normal window.
