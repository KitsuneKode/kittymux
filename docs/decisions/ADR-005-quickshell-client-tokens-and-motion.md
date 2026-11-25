# ADR-005: Quickshell Client Architecture, Live Theme Tokens, and Calm Motion

## Status
Accepted

## Date
2026-11-21

## Context
The standalone Quickshell client (`client/`) renders a GPU-accelerated sidebar outside kitty (either docked as a Wayland layer-shell edge panel or attached over a kitty window's vertical bar on Hyprland). It must stay consistent with the in-kitty tab bar and panel on grouping, colours, state semantics, and motion restraint without polling or duplicating shell-injection risks.

## Decision
- **Single-source-of-truth file watching (`client/services/Feed.qml`, `client/lib/logic.js`)**:
  - Watch `$KITTYMUX_STATE/tabs.json` (written atomically by `kittymux_scan.py` only on visible change) and `$KITTYMUX_STATE/panel-group` so the client and panel share grouping state without polling.
  - Keep all pure data/layout rules in `client/lib/logic.js` (`.pragma library`, no QML types) so `node tests/client_logic.mjs` tests the exact shipped logic.
  - Execute actions (`kittymux act`, `kittymux mute`/`unmute`) strictly as argument arrays, never shell strings.
  - Track optimistic `pendingMute` state on click so rapid double-clicks mute then unmute before the scanner's next pass confirms.
  - Use `Object.create(null)` when indexing project groups by name so repositories named `constructor` or `toString` work safely.
- **Live kitty theme tokens (`client/config/Theme.qml`)**:
  - Derive every colour token from the focused kitty's `palette` in `tabs.json` (falling back to a neutral monochrome tone before the first document arrives); never hardcode a theme palette.
  - Colour is reserved for state (`waiting` orange, `done` green, `alert` red); `working` uses the text tone (motion, not colour, signals activity); the active-tab hairline uses `accent` at 45% opacity so state colours lead.
  - Glass pulls dark themes toward black for compositor blur (`kittymux-client` layer namespace) while light themes keep their own light background.
- **Rendering details (`client/components/`)**:
  - `Brand.qml`: Read `assets/icons/<brand>.svg` once and tint via `#rrggbb` fill, applying alpha on `Image.opacity` (Qt serializes translucent colours as `#aarrggbb`, which SVG rejects). Fall back to agent initial or a drawn terminal outline (avoiding PUA glyphs that depend on a loaded icon font).
  - `Label.qml`: Use FreeType rendering (`Text.NativeRendering`) rather than Qt's distance-field atlas for crisp UI sizes and reliable variable-font rendering; apply SF tracking compensation manually where Qt ignores `trak` tables, and enable tabular figures for changing counters.
  - `RollingNumber.qml`: Lay digits out right-to-left (suffix first, then units upward) so adding a leading digit does not re-roll lower digits; spring targets wrap via shortest modulo-10 distance (`9 -> 0` steps forward by 1).
  - `Sidebar.qml`: Sync sections/tabs into a keyed `ListModel` (move/insert/update/remove in place) so state changes update in place and arrivals/departures animate without rebuilding the list. Keep `ready = false` during the initial fill so startup appears whole without entrance animations. Preserve keyboard selection by tab key across list reflows, and clamp keyboard navigation at list ends without wrapping.
- **Calm, interruptible motion (`Spring.qml`, `Highlight.qml`, `StateRing.qml`, `Theme.qml`)**:
  - Three critically damped spring tiers (`fast 0.08s`, `moderate 0.16s`, `slow 0.24s`), integrated in `<= 2 ms` substeps, stopping timers when settled; retargeting preserves velocity for interruptibility. Exits run a tier quicker than entrances.
  - One shared gliding hover/keyboard `Highlight` per list; leaving into empty space fades out so the next hover fades in fresh rather than sliding from a stale row.
  - Working `StateRing` follows kittymux's calm-motion rule: steps a quarter turn every 3 s (gliding over 0.6 s, then resting) rather than spinning continuously; switches to a determinate arc when OSC 9;4 progress is present; settles upright when work stops; pulses once on entering `waiting`.
  - Reduced motion (`KITTYMUX_REDUCE_MOTION=1` or `motion` off) removes travel, glides, scale, and turning while preserving fades and state colour.
- **Hyprland attach-mode placement (`client/lib/logic.js`, `client/services/Hypr.qml`, `client/components/AttachedBar.qml`)**:
  - Combine kitty's framebuffer `geometry` (`tabs.json`) with Hyprland's logical window coords (`hyprctl -j clients`) and monitor scale (`hyprctl -j monitors`, where `x`/`y` are logical and `width`/`height` are physical mode pixels).
  - Subtract `DIVIDER_CELLS = 2` (`tab_bar.SEP_COLS`) so kitty's own background, blur, and divider remain untouched.
  - Hide the overlay when kitty is on another workspace, covered by a fullscreen window, or overlapped by a floating window above kitty.
  - Subscribe to Hyprland's `.socket2.sock` event stream (debouncing bursts by 40 ms) and fade the overlay out during `MOVING_EVENTS` until windows settle.
  - Notify attached kitties via `kittymux client attach <kittyPid> <ownPid>` so kitty suppresses duplicate tab drawing while the client lives.

## Alternatives Considered

### Hardcoding a client theme or polling `kitty @ ls`
- Pros: Simpler standalone startup.
- Cons: Breaks theme matching, adds idle wakeups, and duplicates scanner logic.
- Rejected: Violates kittymux's live-palette and single-source-of-truth rules.

### Rebuilding the QML list delegate tree on every `tabs.json` update
- Pros: Simpler than keyed `ListModel` diffing.
- Cons: Resets scroll position, breaks in-place state transitions, and causes visual flicker.
- Rejected: Keyed diffing keeps state updates smooth.

## Consequences
- `client/lib/logic.js` stays framework-free and unit-tested under Node (`tests/client_logic.mjs`).
- Attach mode remains experimental and opt-in (`KITTYMUX_CLIENT_MODE=attach`) while fractional-scale placement issues are tracked separately.
