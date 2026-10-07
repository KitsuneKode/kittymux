# kittymux UI design system and panel views: design

Status: approved in conversation 2026-10-07 (user: "agree with your recommendation, go complete things"). Visual reference: the design canvas
"kittymux UI Redesign" (boards: Usage v2, Inbox, Providers, Components, Areas, Palette, Setup, Productivity, Architecture).

## Why

The docked panel's Usage view read as a log: every line the same weight, four rows per quota, mid-phrase wraps, text where a picture
would do. There was no Inbox view even though typed inbox events exist. The fix is a shared visual language, not a one-off restyle, so
that every surface looks like one product.

## Decisions

1. **One pure module draws everything.** `python/kittymux_ui.py` (no kitty imports, unit tested under system python) takes a `Palette`
   plus a width and returns lines of styled spans. Renderers (the sidebar kit now; the keymap, peek card and others later) turn spans into
   escape sequences. Components: `chip`, `tabs`, `gauge`, `kv`, `card`, `keycaps`, `spark`, `heat`, `bars`, `tile`.
2. **Cell-native look.** Rounded cards from quadrant and half blocks (`▗▄▖`, `▝▀▘`), thin gauges from lower-half blocks, pills with
   Powerline round caps. kitty draws these glyphs itself, so they stay pixel-exact and need no new font.
3. **Surfaces derive from live colours.** `Palette` gains `card`, `card_hi`, `track` (blends of the live foreground over the background)
   and the calm / warm / hot ramp reuses the existing `done` / `waiting` / `alert` colours. Nothing is hardcoded. Text on a card is held to 4.5:1.
4. **One shape rule.** Pills for chips, tabs and toggles. Cards and buttons share one radius (a half-cell chamfer). Keycaps are square.
5. **One model for every provider.** `python/kittymux_meters.py` turns any provider's rows into four meter kinds: `quota`, `counter`,
   `state`, `spend`. The panel draws by kind, so a new provider needs no UI code. Collectors keep their text rows (the overlay still uses
   them) and gain numeric sidecar fields (`rem_s`, `window_s`, `tok`, `cached`, `sess`, `ago_s`).
6. **Panel views.** Agents, Usage, Inbox. Inactive tabs are icon-only; the active tab shows its label. Usage is a provider strip plus one
   focus card; details come from the selected provider, not from always-on text. Inbox lists typed events with Jump and Dismiss.
7. **Quickshell is an optional second skin, not the base.** The contract (`scan-<pid>.json`, `inbox-snapshot.json`, the meters, the
   `kittymux` verbs) is the product boundary. Nothing here depends on Quickshell. A spike belongs to a later change and needs the user to install it.
8. **Answer in place is out of scope for this pass.** It sends keystrokes into an agent pane and needs a per-agent verified key map and a
   safety review (destructive commands only offer Review). Inbox ships Jump and Dismiss.

## Non-goals

Replacing the tab bar, rewriting the Agents deck rows, any compositor-level UI, any network call, any new dependency, storing screen text.

## Rules kept

No hardcoded palette; no module-level timer state; no per-tab file reads on the bar's draw path; every smoke rig runs under `socket-only` and
never touches another kitty; docs and feature YAML change in the same commit as a user-visible change.

## Verification

Unit tests for every component (exact widths, no mid-token wraps, contrast >= 4.5:1 on cards in dark and light, hostile text cleaned).
`tests/shot_panel.sh` renders the real panel in an isolated Xvfb kitty (dark and light, two widths) and the PNGs are read before the work is
called done. `python3 -m unittest discover -s tests` and `tests/test_docs.py` stay green.
