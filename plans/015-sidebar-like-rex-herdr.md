# 015: The sidebar, the pane header and the states — what to take from Rex and herdr

Status: proposed 2026-11-11. Direction A chosen by the owner (grouped, one line per tab).
References: Rex (owner's screenshots, 2026-11-11), herdr (T3 thread 7c17e021 attachment),
loading.dev (calm, single-purpose indicators). Rules: `.claude/skills/kittymux-ui/SKILL.md`.

Not a Rex clone. Rex is a whole terminal (its own window chrome, tab bar, floating and
minimised panes). kittymux lives inside kitty, so it takes what kitty can draw well: the
sidebar, the pane header, the states, and one notification ladder. Everything reads as one
interface: the same glyphs, words and colours in the bar, the pane header, the panel, the
desktop popup and the kuwai island.

## 1. What to take, and what not

| Rex / herdr does | kittymux | Why |
|---|---|---|
| Sidebar grouped by session/space, small muted headers | **Take** (bar, direction A) | The repeated place line on every tab becomes one group header |
| One line per item: icon, name, quiet meta on the right | **Take** | Twice the tabs on screen; state reads first |
| Active row as a soft pill | **Have** (card / shader) | Keep, one step quieter on hover |
| `•••` on a row that has news, "Needs you" chip | **Take**, as the state glyph and the needs-you line | One meaning per mark |
| App icons for plain programs (Neovim `N`, pnpm, zsh `>_`) | **Take** with Nerd Font glyphs, muted | Plain tabs stop all looking the same |
| Agent logos | **Have**; monochrome muted unless active or needs you | Colour stays for state |
| Pane header: icon, title, path, controls on the right | **Take the header**; controls only if kitty delivers clicks there (spike first) | kitty's title bar is drawn by `window_title_bar.py`; click routing is unproven |
| Window chrome, top tab strip | **Leave** | kitty and Hyprland own those |
| Floating panes, minimised pane chip | **Leave in kitty**; offer the chip in kuwai instead (§5) | kitty has no floating panes; Hyprland windows do |
| Live simulators, video in panes | **Leave** | Not a multiplexer's job here |

## 2. The bar (direction A)

```
 archlinux                         «      header: host, collapse
 1 needs you · 2 working · 7 tabs          counts in words, state colours

 R rice   feat/assistant…                  group: hue letter, project, branch (faint)
   ◐ Fix notch alerts            3m        working: turning circle, age
   ! Review findings             1m        needs you: bold !, waiting colour, stripe
     Allow edit to Notifs.qml?             the question, only for needs you
   ✓ Merge state-first          12m        done (unseen): check, clears when looked at
   N notes.md                              plain program: its glyph, no state

 K kittymux   main
   ◐ Bar redesign                1m

 ~ home
   >_ zsh
```

Row anatomy (cells): 2-cell indent · state or program glyph · 1 space · title (primary;
bold when active or needs you) · age right-aligned (faint) · tab number only on the active
row. Group header: hue letter in a 1-cell chip · project (muted, bold) · branch (faint,
middle-ellipsis). One blank line between groups, none between rows.

Order: groups with something that needs you first, then by most recent activity; inside a
group, needs you, working, done, the rest. A group with only settled tabs collapses to its
header after 6 (`+4 more`, click to open).

States (one glyph each, readable without colour): starting `○` faint "starting…",
working `◐◓◑◒` (one step per 3 s), needs you `!`, limited `◷` "back in 42m", error `✕`,
done `✓`, plain program = its glyph. Stale data: the header says "usage · 5m ago" once.

Interactions: click a row → jump; click a group header → collapse/expand; right-click a
row → the existing menu (mute, close). Keyboard: unchanged (`g` regroups in the panel).

## 3. Loading, the loading.dev way

One indicator per meaning, never decoration: the stepping circle for "an agent is working",
a faint `starting…` before the first scan, `restoring` rows while a session restores. No
spinners anywhere else; progress (OSC 9;4) stays the hairline with its percent. Reduced
motion: the still first frame.

## 4. Edge cases to test (all in the all-states rig, dark and light)

16-column rail (groups collapse to their letter chips, rows to glyphs) · a 60-character
title · two tabs of the same repo (twins) · a worktree · no git · the home folder ·
ssh/remote tab · root shell · 40 tabs (collapsing, scroll) · a muted agent · an agent
that needs you in a background split (the tab shows `!`, the pane is ringed) · OSC
progress, paused and failed · a restored session · the light theme · no colour (glyphs
only) · a font without the circle glyphs (falls back to `*`).

## 5. In the kuwai island (rice), not kitty

- Minimised windows as a chip, Rex-style: Hyprland `special:minimized` windows show as a
  pill in the resting notch; click restores. (Super+M to minimise.)
- The island's agent rings and alerts use the same glyphs and words as the bar.

## 6. Pruning

Keep: the bar (A), the panel (cells, with Usage and Inbox) and its pixel mode (the rich
view; it hides the bar while docked). Retire: the Quickshell client (`client/`), which
duplicates the pixel panel as a separate window. Owner to confirm.

## 7. Order of work

1. The all-states rig (`tests/shot_states.sh`): every state and edge case above, dark and
   light, wide and rail. The before picture.
2. The bar's grouped one-line rows (tab_bar.py), behind `kittymux features on groups` until
   the rig and the unit tests pass, then on by default.
3. Program glyphs for plain tabs (a small map: nvim, vim, hx, pnpm, npm, bun, node, python,
   git/lazygit, ssh, htop/btop, zsh/bash/fish).
4. The pane header restyle to match; the controls spike.
5. Retire the client (if confirmed). Docs, CHANGELOG, README table.
