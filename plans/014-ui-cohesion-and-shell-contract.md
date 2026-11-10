# Plan 014: One look across kittymux, and a live contract for the desktop shell

> **Executor instructions**: read the whole plan first. Phases are independent
> enough to ship one at a time; do them in order unless told otherwise. Honour
> the STOP conditions. Update `plans/README.md` when a phase is done.
>
> **Drift check (run first)**: `git status --short` must be clean except for
> files you own. On 2026-11-05 this tree had uncommitted edits to `README.md`,
> `kittymux.conf`, `kittymux-keys.conf.tpl`, `python/kittymux_wmfocus.py` and
> `tests/test_wmfocus.py` from another session: get them committed (or ask)
> before you start. Then `git log --oneline -15` to see what the bar work
> (cards, session folders, OSC 9;4 progress, OSC 7501 relay) already changed.

## Status

- **Priority**: P1 (look), P1 (contract), P2 (panel restyle)
- **Effort**: M per phase
- **Risk**: MED (the tab bar is always on screen; the contract has a consumer)
- **Written**: 2026-11-05, from the rice shell side (~/Projects/rice), which
  reads kittymux's state for its island and Agents tab.

## Why this matters

kittymux now has a lot of surface (vertical bar, deck, docked panel with
Agents / Usage / Inbox, peek card, leader card, attention queue, usage HUD)
and it is drawn in two places: inside kitty (character cells) and, on this
machine, in the rice desktop shell (Quickshell/QML: the island and the
Notification Center's Agents tab). The two read the same data but don't
share a look or a live feed:

1. **One accent does everything.** In the panel shots (site/public/assets/
   shots/panel-*-dark.png, 2026-10-08) pink marks the active view pill, the
   Jump button, the left bars, the session heading and the usage bars. The
   state colours (yellow waiting · blue working · green done · red limit, each
   with its own glyph) are good and should be the only loud colours.
2. **Rows speak at one volume.** Ports, pane counts and branch sit at the
   same weight as "needs you 4m".
3. **Icon-only view pills.** Grid, pie and envelope are hard to tell apart;
   only the active one has a label.
4. **Missing data looks broken.** Providers without data in Usage are rows of
   dashes.
5. **The shell has to poll and parse.** There is no live "who is working"
   file; the shell runs `kittymux pick --json` every 20 s (160 ms each) and
   splits `text` on runs of two spaces to recover agent / title / cwd /
   status. Any change to that menu text breaks the island.

## Current state (facts, 2026-11-05)

### What the shell reads today (rice: `shell/services/Kittymux.qml`)

| Source | Use | Notes |
|---|---|---|
| `$STATE/inbox-snapshot.json` (watched) | moments: "Claude · Needs you", "Done", "Hit a limit"; Agents tab | good: atomic, has `id, t, kind, severity, agent, tab, title, body, status` |
| `kittymux pick --json` (every 20 s; every 4 s while the Agents tab shows) | running agents for the island's agent stack | parsed from menu `text`; `tone === "active"` means working |
| `kittymux act JSON` | jump from the island | fine |
| `kittymux inbox ack ID` | mark read | fine |
| `agent-usage.json` | usage card | fine |
| brand marks | `shell/assets/brands/*.svg` (copies of kittymux assets) | mapping lives in the shell (`brands` table) |

The island also has `modules/island/AgentStack.qml` (up to three stacked
marks, "+N", needs-you first, a chooser) built by the island session.

### Problems seen on the machine

- **No live running-agents feed** (above). `agent-sessions.json` is a
  journal (records with `state`, `work_since`, `last`, `open`) and is only
  rewritten now and then; `panes-<pid>.json` / `scan-<pid>.json` were `{}`
  for two of three kitty instances while agents ran. Neither is usable as
  "who is working right now".
- **`cli-errors.log`**: bursts of `workflow find-session: ValueError: kitty
  snapshot unavailable` (2026-11-02 14:26, eight in four seconds). A caller
  retries in a tight loop when the snapshot fails; it should back off and
  say once.
- **Prompt events look like agents.** A `sudo` password prompt arrives as
  `kind: permission, agent: "sudo", severity: needs-you`, and the island said
  "Sudo · Needs you" with an agent glyph. Consumers can't tell a tool prompt
  from an agent waiting.
- **Docs screenshots are a month old** (2026-10-08); the bar has changed
  since (inset card for the active tab, session folders, progress fill).

## Goals

1. kittymux's own UI (bar, deck, panel, peek) and the shell share one set of
   colour roles and one hierarchy.
2. The shell gets a live, versioned, documented snapshot of agents, so it
   never parses menu text or polls.
3. Each surface has one home on a machine that runs both: kittymux owns
   what lives inside kitty; the desktop shell owns the desktop overview. The
   docked panel stays first-class for people without the shell.

## Design direction

### Colour roles (derive from the kitty theme, as plan 002 does)

| Role | Use | Never |
|---|---|---|
| **accent** | selection and focus only: the active view pill, the selected row, a focus ring | buttons, bars, headings, charts |
| **state: waiting** (yellow/orange, ◆ / !) | needs you, permission, a question | decoration |
| **state: working** (blue, ◐) | a running turn | idle |
| **state: done** (green, ✓) | finished since you looked | anything else |
| **state: limit / error** (red, ⊘) | usage limit, crash | warnings that aren't blocking |
| **project tint** | a calm hue per project, low chroma, kept clear of the state hues | text you must read |
| **text** primary / secondary / tertiary | titles / meta / hints | |

Buttons are neutral (a surface one step lighter), the primary action in a
card can be text-primary on that surface; charts use the state colour of
what they measure or a neutral.

### Hierarchy

- **A tab row: two lines at most.** Line 1: mark, title, state glyph. Line 2:
  the state in words when there is one ("needs you · 4m", "done · 3m",
  "resets in 42m"), else the folder or branch. Ports, pane counts and PR
  numbers move to the peek card and the selected row.
- **The summary line stays** ("7 tabs · ! 2 need you · 2 working"): it's the
  best thing on the panel.
- **View pills get labels** ("Agents", "Usage", "Inbox") or at least a
  label on hover/selection; the counts sit after the label.
- **Unavailable data** says so once: "not connected" in tertiary text, no
  dashed placeholder bars.
- **Inbox cards** keep Jump and Dismiss; Jump becomes the neutral primary
  (not the accent).

### Options to decide (recommendation first)

1. **Where the overview lives on a machine with the shell**: the shell's
   Agents tab (recommended: real type, icons, motion, reachable from any app)
   vs. the docked panel (keep for non-shell users) vs. both equally.
2. **Live feed format**: a snapshot file rewritten atomically on change
   (recommended: same pattern as `inbox-snapshot.json`, trivially watched,
   no daemon) vs. a socket (more moving parts) vs. D-Bus signals.
3. **Who maps agent → brand mark**: kittymux puts a `brand` key in the
   snapshot (recommended: one table) vs. each consumer keeps its own.

## Phase 1: colour roles and hierarchy (the cheapest big win)

1. Add the roles above to the shared token module (plan 002's module);
   replace every direct use of the accent outside selection/focus.
2. Tab rows: two lines, state first; move ports / pane counts / PR to peek
   and the selected row.
3. Panel: labelled view pills; neutral buttons; "not connected" instead of
   dashes; charts in state or neutral colours.
4. Regenerate the docs shots (`kittymux demo` + `kittymux screenshot`),
   dark and light.

**Verify**: the existing bar/deck/panel tests; screenshots at the narrow
and wide bar widths; a colour-blind check (state readable by glyph alone).

## Phase 2: `agents.json`, a live snapshot for other surfaces

Write `$STATE/agents.json` atomically (tmp + rename) whenever an agent's
state changes (the scanner and hooks already know: OSC 7501, Claude hooks,
the screen scan), and on start-up. Shape:

```json
{
  "version": 1,
  "t": 1793780793.0,
  "agents": [
    {
      "key": "w4035.19",
      "agent": "claude",
      "brand": "claude",
      "state": "working",
      "since": 1793780700.0,
      "title": "Port Hyprland configs to Lua",
      "cwd": "~/.config/hypr",
      "project": "hypr",
      "session": "kitty-session",
      "question": null,
      "progress": null,
      "action": { "op": "jump", "...": "same object `act` takes today" }
    }
  ],
  "counts": { "working": 1, "waiting": 0, "done": 2 }
}
```

- `state` is one of `working | waiting | done | idle | limit | error`.
- `question` is the agent's own prompt text when waiting (already shown in the deck).
- `progress` is 0–1 when the program reports OSC 9;4, else null.
- `brand` is the asset name (the shell keeps copies in `assets/brands`).
- Tool prompts (sudo, ssh, git, pacman) keep coming through the inbox, with
  a new `source: "tool"` (agents get `source: "agent"`), so consumers can
  word them differently ("A password in kitty" vs "Claude needs you").
- Document it in `docs/inbox.md` beside the inbox contract, with the version
  rule: additive changes keep `version`, breaking ones bump it.

**Verify**: a test that drives a fake agent through working → waiting →
done and asserts each write; the file is never partially written (rename);
no write when nothing changed.

## Phase 3: the shell consumes it (rice side; for the shell session)

In `~/Projects/rice/shell/services/Kittymux.qml`: watch `agents.json` with a
FileView; derive `running` / `working` from it; delete the 20 s `pick`
timer and the `text` parser; fall back to `pick` only when the file is
missing (older kittymux). Then the island's agent stack and moments are
instant. Clicking an agent moment jumps via `action`.

## Phase 4: docked panel restyle

Apply phase 1's roles to the panel views (Agents, Usage, Inbox, Settings).
Keep it fully usable on its own.

## Also fix while there

- `workflow find-session` retry storm on "kitty snapshot unavailable": back
  off (e.g. 0.5 s, 1 s, 2 s, then give up) and log once.
- `panes-<pid>.json` / `scan-<pid>.json` written as `{}` while agents run in
  that kitty: confirm whether that's intended (no panes tracked) or a bug.

## STOP conditions

- The working tree has someone else's uncommitted changes in a file you
  need: stop and ask.
- A change would alter `inbox-snapshot.json`'s existing fields (the shell
  reads them): additive only.
- Screenshots show the state colours no longer distinguishable by glyph.

## Context for the executor

- The user's desktop: Hyprland 0.57 (Lua config "kuwai") + the "rice"
  Quickshell shell, both in `~/Projects/rice`; the session runs from a
  stable worktree (`~/.local/share/kuwai`) and `rice promote` moves it.
- The user's taste: calm, Apple-like restraint; one meaning per colour; no
  noise in rows; motion only where it explains something.
- Don't open full-screen or keyboard-grabbing UI to test while the user may
  be typing; use `kittymux demo` (an isolated window) and screenshots.
