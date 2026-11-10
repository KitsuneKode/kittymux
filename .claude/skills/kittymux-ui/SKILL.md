---
name: kittymux-ui
description: Design or change anything kittymux draws (the vertical tab bar, pane headers, the Agents panel, peek, the palette) so it reads like a finished product: T3 Code's sidebar hierarchy in compact form, Rex's state-first rows, and the aiforui.dev rules (design engineering, make-interfaces-feel-better, better-typography, animate) translated to kitty's character cells and the bar shader. Use before touching python/tab_bar.py, the panel or the shader, or when the bar "looks unfinished".
---

# kittymux UI

kitty's bar is cells, not pixels: one font, one size, colour and weight per cell, Nerd Font glyphs,
and the optional shader layer (`kittymux cards`) for fills, rounding, glass and hover. Every web rule
below is translated to that medium. Mechanics and gotchas: `docs/agents/layout.md`,
`docs/agents/conventions.md`; checks: `docs/agents/verify.md`. The plan these rules serve:
`plans/014-ui-cohesion-and-shell-contract.md`.

## Row hierarchy (T3 Code's sidebar, compact)

T3 Code's rows read in three steps, each quieter than the last. kittymux keeps that order in 2 lines:

| Line | Left | Right |
| --- | --- | --- |
| 1 | state glyph (state colour) · **title** (primary, bold) | age in the state's words, muted: `3m`, `done 3m`, `needs you 4m` |
| 2 | brand mark · project or folder · branch (faint) | progress `64%` or a count, faint |

- **State before brand.** The loudest thing on a row is its state, never the agent's logo. A row
  must be readable with colour off: each state has its own glyph.
- **Groups like T3:** `Needs you` · `Working` · `Settled N` (collapsed past a few), headers in the
  faint style with a count, the needs-you group first. Inside a group, newest first.
- **The active row** is the inset card (shader) or the reverse block; hover is one step quieter
  than active and spans the whole row.
- Tab numbers are the faintest thing on the row, or only on the active row.

## States (Rex's ladder, one meaning each)

| State | Glyph | Colour | Words |
| --- | --- | --- | --- |
| starting | hollow dot, still | faint | `starting…` (never "idle" before the first scan) |
| working | a calm turning mark (◐◓◑◒ at a few fps), never braille dots that read as a menu `⋮` | working | `3m` |
| needs you | filled dot + the tab's stripe | waiting | `needs you 4m`, the question in peek |
| done, unseen | check | done | `done 3m`, clears when you look |
| limited | clock | waiting, dim | `back in 42m` |
| error | cross | alert | `failed` |
| stale data | — | faint | `usage · 5m ago` |
| unavailable | — | faint | `not connected`, said once, not rows of dashes |

One escalation ladder for a change, in this order, each tested: verdict → `agents.json` → bar
redraw → inbox → popup after the settle delay. Looking at the pane: nothing but the row. Another
tab: stripe and header count. Another app: desktop popup with Jump (and the kuwai island moment).
Working → waiting → working inside the settle window never pops.

## Translated rules

- **Hierarchy by weight and colour, not size** (one cell size): primary + bold for the title,
  `muted` for meta, `faint` for the third step. Three steps, no more.
- **One accent**, meaning "where you are" only. State colours are the only loud colours.
- **Truncate with a way back:** middle-ellipsis paths (`feat/ass…agent`), end-ellipsis titles;
  the full string is in peek. Never let a long branch push the age off the row.
- **Logos:** the agent's own mark at one cell, monochrome in the muted colour unless the row is
  active or needs you; never a logo in place of the state glyph.
- **Spacing is cells:** one blank cell of gutter each side, a blank line only between groups,
  never between rows of a group; nothing left laid out for content that isn't there.
- **Motion:** only where it explains something (working spins, a needs-you stripe draws in once);
  shader animations for the tab-change glow; reduced-motion (`kittymux features off motion`)
  stops all of it. Nothing on hover but the highlight.
- **Loading:** a restored session shows placeholder rows that say `restoring`, not empty tabs.

## Verify

`shot_bar` in dark and light, wide and the 16-column rail, against the all-states test screen
(every state at once); `python3 -m unittest discover -s tests`; the rigs in verify.md never touch
another kitty (`KITTYMUX_SOCKET_DIRS`). Say which shots you looked at.
