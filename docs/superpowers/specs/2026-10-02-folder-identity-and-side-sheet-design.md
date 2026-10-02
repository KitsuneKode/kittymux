# Folder identity + hover side sheet — design

Status: draft for review · Branch: `folder-sheet` (worktree `.worktrees/folder-sheet`) · Date: 2026-10-02

## 1. Problem and intent

With many tabs, the vertical bar does not say **where** each tab is. A repo tab shows only its branch
(`tab_bar.py`, `_draw_vertical`: folder only when there is no branch); agent tabs often carry a custom
title ("Claude: refactor auth"); four tabs in four projects can read the same. UIs that hide the working
directory make window-hopping guesswork.

Success looks like: glancing at the bar, you can tell **which project** each tab is in, tell two
look-alike tabs apart, and — without leaving your current pane — peek at any tab in a partial side sheet
that is cheap, native-feeling and never steals focus unasked.

Said by the user: highlight the pwd name; a hover side sheet "like a web overlay but partial"; use kitty's
native facilities and the docs/source for performance and taste; include the per-project hue and the
duplicate-title disambiguation; make it good enough for the community.
Assumed (correct me): Wayland/Hyprland is the primary target for the floating sheet; the sheet's default
look is quiet; the per-project hue is on by default but easy to turn off.

## 2. What kitty gives us (verified against 0.49.2 source and docs)

| Facility | Finding | Use |
|---|---|---|
| Tab-bar hover | `TabManager.handle_tab_bar_mouse` has a motion branch (`button == -1`) that returns at once; AGENTS.md records that C sends the bar no idle motion. **Unverified** whether any idle motion reaches Python. | Probe P0-a decides whether hover can open the sheet. |
| `launch --type os-panel` / `kitten panel` | Layer-shell surface: `--edge`, `--layer overlay`, `--margin-*` (px), `--exclusive-zone` (+`--override-exclusive-zone`), `--focus-policy not-allowed\|on-demand\|exclusive`, `--hide-on-focus-loss`, `--single-instance`. Wayland only. | The sheet. `exclusive-zone 0`-style (no reserved space), `focus-policy not-allowed` for hover peeks. |
| Layer-shell margins | Relative to the **screen**, not to the kitty OS window. kitty does not know its window's screen position on Wayland. | Placement needs `hyprctl clients -j` (`at`, `size`); without it the sheet docks to the screen edge like `mux-panel`. Probe P0-b. |
| Pane title bars | `window_title_bar*` already in `kittymux.conf` (off). `window_title_template` and a `window_title_bar.py` `draw_window_title(data)` hook exist; `{custom}` exposes it. What `data` carries (cwd?) is **unverified**. | Folder per pane, same highlight as the bar. Probe P0-c. |
| OSC 7 / `current_cwd` | Already used (`_active_window_info`). | No change. |
| `tab_bar_filter`, `tab_activity_symbol` | Exist. | **Out of scope** (do not fix the pwd problem, add config surface). |

Options that exist only in newer kitty go through `kittymux_layout.gated_conf`, never `kittymux.conf`
(AGENTS.md). `window_title_template` follows that rule.

## 3. Scope (priority order, each phase shippable alone)

**P0 — probes (throwaway; output is an answer).** In an isolated Xvfb kitty with `KITTYMUX_SOCKET_DIRS` set
and the usual tripwire: (a) log `handle_tab_bar_mouse` motion under `xdotool mousemove` with no button;
(b) launch an os-panel and read where Hyprland places `margin-*` relative to a known window (manual on the
real compositor — Xvfb has no layer-shell, so this one is **manual and documented as such**); (c) dump
`draw_window_title(data)` keys; (d) time a cold `os-panel` kitten from launch to first paint (budget ≤ 150 ms). Results are written into `docs/compatibility.md` as verified / not.

**P1 — folder identity in the bar (the original ask).**
- New pure module `python/kittymux_place.py` (no kitty imports, unit-tested): given `kittymux_git.info(cwd)`,
  the tab's cleaned title and the available cells, returns ordered pieces
  `[(text, role)]`, roles `project | inner | branch | worktree`.
  Layout: ` project[:worktree]/inner  branch`. Shrink order: drop `branch`, then `inner`, then middle-truncate
  `project`; the project name is never dropped while ≥ 4 cells exist.
- If the title already equals the project name (shell/editor tabs: `zsh` → folder), the subtitle skips the
  folder and shows `inner  branch` instead (no duplicate words).
- Rendering in `tab_bar._draw_vertical`: `project` in `pal.text` (bold on the active tab, `pal.muted` on others),
  `inner` in `pal.faint`, `branch` in `pal.done` hue as the horizontal bar does. Outside a repo: `short_path`
  as now. State words / pending question / `⚠` keep their current priority (reserve-room logic unchanged).
- Rail (compact): tab number takes the project hue (see below); no extra text.

**P1b — stable per-project hue.** `kittymux_theme.project_hue(name, accent, bg)`: SHA-1 of the project name
(not Python `hash`, which is salted per process) → one of 12 hue slots; rotate the **live accent's** hue,
keep its saturation/lightness, then nudge lightness until contrast against the row background ≥ 4.5:1.
No palette literals — it follows theme changes. Used for: the folder glyph (always), the project name (active tab
and any tab in a title collision), the rail number. Redundant with the text, never the only cue.
Off switch: `hue-off` flag file / `KITTYMUX_HUE=off`, listed in the README with the other off switches.
Decided: default on (see 3d).

**P1c — duplicate-title disambiguation.** A `@_per_pass` helper computes the set of cleaned titles shared by
2+ tabs of the OS window once per pass. Colliding tabs get the project name emphasised (bold + hue) on every
tab, not only the active one. No extra rows, no title rewriting.

**P2 — the side sheet (approach B).**
- Pure `python/kittymux_sheet.py` builds the card model from data we already publish: the merged verdict
  (`kittymux_agents.load_panes/merge_scan` → `resolve_status`, with its `why`), `kittymux_git`, the changes
  summary (`kittymux_changes`), the pane map. `peek-kit.py` keeps rendering (fallback overlay on X11) from the same model, so
  the two cannot drift.
- Card content: project/branch/worktree, agent + state with age and **why**, what it is waiting for, what it
  changed (done tabs), pane map, last ~12 screen lines. Screen text is read live via one
  `kitty @ get-text` for the shown tab and never stored (AGENTS.md: never log screen text).
- Window: `kitty @ launch --type os-panel` (`edge=left`, `layer=overlay`, exclusive zone 0 / not reserved,
  `focus-policy=not-allowed` when hover-opened, `on-demand` when opened by key/click so Esc/arrows work), margins from
  `hyprctl clients -j` + the tab's row geometry; fallback: screen-edge dock. Opened by the existing
  right-click and a new chord (chord must pass the checks in AGENTS.md: ours, `kittymux.conf`, the user's confs,
  `hyprctl binds`, real key events). ↑/↓ walks tabs and the sheet follows; Enter jumps (to the asking pane first);
  Esc/q/click-outside closes in **one** keypress (`select`/`os.read`, lone ESC = Escape).
- Lifecycle state in `sys.modules["_kittymux_sheet_rt"]`; no timer while closed; at most one `get-text` per
  second while open; never opens or moves focus on its own.

**P3 — hover (approach C's enhancement).** Only if P0-a shows motion reaches Python: a trailing-timer dwell
(~400 ms on the same tab) opens the sheet; leaving bar + sheet for ~300 ms closes it. If P0-a fails, hover is
simply not offered on the bar (it still works inside the sheet and the docked panel) and the docs say so.
No `hyprctl cursorpos` polling.

**P4 — pane title bars (best effort, gated on P0-c).** `window_title_bar.py` returns `project/inner  branch`
with the same highlight when `data` gives enough to resolve it; otherwise the title template stays kitty's
default. Bars remain off by default (`ctrl+alt+shift+w` shows them), so this only improves what you see on demand.

**P5 — community polish.** README before/after shots made with `kittymux screenshot`; `kittymux demo` gains
two same-named-project tabs so the disambiguation is visible on first run; `docs/sheet.md`; `docs/compatibility.md`
rows marked verified / unverified honestly; CHANGELOG; `kittymux doctor` reports layer-shell support, `hyprctl`
presence and the chosen chord; keymap overlay entry via the `# key — description` comment; README key table and
`kittymux-keys.conf.tpl` changed in one commit.

## 3b. UI perspective (the rules the pieces above are drawn by)

1. **One emphasis per row.** In the subtitle the project name is the only bold/bright element; inner path and branch
   step down (`text` → `faint`), state words keep their own hue. Today the branch, pane map, state and `⚠` can all
   compete.
2. **Same grammar everywhere.** `project[:worktree]/inner  branch` reads identically in the bar, the sheet's header,
   the pane title bar and the horizontal anchor (`kittymux_git.label`). One function builds it; four surfaces render it.
3. **Calm by default, loud only for you.** Needs-you keeps its stripe/colour; the hue and folder never use the
   alert/waiting colours, so attention cues stay unambiguous.
4. **Rhythm and alignment.** Subtitle starts at the title's column (3), index right-aligned as now; the sheet's rows
   share one left edge and one separator character; no new box-drawing frames inside the sheet (it is a surface, not a dialog).
5. **Motion restraint.** The sheet appears and disappears without animation; the only moving thing stays the existing spinner.
6. **Accessible.** Contrast ≥ 4.5:1 for every text role on every theme tested; colour is never the only carrier of meaning.
7. **Verified by looking.** Before/after screenshots (`kittymux screenshot`, Xvfb) for dark and light themes with 4, 12 and 23
   tabs and at bar widths 12 (rail), 24, 32, 40 — reviewed before each phase merges, not only unit-tested.

## 3c. Pluggable by design (use only the parts you want)

Nothing here is all-or-nothing. Each capability is an independent **feature** with its own off switch, and turning
one off must leave the others working and today's behaviour intact.

| Feature | What it controls | Default |
|---|---|---|
| `folder` | project/branch subtitle (P1) | on |
| `hue` | per-project colour (P1b) | on (open decision) |
| `collide` | emphasis on look-alike tabs (P1c) | on |
| `sheet` | the side sheet, click/chord/keys (P2) | on |
| `hover` | hover-to-open (P3; only exists if the probe passes) | off (opt-in) |
| `panetitle` | folder in pane title bars (P4) | off (bars are off anyway) |

- One pure module, `python/kittymux_features.py`: precedence **env var > flag file in `$KITTYMUX_STATE` > default**,
  the same off-switch convention the README already documents (`notify-off`, `KITTYMUX_NOTIFY`, …). Resolved once per
  draw pass through `@_per_pass` — no per-tab file reads.
- Presets for people who want little or lots: `minimal` (folder only), `default`, `full` (everything including hover).
  `kittymux features` lists the state; `kittymux features on|off <name>` and `kittymux features preset <name>` flip it;
  `kittymux doctor` prints the same table. Changes apply on the next reload (no restart).
- Modules stay separable: `kittymux_place` (folder/collide), `kittymux_theme.project_hue`, `kittymux_sheet` +
  `sheet-kit.py`/`peek-kit.py`, `window_title_bar.py` have no import of each other; `tab_bar.py` is the only integrator.
  Someone who copies just `kittymux_place.py` into their own `tab_bar.py` gets the folder line and nothing else.
- Guarantee, tested: with every feature off the bar renders exactly as it does today (golden comparison against the
  current subtitle builder), and each feature on its own passes the same checks.
- Docs: a short "Pick what you want" section in the README with the three presets and the one-line commands.

## 3d. Decisions (delegated by the user, 2026-10-02)

1. **Hue: on by default, restrained.** Premium here means quiet and consistent (the t3code lineage already used for the
   status hues): the hue colours only the folder glyph, the project name on the active tab / on a collision, and the rail
   number — never fills, borders or stripes. Hue steps are spaced so neighbours differ in more than colour: bold/dim,
   position and the text itself carry the meaning, so it holds for colour-blind users and in a monochrome theme. The hue is
   skipped (accent used as-is) when the theme leaves too little lightness range to reach 4.5:1. `hue` stays one switch away.
2. **Sheet: spawned on demand, placed once.** One `hyprctl clients -j` call when it opens (no polling), geometry cached for
   that open; the kitten redraws only when the card model's hash changes. Open-to-first-paint budget **≤ 150 ms** measured in
   P0 (probe d); if the cold kitten start misses it, a resident hidden panel (`--single-instance`) is evaluated and chosen only
   if its idle cost is measured and acceptable. Closed = no process, no timer. This matches how kitty itself works: panels are
   separate layer-shell surfaces, the tab bar stays a cheap cell grid.
3. **Premium polish, concretely:** tabular alignment of ages/counts, one hit-target height for every clickable row, hover and
   keyboard-selected rows share one style, the focus ring is the same accent as the bar's rail, empty and error states have
   copy (no blank card), long names truncate in the middle so both ends stay readable, and the sheet reads the same in
   light and dark themes. Keyboard only works end to end (open, walk, jump, close); everything has a visible label in the keymap overlay.

## 3e. Early probe answers (dry run, Xvfb, kitty 0.49.2 — re-recorded by plan Task 9)

- **P0-a:** idle mouse motion over the tab bar does **not** reach Python (0 of 8 moves; only press/release arrive). Hover cannot be
  triggered from the bar. **P3 narrows to hover inside the sheet and the docked panel**; the bar itself opens the sheet by click or key.
- **P0-c:** `draw_window_title` receives `WindowTitleData(has_activity_since_last_focus, is_active, needs_attention, tab_id, title, window_id)`.
  There is no cwd, but `window_id` resolves it (`get_boss().window_id_map[window_id].child.current_cwd`) → **P4 is feasible**.
- **P0-b / P0-d** (layer-shell placement, panel start time) need Hyprland and are still to be run by hand (`tests/probe_panel.sh`).

## 4. Non-goals

Per-tab text rewriting of titles; new icon-font glyphs (a running kitty would need a restart — AGENTS.md); a hover
resize cursor over the bar (kitty forces a hand there); X11 floating sheet; touching `tab_bar_filter`/activity symbols;
any default-on shader/look beyond the hue.

## 5. Performance budget and rules honoured

- Draw path: the new work is two `@_per_pass` lookups (place pieces, collision set) plus a cached hue per project
  name. No per-tab `os.stat`, file read or subprocess. Budget: draw_tab p50 within +0.05 ms of today at 23 tabs,
  measured with the existing `KITTYMUX_PROFILE` hook before and after (numbers go in the commit message).
- Sheet: zero cost when closed; ≤ 1 `get-text`/s while open; reads `scan-<pid>.json` and the panes journal instead of
  running `kitty @ ls` every second (verify the tab→window mapping is in `panes-<pid>.json`; if not, keep one `ls`).
- No hardcoded palettes; no module-level timers (runtime state in `sys.modules`); redraw via
  `kittymux_scan.refresh_bar`; helper modules reload on every config load; every new suppression/outcome has a static `why`.
- Never restart live kitties; apply to live by `kittymux upgrade` only; record `kitty @ ls` window counts before/after.

## 6. Testing

- Unit (`tests/`): `kittymux_place` (repo, worktree, nested, non-repo, title==project, widths 4..40, wide chars);
  `project_hue` (deterministic across processes, 12 slots, contrast ≥ 4.5 on light and dark themes, follows accent);
  collision set; sheet card model; one-key close parser.
- Real-kitty smoke (Xvfb, private config/socket, SKIP if tools missing, tripwire on every other kitty):
  `smoke_place.sh` (two same-title tabs in different repos render distinguishable subtitles — verified by pixels/
  `get-text` of the rendered bar), `smoke_sheet.sh` (fallback overlay path, one Esc closes, chord does not stack),
  and the P0 motion probe kept as a regression check if it passes.
- **Manual only, stated as such in `docs/testing.md`:** os-panel placement and layer-shell behaviour on Hyprland. An Xvfb
  run is never reported as compositor verification.
- `kittymux_features`: precedence (env > flag > default), presets, unknown names rejected, every on/off combination
  (2^6) renders without error, all-off equals today's output.
- Existing suites (`unittest discover`, `test_mux_status.sh`, `test_socket_lib.sh`, `smoke_state/click/sidebar/…`) stay green.

## 7. Risks

1. Layer-shell margins are screen-relative and kitty cannot see its own position → sheet placement depends on
   `hyprctl`; fallback is a screen-edge dock (still useful, less pretty).
2. Idle motion may never reach Python → hover is an enhancement, not the design's foundation (hence approach C).
3. `window_title_bar.py` `data` may lack the cwd → P4 may shrink to "unchanged" and be dropped without affecting P1–P3.
4. A hue-per-project can read as noise → it is subtle (glyph + name), accessible (text carries the meaning) and off with one switch.

## 8. Rollout

Work in `.worktrees/folder-sheet`; merge to `main` per phase (P1 first); apply by `kittymux upgrade`
(reload twice + doctor). Nothing leaves `main` half-edited.
