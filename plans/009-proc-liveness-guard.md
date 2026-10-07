# 009 — Guard `/proc` liveness checks so non-Linux hosts don't delete live state

## Context

kittymux declares itself Linux-only (README, `docs/compatibility.md`), but several cleanup
paths use `os.path.exists("/proc/<pid>")` as "is this kitty process alive". On a host without
`/proc` (macOS, some containers) that check returns `False` for *every* pid — turning
"can't tell" into "definitely dead", and the cleanup code then **deletes other, actually-live
kitty instances' state files**. That is worse than "feature doesn't work": it's active harm.

## Sites (verified)

| File | Code | Effect when `/proc` is absent |
|---|---|---|
| `python/pane-state.py` ~line 64 | `_cleanup_stale` unlinks `panes-/scan-<pid>.json` when `/proc/<pid>` missing | every kitty deletes every other kitty's pane/scan state |
| `python/kittymux_layout.py` ~line 492 | `cleanup_stale` unlinks `layout-<pid>.json` | running kitties' saved layouts revert to default on next reload |
| `python/kittymux_journal.py` ~line 214 | `_alive(pid)` → `is_running` | every journal record reports "not running" (display-only) |
| `python/sidebar-kit.py` ~line 147 | `_proc_ppids` | empty → port/pane extras missing (already degrades gracefully) |

## Fix (sketch)

One shared helper, e.g. `proc_alive(pid)` in a pure module both sides import (or a tiny local
helper per file — these modules intentionally avoid cross-imports in a few places; match the
file's existing import style):

```python
def _alive(pid: int) -> bool:
    proc = "/proc"
    if not os.path.isdir(proc):
        return True                      # cannot tell → treat as alive, never garbage-collect
    return bool(pid) and os.path.isdir(f"{proc}/{pid}")
```

Apply to the three cleanup/liveness call sites. For `journal._alive` also keep the signature
(`proc="/proc"` param exists for tests) and return `True` when `os.path.isdir(proc)` is False.

## Steps

1. Worktree `.worktrees/proc-guard`.
2. Unit tests first: each touched module's existing test file gets a case that monkeypatches
   `os.path.isdir` (or passes `proc="/nonexistent"`) and asserts the file/record is kept.
3. Update `docs/compatibility.md`: add a line that without `/proc` kittymux degrades to
   "keep everything" rather than deleting other instances' state.

## Acceptance criteria

- With `/proc` unmounted/absent, `_cleanup_stale`/`cleanup_stale` delete nothing and journal
  entries keep their last-known state.
- Linux behaviour unchanged (tests still pass, including the existing stale-file cleanup
  tests — they must keep a fake `/proc` or mock `_alive`).
- `python3 -m unittest discover -s tests` passes; `python3 -m py_compile` on touched files.

## Risks / STOP conditions

- The pid-recycle case (a pid reused by a non-kitty process) is already accepted by the
  existing code — do not try to additionally check `/proc/<pid>/comm` inside this plan; that
  would change Linux semantics. If reviewers want it, separate plan.
- Some files load watchers into kitty's interpreter — never import kitty modules in the new
  helper path; keep helpers pure.

Effort: XS · Priority: P2 · Files: `python/pane-state.py`, `python/kittymux_layout.py`,
`python/kittymux_journal.py`, tests, `docs/compatibility.md`.
