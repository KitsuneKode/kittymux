# ADR-004: Pixel Tab Bar Column-0 Row Map and Shader Channel

## Status
Accepted

## Date
2026-11-21

## Context
Kitty's `custom_shaders` API passes the terminal backbuffer, viewport size, pointer position, central area bounds, and animation/time uniforms to Slang fragment shaders, but provides no channel for Python to pass arbitrary per-row geometry, active/working flags, or device pixel scale uniforms. Meanwhile, `python/kittymux_barpx.py` renders the vertical pixel tab bar as a PNG displayed through kitty's OS window background image behind blank tab-bar cells.

## Decision
- **Column-0 steganographic row map (`assets/shaders/kittymux-pxbar.slang`, `assets/shaders/kittymux-pxwave.slang`)**:
  - Column 0 of the rendered sidebar PNG encodes per-row metadata: each tab row uses an alternating marker colour offset from the bar background (`+6`/`+12` for normal rows; `+30`/`+36` red-channel offset past `FAMILY = 0.09` for working rows), while headers, labels, and gaps keep the bar colour.
  - The bottom of column 0 contains a run of `SCALE_RUN * scale` (`RUN = 8.0`) device pixels from which shaders recover the display/UI scale factor (`scale_of`).
  - `kittymux-pxbar.slang` repaints column 0 from column 1 (`t.pos + float2(px.x, 0.0)`) so the metadata strip is invisible.
  - The pixel bar is anchored top-left (`bar_span` activates on the left edge only) and its geometry constants (`INSET = 5`, `PAD = 10`, `R = 10`, `RAIL_MAX = 130`, `CARD_M = 6`, `CARD_R = 10`) match `python/kittymux_barpx.py`.
- **Gamma-encoded colour math**:
  - Both marker distance comparisons (`EPS = 0.008`) and hover/press veil blends execute in gamma-encoded (`pow(..., 1/2.2)`) space rather than linear RGB. In linear RGB, 6-level markers near black collapse to ~0.002 distance and merge, and linear hover lerps appear brighter than cairo's sRGB `0.085` active card veil on dark themes.
- **Hover, close cross, and terminal card framing (`kittymux-pxbar.slang`)**:
  - Static shader: kitty redraws only when pointer or frame changes.
  - On non-rail bars, hovering a tab row draws a rounded highlight veil, lifts settled text ink slightly, masks the right-hand age slot, and draws a close cross that brightens inside its 18 logical-px hit square. On the narrow rail (`< RAIL_MAX * sc`), the tile highlights without a close cross.
  - Outside the tab bar (`t.pos.x > span.y`), the terminal viewport is framed as a rounded card (`CARD_M`, `CARD_R`) resting on the sidebar's material with a subtle edge hairline; interior pixels (`edge > 40px`) early-return untouched.
- **Event-gated working animation (`kittymux-pxwave.slang`)**:
  - Runs at 15 fps only between `user:kmx-wave-on` and `user:kmx-wave-off` events emitted by `kittymux_pxbar.publish`, so an idle bar incurs zero animation cost.
  - Draws a calm 3-bar wave (`SPEED = 0.85` waves/s) in the end slot using sampled row background/ink colours, yielding to the close cross when the row is under the pointer.
- **Cell-bar cards and glow shaders (`kittymux-cards.slang`, `kittymux-glow.slang`)**:
  - Derive bar (`BAR_W = 0.05`), active card (`CARD_W = 0.15`), and hover (`HOVER_W = 0.09`) colours from kitty's live `background`/`foreground` matching `kittymux_theme`.
  - Round OSC 9;4 progress fills only near the bar's outer left/right edges so partial progress bars keep a square inner edge.
  - Glass mode makes only bar pixels translucent (`GLASS_A = 0.72`) while keeping cards and text opaque.
  - `kittymux-glow.slang` runs only during kitty's tab-change animation and lights both active cards and fill pixels.

## Alternatives Considered

### Re-rendering and re-uploading the PNG on every mouse move or wave frame
- Pros: No shader metadata channel required.
- Cons: High CPU/IPC cost per pointer move and 15 fps Cairo PNG encoding for working indicators.
- Rejected: GPU shaders keep hover and wave animations cheap and responsive.

### Comparing markers in linear RGB
- Pros: Avoids `pow` encode/decode calls.
- Cons: Quantized dark-theme markers merge and dark-bar hover looks brighter than the active card.
- Rejected: Gamma-encoded math is required for dark-theme fidelity.

## Consequences
- `python/kittymux_barpx.py` and `assets/shaders/kittymux-pxbar.slang`/`kittymux-pxwave.slang` share a strict pixel-encoding contract; changing marker offsets, `INSET`, `PAD`, `RAIL_MAX`, or `SCALE_RUN` requires updating both.
- Left-edge anchoring is assumed by `kittymux-pxbar.slang` and `kittymux-pxwave.slang`.
