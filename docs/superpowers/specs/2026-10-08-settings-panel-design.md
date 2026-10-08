# Settings panel — design

Status: **proposed, not built.** Written 2026-10-08 for review. Nothing here changes behaviour until it is approved.

## The problem

kittymux has about twenty switches and no place to see them. Twelve live in `kittymux_features` (`kittymux features`), and the rest are separate flag files or environment variables, each read by hand at its own call site:

| Switch | How it is read today | Where |
|---|---|---|
| `folder hue collide panetitle motion titles sudo loginprompt pkgprompt socketlink` (+ planned `sheet hover`) | `kittymux_features.enabled()` | one module, CLI `kittymux features` |
| notifications: `notify`, `notify-done` | `KITTYMUX_NOTIFY=0` or file `notify-off` / `notify-done-off`, tested inline | `kittymux_scan`, `bin/kittymux` (two copies of the test) |
| `bell` | `KITTYMUX_BELL=0` or file `bell-off` | `kittymux_scan._alert` |
| `autosave`, `changes`, `journal` | `KITTYMUX_X=0` or file `x-off`, one function each | `kittymux_scan` |
| `attention` (let a bell move focus) | `KITTYMUX_ATTENTION=1` or file `attention-on` | `kittymux_layout` |
| `resume` (auto-resume agents) | `KITTYMUX_RESUME=auto` | `kittymux_resume` |
| `usage live` (network requests for quotas) | `KITTYMUX_USAGE_LIVE=1` | collectors |

The result: a user who wants "no sounds, no completions, keep the folder line" has to know six file names, and the README is the only index. A panel that edits these would be easy to build badly: if the panel knows file names and the scanner knows file names, they will drift.

## Goals

1. One place to see every switch, what it does, whether it is on, and **why** it is in that state (default, a flag file you made, or an environment variable).
2. Change a switch with one key or one click, and see it take effect.
3. The CLI and the panel are two views of one model; neither owns a file name.
4. Switches that change what leaves the machine or what moves your focus say so before they flip.

## Non-goals

- Not a config editor: colours, widths, key bindings and agent definitions stay in their files.
- No new storage. State stays in `$KITTYMUX_STATE` flag files, so the panel is optional and everything keeps working over ssh or with the panel closed.
- Nothing that types into an agent, and nothing that reads screen text.

## Design

### 1. One catalog (pure): `python/kittymux_switches.py`

A `Switch` is data: `id`, `group`, `label` (what a person calls it), `help` (one sentence, ≤ 90 characters, written for the person), `default`, `kind` (`switch`), `status` (`live` | `planned`), `risk` (`none` | `network` | `focus` | `resume`), and `legacy` (the old flag-file name and env value, when they differ from the generic `<id>-off|-on` and `KITTYMUX_<ID>`).

`resolve(id)` returns `(on, where)` with `where` ∈ `env | flag | default`, by the precedence that already exists: environment > flag file > default. `set(id, on)` writes **at most one** flag file (none when the value equals the default), as `set_feature` does now. `kittymux_features` becomes a thin facade over this module, so every existing caller and test keeps working.

Every hand-rolled check in the table above is replaced by `switches.enabled("notify")`. That is the real fix; the panel is the visible part of it. A source-scan test (the pattern `test_timers` uses for `add_timer`) forbids `os.path.exists(... "-off")` outside the module.

Groups, in the order shown: **Bar** (folder, hue, collide, panetitle, motion, titles), **Notifications** (notify, notify-done, bell, sudo, loginprompt, pkgprompt), **Safety and recovery** (autosave, journal, changes, socketlink), **Opt-in** (attention, resume auto, usage live). Planned switches (`sheet`, `hover`) are listed at the end of Bar, dimmed, and cannot be toggled; the CLI already says they do nothing yet.

### 2. A fourth view (pure): `python/kittymux_settingsview.py`

Same shape as `kittymux_inboxview`: `build(rows, width, height, sel, now) → SettingsView(lines, rows, chips, buttons)` where the regions are screen coordinates for `sidebar-kit` to hit-test. All colours come from `Palette` tokens through `kittymux_ui.Kit`; nothing is hardcoded.

```
 ▦  ◔  ✉  ⚙ Settings            ← the strip gains a fourth pill (icon-only when narrow)
 Preset  [minimal] [default] [full]
 BAR
 ▸ Folder line          ● on        the project and branch under each tab
   Colour per project   ● on        a stable tint for each project
   Motion               ○ off       the spinner stays still
 NOTIFICATIONS
   Needs-you popups     ● on
   Completion popups    ● on
   Bell                 ○ off  env   set by KITTYMUX_BELL in your environment
 OPT-IN
   Live usage requests  ○ off        asks each provider for your quota
 ───
 ␣ toggle   p preset   r reset   ? keys
```

- A row shows state with a glyph **and** a word (`on`/`off`), never colour alone. The marker `env` or `file` appears only when the value is not the default, so the default look is quiet.
- An environment-set row is **locked**: the toggle does nothing and the row says which variable holds it. A click on it opens a one-line card explaining how to unset it. We never edit your shell.
- Risky switches (`network`, `focus`, `resume`) ask first, in the panel: the row expands to two lines of consequence ("kittymux will contact each provider's API with your own login to read quotas") and `⏎` confirms, `esc` cancels. Turning one **off** never asks.
- Narrow tiers, as the other views do: full word + help → name + state → glyph + state. At 26 columns help text is dropped and the group titles stay.
- Keys: `j k ↑ ↓` move, `space` or `⏎` toggle, `p` cycles presets, `r` resets the row to its default, `R` resets the group, `?` the key card, `esc` back to Agents. The pill key is `s` (to be checked free: the panel does not bind it today). Mouse: click a row to toggle, click a preset chip, hover lights the row.

### 3. Applying a change

`set` writes the file, then `_nudge_bars()` (the existing "reload every kitty once" call) runs on a worker, never on the UI thread, and is **coalesced**: ten quick toggles cause one reload. The footer shows `applied to 2 kitties` or `saved; the bar picks it up on its next redraw` when none answered. A write failure (read-only state directory, a directory named `hue-off`) shows inline on the row and changes nothing; nothing is half-saved because a switch is one file.

### 4. CLI parity

`kittymux features` keeps working and gains the groups. New: `kittymux settings` opens the panel on the Settings view (or prints the same list when no panel runs), and `kittymux features on|off|preset` accept every id in the catalog, including `notify`, `notify-done`, `bell`, `autosave`, `journal`, `changes`, `attention`, `resume-auto`, `usage-live`. Old flag-file names keep working because `legacy` maps them: nobody has to touch the files they already made.

## Migration (the risky part)

The catalog must read exactly what the scanner reads today. Before any call site changes, a table test builds every combination of env value and flag file for each legacy switch and asserts `switches.enabled(id)` equals the old inline expression (kept in the test as the specification). Only then are the call sites replaced, one module per commit. Behaviour for existing users is identical by construction; the test is the proof.

`KITTYMUX_RESUME=auto` is a value, not a boolean; it maps to switch `resume-auto` with `legacy.env = ("KITTYMUX_RESUME", "auto")`. Anything unrecognised reads as the default, as now.

## Tests

- Pure: catalog completeness (every id in `FEATURES` and every legacy switch above is present; every `help` ≤ 90 characters, no trailing period variants, no "please"); precedence (env > flag > default, `-off` wins over `-on`); the legacy equivalence table; `set` leaves no file at the default; locked rows; each narrow tier draws lines of exactly the width asked for (the `fit_line` rule); every region is inside the screen; a hostile label or env value is `clean`ed.
- Source scan: no inline flag-file checks outside `kittymux_switches`.
- `tests/shot_settings.sh` renders the view on synthetic state at 26, 32 and 48 columns, dark and light, and the PNGs are read (the repo rule: a look is verified by looking).
- `tests/smoke_settings.sh`, real keys and mouse in the panel on a private kitty: toggle by key and by click, a locked row stays locked, a risky switch asks, `esc` goes back, ten toggles cause one reload, with the usual tripwire on every other kitty.
- Docs: `peek-deck-and-panel`, `customization`, `cli-reference` and the feature YAML change in the same commit (`test_docs` guards them).

## Build order

1. `kittymux_switches` + the equivalence table; `kittymux_features` as a facade. No UI change.
2. Replace the inline checks, one module per commit.
3. `kittymux_settingsview` read-only (shows state and source) and the strip pill.
4. Toggles, presets, reset, the env lock.
5. Confirmations for risky switches.
6. CLI `settings`, docs, site facts (`tools/export_facts.py` already exports features; it gains groups).

Steps 1–2 are valuable on their own and have no visible risk; the panel can be dropped after them and the code is still better.

## Open questions

1. **Names the user sees.** "Needs-you popups" and "Completion popups" instead of `notify` and `notify-done`: confirm the wording.
2. **`usage live`** talks to the network with your own credentials. Should turning it on require typing `yes`, as the CLI does, or is the two-line card enough?
3. **Per-kitty or global.** Switches live in the shared state directory and apply to every running kitty. A per-instance switch would be a different design; this one deliberately has none.
4. **The pill key.** `s` is proposed; if it clashes with a future "search" or "sessions" key, `,` (the usual "preferences" key) is the fallback.
