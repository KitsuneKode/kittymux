# Plan 003: Redesign the vertical tab bar (shadcn-sidebar / cmux style rows, session header, clean backgrounds)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8681a7d..HEAD -- python/tab_bar.py kittymux.conf README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition. NOTE: plans 001 and 002 also modify
> `python/tab_bar.py` — they must be DONE first, so expect that diff; re-read
> the file fully before starting.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (visual, always-on UI; verified in a scratch kitty)
- **Depends on**: plans/002-theme-tokens-from-kitty-colors.md
- **Category**: dx / design
- **Planned at**: commit `8681a7d`, 2026-09-29

## Why this matters

With `tab_bar_edge left`, the bar currently looks patchy: each row is a tan
rectangle (kitty's pre-fill) with differently-coloured text cells stamped on it, the
whole empty bar area turns a foreign navy, the first row is pushed right by an inline
`[session]` prefix, and subtitles are indented inconsistently. The goal is the
look of a shadcn `Sidebar` / cmux workspace list: a quiet bar, a single filled row
for the active tab with a left accent rail, small muted subtitles, one coloured status
dot, and a proper session header row — using the plan-002 palette tokens so it follows
the user's theme.

## Current state

Files: `python/tab_bar.py` (draw logic), `kittymux.conf` (`tab_title_max_lines 2`).

Verified facts about kitty 0.49.1's vertical tab bar (from
`/usr/lib/kitty/kitty/tab_bar.py`, `update_vertical`, lines ~1046–1141 — read it):

1. Kitty calls `draw_tab` **twice per tab per redraw**: once to *measure* height
   (`extra_data.for_layout == True`, drawn at row 0), then again to draw for real.
   A tab's height = `screen.cursor.y - row + 1` **after** your draw returns, capped at
   `draw_data.max_tab_title_lines` (= option `tab_title_max_lines`, currently 2).
   So **leave `screen.cursor.y` on your last used row**.
2. Before the real draw, kitty **pre-fills** every row of the tab with
   `draw_data.tab_bg(tab)` (opts `active_tab_background` / `inactive_tab_background`)
   using `s.draw(' ' * s.columns)`; DECAWM (autowrap) is off, so drawing exactly
   `screen.columns` spaces is safe. Text you draw only covers its own cells — that is
   the patchwork.
3. Between the measure pass and the real pass kitty calls
   `s.erase_in_display(2, False)`, which fills the whole bar using the **current cursor
   background**. Our `draw_tab` currently ends with `screen.cursor.bg == _BG` (navy),
   so the entire bar is erased to navy. In the horizontal path kitty resets
   `s.cursor.bg = s.cursor.fg = 0`; the vertical path does not. **Reset
   `screen.cursor.bg = 0; screen.cursor.fg = 0` at the end of `draw_tab`.**
4. Kitty inserts one blank spacing row between tabs automatically (dropped when space
   runs out). `is_last` is always `True` in vertical mode; use `extra_data.next_tab`.
5. Tab click hit-area = the tab's rows (`TabExtent`), x full width. A header row drawn
   inside tab 1 is therefore clickable as tab 1 — acceptable.
6. `screen.columns` is the real bar width; `max_title_length` can exceed it
   (existing code already clamps to `screen.columns`; keep doing so).

Excerpt of current `draw_tab` structure (`python/tab_bar.py`, after plans 001/002):
inline `[session] ` prefix when `index == 1`; line 1 = `▌`/space + icon in a fixed
3-cell column + `N:title` + right-aligned marks (`●`, ` !`); line 2 = subtitle
`branch  N panes  working|waiting` at `x0 + 3 + len(num)`; horizontal mode appends `┃`
separators and the cwd anchor on the last tab. Width math uses `len()` (wrong for wide
glyphs) — use `wcswidth` from `kitty.fast_data_types` instead.

Palette tokens (from plan 002 `kittymux_theme.Palette`): `bg fg text muted faint surface
surface_hi accent working waiting done alert info` — plain `0xRRGGBB` ints; tag with
`as_rgb` at draw time.

## Design spec (implement exactly; vertical mode only)

```
 SESSION-NAME              4 · ! 1          <- header row (tab 1 only): faint uppercase name,
                                               right side: "N tabs" muted + "! K" in waiting colour
▌ ◉ title of the tab       ●                 <- active row: accent rail ▌, agent glyph, bold title,
▌   ⎇ main · 2 panes  3                         right-aligned status dot; line 2 subtitle; index right
  ◉ other tab                                <- inactive: no fill, muted title
    ⎇ feat/x · waiting    2
```

- **Fill**: active tab rows filled with `surface_hi`; inactive rows filled with the
  bar's default background (`cursor.bg = 0`, i.e. transparent to the terminal bg).
  Implement by *repainting* the rows yourself at the start of `draw_tab`:
  set `cursor.bg`, then for each row `y0..y0+n-1`: `cursor.x=0; cursor.y=row;
  screen.draw(' ' * screen.columns)`; restore `cursor.x=0, cursor.y=y0`.
  `n = header(1 if tab 1) + title(1) + subtitle(1 if present)`. Compute *everything*
  (title, subtitle, status) **before** painting so `n` is known. Never paint more rows
  than you use (the spacing row must stay default-bg).
- **Rail**: `▌` in `accent` on every used row of the active tab; a space otherwise.
- **Icon column**: fixed 3 cells (`rail`, `glyph|space`, space). Agent glyph in brand
  colour (`as_rgb(brand)` active, `as_rgb(dim(brand))` inactive); non-agent tabs show
  no glyph.
- **Title**: `text` + bold for active, `muted` for inactive. Strip nothing else from the
  existing `_compact_title` logic.
- **Status dot** (right-aligned on line 1, one cell + 1 margin): `●` colour by state —
  unread output → `done`; agent working → `working`; agent waiting → `waiting`;
  none → nothing. (Words "working/waiting" stay in the subtitle in `faint`/state colour.)
- **Subtitle** (line 2): `<branch icon> branch` in `muted`, then `· N panes` (only if
  >1) in `faint`, then state word in its state colour. Branch icon `` is already
  used by `sidebar-kit.py` (Nerd Font symbol_map covers it).
- **Index**: right-aligned on line 2, `faint`, plain number (no colon). Do NOT remove —
  `ctrl+alt+1..9` jumps by it.
- **Header**: session name upper-cased, `faint`, bold off; `N tabs` right-aligned `muted`
  and, if any waiting agents in *this OS window's visible tabs*, `! K` in `waiting`.
  (Count waiting via the same `_agent_waiting` helper over `extra_data`? — not available;
  instead maintain a per-redraw counter: reset when `index == 1` in the measure pass and
  accumulate, or simply omit the waiting count and show only `N tabs` if that proves
  brittle. Prefer the simple version; note the choice in your report.)
- **Width/truncation**: every horizontal budget uses `screen.columns` and
  `wcswidth`; truncate with `…`; degenerate widths (< 8 cols) fall back to icon + rail only.
- **Horizontal mode** (`tab_bar_edge bottom/top`): keep current behaviour and layout;
  only the palette/`bg` reset changes from plan 002/this plan. Replace the permanent
  right-anchor `⚠` with `⚠ <provider> <pct>%` for the highest provider window ≥ 85%
  (extend `_usage_alert` to return `(provider, pct) | None`; data lives in
  `agent-usage.json` → `providers[].rows[].pct`; the provider name key is `providers[].name`
  — confirm by reading one file: `python3 -c "import json;print(json.load(open('$HOME/.local/state/kittymux/agent-usage.json'))['providers'][0].keys())"`).

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax | `python3 -m py_compile python/tab_bar.py` | exit 0 |
| Effective config | `kitty --debug-config 2>/dev/null \| grep -E "tab_title_max_lines\|tab_bar_edge"` | shows `tab_title_max_lines 3` (see Step 1) |
| Scratch kitty | see Step 5 | renders |
| Screenshot (needs display) | `grim -g "<x>,<y> <w>x<h>" out.png` | file written |

## Scope

**In scope**: `python/tab_bar.py`, `kittymux.conf`, `README.md` (screenshot/notes only if needed), `plans/README.md` status.

**Out of scope**:
- `python/sidebar-kit.py` (plan 004), `python/pane-state.py` (plan 005), status *semantics*
  (waiting/working heuristics stay as-is — plan 005 replaces them).
- The user's `~/.config/kitty/*` (never edit; if their `userprefs.conf` overrides
  `tab_title_max_lines`, report it instead).
- Adding a bar footer or hover effects — impossible with kitty's tab bar; deliberately not attempted.

## Git workflow

- Branch: `advisor/003-vertical-tab-bar`
- Commit per step; style e.g. `tab bar: repaint rows from theme tokens, session header row`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Allow 3-line tabs

In `kittymux.conf`, change `tab_title_max_lines 2` → `3` and update its comment
("session header + title + subtitle"). Heights are dynamic (cursor-based), so 2-line
tabs stay 2 lines.

**Verify**: `kitty --debug-config 2>/dev/null | grep tab_title_max_lines` → `3`. If it prints `2`, the user's
`userprefs.conf` (loaded later) overrides it — do not edit their file; note it in your report and, for the scratch
instance in Step 5, pass `-o tab_title_max_lines=3`.

### Step 2: Restructure `draw_tab` into compute → paint → draw (vertical only)

Refactor so a vertical draw does, in order: (a) resolve title/agent/branch/status data
(reuse existing helpers), (b) compute `n` rows, (c) `_paint_rows(screen, y0, n, bg)`
(helper: sets `cursor.bg`, repaints, restores cursor to `(0, y0)`), (d) draw header
(if `index == 1`), line 1, line 2 per the spec, (e) leave `cursor.y` on the last used
row, (f) end with `screen.cursor.bg = 0; screen.cursor.fg = 0; screen.cursor.bold = False`.
Remove the inline `[session] ` prefix from vertical mode only (horizontal keeps it).
Keep horizontal branch of the function functionally unchanged.

**Verify**: `python3 -m py_compile python/tab_bar.py` → exit 0.

### Step 3: Width-correct truncation

Replace `len()`-based width math in the vertical path with `wcswidth` (import from
`kitty.fast_data_types`). Add a small `_fit(text, width)` helper that truncates by
cells with `…`.

**Verify**: py_compile → exit 0; `grep -n "len(num)" python/tab_bar.py` → no remaining use in the vertical path.

### Step 4: Named usage alert (horizontal anchor)

Extend `_usage_alert()` to return `(provider, pct)` of the worst window ≥ 85 or `None`;
update `_draw_cwd_anchor` to render `⚠ claude 91%` in `alert` colour (adjust `text_w`
accounting). Keep the existing spawn/caching logic intact.

**Verify**: py_compile → exit 0.

### Step 5: Visual verification in a scratch kitty

Use a temporary `KITTY_CONFIG_DIRECTORY` as in plan 002 Step 6 (never the user's
config), with `-o tab_bar_edge=left -o tab_title_max_lines=3`, a session of 5 tabs
(one with 2 panes; two running processes whose argv0 is `claude`/`codex`, e.g.
`launch sh -c 'exec -a claude sleep 600'`; one in a git repo, one not; one long title).
Screenshot and confirm each acceptance item:

- [ ] no navy/foreign background anywhere; empty bar area equals the terminal background
- [ ] only the active tab has a fill; inactive rows have none; spacing rows stay blank
- [ ] accent rail spans all rows of the active tab
- [ ] header row is on its own line; tab 1 is NOT shifted right relative to the others
- [ ] status dot right-aligned with one cell margin; subtitle aligned under the title
- [ ] inactive agent icon is a dimmed brand colour (regression check for plan 001)
- [ ] resize the bar narrower/wider (change `tab_bar_min_width`-equivalent by resizing the OS window, or use
      `-o font_size=…`): no text bleeds past the edge; no wrap
- [ ] switch `tab_bar_edge` to `bottom` via `kitty @ --to unix:/tmp/kmx-t load-config --override tab_bar_edge=bottom`:
      horizontal bar still renders correctly, `⚠` (if any) names a provider
- [ ] repeat once with a light theme included instead of the gruvbox theme: still readable

Close the scratch instance: `kitty @ --to unix:/tmp/kmx-t close-window --match all`.

**Verify**: checklist complete; attach/describe screenshots. If no display is available, say so —
then only the compile gate is verified.

## Test plan

Kitty draw code is not unit-testable outside kitty; the acceptance checklist in Step 5 is the test.
If you factor out pure helpers (`_fit`), keep them free of kitty imports except `wcswidth` passed as a
parameter, and add `tests/test_tabbar_helpers.py` (unittest; structure as in `tests/test_theme.py`
from plan 002).

## Done criteria

- [ ] `python3 -m py_compile python/tab_bar.py` exits 0
- [ ] `grep -n "\[\" *$\|screen.draw(\"\[\")" python/tab_bar.py` shows the `[session]` prefix only inside the horizontal branch
- [ ] `grep -n "cursor.bg = 0" python/tab_bar.py` shows the end-of-`draw_tab` reset
- [ ] `grep -n "tab_title_max_lines" kittymux.conf` → `3`
- [ ] All Step 5 acceptance items confirmed (or the headless limitation reported)
- [ ] Only in-scope files modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

- Repainting rows with `screen.draw(' ' * screen.columns)` visibly wraps/scrolls the bar (DECAWM assumption wrong) —
  report; do not fall back to editing the user's colour options.
- Tab heights come out wrong (rows overlap, or the header pushes tab 1 to a height of 2 instead of 3) despite
  `tab_title_max_lines 3` — report the measured `cursor.y` values.
- The user's config overrides `tab_title_max_lines` and you cannot verify otherwise.
- Any step requires editing an out-of-scope file.

## Maintenance notes

- `draw_tab` runs twice per tab per redraw (measure + draw) and on every bar refresh —
  keep per-call work cached (`_git_anchor` has a 1s TTL cache; `_active_window_info`
  is uncached — consider caching by `(tab_id, window.id)` for 0.5s if profiling shows cost).
- If plan 005 lands, replace the status derivation in one place (a `_tab_status(tab_id)` helper you may
  introduce here) — keep the state → colour mapping in the theme tokens.
- Reviewer: check narrow-bar behaviour and wide-glyph (CJK/emoji) titles; confirm the `cursor.bg = 0` reset
  did not change horizontal mode (kitty already resets it there).
