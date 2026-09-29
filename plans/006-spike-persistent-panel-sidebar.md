# Plan 006 (SPIKE): Can the deck run as a persistent, docked `kitten panel` sidebar on Hyprland?

> **Executor instructions**: This is a **time-boxed investigation**, not a feature. Its deliverable is a
> written report (`plans/006-spike-report.md`) plus, only if the answer is "yes", a small unwired prototype
> script. Run every verification command and record actual output. If anything in "STOP conditions" occurs,
> stop and report. When done, update the status row in `plans/README.md` — unless a reviewer dispatched you and
> told you they maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8681a7d..HEAD -- python/sidebar-kit.py bin/`
> Plan 004 refactors `sidebar-kit.py` (and may add `python/kittymux_deck.py`) — it must be DONE first.

## Status

- **Priority**: P3
- **Effort**: M (spike; ≤ half a day)
- **Risk**: MED — briefly docks a layer-shell surface on the operator's *live* Hyprland session
- **Depends on**: plans/004-sidebar-deck-fixes-and-grouping.md
- **Category**: direction
- **Planned at**: commit `8681a7d`, 2026-09-29

## Why this matters

The deck (`ctrl+alt+b`) is a modal overlay; the closest thing to a cmux/shadcn *persistent* sidebar in kitty is
`kitten panel`, which draws a GPU-accelerated kitty surface docked to a screen edge and — on Wayland
compositors supporting wlr-layer-shell (Hyprland does) — can reserve screen space (exclusive zone) so tiled windows
shrink beside it. A docked panel showing *all* agent tabs across OS windows/workspaces (the user runs ~7 kitty OS
windows) would be always-visible, with real hover/click. But it is a different architecture (per-screen, not per-tab-bar),
so we need facts before committing to building it.

## Current state

- Doc facts (kitty 0.49 docs, https://sw.kovidgoyal.net/kitty/kittens/panel/): `kitten panel [options] [cmdline-to-run …]`;
  options include `--edge` (`background, bottom, center, center-sized, left, none, right, top`; default `top`),
  `--columns`, `--lines`, `--layer` (`background, bottom, overlay, top`; default `bottom`), `--margin-{top,left,bottom,right}`,
  `--override/-o`, `--config/-c`, `--listen-on`, and an `--exclusive-zone` option (Wayland only; docs note an override flag
  may be needed for an edge to respect it). Panels are controllable via remote control (show/hide/resize/launch).
  **Exact flag names/semantics must be read from `kitten panel --help` — do not trust this list.**
- `python/sidebar-kit.py` is a `kittens.tui` kitten using `kitten_ui(allow_remote_control=True)`: it obtains data via
  `main.remote_control(["ls"])`, which targets *the kitty it runs in*. A panel is a **separate kitty instance**, so the
  deck run inside a panel must talk to the *main* kitty's socket (`unix:/tmp/mykitty-<pid>`; scripts in this repo glob
  `/tmp/mykitty-*`), and jumps must focus windows in other kitty processes (and Hyprland workspaces —
  see `lib/mux.sh` `focus_hyprland_by_title`).
- Environment: Hyprland 0.56.2, kitty 0.49.1, `grim`/`hyprctl` available.

## Questions to answer (each needs an observed answer, not an assumption)

1. Does `kitten panel --edge=left --columns=36 <cmd>` run on this setup, and what does `<cmd>` need to be to run a python kitten
   (`kitten /path/sidebar-kit.py`? `kitty +kitten …`? a wrapper script)?
2. Is space reserved? With two tiled windows open, do they shrink when the panel appears (`hyprctl clients -j` sizes before/after)?
3. Layer/visibility: which workspaces show it (per-monitor, all workspaces?); does it appear above fullscreen windows; what
   `hyprctl layers` namespace does it have (for `layerrule`s)?
4. Input: does hover/click (`MouseTracking.full`) work in the panel? Keyboard focus policy — can it take keys on demand (e.g. via a
   Hyprland bind) and give them back?
5. Can the deck inside it read the **main** kitty (`ls`, `get-text`, `focus-window`) — via `KITTY_LISTEN_ON`/`--to` — including
   *other* kitty processes' sockets? Does `focus-window` across processes also switch the Hyprland workspace (needs `hyprctl dispatch`)?
6. Lifecycle: start/stop/toggle (`--single-instance`, remote `resize-os-window --action=toggle-visibility`, or kill/relaunch)?
   Resource cost: idle CPU of the panel process over 60 s (`ps -o %cpu,rss -p <pid>`).

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Panel help | `kitten panel --help` | full option list |
| Try a panel | `kitten panel --edge=left --columns=36 --layer=top --listen-on=unix:/tmp/kmx-panel <cmd> &` | surface appears at left edge |
| Layers | `hyprctl layers` | lists the panel's namespace/geometry |
| Window sizes | `hyprctl clients -j \| jq '.[] \| {class,at,size}'` | before/after comparison |
| Kill the panel | `kill <pid>` or `kitten @ --to unix:/tmp/kmx-panel close-window --match all` | surface disappears |

## Scope

**In scope**: `plans/006-spike-report.md` (create), and — **only if the spike says yes** — `bin/mux-panel` (create; **not** bound to any key).

**Out of scope**: `kittymux-keys.conf.tpl` (no keybinding), Hyprland config files (`~/.config/hypr/*` — propose `layerrule`s in the report, never edit),
`python/sidebar-kit.py` behaviour changes (list required changes in the report instead), any user config under `~/.config/kitty`.

## Git workflow

- Branch: `advisor/006-panel-spike`. Commit the report (and prototype if any): `spike: kitten panel sidebar findings`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 0: Ask before docking anything

This spike briefly changes the operator's live desktop (a docked surface; tiled windows may resize). **Confirm the operator is
present and agrees** before Step 2. If you cannot ask, do Step 1 only and mark the rest BLOCKED.

### Step 1: Read the real interface

Run `kitten panel --help`; save the exact option names for edge/columns/exclusive-zone/layer/focus/toggle in the report. Note the
`--exclusive-zone` requirements. **Verify**: report contains the verbatim relevant help lines.

### Step 2: Minimal panel with a trivial command

Start `kitten panel --edge=left --columns=36 --layer=top <flags for reserved space> sh -c 'echo hello; sleep 3600'`, then answer
Q2/Q3 with `hyprctl layers` and before/after `hyprctl clients -j` (screenshot with `grim` if useful). Kill it after.
**Verify**: raw command outputs pasted into the report.

### Step 3: Run the deck inside it

Start the panel with the deck as its command, with `KITTY_LISTEN_ON` (or the deck's `--to`) pointing at a scratch main kitty
(`kitty --class kmx-t --listen-on unix:/tmp/kmx-t …` with a few tabs). Answer Q1, Q4, Q5: does it render, does hover/click work
(`grim` screenshot + manual check by the operator), can it `focus-tab` in the main kitty? Record required changes to
`sidebar-kit.py` (e.g. accept `--to`, drop the modal quit-on-jump, handle multiple kitty sockets).
**Verify**: report has a per-question table: answer, evidence (command + output), confidence.

### Step 4: Lifecycle + cost

Answer Q6. Measure idle CPU/RSS over 60 s.
**Verify**: numbers in the report.

### Step 5: Verdict and (conditional) prototype

Write a **go / no-go / go-with-caveats** verdict with a coarse effort estimate for productionising (design sketch: which files
change, what state moves where). If go: add `bin/mux-panel` (start|stop|toggle) that wraps the working command from Step 3;
`bash -n` + `shellcheck -S warning` clean; not bound to a key.

**Verify**: `plans/006-spike-report.md` exists with all six questions answered; if `bin/mux-panel` exists: `bash -n bin/mux-panel` → 0.

## Test plan

Not applicable (investigation). The report is the artifact; every claim needs command output or a screenshot path.

## Done criteria

- [ ] `plans/006-spike-report.md` exists, answers Q1–Q6 with evidence, and ends with a verdict
- [ ] All panel processes started during the spike are stopped (`pgrep -af "kitten panel"` → none of yours)
- [ ] No files modified outside the scope list (`git status`); no Hyprland/kitty user config touched
- [ ] `plans/README.md` status row updated

## STOP conditions

- `kitten panel` doesn't start or crashes the operator's session — stop immediately, kill it, report.
- The operator hasn't approved docking a panel (Step 0).
- Answering a question would require editing Hyprland config or the user's kitty config — describe the needed change instead.
- Time-box exceeded (~half a day): write up what you know and stop.

## Maintenance notes

- If the verdict is "go", the production plan should reuse plan 004's `kittymux_deck.py` seam and be written as a new plan
  (do not extend this spike into a feature).
- Multi-instance reality: this repo globs `/tmp/mykitty-*` for sockets; a panel-based deck should share one helper for
  "enumerate kitty instances" rather than another glob (see `bin/mux-agents.sh`).
