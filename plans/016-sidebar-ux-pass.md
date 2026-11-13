# 016: The pixel sidebar, made to work like a product — clicks, keys, readability

Status: proposed 2026-11-12, from the owner's live use of the pixel tab bar (pxbar on, Hyprland, DP-3 at 1×, eDP-1 at 1.33×).
Progress (2026-11-13; check `git log main` before trusting this line):
- DONE, merged and live: §0 clicks/drag (#26), §1 tab navigation follows the bar (#27), §3 the × in the end mark's slot and the
  rail expand button and tiles (#30, part of §5), §4 type scales with the terminal font (#30), §8 the 14 duplicate chords retired
  with leader mode and doctor naming working twins (#34, #38), §9 answer / plain-text questions / account (#31, #32, #33), the
  hook-less quoted-prompt false alarm for Antigravity and OpenCode (#35). Seen on the real compositor at 1.33× on 2026-11-13
  (private test kitty on eDP-1): rows, groups, needs-you with its question, progress and the wave all draw cleanly.
- OPEN: §2 a working row says what it is doing (still "Working"); §4 pixel snapping at 1× (not yet looked at on DP-3); §5 a
  narrower rail; §6 glass (the bar is near opaque); §7 the wheel over the bar; §8 the keys sheet by families.
- §9 left: Cursor's quoted-prompt false alarm is real (a finished reply quoting "Do you want to proceed? (y/n)" reads as
  waiting). Its idle line is "→ Add a follow-up" (working: the same line plus "ctrl+c to stop", captured 2026-11-13), but it
  can only become an idle-only marker once Cursor's approval prompt is captured: the owner's Cursor CLI is in Run Everything,
  so it never asks. The OpenCode 2 plugin is draft #43 (OpenCode 2 runs plugins in one shared server; needs per-pane routing).
Continues plan 015. Rules: `.claude/skills/kittymux-ui/SKILL.md`. Reference look: the owner's mockup artifact
("kittymux sidebar", claude.ai/artifact/WQjhjqXKGCic6GALD4aHXu; a copy is `~/Downloads/kittymux sidebar.html`).

The owner's words, in order of pain: clicks do not open the tab; ctrl+tab lags, lands on hidden tabs and walks a different
order from the bar; the × is too large; the rail wastes space and has no way back; the text is small and soft beside the
terminal; clicking a session does not show what is going on; the shortcuts feel annoying and worthless.

## 0. Done before this plan

- **Clicks and drag and drop** (PR #26): kitty kept the hooks from its first load; every reload now rebuilds them
  (`kittymux_barsize._hook`). Live after `kittymux upgrade`, no restart. Verify drag and drop by hand after it lands.
- **Neovim scrollback in Claude tabs**: `"tui": "fullscreen"` removed from `~/.claude/settings.json` (owner's choice): the
  fullscreen renderer draws on the alternate screen, which keeps no history. New Claude sessions only.
- **Scrollback cap**: `scrollback_pager_history_size 16` in the owner's userprefs (kitty-scrollback.nvim keeps 100,000 lines).

## 1. Tab navigation follows the bar

- `ctrl+tab` / `ctrl+shift+tab` walk the rows **in the order the bar draws them** (groups, then rows), not kitty's tab order.
  An in-process kitten (`result_handler(no_ui=True)`) reads the last drawn order from `_kittymux_pxbar_rt` (or computes
  `kittymux_groups` the same way) and focuses the next tab. Fallback without the pixel bar: kitty's `next_tab`.
- **Never land on a tab you cannot see:** the group holding the active tab never folds (check `kittymux_groups`), and a
  scrolled-out active row scrolls into view (already true; test it with ctrl+tab).
- **The highlight moves with the key:** measure key → picture swap latency in a rig (xdotool key, probe the picture's
  active row); the target is the next frame. If the picture waits for kitty's tab bar redraw, mark it dirty on tab change.
- Keep `shift+left/right` session-scoped, documented as such. Tests: unit (order walk, wrap, folded groups), rig with real keys.

## 2. A click shows what is going on

- The second line of a working row says what it is doing, not just `Working · 6m`: the scanner's latest activity line
  (Claude's `Verb… (6m 52s)`, a tool name, the file it edits), bounded and cleaned, never raw screen text in logs.
- Clicking the row you are already on, or a right click, opens peek (exists: right click) with the question, last output
  lines and the diff summary. Make it discoverable: the footer keys sheet and README say so.
- Press feedback on pointer-down (the row's pressed state, instant), activation on release (kitty's rule; keep it).

## 3. The row end: one slot, one thing

- The × replaces the end mark **in the same slot** (the mockup's `.end > *` grid cell): the wave/age/dot fades out under
  the pointer, the × fades in. Today two shaders place them differently (hover shader cy = top − 15 px, the wave at
  top + 10): give both one constant from `kittymux_barpx` (the title line's centre) and test the geometry in
  `test_pxbar` (the shader source is read there already).
- The × is 10 px, stroke 1.6, muted colour, brightening only when its own 20 px square is hovered. Rail: no ×.

## 4. Size and sharpness at 1×

- **Type scale follows the terminal font:** the bar's sizes (13 px title, 11 px meta) are fixed today and read small beside a
  15 px terminal font. Scale them from kitty's cell height (one ratio, clamped), so the bar matches whatever font the owner
  uses. Row heights, tiles and the header follow the same ratio.
- **Pixel snapping at integer scales:** at 1× the marks and the wave are soft. Snap tile rects, rules and wave bars to device
  pixels, render icons at an integer size, use hinting for the small text (pango font options) at 1×.
- Check every picture at 1× AND 1.33×, dark and light (shot_states at both scales; the live-test kitty on eDP-1 and DP-3).

## 5. The rail

- Narrower: kitty sizes a custom bar from what `draw_tab` draws (`tab_title_max_length` + measured decorations, 9 columns
  at the minimum). Find the smallest the compact draw allows (target ~48 px logical, the mockup), without breaking the cell
  bar's rail (`smoke_sidebar`).
- A visible expand button (the header's sidebar icon, as in the wide bar), not only the mascot tile.
- Tiles evenly sized and spaced (34 px rows, 28 px tiles), state dots one size, progress under the tile.

## 6. Glass and depth

- The mockup: panel at 78 % over a blur, a hairline edge, a soft shadow; the terminal a card. Today the bar is close to
  opaque at `background_opacity 0.85`. Tune `glass_alpha`/`material_alpha` against the owner's wallpaper on the real
  screen; never more transparent than legible (check contrast of muted/faint text over the brightest wallpaper patch).

## 7. Mouse

- Wheel over the bar scrolls the rows (pages today only by the ↑/↓ bands).
- Hover is instant (no fade on high-frequency surfaces), spans the whole row, one step under active; the pointer stays
  the hand kitty uses over the bar.

## 8. Shortcuts: fewer, memorable, all alive

Inventory first (`kittymux keys`, 137 maps in kittymux-keys.conf + kitty defaults + userprefs), then a proposal the owner
approves BEFORE any key changes:
- One family per intent, like the owner's Neovim keys (`ctrl+shift+h/g/f`): tabs and sessions, panes, agents, overlays.
- Remove the dead ones: `ctrl+alt+e` → kitty's own `ctrl+shift+f7` (number the panes), `ctrl+alt+shift+w` →
  `ctrl+shift+q` (close tab, exists). Hyprland takes both first.
- Every chord checked against the template, kittymux.conf, the owner's confs and `hyprctl binds -j` (doctor), tried with real
  key events (`smoke_keys`, `smoke_spawn`), README key table and template in one commit (AGENTS.md "Keys").
- The keys sheet overlay shows the families, not 137 rows.

## 9. Queued, decided by the owner

- `kittymux answer <key> allow|deny|text` for the rice notch: re-read the pane, refuse if the prompt changed (owner: yes).
- A question asked in plain text at the end of a turn reads as "needs you" (owner: yes). This changes the contract's
  "a plain question is done": positive evidence only (the last reply's last paragraph ends with "?", the composer idle),
  never silence. Update `status-contract.md`; test with real captures.
- `account` on each agents.json row (rice asked): "" for the default config dir, else a label from `CLAUDE_CONFIG_DIR`'s
  basename (".claude_personal" → "personal"), `CODEX_HOME` likewise; read from `/proc/<fg pid>/environ`, never log values.
- False "needs you" for hook-less agents when a finished reply contains dialog-footer words: an idle-composer marker per
  agent (Antigravity: `? for shortcuts`; capture Cursor's and OpenCode's idle screens first).
- Capture Cursor Agent's real command-approval prompt (the last capture stalled on "Trusting workspace…").

## Verify (each part)

Test first where a test can see it; rigs never touch another kitty; pictures at 1× and 1.33×, dark and light, wide and rail,
read before and after; `kittymux upgrade` on the live kitty with window counts before/after; say what was not verified.
