# Plan 004: Make the sidebar deck non-blocking, correct, session-grouped, and visually clean

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8681a7d..HEAD -- python/sidebar-kit.py`
> Plan 002 also edits this file (palette/agents) — it must be DONE first; re-read the whole
> file before starting and treat other unexpected diffs as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW–MED (overlay only; never touches the live tab bar)
- **Depends on**: plans/002-theme-tokens-from-kitty-colors.md
- **Category**: bug / dx
- **Planned at**: commit `8681a7d`, 2026-09-29

## Why this matters

`ctrl+alt+b` opens the "sidebar command deck" (`python/sidebar-kit.py`), a `kittens.tui`
overlay with mouse hover/click and a live pane preview. It works but: it blocks its own event
loop with synchronous subprocess calls every 1.5 s (one `git` spawn per tab plus two
remote-control calls); it lists *every* tab of every OS window and session with no grouping;
its "focused" rail appeared on three rows and not on the active tab in a scratch test; the
selected-row fill stops short of the right edge; and the help line is truncated
(`… click to go · q` cut off). This plan fixes those and groups rows by session, making the deck
trustworthy and closer to a cmux/shadcn workspace list.

## Current state

`python/sidebar-kit.py` (338 lines) — runs as a kitten (separate process, `exec`'d: **no `__file__`**,
`kitten_ui(allow_remote_control=True)`; remote control via `main.remote_control([...], capture_output=True, text=True)`).

Key parts (line numbers approximate; re-read the file):

```python
def _git_branch(cwd):                       # one subprocess per row, timeout 0.4s, called from Row.__init__
    ... subprocess.run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"], timeout=0.4)

class Row:  # built from `kitty @ ls` tab dicts
    ...
    self.focused = bool(aw.get("is_focused"))          # <- suspect: marks several rows in a test
    self.unread = bool(tab.get("needs_attention") or aw.get("has_activity"))

def _tick(self):                            # every 1.5s, ON the event loop
    keep_wid = self.rows[self.sel].win_id if self.rows else 0   # unused
    self.refresh_data()                     # _rc("ls") + N git spawns, synchronous
    self.preview_for = 0
    self._refresh_preview()                 # _rc("get-text", ...)
    self.draw_screen(); self._schedule()

# draw_screen: header text, then
w(styled(" j/k move · ⏎ jump · click to go · q quit".ljust(bar_w)[:bar_w], ...))   # bar_w == 36 → truncated
...
line = edge + icon + styled(f"{title:<{title_w}.{title_w}s}", bg=bg) + mark + wait
w(line + (styled(repeat(" ", bar_w), bg=bg) if bg else ""))     # fill past the row width; leaves gap/overdraw
```

Layout constants: `_geom()` → `bar_w = 36 if cols >= 64 else cols`; preview column at `bar_w + 1`; rows are 2 lines each
(`per = (rows - 2) // 2`), mouse maps `_row_at(y)`: `idx = offset + (y - 2) // 2`.

Session facts: kittymux sessions are kitty-native (kitty 0.49 `goto_session`, `save_as_session`); tabs of parked
sessions still appear in `kitty @ ls`. Kitty can match by session: `kitty @ ls --match-tab 'session:^NAME$'`
(used in `lib/mux.sh` `find_os_window_for_session`, line ~394). The tab bar's `TabBarData.session_name` shows
kitty knows each tab's session. **Whether the `ls` JSON itself carries a session key is unverified** — Step 1 finds out.

Conventions: kitten style is plain procedural Python + one `Handler` subclass; palette/agent tokens come from
`kittymux_theme` / `kittymux_agents` after plan 002. Kitten verification recipe is in `AGENTS.md`
("Scratch instance for UI tests").

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax | `python3 -m py_compile python/sidebar-kit.py` | exit 0 |
| Scratch kitty | `kitty --class kmx-t --listen-on unix:/tmp/kmx-t --session <file> &` | window |
| Open deck in it | `kitty @ --to unix:/tmp/kmx-t action kitten $PWD/python/sidebar-kit.py` | overlay appears |
| Inspect JSON | `kitty @ --to unix:/tmp/kmx-t ls \| python3 -m json.tool \| head -80` | JSON tree |
| Read deck text | `kitty @ --to unix:/tmp/kmx-t get-text --match title:. --extent screen` (pick the overlay window id from `ls`) | rendered rows |
| Error log | `cat /tmp/sidebar-kit-err.log` | empty |

## Scope

**In scope**: `python/sidebar-kit.py`; (if needed for tests) `tests/test_sidebar_helpers.py`;
`plans/README.md` status.

**Out of scope**: the tab bar (`tab_bar.py`), `pane-state.py`, keymap (`.tpl`), any `bin/*` script,
persistent-panel work (plan 006), status semantics (plan 005).

## Git workflow

- Branch: `advisor/004-sidebar-deck`
- Commit per step; style e.g. `sidebar: refresh off-thread, group by session`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Discover the ground truth (no code changes yet)

In a scratch kitty with 3 tabs in 2 sessions (write two session files `s1.kitty`/`s2.kitty`; load with
`--session`, then `kitty @ … action goto_session s2` or use `launch --type=tab` and `goto_session`):
1. Print `kitty @ ls` and record which keys hold: session name (per tab or per window?), tab `is_active`,
   OS-window `is_focused`, window `is_focused`, `is_self`, `active_window_history`.
2. Determine why 3 rows got the `▌` focus rail: dump `aw.get("is_focused")` for each tab's active window.
3. Record findings in your final report (short table). **Then** pick the focus rule:
   the tab is "current" iff its OS window `is_focused` **and** the tab `is_active` (adjust if the JSON says otherwise).

**Verify**: findings written down; nothing modified (`git status` clean).

### Step 2: Refresh off the event loop, cache git

- Do data collection (`ls`, git branches) in a worker thread (`threading.Thread`, daemon) that posts results
  back with `self.asyncio_loop.call_soon_threadsafe(self._apply, snapshot)`; `_apply` builds `Row`s, clamps, redraws.
  Only one refresh in flight (guard flag); skip a tick if the previous is still running.
- `Row.__init__` must not spawn anything — pass in a `branches: dict[str, str]` computed by the worker with a
  per-cwd cache (TTL 5 s) and a single `git -C cwd rev-parse --abbrev-ref HEAD` per *distinct* cwd.
- Remove the unused `keep_wid`. Keep `preview` refresh (`get-text`) in the same worker; only refetch when the
  selected row or its window changes, or on each tick for the selected row (as now).
- Remote-control note: `main.remote_control(...)` is a blocking subprocess call — fine inside the worker.

**Verify**: `python3 -m py_compile python/sidebar-kit.py` → exit 0; open the deck in a scratch kitty with 8+ tabs
and confirm keys `j/k` respond instantly while a tick runs (`kitty @ … send-key j` then `get-text` shows the moved
selection within ~200 ms); `/tmp/sidebar-kit-err.log` empty.

### Step 3: Fix focus, hint line, and row fill geometry

- Focus rail: use the rule from Step 1.
- Hint line: shorten to fit `bar_w` (e.g. `j/k move · ⏎ go · click · q quit`) **and** assert
  `len(hint) <= bar_w` at import via a small pure function `_hint(bar_w)` that drops trailing items if narrow.
- Row rendering: build each line as a list of `(text, style)` cells, compute the exact padded width to `bar_w`,
  and write *once* with the row background applied to the whole line (`selected` → `surface_hi` from plan 002).
  Delete the extra `repeat(" ", bar_w)` overdraw.
- Keep the 2-lines-per-row mouse mapping consistent with any added group-header rows (Step 4).

**Verify**: py_compile → exit 0; `get-text` of the deck shows every row line exactly `bar_w` cells wide up to the
separator column (assert programmatically: strip trailing spaces off each of the first `bar_w` cells and confirm no
character is drawn at column `bar_w-1+` on the left pane; note the `│` at `bar_w`).

### Step 4: Group rows by session

Using the Step-1 findings, group tabs under a one-line header per session (header style: `faint`, uppercase name,
right-aligned tab count; the *current* session's header uses `accent`). Rows stay 2 lines. Keyboard: `j/k` skip
headers; `J/K` (shift) jump between sessions; mouse clicks on a header do nothing. Order: current session first, then
by most recently used if available, else name. Tabs with no session go under `(no session)`.
Update `_row_at` to account for headers (build an explicit `layout: list[Item]` mapping y → row index).
If the JSON lacks per-tab session info (Step 1), obtain it with one
`ls --match-tab "session:^NAME$"` query per known session in the worker (session names from
`$KITTYMUX_STATE/sessions/*.kitty` filenames — see `lib/mux.sh` `session_name_from_file`).

**Verify**: py_compile → exit 0; in the scratch instance with two sessions the deck shows two group headers
with correct membership (`get-text` output contains both header names and each tab under the right one);
clicking a tab in the *other* session jumps to it (use `kitty @ send-mouse`? not available — instead press
`J` then `Enter` via `send-key`, then `kitty @ ls` shows the target tab active).

### Step 5: Docs

Update the deck's one-liner in `README.md`'s key table only if key semantics changed (`ctrl+alt+b` row); keep the
`.tpl` comment format untouched.

**Verify**: `git diff --stat` shows only in-scope files.

## Test plan

Pure helpers (`_hint`, layout/hit-map builder, grouping/ordering) go in module-level functions with no kitty
imports and get `tests/test_sidebar_helpers.py` (unittest; import the module by path with `importlib` — it has
top-level `kittens.tui` imports, so instead move the pure helpers into a new `python/kittymux_deck.py` and test
that): cases — grouping order (current session first), header skipping, `_row_at` mapping with headers and offset,
`_hint` never exceeds width for widths 20–80. Run: `python3 -m unittest discover -s tests -v` → all pass.
(If you create `python/kittymux_deck.py`, add its symlink to `install.sh` exactly as plan 002 did for its modules —
that is the one permitted `install.sh` edit.)

## Done criteria

- [ ] `python3 -m py_compile python/*.py` exits 0
- [ ] `python3 -m unittest discover -s tests` exits 0, new tests included
- [ ] `grep -n "subprocess" python/sidebar-kit.py` shows no call reachable from `Row.__init__` or `draw_screen`
- [ ] `grep -n "repeat(\" \", bar_w)" python/sidebar-kit.py` → no match
- [ ] Scratch-instance checks from Steps 2–4 performed and reported
- [ ] Only in-scope files (+ `install.sh` if a helper module was added) modified
- [ ] `plans/README.md` status row updated

## STOP conditions

- `kitty @ ls` gives no way to tell which tab is current/which session a tab belongs to (Step 1) — report the JSON shape.
- Threaded remote control deadlocks or the kitten exits (check `/tmp/sidebar-kit-err.log`) — report; don't add sleeps.
- Grouping requires changes outside `sidebar-kit.py` (+ optional helper module).

## Maintenance notes

- Plan 006 (persistent `kitten panel` sidebar) reuses this file's `Handler`; keep data collection separate from
  drawing so it can be lifted out (`kittymux_deck.py` is that seam).
- Reviewer: check terminal-resize behaviour, empty state (no tabs), and >1 OS window (deck lists all — decide with
  the owner whether to scope to the current OS window; default to *all*, current OS window's session first).
- The error log path `/tmp/sidebar-kit-err.log` is fixed and world-readable in `/tmp`; moving it under
  `$KITTYMUX_STATE` is a cheap follow-up (deferred).
