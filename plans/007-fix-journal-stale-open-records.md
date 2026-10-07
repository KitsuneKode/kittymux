# 007 — Journal: agent exit inside a live window leaves a permanently "open" record

## Context

`kittymux_journal` keeps `agent-sessions.json`: one record per agent session with `open: true`
while it runs. The scanner feeds it via `_journal_note` (on state change) and `_journal_tick`
(heartbeat + close-out). `kittymux sessions history` shows records with `running` when
`rec.open` and the owning kitty pid is alive; `kittymux sessions recover` (`recoverable()`)
offers to restart entries that are **not** running.

## Bug

When an agent process exits but its window stays open (Claude exits back to the shell — the
most common way a session ends):

1. `scan_window` (`python/kittymux_scan.py` ~line 191–202): `agent_of(window)` returns `None` →
   the verdict is cleared/popped and the function returns early. `_journal_note` is never
   called for that window again.
2. The heartbeat in `_journal_tick` (~line 610–613) only calls `_journal_note` for windows
   whose verdict has `agent` — this window no longer has one.
3. `rt["keys"][wid]` still holds the old journal key. `gone` (~line 615) only removes keys for
   windows that closed; this window is alive, so the key stays and remains in `running`
   (~line 618).
4. `J.close_missing(recs, os.getpid(), running, wall)` (~line 619) only closes records whose
   key is **not** in `running` → the record is never finalised.

Result: the record stays `open: true` until the window (or kitty) dies. It shows as
**running** in `sessions history`/`pick` even though the agent exited hours ago, and
`recoverable()` skips it (`not e["running"]`), so `sessions recover` can never offer to
restart an agent that exited inside a still-open window.

The same stale-key path exists inside `_journal_note` (~line 587): when
`R.identify(...)` returns `None` the function returns early without clearing
`rt["keys"][wid]`.

## Fix (sketch)

Two insertion points, both a few lines in `python/kittymux_scan.py`:

1. In `scan_window`'s `agent is None` branch (before the verdict write at ~line 196–202):
   `rt = _journal_rt(); if rt["keys"].pop(wid, None) is not None: rt["dirty"] = True`.
   Dropping the key removes it from `running` in the next `_journal_tick`, so
   `close_missing` finalises the record (accumulates `work_s`, sets `open: false`).
2. In `_journal_note`, when `ident is None`: same `pop` + `dirty` (covers the case where the
   verdict still shows an agent but the process table no longer does).

Design note: using the verdict's agent signal (not a per-tick `ident` result) keeps this no
flappier than the tab bar's own agent detection — a transient `/proc` read failure already
clears the verdict today. `close_missing` re-open is safe: if the same agent/session
reappears, `observe()` finds the record by key and sets `open: true` again; worst case is one
open→closed→open flap on a genuinely intermittent detection, which is no worse than today.

## Steps

1. Work in an isolated worktree (`.worktrees/journal-close`) per AGENTS.md.
2. Add a pure test first (`tests/test_journal.py` or the closest existing scanner test):
   simulate a window that had a journal key, then `scan_window`/`_journal_tick` with
   `agent_of → None` and a live window id; assert `close_missing` marks the record
   `open: false`. The existing test suite already fakes windows/verdicts — follow its
   fixture style; do not spawn a real kitty.
3. Implement the two insertion points above.
4. Also handle `wid` entries whose value is `None` (line ~580 seeds `None` placeholders when
   the journal is disabled — `pop` must not treat those as "was bound").
5. Run: `python3 -m unittest discover -s tests` and `python3 -m py_compile python/kittymux_scan.py`.

## Acceptance criteria

- A window whose agent exits (verdict loses `agent`) has its journal record closed within one
  heartbeat tick: `open: false`, `work_s` finalised.
- Record shows `running: false` in `entries()` and becomes eligible for `recoverable()`.
- No behaviour change when the agent is still running, when the window itself closes
  (existing `gone` path), or when the journal is disabled.
- `python3 -m unittest discover -s tests` passes; `git diff --check` clean.

## Risks / STOP conditions

- Do not change `observe()`/`close_missing()` semantics in `kittymux_journal.py` — the merge
  contract (`flags_ts`, `open`) is load-bearing for `pin`/`settle`. STOP if the fix seems to
  need a journal-format change.
- Do not persist screen text or cmdlines anywhere new.
- If a different module also reads `rt["keys"]`, re-check before editing (grep for `["keys"]`
  in `kittymux_scan.py`).

Effort: S · Priority: P1 · Files: `python/kittymux_scan.py`, one test file.
