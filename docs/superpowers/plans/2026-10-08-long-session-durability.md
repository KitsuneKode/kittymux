# Long-session durability Implementation Plan

Status: **executed 2026-10-08** (PR #5, merged). Deviations from the text below: `append_capped` seeks `-(cap // 2)` (the plan's `-cap // 2` is the same for even caps and wrong for odd ones); Task 6 needed no code (measured 0 zombies); the weekly soak has not run on GitHub yet (it runs on the next Monday, or by hand from the Actions tab). One unrelated flake showed up in CI: `smoke_changes` failed once on kitty 0.49.1 ("the repository's object store was written to") and passed on rerun; it has not been investigated.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A kitty that has run for a month holds no memory, files or processes that grow with how long it has run or how many windows it has seen, and a test fails the day someone adds a container that does.

**Architecture:** Fix each confirmed leak at its own site with the smallest change, put the two repeated patterns (a table with a size cap, a log with a size cap) in one pure module `python/kittymux_bounded.py` so the next person reaches for it instead of writing a third copy, then add a guard test that lists every module-level container and demands a reason for each, and a scheduled soak that measures instead of guessing.

**Tech Stack:** Python 3 (runs in kitty's interpreter; no kitty imports in the new module), `unittest`, bash, GitHub Actions.

**Spec:** none; the source is the review summarised in `docs/superpowers/plans/2026-10-08-socket-and-diagnostics.md` ("Where this came from"). The rules this plan serves are in `docs/agents/conventions.md` (long-lived state lives in `sys.modules["_kittymux_scan_rt"]`) and `AGENTS.md` (no module-level timer state).

## Global Constraints

- Every new `.py` file is pure where it can be: no `kitty.*` imports, so it unit-tests under system python.
- A module the tab bar or scanner imports is reloaded on every config load (`kittymux_reload.reload_all`): new modules need no registration, but they must not keep state in module globals that has to survive a reload.
- Never log or store screen text (`docs/agents/status-contract.md`). Nothing added here writes any.
- Each task ends green on `python3 -m unittest discover -s tests` and `py_compile` on touched files, and is one commit.
- Smoke rigs that start a kitty follow the repo rules: `KITTYMUX_SOCKET_DIRS` set to the rig's own dir and a tripwire on every other kitty. This plan adds no rig that does not already exist (`soak_kitty.sh`).
- Do not push `main` for the sake of this plan alone: pushing deploys the site. Work on branch `durability`, merge by fast-forward when CI is green.

## Review Focus

- A window that reports (inbox event) and then closes without being looked at: its id must leave `unread` (verified leak, Task 1).
- A session resumed after its record was pruned from memory must not lose its history in the file (Task 2 must prune by the same rule as the file, never earlier).
- A table at its cap must keep the newest entries, not the first ones (Task 3).
- A dead kitty's `decisions-<pid>.jsonl` must go, a live one's must stay, and a pid reused by another program must not delete a live kitty's file (Task 4: liveness is `/proc/<pid>`, same rule as the files already reaped).
- A log at its cap keeps writing (never stops logging), and never raises into kitty's event loop (Task 5).
- The guard test must fail for a new unbounded container and say what to do (Task 7).

## What was checked

| Review claim | Result |
|---|---|
| `unread` set never pruned on close | **True.** Eight announced windows closed: all eight ids stayed. The existing test `test_the_unread_set_forgets_windows_that_closed` passes only because its windows never announce, so the set is always empty (it asserts about nothing). |
| Journal in-memory records never pruned | **True** (`rt["recs"]` in `kittymux_scan._journal_rt`; `prune()` runs only on the merged copy inside `flush`). |
| `_ERR_SEEN` insert-only | **True** (`tab_bar.py`, one entry per distinct last traceback line). |
| `decisions-<pid>.jsonl` and `changes-<pid>.json` never reaped | **True** (`pane-state._cleanup_stale` matches `panes|scan` only). Seven 88-byte `decisions-*` files of dead kitties were in the author's state directory. |
| `scan-debug.log` / `scan-trace.log` unrotated | **True**, but only with `KITTYMUX_DEBUG` set. |
| Zombie children from fire-and-forget `Popen` | **Not true in practice.** CPython reaps finished children of dropped `Popen` objects on the next `Popen()` call. Measured: 0 zombies after a 15-cycle soak (Task 6). |
| `/tmp/mykitty-<pid>` of a killed kitty poisons "newest" | Real, handled in the sockets plan, not here. |

## File Structure

- Create `python/kittymux_bounded.py` — `cap_newest(table, cap)`, `seen_within(table, key, now, window, cap)`, `append_capped(path, text, cap)`; pure.
- Create `tests/test_bounded.py` — the module's tests.
- Create `tests/test_bounded_state.py` — the guard: every module-level container is listed with a reason.
- Modify `python/kittymux_scan.py` — prune `unread`; prune journal records; use `append_capped` for the two debug logs.
- Modify `python/tab_bar.py` — `_ERR_SEEN` through `seen_within`.
- Modify `python/pane-state.py` — reap `decisions-` and `changes-` files of dead kitties.
- Modify `tests/test_scan_bounded.py`, `tests/test_pane_state.py` — new cases.
- Modify `tests/soak_kitty.sh`, create `.github/workflows/soak.yml` — measure state-directory bytes, run weekly.
- Modify `docs/agents/verify.md` (the soak and the guard), `CHANGELOG.md` (one line under Fixed).

---

### Task 1: `unread` forgets windows that closed

**Files:**
- Modify: `python/kittymux_scan.py` (in `scan_all`, next to `seen &= live`)
- Test: `tests/test_scan_bounded.py`

**Interfaces:**
- Consumes: `_RT` runtime namespace (`vars(_RT)["unread"]`, a `set[str]` of window ids), the `live` set built in `scan_all`.
- Produces: nothing new; `unread` is a subset of live window ids after every scan.

- [ ] **Step 1: Replace the vacuous test with one that fails today**

In `tests/test_scan_bounded.py` replace `test_the_unread_set_forgets_windows_that_closed` with:

```python
    def test_the_unread_set_forgets_windows_that_closed(self):
        """A window that reported something (a question: one event per window) and closed unseen must not stay in `unread` for ever.
        The old version of this test never announced anything, so the set was always empty and it proved nothing."""
        with mock.patch.object(KS, "_notify", return_value="sent"):
            for i in range(1, 9):
                w = FakeWindow(i, "codex", "› Ask Codex\n")
                self.add(w)
                KS.scan_all()
                KS._announce(w, "question", "codex", "screen", f"q{i}")
            self.assertEqual(len(vars(KS._RT).get("unread", ())), 8, "the test must really populate the set, or it asserts about nothing")
            self.k.boss.all_windows[:] = []
            self.k.boss.window_id_map.clear()
            KS.scan_all()
        self.assertEqual(vars(KS._RT).get("unread", set()), set())
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 -m unittest tests.test_scan_bounded.BoundedStateTests.test_the_unread_set_forgets_windows_that_closed -v`
Expected: FAIL, `AssertionError: Items in the first set but not the second: '1' … '8'`.

- [ ] **Step 3: Prune on close**

In `python/kittymux_scan.py`, directly after the block

```python
        seen = vars(_RT).get("prompt_seen")
        if seen:
            seen &= live
```

add:

```python
        unread = vars(_RT).get("unread")
        if unread:
            unread &= live                  # a window that reported and then closed unseen: its id must not outlive it
```

- [ ] **Step 4: Run the test and the file's other tests**

Run: `python3 -m unittest tests.test_scan_bounded tests.test_scan -v 2>&1 | tail -5`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add python/kittymux_scan.py tests/test_scan_bounded.py
git commit -m "scan: the unread set forgets windows that closed (its test never populated it)"
```

---

### Task 2: the journal's in-memory records follow the file's limits

**Files:**
- Modify: `python/kittymux_scan.py` (`_journal_tick`)
- Test: `tests/test_journal.py`, `tests/test_scan.py`

**Interfaces:**
- Consumes: `kittymux_journal.prune(records, now)` (age `MAX_AGE_S` and size `RECORD_MAX`, pinned exempt), already called on the merged copy inside `flush`.
- Produces: `rt["recs"]` obeys the same limits as the file, so a record the file dropped cannot flap back on the next heartbeat.

The in-memory copy must be dropped by **exactly the file's rule and no earlier**: `observe()` creates a fresh record (`turns` 0, `work_s` 0) for a key it does not hold, and `flush` lets the record with the larger `last` win, so dropping a live-but-quiet session early would overwrite its history with a blank one. Only `prune()`'s own criteria are safe.

- [ ] **Step 1: Write the test that fails today**

Append to `tests/test_scan_bounded.py`:

```python
    def test_journal_records_in_memory_stop_at_the_files_limits(self):
        J, _ = KS._journal_mod()
        rt = KS._journal_rt()
        now = 10_000_000.0
        for i in range(J.RECORD_MAX + 50):                                   # more sessions than the file keeps
            rt["recs"][f"claude:{i}"] = {"agent": "claude", "last": now - (J.RECORD_MAX + 50 - i), "open": False}
        rt["recs"]["claude:old"] = {"agent": "claude", "last": now - J.MAX_AGE_S - 1, "open": False}
        rt["recs"]["claude:pinned-old"] = {"agent": "claude", "last": now - J.MAX_AGE_S - 1, "open": False, "pinned": True}
        KS._journal_prune_memory(now)
        self.assertLessEqual(len([r for r in rt["recs"].values() if not r.get("pinned")]), J.RECORD_MAX)
        self.assertNotIn("claude:old", rt["recs"])
        self.assertIn("claude:pinned-old", rt["recs"])                       # pinned means keep, in memory too
        self.assertIn(f"claude:{J.RECORD_MAX + 49}", rt["recs"])             # the newest survive
```

- [ ] **Step 2: Run it**

Run: `python3 -m unittest tests.test_scan_bounded -v 2>&1 | grep -E "journal_records|Error|OK|FAIL"`
Expected: FAIL with `AttributeError: module 'kittymux_scan' has no attribute '_journal_prune_memory'`.

- [ ] **Step 3: Add the function and call it**

In `python/kittymux_scan.py`, below `_journal_rt`:

```python
def _journal_prune_memory(wall: float) -> None:
    """The in-memory records obey the file's limits (kittymux_journal.prune: age and count, pinned exempt) and no stricter ones: a record dropped early would come back
    blank on the next observation and win the merge by its newer `last`. Never raises."""
    try:
        J, _ = _journal_mod()
        J.prune(_journal_rt()["recs"], wall)
    except Exception:
        _debug()
```

and in `_journal_tick`, right after the `if J.close_missing(...) or gone: rt["dirty"] = True` statement:

```python
        _journal_prune_memory(wall)
```

- [ ] **Step 4: Run journal and scan tests**

Run: `python3 -m unittest tests.test_scan_bounded tests.test_journal tests.test_scan 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add python/kittymux_scan.py tests/test_scan_bounded.py
git commit -m "scan: the journal's records in memory stop at the file's age and count limits"
```

---

### Task 3: `kittymux_bounded` and the tab bar's error map

**Files:**
- Create: `python/kittymux_bounded.py`, `tests/test_bounded.py`
- Modify: `python/tab_bar.py` (`_ERR_SEEN`, `_log_exception`)

**Interfaces:**
- Produces:
  - `cap_newest(table: dict, cap: int) -> int` — drops the oldest-inserted entries until `len(table) <= cap`; returns how many were dropped. Relies on dict insertion order.
  - `seen_within(table: dict, key, now: float, window: float, cap: int = 256) -> bool` — True when `key` was recorded less than `window` seconds ago (the caller then skips); otherwise records `now` for `key`, re-inserting it last so it counts as newest, caps the table, and returns False.
  - `append_capped(path, text: str, cap: int = 65536) -> bool` — appends `text`; when the file exceeds `cap` bytes it is rewritten keeping the last half; never raises; returns whether it wrote.

- [ ] **Step 1: Write the tests**

`tests/test_bounded.py`:

```python
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_bounded as B  # noqa: E402


class CapNewestTests(unittest.TestCase):
    def test_keeps_the_newest_inserted(self):
        t = {i: i for i in range(10)}
        self.assertEqual(B.cap_newest(t, 4), 6)
        self.assertEqual(list(t), [6, 7, 8, 9])

    def test_under_the_cap_changes_nothing(self):
        t = {1: 1}
        self.assertEqual(B.cap_newest(t, 4), 0)
        self.assertEqual(t, {1: 1})

    def test_a_zero_or_negative_cap_empties_the_table(self):
        t = {1: 1, 2: 2}
        B.cap_newest(t, 0)
        self.assertEqual(t, {})


class SeenWithinTests(unittest.TestCase):
    def test_a_repeat_inside_the_window_is_reported_once(self):
        t = {}
        self.assertFalse(B.seen_within(t, "boom", 100.0, 60.0))
        self.assertTrue(B.seen_within(t, "boom", 130.0, 60.0))
        self.assertFalse(B.seen_within(t, "boom", 161.0, 60.0))        # the window passed: log it again

    def test_distinct_keys_never_exceed_the_cap_and_the_newest_survive(self):
        t = {}
        for i in range(1000):
            B.seen_within(t, f"error {i}", float(i), 60.0, cap=64)
        self.assertLessEqual(len(t), 64)
        self.assertIn("error 999", t)
        self.assertNotIn("error 0", t)

    def test_a_zero_window_sees_every_repeat(self):              # tests set KITTYMUX_ERR_DEDUPE=0 to see every error
        t = {}
        self.assertFalse(B.seen_within(t, "x", 1.0, 0.0))
        self.assertFalse(B.seen_within(t, "x", 1.0, 0.0))


class AppendCappedTests(unittest.TestCase):
    def test_a_log_past_the_cap_keeps_its_tail_and_keeps_logging(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.log")
            for i in range(400):
                self.assertTrue(B.append_capped(path, f"line {i:04d} " + "x" * 90 + "\n", cap=8192))
            size = os.path.getsize(path)
            self.assertLessEqual(size, 8192 + 200)
            text = open(path, encoding="utf-8").read()
            self.assertIn("line 0399", text)
            self.assertNotIn("line 0000", text)
            self.assertTrue(text.startswith("line "), "the cut must land on a line start, not mid-line")

    def test_an_unwritable_path_returns_false_instead_of_raising(self):
        self.assertFalse(B.append_capped("/proc/definitely/not/here.log", "x"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and watch it fail**

Run: `python3 -m unittest tests.test_bounded 2>&1 | tail -3`
Expected: `ModuleNotFoundError: No module named 'kittymux_bounded'`.

- [ ] **Step 3: Write the module**

`python/kittymux_bounded.py`:

```python
"""The two ways kittymux keeps a long-lived thing from growing without limit: a table with a size cap and a log with a size cap. Pure; no kitty imports.

The scanner and the tab bar live as long as kitty does. Anything keyed by something that keeps arriving (a window id, an error text, a path) must be capped,
or a month-long session grows by one entry per distinct key it ever saw. `tests/test_bounded_state.py` lists every module-level container and asks why it is
safe; when the answer is "it is capped", use these instead of writing a third copy."""
from __future__ import annotations

import os


def cap_newest(table: dict, cap: int) -> int:
    """Drop the oldest-inserted entries until `len(table) <= cap`. Returns how many went. (A dict remembers insertion order; re-insert a key to make it newest.)"""
    drop = len(table) - max(0, cap)
    if drop <= 0:
        return 0
    for key in list(table)[:drop]:
        del table[key]
    return drop


def seen_within(table: dict, key, now: float, window: float, cap: int = 256) -> bool:
    """Has `key` been seen less than `window` seconds ago? True means "skip it". Otherwise it is recorded as seen now (and made the newest entry) and False is
    returned. The table never holds more than `cap` keys."""
    last = table.get(key)
    if last is not None and window > 0 and now - last < window:
        return True
    table.pop(key, None)
    table[key] = now
    cap_newest(table, cap)
    return False


def append_capped(path, text: str, cap: int = 64 * 1024) -> bool:
    """Append `text` to a log that never passes about `cap` bytes: past it, the file is rewritten with its newest half, cut at a line start. Never raises."""
    try:
        path = os.fspath(path)
        if os.path.exists(path) and os.path.getsize(path) > cap:
            with open(path, "rb") as f:
                f.seek(-cap // 2, os.SEEK_END)
                tail = f.read()
            nl = tail.find(b"\n")
            tail = tail[nl + 1:] if nl >= 0 else b""
            fd = os.open(path, os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(tail)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception:
        return False
```

- [ ] **Step 4: Run, expect pass**

Run: `python3 -m unittest tests.test_bounded 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 5: Use it for the tab bar's error map**

In `python/tab_bar.py` find

```python
        now = time.monotonic()
        if now - _ERR_SEEN.get(key, -1e9) < _ERR_DEDUPE:
            return
        _ERR_SEEN[key] = now
```

and replace with

```python
        import kittymux_bounded
        if kittymux_bounded.seen_within(_ERR_SEEN, key, time.monotonic(), _ERR_DEDUPE):
            return
```

- [ ] **Step 6: Check the tab bar still logs and dedupes**

Run: `python3 -m py_compile python/tab_bar.py && bash tests/smoke_state.sh 2>&1 | tail -3`
Expected: `PASS` (the rig fails on `tab_bar-error.log` content if the tab bar raised).

- [ ] **Step 7: Commit**

```bash
git add python/kittymux_bounded.py tests/test_bounded.py python/tab_bar.py
git commit -m "bounded: one place for capped tables and logs; the tab bar's error map uses it"
```

---

### Task 4: reap what a dead kitty leaves

**Files:**
- Modify: `python/pane-state.py` (`_cleanup_stale`)
- Test: `tests/test_pane_state.py`

**Interfaces:**
- Consumes: the file names `panes-<pid>.json`, `scan-<pid>.json` (existing), `decisions-<pid>.jsonl`, `changes-<pid>.json` (`kittymux_scan.decisions_path`, `kittymux_changes.path_for`).
- Produces: all four, and their `.tmp` forms, removed when `/proc/<pid>` is absent; kept whenever `/proc` is unavailable (existing rule).

- [ ] **Step 1: Extend the test**

In `tests/test_pane_state.py::test_stale_files_of_dead_kitties_are_removed` add `f"decisions-{dead}.jsonl"` and `f"changes-{dead}.json"` to the files created, `f"decisions-{alive}.jsonl"` and `f"changes-{alive}.json"` too, and assert after cleanup:

```python
        for name in (f"decisions-{dead}.jsonl", f"changes-{dead}.json"):
            self.assertNotIn(name, left)
        for name in (f"decisions-{alive}.jsonl", f"changes-{alive}.json"):
            self.assertIn(name, left)
```

- [ ] **Step 2: Run, expect failure**

Run: `python3 -m unittest tests.test_pane_state -v 2>&1 | grep -E "stale_files|AssertionError|OK|FAIL"`
Expected: FAIL (`'decisions-… ' unexpectedly found`).

- [ ] **Step 3: Widen the pattern**

In `python/pane-state.py::_cleanup_stale` change

```python
            m = re.fullmatch(r"(?:panes|scan)-(\d+)\.json(?:\.tmp)?", name)
```

to

```python
            m = re.fullmatch(r"(?:panes|scan|changes)-(\d+)\.json(?:\.tmp)?|decisions-(\d+)\.jsonl(?:\.tmp)?", name)
            pid = (m.group(1) or m.group(2)) if m else None
```

and use `pid` in the two places that used `m.group(1)`:

```python
            if m and int(pid) != os.getpid() and not os.path.exists(f"/proc/{pid}"):
```

- [ ] **Step 4: Run**

Run: `python3 -m unittest tests.test_pane_state 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add python/pane-state.py tests/test_pane_state.py
git commit -m "pane-state: reap decisions and changes files of kitties that are gone"
```

---

### Task 5: the scanner's debug logs have a cap

**Files:**
- Modify: `python/kittymux_scan.py` (`_debug`, `_trace`)
- Test: `tests/test_scan.py`

- [ ] **Step 1: Write the test**

Append to `tests/test_scan.py` inside `ScanBase`-derived class `DebugLogTests` (new, in the same file):

```python
class DebugLogTests(ScanBase):
    def test_the_debug_and_trace_logs_are_capped(self):
        with mock.patch.dict(os.environ, {"KITTYMUX_DEBUG": "trace"}):
            for i in range(3000):
                KS._trace(f"event {i} " + "x" * 80)
        path = os.path.join(KS.state_dir(), "scan-trace.log")
        self.assertLess(os.path.getsize(path), 70 * 1024)
        self.assertIn("event 2999", open(path, encoding="utf-8").read())
```

(`mock`, `os` are already imported by the file; if not, add the imports.)

- [ ] **Step 2: Run, expect failure**

Run: `python3 -m unittest tests.test_scan.DebugLogTests -v 2>&1 | tail -4`
Expected: FAIL, size over the limit (about 270 KB).

- [ ] **Step 3: Use `append_capped`**

In `python/kittymux_scan.py` replace the bodies of the two `with open(...) as f: f.write(...)` blocks:

```python
def _debug() -> None:
    if not os.environ.get("KITTYMUX_DEBUG"):
        return
    try:
        import traceback
        import kittymux_bounded
        os.makedirs(state_dir(), mode=0o700, exist_ok=True)
        kittymux_bounded.append_capped(os.path.join(state_dir(), "scan-debug.log"), traceback.format_exc() + "\n")
    except Exception:
        pass
```

```python
def _trace(msg: str) -> None:
    if os.environ.get("KITTYMUX_DEBUG") != "trace":
        return
    try:
        import kittymux_bounded
        kittymux_bounded.append_capped(os.path.join(state_dir(), "scan-trace.log"), f"{time.monotonic():.3f} {msg}\n")
    except Exception:
        pass
```

Keep each function's existing docstring.

- [ ] **Step 4: Run, commit**

Run: `python3 -m unittest tests.test_scan 2>&1 | tail -3` — expect `OK`.

```bash
git add python/kittymux_scan.py tests/test_scan.py
git commit -m "scan: debug and trace logs stop at 64 KB"
```

---

### Task 6: fire-and-forget children: measured, nothing to fix

**Files:** none.

CPython keeps a list of unfinished `Popen` objects whose owner dropped them and polls it on every later `Popen()`, so a finished child is a zombie only until the next spawn. `soak_kitty.sh` counts zombie children of kitty and fails above 2.

**Measured 2026-10-08** (`bash tests/soak_kitty.sh 15`, kitty 0.49.2, Xvfb): `zombies=0` at the start and at the end; file descriptors 21 → 21; threads 36 → 36; resident memory 174 MB → 186 MB (+11 MB, of which +0.8 MB between cycle 10 and the end, so mostly warm-up; the soak's own limit is +60 MB over 40 cycles).

So: **no code**. A helper that reaps children would fix a leak that does not exist, and the next review would then find the helper. The weekly soak (Task 8) keeps measuring it; if `zombies` ever passes 2 there, the fix is one function, written then:

```python
def reap(procs: list) -> list:
    """Drop the finished ones from a list of Popen objects (poll() collects their exit status, so no zombie is left); return the still-running ones."""
    return [p for p in procs if p.poll() is None]
```

- [ ] **Step 1: Record the number**

Put the measurement above in the commit message of Task 8. Nothing to commit here.

---

### Task 7: the guard — every module-level container says why it is safe

**Files:**
- Create: `tests/test_bounded_state.py`

**Interfaces:**
- Consumes: the AST of every `python/*.py` and `python/collectors/*.py`.
- Produces: a failing test that names a new module-level `dict`/`list`/`set`/`deque` and says where to put its reason.

The list below is every empty module-level container that exists today (found by the same scan this test runs), each with the reason it is bounded.

- [ ] **Step 1: Write the test**

```python
"""A module-level dict, list or set that something keeps adding to is a leak waiting for a long enough session. This lists every one that exists and why it is
safe. A new one fails this test: bound it (python/kittymux_bounded.py) or add a line here saying what bounds it."""
import ast
import glob
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")

SAFE = {
    ("kittymux_agents.py", "TOOLS"): "filled once at import from a constant table",
    ("kittymux_barsize.py", "_DEFAULTS"): "a fixed set of named fields; copied into sys.modules['_kittymux_barsize_rt'], never grown",
    ("kittymux_git.py", "_cache"): "capped at _CACHE_MAX, oldest dropped",
    ("kittymux_keymap.py", "_MOD_NAME"): "a copy of a constant table",
    ("pane-state.py", "_state"): "one entry per live window; popped in on_close",
    ("tab_bar.py", "_MEMO"): "emptied at the start of every pass (_per_pass)",
    ("tab_bar.py", "_TITLE_KEY_CACHE"): "rebuilt each pass from the tabs that exist",
    ("tab_bar.py", "_dump_rows"): "test hook (KITTYMUX_BAR_DUMP), one row per tab id, off by default",
    ("tab_bar.py", "_AWI_CACHE"): "pruned past 64 entries by age",
    ("tab_bar.py", "_RISK"): "one key, 'table'",
    ("tab_bar.py", "_MASCOT_OK"): "one key, 'ok'",
    ("tab_bar.py", "_ERR_SEEN"): "capped by kittymux_bounded.seen_within",
}
CONTAINERS = {"dict", "list", "set", "deque", "OrderedDict", "defaultdict"}


def empty_containers():
    found = []
    for path in sorted(glob.glob(os.path.join(ROOT, "python", "*.py")) + glob.glob(os.path.join(ROOT, "python", "collectors", "*.py"))):
        src = open(path, encoding="utf-8").read()
        for node in ast.parse(src).body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
                continue
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            name = getattr(target, "id", None)
            v = node.value
            empty_literal = isinstance(v, (ast.Dict, ast.List, ast.Set)) and not (getattr(v, "keys", None) or getattr(v, "elts", None))
            constructor = isinstance(v, ast.Call) and getattr(v.func, "id", getattr(v.func, "attr", None)) in CONTAINERS
            if name and (empty_literal or constructor):
                found.append((os.path.basename(path), name))
    return found


class BoundedStateTests(unittest.TestCase):
    def test_every_module_level_container_has_a_reason(self):
        unlisted = [c for c in empty_containers() if c not in SAFE]
        self.assertEqual(unlisted, [], "a new module-level container: bound it with kittymux_bounded, then add (file, name): reason to SAFE in tests/test_bounded_state.py")

    def test_the_list_has_no_entries_for_things_that_are_gone(self):
        present = set(empty_containers())
        gone = [k for k in SAFE if k not in present]
        self.assertEqual(gone, [], "remove these from SAFE, they no longer exist")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run**

Run: `python3 -m unittest tests.test_bounded_state -v 2>&1 | tail -6`
Expected: `OK`. If `unlisted` is not empty, the scan found a container this plan missed: read it, bound or justify it, and fix the plan's table in the same commit.

- [ ] **Step 3: Prove it can fail (the control)**

Run: `printf '\n_leak = {}\n' >> python/kittymux_git.py && python3 -m unittest tests.test_bounded_state 2>&1 | grep -E "unlisted|FAIL|OK"; git checkout python/kittymux_git.py`
Expected: `FAIL` naming `('kittymux_git.py', '_leak')`; the checkout restores the file.

- [ ] **Step 4: Commit**

```bash
git add tests/test_bounded_state.py
git commit -m "tests: every module-level container must say why it cannot grow without limit"
```

---

### Task 8: the soak measures disk too, and runs weekly

**Files:**
- Modify: `tests/soak_kitty.sh`
- Create: `.github/workflows/soak.yml`
- Modify: `docs/agents/verify.md`, `CHANGELOG.md`

- [ ] **Step 1: Make the soak assert state-directory size**

In `tests/soak_kitty.sh`, before the final `echo "PASS: …"`, add:

```bash
bytes=$(du -sb "$STATE" 2>/dev/null | cut -f1)
[ "${bytes:-0}" -le $((2 * 1024 * 1024)) ] || fail "the state directory grew to ${bytes} bytes: something logs or caches without a cap ($(ls -S "$STATE" | head -3 | tr '\n' ' '))"
```

and append `, state dir ${bytes} bytes` to the PASS line.

- [ ] **Step 2: Run it once locally**

Run: `bash tests/soak_kitty.sh 15 2>&1 | tail -4`
Expected: `PASS` with a byte count well under 2 MB. If it fails, the file named in the message is a real finding: fix it before widening the limit.

- [ ] **Step 3: Schedule it**

`.github/workflows/soak.yml`:

```yaml
name: soak

on:
  schedule:
    - cron: "17 3 * * 1"      # Mondays, 03:17 UTC
  workflow_dispatch:

jobs:
  soak:
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - name: system deps
        run: |
          sudo apt-get update -qq
          sudo apt-get install -y -qq xvfb xdotool jq fzf fontconfig dbus \
            libgl1-mesa-dri libglx-mesa0 libegl1 libxkbcommon-x11-0 libxcb-xkb1 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 \
            libxcb-image0 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0 libxcursor1 libxi6 libxrandr2
      - name: kitty 0.49.2
        run: |
          curl -fsSL https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin launch=n dest="$HOME/.local" installer="version-0.49.2"
          echo "$HOME/.local/kitty.app/bin" >> "$GITHUB_PATH"
      - name: soak (40 cycles of windows opening, asking, hitting limits and closing)
        run: bash tests/soak_kitty.sh 40
```

- [ ] **Step 4: Docs and changelog**

In `docs/agents/verify.md` under the soak entry add: "Runs weekly in `.github/workflows/soak.yml`; it also fails when the state directory passes 2 MB." and a line for `test_bounded_state`: "every module-level container is listed with the reason it cannot grow". In `CHANGELOG.md` under `### Fixed` add one line: "**A kitty left open for weeks no longer collects state.** The unread-window set, the session journal's in-memory copy, the tab bar's error map and the scanner's debug logs are capped; the decisions and change files of kitties that exited are removed with the rest of their state."

- [ ] **Step 5: Full check and commit**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3 && python3 -m unittest tests.test_docs 2>&1 | tail -2`
Expected: `OK` twice.

```bash
git add tests/soak_kitty.sh .github/workflows/soak.yml docs/agents/verify.md CHANGELOG.md
git commit -m "soak: measure the state directory, run it weekly; document the guard"
```

---

## Self-review

- **Coverage:** the review's leak table items 1 (Task 1), 2 (Task 2), 3 (Task 3), 4 (Task 4), 5 (Task 5), 16 (Task 6: measured, nothing to fix); the "bounded-everything" rule (Task 7); the soak (Task 8). Item 6 (sockets of killed kitties) belongs to the sockets plan.
- **Placeholders:** none; Task 6 is a decision with both branches written out.
- **Names:** `cap_newest`, `seen_within`, `append_capped`, `reap` (Task 6 only), `_journal_prune_memory`, `SAFE` are used identically wherever they appear.
- **Not in this plan:** monotonic clocks (`LIMIT_UNKNOWN_S` and friends) and the inbox lock/fold cost. Both change behaviour and belong with the engine-correctness plan, each with its own burst test.

## Execution

Branch `durability`, one commit per task. Tasks 1, 2 and 4 are independent; 3 must precede 5 (uses `append_capped`) and 7 (lists `_ERR_SEEN` as capped); 6 is a record, not code. Run the rigs named in `AGENTS.md` for the scanner (`smoke_state`, `smoke_inbox`, `smoke_prompts`) before the merge, and read the CI result.
