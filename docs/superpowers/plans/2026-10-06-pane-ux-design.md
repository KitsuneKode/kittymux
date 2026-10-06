# kittymux pane controls and UI review — 2026-10-06

Read-only review of pane rearrangement, the vertical tab bar, peek/deck preview, pane captions and related draw/scan performance. Repository was clean on `main` before and after. Installed kitty reports 0.49.2. No live kitty was restarted, reloaded or focused. Source changes are not implemented.

## What already works

| Task | Existing control |
| --- | --- |
| Swap the current pane with a chosen pane | Ctrl+Alt+Shift+Y, then the displayed pane selector |
| Select a pane visually | Ctrl+Alt+E |
| Show pane captions / native drag handles | Ctrl+Alt+Shift+C |
| Cycle layouts | Ctrl+Alt+Space |
| Equalize splits | Ctrl+Alt+0 |
| Preview a tab | Right-click its vertical bar row |
| Preview the longest-waiting agent | Ctrl+Alt+Shift+Q |
| Hover previews inside the deck | Ctrl+Alt+B, then hover a tab or pane row |
| Persistent panel | Ctrl+Alt+Shift+B, on supported Wayland setups |

Source: `kittymux-keys.conf.tpl:74`, `python/kittymux_barsize.py:314`, `python/sidebar-kit.py:373`.

Kitty documents visual swapping, directional `move_window`, split rotation and `rotate 180`. Directional movement exchanges pane positions in the installed splits implementation; it does not respawn the processes. `rotate 180` swaps children of the current split, which can include a whole nested group. It is not an arbitrary destination picker. [Actions](https://sw.kovidgoyal.net/kitty/actions/#action-swap_with_window), [splits](https://sw.kovidgoyal.net/kitty/layouts/#the-splits-layout).

Ordinary tab-bar hover previews cannot be added with a normal kitty config hook on 0.49.2: its C handler deliberately skips idle motion, while allowing drag motion. The deck/panel already receives hover events. [Versioned upstream implementation](https://github.com/kovidgoyal/kitty/blob/v0.49.2/kitty/mouse.c#L900-L921).

## Confirmed findings

| Severity | Location | Current behavior | Recommended behavior | Evidence |
| --- | --- | --- | --- | --- |
| HIGH | `python/tab_bar.py:571`, `python/kittymux_deck.py:178` | The map has one terminal row: only two vertical sample positions. Three equally stacked panes yield IDs 1 and 3, omitting pane 2. | Always retain the actual pane count. Keep the small map as an approximate overview; offer a larger numbered map in peek/deck. Use a compact count/chip fallback when the sampled map cannot represent every visible pane. | Actual `layout_minimap` call returned represented IDs `[1, 3]`, expected `[1, 2, 3]`. Three side-by-side panes returned all three. Light-theme synthetic three-pane render inspected. |
| MEDIUM | `python/kittymux_place.py:91`, `python/tab_bar.py:1241` | Folder text wins when the map would leave fewer than six folder cells. The map then fails the all-or-nothing fit check; the split count is also absent because a map was selected earlier. | Reserve a small explicit split-count indicator; progressively omit map, branch and path details without losing that count. | Minimum-width dark and light screenshots show the three-pane docs tab with only its branch. |

These are reproduced paths, not proof that either explains every occurrence in the user's live session. The requested distinction between layout blocks and agent-status indicators remains unanswered. If the missing indicator is the resize arrow or agent status instead, it needs its own reproduction.

## Recommended first implementation

1. **Pane mode.** Candidate entry: Ctrl+Alt+Shift+semicolon. Inside it: arrows or h/j/k/l exchange the current pane with a directional neighbor, r rotates the current split, s swaps its split's two sides, e equalizes. Escape exits; use a short timeout and a visible action hint. Preserve the direct numbered swap. Finish the mode before entering the visual swap picker so its selector keys cannot conflict. A hidden bar also needs feedback, for example a native command-palette entry or small transient help overlay.
2. **Reliable split indicator.** A compact pane count always remains in the full sidebar. When room permits, show an approximate shape and focused-pane mark. Numbered pane chips can show `!`, `⊘`, a spinner or `✓` from the existing merged resolver; they supplement the map rather than depend on colors alone. A detailed two-dimensional map belongs in peek/deck where there is space. Do not add rows beyond kitty's per-tab height cap.
3. **Preview polish.** Keep right-click peek on the native bar. In deck/panel, delay expensive preview requests briefly during pointer traversal and retain latest-selection-wins cancellation. Include a larger numbered layout diagram and pane selection in peek. Label which pane is being previewed: `collect` already supplies `shown_title`, but `draw_screen` does not display it. Reserve state-badge space before fitting long titles; wrap full title/path details in the expanded card.
4. **Optional pane captions.** The current custom caption is folder/branch/title, not kittymux's merged agent state (`python/kittymux_panetitle.py:157`). If per-pane status is desired, reserve a compact state symbol before the path. Use the same merged view as every other consumer. Keep captions opt-in and provide a count/status fallback for narrow panes.

The candidate prefix was absent from the local kitty configs searched. Ctrl+Alt arrows are claimed by Hyprland, and Ctrl+Alt+Shift arrows are already kittymux tab movement. The live `hyprctl binds -j` query did not return usable JSON, so the candidate is **not yet verified collision-free**. Before adding it, normalize modifier order across all loaded configs, query the live WM and drive real key events in a private rig. Update the template, README, mode hints/key overlay and published docs together.

Kitty provides native keyboard modes with per-mode timeouts. Its command palette lists custom mode bindings and their entry keys, which can improve discovery without adding another launcher. [Keyboard modes/timeouts](https://sw.kovidgoyal.net/kitty/conf/#opt-kitty.map_timeout), [command palette](https://sw.kovidgoyal.net/kitty/kittens/command-palette/#custom-keyboard-modes).

## Performance evidence and next measurements

`tests/profile_bar.sh` with 23 tabs, a synthetic working agent, a private Xvfb display and software rendering reported mean **0.084 ms per draw_tab invocation** across its final six 200-call groups; worst recorded invocation **3.326 ms**. Group means ranged 0.059–0.097 ms. This includes kitty's draw callbacks and is not a complete frame, p99, scanner cost, compositor cost or keyboard latency measurement. Multiplying by 23 gives roughly 1.9 ms only as a rough draw-cost estimate.

Existing optimizations are present: per-pass shared lookups, title/foreground caches, spinner timer stopped with no working agents, half-rate spinner redraw for unfocused OS windows, slower scanning with no agents and bounded latest-selection-wins preview work. These are not new gains to promise.

Candidate improvements, requiring before/after measurements:

- Cache mini-map geometry by visible window IDs, pane rectangles and dimensions; update colors when focus/status/palette changes. Current `_pane_map` rebuilds geometry on each invocation. Measure with many split tabs; the existing profiler mostly uses single-pane tabs.
- Measure scanner time separately with multiple agents. `scan_window` serializes the visible screen using `window.as_text()` before classification discards all but the bottom non-empty lines. Explore a bounded extraction with exact behavioral parity, or screen-change-aware classification caching while still running the resolver's timed transitions every tick. Never infer completion from skipped reads.
- Separate spinner paint from snapshot/preview work in the deck. Profile whole-screen redraw, RC subprocess count, idle CPU and worst preview latency before choosing a more complex rendering path.
- Avoid arbitrary reductions to kitty's input/repaint delays: documentation explicitly describes responsiveness/CPU and flicker tradeoffs. [Performance tuning](https://sw.kovidgoyal.net/kitty/conf/#performance-tuning).

## Verification and coverage

- Inspected original screenshot, normal dark sidebar, normal light three-pane stack, minimum-width dark/light three-pane stacks.
- Screenshots: `/tmp/kittymux-audit-dark.png`, `/tmp/kittymux-audit-light-stacked.png`, `/tmp/kittymux-audit-dark-narrow.png`, `/tmp/kittymux-audit-light-narrow.png`.
- Existing deck tests: 49 passed. Pane-title tests: 15 passed. Keymap tests: 23 passed. The explicit three-stacked-pane probe failed as described; no regression test or fix was added.
- Screenshot and profiler rigs used their own private Xvfb kitty, synthetic agents and explicit private remote-control sockets. Initial sandbox attempts skipped because Xvfb could not start; approved isolated runs succeeded.
- Runtime preview interaction, error/empty states, actual Wayland panel behavior, proposed shortcut delivery, scanner CPU and end-to-end latency were **not verified**. Peek/deck/caption recommendations are based on source inspection, not a completed redesign review.
- UI polish owner skill was available. The separate better-accessibility, better-layout, better-writing, better-typography and better-colors owner skills were not in the available catalog, so those formal domain reviews are **Not reviewed**. This is not a holistic accessibility approval.

**Verdict: Block approval of the layout indicator's accuracy until the omitted-pane case has an explicit fallback.** Recommended order: reliable split count/map fallback, pane controls, preview improvements, then measured performance work.
