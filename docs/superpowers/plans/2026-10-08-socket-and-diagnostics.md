# Which kitty, and why did it fail: Implementation Plan

Status: **executed 2026-10-08** (PRs #4 and #6). Deviations: Task 1's table found two real drifts and the shell was changed to match Python (except an inherited `fd:` handle, which stays first in `mux_resolve_socket` because a kitten's own channel cannot be stale); Task 3 left `join` alone (it already validated its values and its tests expect its own usage text); Task 4 exempts the deck chord `ctrl+alt+b` (the docked panel is the same program, so a twin keyed on its command line would close the panel when the chord is pressed in it) and the real-key check showed the toggle for the sessionizer, layout picker and the cwd HUD's `shift+i` variant, but was inconclusive for `ctrl+alt+i` and `ctrl+alt+g` (the overlays exit at once in a rig with no agents); Task 5 left `sessions autosave`, the journal-key resolver and `workflow` on `_target_socket`; Task 2 also logs `workflow` failures and shows the last three in `doctor`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A kittymux command acts on the kitty the user meant, in the shell and in Python alike, and when it cannot, it says why in words that fit what happened, even when it was started by a key and has no terminal to print to.

**Architecture:** Keep the one trusted rule ("a socket we own; the kitty we were started in beats any guess") and make its three implementations (Python `kittymux_sockets`, shell `lib/socket.sh`, `bin/mux-panel`) provably agree with a table test instead of rewriting shell into Python (key-bound shell scripts must stay fast). Put the "no kitty" wording in one pure module, give failed key-bound commands a small log to leave evidence in, parse option values in one place, and close the overlay-stacking gap in the key template by test.

**Tech Stack:** Python 3 (`bin/kittymux` is one file loaded by tests through `SourceFileLoader`), bash, `unittest`, the key template `kittymux-keys.conf.tpl`.

**Spec:** none. Where this came from is below.

## Where this came from

An architecture review of commit 4dbcef7 (CLI, TUI, engines) and the author's report that after "pulling a window out" the sidebar stopped taking clicks, keys stopped navigating, and opening a new kitty window sometimes fixed it. Two causes were found and are already fixed or in review:

- Task 0 (done): the docked panel's `mux-panel` looked for the active kitty at `/tmp/mykitty-<pid>`, while sockets live in `$XDG_RUNTIME_DIR`, so it fell back to the **newest** socket: with a second kitty open it watched and acted on the wrong one (PR #4: `mux_own_socket`, `mux_socket_for_pid`, `mux-panel target`).
- The deck's `t`/`a` froze the panel and kept an exclusive keyboard grab (merged, `tests/test_panel_actions.py`).

## Global Constraints

- A socket is trusted only if it is a real socket owned by the current user (`mux_owned_socket`, `_owned_socket`). No task weakens this.
- A command started inside a kitty acts on THAT kitty, never on "the focused one" (`AGENTS.md`, rules). Focus-guessing is for commands started from outside every kitty.
- Printed output that may be pasted goes through `kittymux_journal.redact_argv`; the new error log stores fixed wording and paths only, never screen text, titles or agent output.
- Every behaviour change has a test that fails before it and passes after (a control).
- `bin/kittymux` is loaded by `tests/test_kittymux_cli.py` with `load()`; new tests there call functions directly and patch `subprocess`/`_run`/`_ls`, so they never touch a real kitty (`AGENTS.md`: a test must never touch another kitty).
- Exit code 2 means "you used it wrong", 1 means "it could not do it" (the convention the CLI already follows).
- Branch `sockets`, one commit per task, fast-forward merge; do not push `main` for this alone (a push deploys the site).

## Review Focus

- Two kitties open, command started from a window-manager bind (no own kitty): it must act on the one with the keyboard focus, not the newest (Task 5).
- Two kitties open, command started by a key inside the OLDER one: it must act on the older one, in shell scripts too (Task 1; the panel case is Task 0).
- `KITTYMUX_SOCKET_DIRS` set (every smoke rig sets it): shell and Python must both honour it (Task 1).
- `spawn --cwd` with no value, `fanout "x" claude --name` with no value: exit 2 and nothing started, not a spawn in the wrong directory (Task 3).
- A key-bound command that fails leaves one line a person can find (`kittymux doctor` shows it), and the log cannot grow without limit (Task 2).
- An overlay opened twice by pressing its chord twice: one overlay, not two (Task 4).

## What was checked

| Review claim | Result |
|---|---|
| Two socket resolvers; layout/sessions/changes/explain/snooze/screenshot use "newest" | **True.** `_target_socket` (own, else newest) vs `_focused_socket` (own, else focused, else newest). Inside a kitty both give the own kitty; they differ only for commands started from outside one (WM binds). |
| Shell, Python and `mux-panel` socket resolution drifted | **True.** `lib/socket.sh` ignored `KITTYMUX_SOCKET_DIRS` and looked in `/tmp` before `$XDG_RUNTIME_DIR` (Python: the reverse); `mux-panel` hard-coded `/tmp`. The first two are fixed for the new functions (PR #4); the rest is Task 1. |
| `_run` drops stderr and the exception class | **True** (`bin/kittymux` `_run`: any exception becomes `(1, "")`). |
| Six wordings of "no socket" | **True**: 14 sites (`grep -n "no kitty remote-control socket found" bin/kittymux`), only `doctor`'s names the fix. |
| `hooks --settings` without a value is a traceback | **True** (`argv[argv.index("--settings") + 1]`). |
| `kittymux panel summon|dock` rejected | **True and fixed** (PR #3). |
| Five parsers swallow a dangling value | **True** for `sessions new`, `spawn --cwd`, `fanout`, `explain --window`; `join` is the correct template (it validates). |
| `sessions restore` spawns `kitty` unguarded | **True** (`subprocess.Popen(["kitty", "--session", …])`: `FileNotFoundError` if kitty is not on PATH, and "opening … in a new kitty" is printed even if it dies at once). The second half is not fixable without waiting; only the first is in scope. |
| Overlays missing close-binds | **True** for 11 of the 14 `--type=overlay` binds in the template, and for the deck's `kitten` bind (12 chords, listed in Task 4). |

## File Structure

- Create `python/kittymux_diag.py` — pure: `SETUP_HINT`, `no_socket_message(cmd, dirs)`, `describe_failure(rc, err, exc)`, `log_failure(state_dir, cmd, text, now)`.
- Create `python/kittymux_cliargs.py` — pure: `UsageError`, `take(it, flag)`.
- Create `tests/test_socket_parity.py`, `tests/test_diag.py`, `tests/test_cliargs.py`.
- Modify `lib/socket.sh` (`mux_own_socket`, `mux_kitty_sockets`), `bin/kittymux` (the sites listed per task), `kittymux-keys.conf.tpl`, `tests/test_keys_leader.py`, `tests/test_kittymux_cli.py`, `docs/agents/conventions.md`, `docs/users/troubleshooting.mdx`, `CHANGELOG.md`.

---

### Task 0 (done): the panel watches the kitty that started it

PR #4 (`panel-target`). Listed so the numbering in the review matches. Nothing to do.

---

### Task 1: one contract for "which kitty", checked by a table

**Files:**
- Create: `tests/test_socket_parity.py`
- Modify: `lib/socket.sh` (`mux_own_socket`, `mux_kitty_sockets`)

**Interfaces:**
- Consumes: Python `kittymux_sockets.own(directories, owned, env, ppid)` and `target(own_socket, directories, owned, env)`; shell `mux_own_socket`, `mux_resolve_socket`, `mux_kitty_sockets`.
- Produces: shell and Python give the same answer for the same filesystem and environment in every scenario of the table.

The Python order is: a socket named for the parent pid in any socket directory, then a `KITTY_LISTEN_ON` hint (an `fd:` handle or an owned `unix:` path), then `KITTY_PID`. The shell `mux_own_socket` has parent and `KITTY_PID` but not the hint; `mux_kitty_sockets` lists only `/tmp` and `$XDG_RUNTIME_DIR` and ignores `KITTYMUX_SOCKET_DIRS`.

- [ ] **Step 1: Write the table test**

`tests/test_socket_parity.py`:

```python
"""The shell and Python resolvers answer "which kitty" from the same rules. They are two implementations on purpose (key-bound shell scripts must not start
python for this), so this table is what keeps them from drifting again: the same sockets, the same environment, the same answer."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "python"))
import kittymux_sockets as S  # noqa: E402

LIB = os.path.join(ROOT, "lib", "socket.sh")


def owned(path):
    return S.is_owned_socket(path)


class Rig:
    """Real sockets in temporary directories; `run` asks both resolvers the same question."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = lambda name: os.path.join(self.tmp.name, name)
        self.socks = []

    def make(self, directory, name):
        os.makedirs(directory, exist_ok=True)
        s = socket.socket(socket.AF_UNIX)
        path = os.path.join(directory, name)
        s.bind(path)
        self.socks.append(s)
        time.sleep(0.02)                                   # distinct mtimes: "newest" must be decidable
        return path

    def close(self):
        for s in self.socks:
            s.close()
        self.tmp.cleanup()

    def python(self, dirs, env, ppid):
        own = lambda: S.own(dirs, owned, env, ppid)       # noqa: E731
        return own() or "", S.target(own, dirs, owned, env) or ""

    def shell(self, dirs, env):
        full = {"PATH": os.environ["PATH"], "KITTYMUX_SOCKET_DIRS": ":".join(dirs), **env}
        def ask(fn):
            p = subprocess.run(["bash", "-c", f'source "{LIB}"; {fn}'], env=full, capture_output=True, text=True)
            return p.stdout if p.returncode == 0 else ""
        return ask("mux_own_socket"), ask("mux_resolve_socket")


class ParityTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)

    def agree(self, dirs, env, expect_own, expect_target):
        ppid = os.getpid()                                  # a bash -c started by this process has this pid as its parent
        py = self.rig.python(dirs, env, ppid)
        sh = self.rig.shell(dirs, env)
        self.assertEqual(py, sh, "python and shell disagree")
        self.assertEqual(py, (expect_own, expect_target))

    def test_the_kitty_that_started_us_beats_a_newer_one(self):
        run = self.rig.dir("run")
        mine = self.rig.make(run, f"mykitty-{os.getpid()}")
        self.rig.make(run, "mykitty-4243")
        self.agree([run], {}, "unix:" + mine, "unix:" + mine)

    def test_kitty_pid_names_the_kitty_when_the_parent_is_not_one(self):
        run = self.rig.dir("run")
        older = self.rig.make(run, "mykitty-4242")
        self.rig.make(run, "mykitty-4243")
        self.agree([run], {"KITTY_PID": "4242"}, "unix:" + older, "unix:" + older)

    def test_an_owned_listen_on_hint_is_used_before_kitty_pid(self):
        run = self.rig.dir("run")
        hinted = self.rig.make(run, "mykitty-4244")
        self.rig.make(run, "mykitty-4242")
        self.agree([run], {"KITTY_LISTEN_ON": "unix:" + hinted, "KITTY_PID": "4242"}, "unix:" + hinted, "unix:" + hinted)

    def test_a_stale_listen_on_hint_is_ignored(self):
        run = self.rig.dir("run")
        real = self.rig.make(run, "mykitty-4242")
        self.agree([run], {"KITTY_LISTEN_ON": "unix:" + os.path.join(run, "gone"), "KITTY_PID": "4242"}, "unix:" + real, "unix:" + real)

    def test_started_outside_every_kitty_the_answer_is_the_newest(self):
        run = self.rig.dir("run")
        self.rig.make(run, "mykitty-4242")
        newest = self.rig.make(run, "mykitty-4243")
        self.agree([run], {}, "", "unix:" + newest)

    def test_the_first_directory_wins_for_a_kitty_with_a_socket_in_two(self):
        private, shared = self.rig.dir("private"), self.rig.dir("shared")
        a = self.rig.make(private, "mykitty-4242")
        self.rig.make(shared, "mykitty-4242")
        self.agree([private, shared], {"KITTY_PID": "4242"}, "unix:" + a, "unix:" + a)

    def test_nothing_anywhere_is_nothing(self):
        empty = self.rig.dir("empty-but-real")
        os.makedirs(empty)
        self.agree([empty], {}, "", "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and read the failures**

Run: `python3 -m unittest tests.test_socket_parity -v 2>&1 | tail -30`
Expected: FAIL in `test_an_owned_listen_on_hint_is_used_before_kitty_pid` (shell has no hint step) and in `test_started_outside_every_kitty_the_answer_is_the_newest` / `test_the_first_directory_wins…` if `mux_kitty_sockets` ignores `KITTYMUX_SOCKET_DIRS`. Each failure is a real drift; if all pass, the table is not asking enough: add scenarios until one fails, then stop adding.

- [ ] **Step 3: Align the shell**

In `lib/socket.sh` change `mux_own_socket` to Python's order:

```bash
mux_own_socket() {
    mux_socket_for_pid "$PPID" && return 0
    if [[ "${KITTY_LISTEN_ON:-}" =~ ^fd:[0-9]+$ ]]; then printf '%s' "$KITTY_LISTEN_ON"; return 0; fi
    if [[ "${KITTY_LISTEN_ON:-}" == unix:* ]] && mux_owned_socket "${KITTY_LISTEN_ON#unix:}"; then printf '%s' "$KITTY_LISTEN_ON"; return 0; fi
    mux_socket_for_pid "${KITTY_PID:-}" && return 0
    return 1
}
```

and make `mux_kitty_sockets` list from `mux_socket_dirs` instead of the hard-coded pair:

```bash
mux_kitty_sockets() {
    local s real seen=$'\n' d
    while IFS= read -r s; do
        mux_owned_socket "$s" || continue
        real=$(readlink -f -- "$s" 2>/dev/null || printf '%s' "$s")
        case "$seen" in *$'\n'"$real"$'\n'*) continue ;; esac
        seen+="$real"$'\n'
        printf '%s\n' "$s"
    done < <(while IFS= read -r d; do ls -t "$d"/mykitty-* 2>/dev/null; done < <(mux_socket_dirs))
}
```

Keep `mux_resolve_socket` using `mux_own_socket`'s first step as it does today (`/tmp/mykitty-$PPID` etc. become `mux_socket_for_pid "$PPID"`), so its behaviour for the legacy `/tmp/kitty-<pid>` spelling is preserved: leave that line exactly as is and only replace the loop above it if the table requires it.

- [ ] **Step 4: Run the table and the shell tests**

Run: `python3 -m unittest tests.test_socket_parity 2>&1 | tail -3 && bash tests/test_socket_lib.sh 2>&1 | grep -c '^FAIL'`
Expected: `OK` and `0`.

- [ ] **Step 5: shellcheck and commit**

Run: `shellcheck -S warning lib/socket.sh bin/mux-panel`
Expected: no output.

```bash
git add lib/socket.sh tests/test_socket_parity.py
git commit -m "socket lib: the shell resolver follows the Python one, and a table test keeps it so"
```

---

### Task 2: one "no kitty" message, and evidence when a key-bound command fails

**Files:**
- Create: `python/kittymux_diag.py`, `tests/test_diag.py`
- Modify: `bin/kittymux` (the 14 print sites; `_run`; `doctor`)
- Modify: `docs/users/troubleshooting.mdx`

**Interfaces:**
- Produces:
  - `SETUP_HINT: str` — "set allow_remote_control socket-only and listen_on unix:${XDG_RUNTIME_DIR}/mykitty in kitty.conf, then restart kitty".
  - `no_socket_message(cmd: str, dirs: list[str]) -> str` — one line: `kittymux <cmd>: no kitty remote-control socket found (looked in <dirs>). <SETUP_HINT>; kittymux doctor checks it.`
  - `describe_failure(rc: int, err: str, exc: BaseException | None) -> str` — a short fixed-vocabulary reason: `timed out`, `kitty is not on PATH`, `kitty refused the command (remote control is off for this window)`, or `kitty @ exited <rc>: <first line of err, control characters removed, 160 characters>`.
  - `log_failure(state_dir: str, cmd: str, text: str, now: float) -> None` — appends `<iso time> <cmd>: <text>` to `cli-errors.log` (0600, `kittymux_bounded.append_capped`, 32 KB), never raises.
  - `recent_failures(state_dir: str, limit: int = 5) -> list[str]`.

- [ ] **Step 1: Write the tests**

`tests/test_diag.py`:

```python
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_diag as D  # noqa: E402


class MessageTests(unittest.TestCase):
    def test_the_message_names_the_command_the_places_and_the_fix(self):
        m = D.no_socket_message("spawn", ["/run/user/1000", "/tmp"])
        self.assertIn("kittymux spawn", m)
        self.assertIn("/run/user/1000", m)
        self.assertIn("allow_remote_control socket-only", m)
        self.assertNotIn("\n", m)

    def test_a_hostile_directory_name_cannot_inject_lines_or_escapes(self):
        m = D.no_socket_message("x", ["/tmp/a\nb\x1b[2J"])
        self.assertNotIn("\n", m)
        self.assertNotIn("\x1b", m)


class DescribeTests(unittest.TestCase):
    def test_each_kind_of_failure_has_its_own_words(self):
        self.assertEqual(D.describe_failure(1, "", subprocess.TimeoutExpired("kitty", 3)), "timed out")
        self.assertEqual(D.describe_failure(1, "", FileNotFoundError()), "kitty is not on PATH")
        self.assertIn("exited 1: boom", D.describe_failure(1, "boom\nsecond line", None))

    def test_stderr_is_one_clean_bounded_line(self):
        text = D.describe_failure(1, "x" * 500 + "\x1b[31m", None)
        self.assertLessEqual(len(text), 200)
        self.assertNotIn("\x1b", text)


class LogTests(unittest.TestCase):
    def test_a_failure_is_logged_private_and_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(3000):
                D.log_failure(d, "nav", f"timed out {i}", 1_700_000_000.0 + i)
            path = os.path.join(d, "cli-errors.log")
            self.assertLess(os.path.getsize(path), 40 * 1024)
            self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
            self.assertTrue(D.recent_failures(d, 2)[-1].endswith("nav: timed out 2999"))

    def test_logging_never_raises(self):
        D.log_failure("/proc/not/a/dir", "nav", "x", 0.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, expect `ModuleNotFoundError`**

Run: `python3 -m unittest tests.test_diag 2>&1 | tail -2`

- [ ] **Step 3: Write the module**

`python/kittymux_diag.py`:

```python
"""What kittymux says when it cannot reach a kitty, in one place. Pure; no kitty imports.

A command bound to a key has no terminal: its stderr goes nowhere, so a failure used to look like "the key did nothing". `log_failure` leaves one line where
`kittymux doctor` shows it. Only fixed wording, directory names and the first line of kitty's own error are stored: never screen text, titles or agent output."""
from __future__ import annotations

import os
import subprocess
import time

SETUP_HINT = "set allow_remote_control socket-only and listen_on unix:${XDG_RUNTIME_DIR}/mykitty in kitty.conf, then restart kitty"
LOG = "cli-errors.log"
_CTRL = {c: " " for c in list(range(0, 32)) + [127] + list(range(0x80, 0xA0))}


def _clean(text, limit: int) -> str:
    return " ".join(str(text).translate(_CTRL).split())[:limit]


def no_socket_message(cmd: str, dirs: list[str]) -> str:
    where = ", ".join(_clean(d, 80) for d in dirs) or "nowhere (no socket directory exists)"
    return f"kittymux {_clean(cmd, 24)}: no kitty remote-control socket found (looked in {where}). {SETUP_HINT}; `kittymux doctor` checks it."


def describe_failure(rc: int, err: str, exc: BaseException | None) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return "timed out"
    if isinstance(exc, FileNotFoundError):
        return "kitty is not on PATH"
    first = _clean((err or "").splitlines()[0] if (err or "").strip() else "", 160)
    return f"kitty @ exited {rc}" + (f": {first}" if first else "")


def log_failure(state_dir: str, cmd: str, text: str, now: float | None = None) -> None:
    try:
        import kittymux_bounded
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() if now is None else now))
        kittymux_bounded.append_capped(os.path.join(state_dir, LOG), f"{stamp} {_clean(cmd, 24)}: {_clean(text, 240)}\n", cap=32 * 1024)
    except Exception:
        pass


def recent_failures(state_dir: str, limit: int = 5) -> list[str]:
    try:
        with open(os.path.join(state_dir, LOG), encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n") for line in f.readlines()[-limit:]]
    except OSError:
        return []
```

This module uses `kittymux_bounded` from the durability plan (Task 3 there). If that plan has not landed, implement Task 3 of it first; the two plans are independent except for this one function.

- [ ] **Step 4: Run, expect pass**

Run: `python3 -m unittest tests.test_diag 2>&1 | tail -2`
Expected: `OK`.

- [ ] **Step 5: Use it at every site**

In `bin/kittymux`:

1. Add near the top helpers:

```python
def _no_socket(cmd: str) -> int:
    """Say there is no kitty to talk to, in the one wording, and leave a line for a command that had no terminal. Exit code 1."""
    import kittymux_diag
    msg = kittymux_diag.no_socket_message(cmd, _socket_dirs())
    print(msg, file=sys.stderr)
    if not sys.stderr.isatty():
        kittymux_diag.log_failure(kittymux_layout.state_dir(), cmd, "no kitty socket")
    return 1
```

2. For each line of `grep -n "no kitty remote-control socket found\|no trusted kitty socket" bin/kittymux` that is a `print(..., file=sys.stderr)` followed by `return N`, replace the print and the return with `return _no_socket("<command name>")`. The command names are the word after `kittymux ` in the old text (`layout`, `sessions`, `spawn`, `reopen`, `fanout`, `changes`, `snooze`, `explain`, `screenshot`, `workflow`; `act` keeps its own "no kitty to act on" because it also covers a rejected payload). Do `doctor` last: its `r.warning("no kitty remote-control socket found", "set …")` becomes `r.warning("no kitty remote-control socket found", kittymux_diag.SETUP_HINT)`.

3. In `workflow_cmd`, the `except (OSError, ValueError, TypeError, KeyError)` branch also calls `kittymux_diag.log_failure(kittymux_layout.state_dir(), "workflow " + argv[0], <str(exc)>)` (bind the exception with `as exc`; `str(exc)` here is one of this module's own fixed `ValueError` texts such as "cannot identify source pane", never window content).

4. In `doctor`, after the live-kitty section, add:

```python
    recent = kittymux_diag.recent_failures(kittymux_layout.state_dir(), 3)
    if recent:
        r.warning("recent commands that could not reach a kitty (newest last)", "\n      ".join(recent))
```

- [ ] **Step 6: Guard against a seventh wording**

Append to `tests/test_kittymux_cli.py`:

```python
class OneNoSocketMessageTests(unittest.TestCase):
    def test_the_wording_lives_in_kittymux_diag_only(self):
        src = open(os.path.join(ROOT, "bin", "kittymux"), encoding="utf-8").read()
        self.assertEqual(src.count("no kitty remote-control socket found"), 1, "only doctor's warning title may carry the phrase; use _no_socket()")
        self.assertNotIn("no trusted kitty socket", src)

    def test_no_socket_prints_one_line_and_returns_1(self):
        m = load()
        with mock.patch.object(m, "_socket_dirs", return_value=["/x"]), mock.patch("sys.stderr") as err, mock.patch.object(err, "isatty", return_value=True, create=True):
            self.assertEqual(m._no_socket("spawn"), 1)
```

- [ ] **Step 7: Run everything, document, commit**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`. Add to `docs/users/troubleshooting.mdx` a short entry "A key does nothing": `kittymux doctor` lists the last commands that could not reach a kitty, `cli-errors.log` in the state directory is the same list, and the setup line. Add a `CHANGELOG.md` Fixed line. Run `python3 -m unittest tests.test_docs`.

```bash
git add -A && git commit -m "cli: one no-kitty message, and a log line for a failed command that had no terminal"
```

---

### Task 3: option values are checked in one place

**Files:**
- Create: `python/kittymux_cliargs.py`, `tests/test_cliargs.py`
- Modify: `bin/kittymux` (`sessions_new`, `spawn_cmd`, `fanout_cmd`, `explain`, `hooks`, `join_cmd`, and `main`'s dispatch)
- Test: `tests/test_kittymux_cli.py`

**Interfaces:**
- Produces: `UsageError(Exception)` and `take(it, flag, *, allow=None) -> str` — the next element of the iterator, or `UsageError(f"{flag} needs a value")` when there is none, when it starts with `--`, or (with `allow`) when it is not one of the allowed values.

- [ ] **Step 1: Write the tests**

`tests/test_cliargs.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_cliargs as A  # noqa: E402


class TakeTests(unittest.TestCase):
    def test_returns_the_next_value(self):
        self.assertEqual(A.take(iter(["/tmp/x"]), "--cwd"), "/tmp/x")

    def test_a_missing_value_is_a_usage_error(self):
        with self.assertRaisesRegex(A.UsageError, "--cwd needs a value"):
            A.take(iter([]), "--cwd")

    def test_another_option_is_not_a_value(self):
        with self.assertRaisesRegex(A.UsageError, "--name needs a value"):
            A.take(iter(["--base"]), "--name")

    def test_a_single_dash_value_is_fine(self):
        self.assertEqual(A.take(iter(["-"]), "--cwd"), "-")

    def test_allowed_values_are_enforced(self):
        self.assertEqual(A.take(iter(["auto"]), "--side", allow=("auto", "right")), "auto")
        with self.assertRaisesRegex(A.UsageError, "--side needs one of: auto, right"):
            A.take(iter(["left"]), "--side", allow=("auto", "right"))


if __name__ == "__main__":
    unittest.main()
```

Append to `tests/test_kittymux_cli.py`:

```python
class DanglingValueTests(unittest.TestCase):
    """An option that ends the command line with no value used to be read as an empty string: `spawn claude --cwd` started claude in the current directory
    (or `/`), `sessions new x --cwd` saved a template for ''. Each is now a usage error (exit 2) and starts nothing."""

    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def run_cmd(self, argv):
        with mock.patch.object(self.m, "_run", side_effect=AssertionError("must not reach kitty")), \
             mock.patch.object(self.m.subprocess, "Popen", side_effect=AssertionError("must not start a process")), \
             mock.patch("sys.stderr") as err:
            code = self.m.main(argv)
        return code, "".join(c.args[0] for c in err.write.call_args_list)

    def test_every_dangling_option_is_exit_2_with_its_name(self):
        for argv, flag in ((["spawn", "claude", "--cwd"], "--cwd"), (["sessions", "new", "x", "--cwd"], "--cwd"),
                           (["sessions", "new", "x", "--agent"], "--agent"), (["fanout", "do it", "claude", "--name"], "--name"),
                           (["fanout", "do it", "claude", "--base"], "--base"), (["explain", "--window"], "--window"),
                           (["hooks", "--settings"], "--settings"), (["join", "--to"], "--to")):
            code, err = self.run_cmd(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(f"{flag} needs a value", err, argv)
```

- [ ] **Step 2: Run, expect failures**

Run: `python3 -m unittest tests.test_cliargs tests.test_kittymux_cli.DanglingValueTests 2>&1 | tail -12`
Expected: import error for the first; for the second, several of the eight commands fail (`hooks --settings` raises `IndexError`).

- [ ] **Step 3: Write the module**

`python/kittymux_cliargs.py`:

```python
"""Reading option values off a command line, in one place. Pure."""
from __future__ import annotations


class UsageError(Exception):
    """The command was used wrongly: print this, exit 2, do nothing else."""


def take(it, flag: str, *, allow=None) -> str:
    """The value that follows `flag`. A missing one, another `--option`, or (when `allow` is given) anything not in it is a usage error. A lone `-` is a value."""
    value = next(it, None)
    if value is None or value.startswith("--"):
        raise UsageError(f"{flag} needs a value")
    if allow is not None and value not in allow:
        raise UsageError(f"{flag} needs one of: {', '.join(allow)}")
    return value
```

- [ ] **Step 4: Use it**

In `bin/kittymux` add `import kittymux_cliargs` where the other helper modules are imported at the top of the file, then:

- `sessions_new`: `opts[a[2:]] = kittymux_cliargs.take(it, a)`
- `spawn_cmd`: `cwd = os.path.abspath(os.path.expanduser(kittymux_cliargs.take(it, a)))`
- `fanout_cmd`: `opts[a[2:]] = kittymux_cliargs.take(it, a)`
- `explain`: `wid = kittymux_cliargs.take(it, a)`; `--last` keeps its `int()` check but takes through `take`
- `join_cmd`: `--to` → `take(it, a)` then the `isdigit` check; `--side` → `take(it, a, allow=("right", "below", "left", "above", "auto"))`
- `hooks`: replace `argv[argv.index("--settings") + 1]` with an iterator walk using `take`.
- In `main`'s dispatch wrapper, catch the error once: wrap the command call in `try: … except kittymux_cliargs.UsageError as e: print(f"kittymux {cmd}: {e}", file=sys.stderr); return 2`.

- [ ] **Step 5: Guard `sessions restore`'s spawn**

Append to `DanglingValueTests`'s file a second class:

```python
class RestoreSpawnTests(unittest.TestCase):
    def test_a_missing_kitty_binary_is_exit_1_and_does_not_claim_success(self):
        m = load()
        with tempfile.TemporaryDirectory() as d:
            session = os.path.join(d, "x.kitty-session")
            open(session, "w").close()
            with mock.patch.object(m, "_find_session", return_value=session), mock.patch.object(m, "_target_socket", return_value=None), \
                 mock.patch.object(m.subprocess, "Popen", side_effect=FileNotFoundError("kitty")), \
                 mock.patch("sys.stdout") as out, mock.patch("sys.stderr"):
                code = m.sessions_restore([session])
        self.assertEqual(code, 1)
        self.assertNotIn("opening", "".join(c.args[0] for c in out.write.call_args_list))
```

(add `import tempfile` to the test file's imports). In `bin/kittymux::sessions_restore` wrap the `subprocess.Popen([...])` and the `print(f"{OK} opening …")` in:

```python
    try:
        subprocess.Popen(["kitty", "--session", path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        print(f"{BAD} could not start kitty: {e.strerror or e}", file=sys.stderr)
        return 1
    print(f"{OK} opening {path} in a new kitty")
    return 0
```

- [ ] **Step 6: Run, expect pass; run the whole suite**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "cli: an option with no value is a usage error (exit 2), checked in one place"
```

---

### Task 4: every overlay closes with its own chord

**Files:**
- Modify: `kittymux-keys.conf.tpl`
- Test: `tests/test_keys_leader.py`

The template's own rule (`AGENTS.md`, Overlay UIs): an overlay gets a title and a `map --when-focus-on title:<t> <same chord> close_window`, or pressing the chord again stacks a second overlay. Today two have it (`kittymux-usage`, `kittymux-pick`, `kittymux-keys`, and the kittens by `cmdline:`) and these do not: `ctrl+alt+i`, `ctrl+alt+shift+i`, `ctrl+alt+g`, `ctrl+alt+shift+g`, `ctrl+alt+semicolon`, `ctrl+alt+shift+l`, `ctrl+shift+space`, `ctrl+alt+shift+n`, `ctrl+alt+shift+m`, `ctrl+alt+shift+s`, `ctrl+alt+shift+p`, and `ctrl+alt+b` (the deck is a `kitten`, matched by `cmdline:sidebar-kit.py`).

- [ ] **Step 1: Write the test that lists them**

Append to `tests/test_keys_leader.py`:

```python
class OverlayCloseBindTests(unittest.TestCase):
    """Pressing an overlay's chord a second time must close it (or at least not stack another): every `--type=overlay` bind and every `kitten` bind needs
    a `--when-focus-on` twin on the same chord that runs `close_window`."""

    def binds(self):
        tpl = open(os.path.join(ROOT, "kittymux-keys.conf.tpl"), encoding="utf-8").read()
        opens, closes = {}, set()
        for line in tpl.splitlines():
            parts = line.split(None, 3)
            if len(parts) >= 3 and parts[0] == "map" and parts[1] != "--when-focus-on":
                action = line.split(None, 2)[2]
                if action.startswith("launch --type=overlay") or action.startswith("kitten "):
                    opens[parts[1]] = action
            elif len(parts) >= 4 and parts[0] == "map" and parts[1] == "--when-focus-on" and line.rstrip().endswith("close_window"):
                closes.add(line.split()[3])
        return opens, closes

    def test_every_overlay_chord_has_a_close_twin(self):
        opens, closes = self.binds()
        missing = sorted(chord for chord in opens if chord not in closes)
        self.assertEqual(missing, [], "these open an overlay but a second press would stack another: add `map --when-focus-on title:<t> <chord> close_window` and a --title")
```

- [ ] **Step 2: Run, expect the twelve chords above in the failure**

Run: `python3 -m unittest tests.test_keys_leader.OverlayCloseBindTests -v 2>&1 | tail -6`

- [ ] **Step 3: Add titles and twins**

For each chord, add `--title kittymux-<name>` to its `launch --type=overlay` line (names: `cwd` for both `i` binds, `agents`, `agent-new`, `send`, `layout`, `sessionizer` for both sessionizer binds, `movetab`, `save`, `projects`) and, below the line, one twin per chord:

```
map --when-focus-on title:kittymux-cwd ctrl+alt+i close_window
map --when-focus-on title:kittymux-cwd ctrl+alt+shift+i close_window
```

and so on. For the deck: `map --when-focus-on cmdline:sidebar-kit.py ctrl+alt+b close_window` (the same form the palette, join and peek kittens use).

- [ ] **Step 4: Run the keys tests and the rigs that press keys**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3; bash tests/smoke_keys.sh 2>&1 | tail -2; bash tests/smoke_spawn.sh 2>&1 | tail -2`
Expected: `OK`, `PASS`, `PASS`. Also run `bash tests/smoke_peek.sh` and `bash tests/smoke_palette.sh`.

- [ ] **Step 5: README and keymap overlay stay in step**

Run: `python3 -m unittest tests.test_docs tests.test_keys_leader 2>&1 | tail -3` — the README table test must still pass (no chord was added or removed, only twins).

```bash
git add -A && git commit -m "keys: every overlay chord has a close twin, so a second press cannot stack another overlay"
```

---

### Task 5: a command started outside every kitty acts on the focused one

**Files:**
- Modify: `bin/kittymux` (the call sites of `_target_socket()` named below)
- Test: `tests/test_kittymux_cli.py`

`_target_socket()` is own → newest. `_focused_socket()` is own → the kitty with the keyboard focus → newest. Inside a kitty they agree; from a window-manager bind they do not, and "newest" is the wrong answer there: a scratch terminal opened a minute ago would receive `layout`, `snooze`, `screenshot`, `changes`.

- [ ] **Step 1: Write the test**

```python
class FocusedBeatsNewestTests(unittest.TestCase):
    """Started from outside every kitty (a WM bind): two kitties, the OLDER one has the keyboard focus. The commands below must act on it."""

    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def test_commands_started_outside_a_kitty_follow_the_focus(self):
        older, newer = "unix:/run/user/1000/mykitty-100", "unix:/run/user/1000/mykitty-200"
        data = {older: [{"is_focused": True, "tabs": []}], newer: [{"is_focused": False, "tabs": []}]}
        for fn in ("layout", "sessions_save", "sessions_list", "sessions_restore", "changes_cmd", "snooze", "explain", "screenshot", "dim"):
            src = open(os.path.join(ROOT, "bin", "kittymux"), encoding="utf-8").read()
            body = src[src.index(f"def {fn}("):]
            body = body[:body.index("\ndef ", 1)]
            self.assertNotIn("_target_socket()", body, f"{fn} must use _focused_socket(): from a WM bind _target_socket() is 'the newest kitty'")
        with mock.patch.object(self.m, "_own_kitty_socket", return_value=None), \
             mock.patch.object(self.m, "_sockets", return_value=[newer, older]), \
             mock.patch.object(self.m, "_ls", side_effect=lambda s: data[s]), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KITTYMUX_TARGET", None)
            self.assertEqual(self.m._focused_socket(), older)
```

- [ ] **Step 2: Run, expect failure naming the first function**

Run: `python3 -m unittest tests.test_kittymux_cli.FocusedBeatsNewestTests 2>&1 | tail -5`
Expected: FAIL: `layout must use _focused_socket()`.

- [ ] **Step 3: Switch the sites**

Replace `_target_socket()` with `_focused_socket()` in `layout`, `sessions_save`, `sessions_list`, `sessions_restore`, `changes_cmd`, `snooze`, `explain` (the single-kitty branch), `screenshot` and `dim`. Leave `workflow_cmd` (always started by a key inside a kitty, so "own" always answers), `sessions_autosave` and `_resolve_journal_key` (offline or journal-only) and `sessions` (dispatch) alone, and say so in the commit message. `_focused_socket` is defined later in the file than `layout`: that is fine in Python (resolved at call time).

- [ ] **Step 4: Run the suite and the rigs that use these commands**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3; bash tests/smoke_resume.sh 2>&1 | tail -2; bash tests/smoke_changes.sh 2>&1 | tail -2; bash tests/smoke_extras.sh 2>&1 | tail -2`
Expected: `OK` and `PASS` ×3.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "cli: commands started from outside a kitty act on the focused one, not the newest"
```

---

### Task 6: say so when a command had to guess

**Files:**
- Modify: `python/kittymux_sockets.py` (`target` gains a sibling), `bin/kittymux` (`_target_socket`, `_focused_socket`)
- Create: `tests/test_sockets_how.py`

- [ ] **Step 1: Test**

`tests/test_sockets_how.py`:

```python
import os
import socket
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_sockets as S  # noqa: E402


class TargetHowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.socks = []
        self.addCleanup(lambda: [s.close() for s in self.socks])

    def sock(self, name):
        s = socket.socket(socket.AF_UNIX)
        path = os.path.join(self.tmp.name, name)
        s.bind(path)
        self.socks.append(s)
        time.sleep(0.02)                                          # distinct mtimes: "newest" must be decidable
        return path

    def test_target_says_how_it_chose(self):
        older, newer = self.sock("mykitty-100"), self.sock("mykitty-200")
        dirs = [self.tmp.name]
        self.assertEqual(S.target_how(lambda: None, dirs, S.is_owned_socket, {}), ("unix:" + newer, "newest"))
        self.assertEqual(S.target_how(lambda: "unix:" + older, dirs, S.is_owned_socket, {}), ("unix:" + older, "own"))
        self.assertEqual(S.target_how(lambda: None, dirs, S.is_owned_socket, {"KITTYMUX_TARGET": "unix:" + older}), ("unix:" + older, "explicit"))
        self.assertEqual(S.target_how(lambda: None, [], S.is_owned_socket, {}), (None, "none"))

    def test_target_still_returns_only_the_socket(self):
        newer = self.sock("mykitty-200")
        self.assertEqual(S.target(lambda: None, [self.tmp.name], S.is_owned_socket, {}), "unix:" + newer)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 1b: Run, expect failure**

Run: `python3 -m unittest tests.test_sockets_how 2>&1 | tail -3`
Expected: `AttributeError: module 'kittymux_sockets' has no attribute 'target_how'`.

- [ ] **Step 2: Implement**

In `python/kittymux_sockets.py` split `target` into `target_how(own_socket, directories, owned, env=None) -> tuple[str | None, str]` returning `(socket, "explicit" | "own" | "newest" | "none")` and keep `target(...)` as `return target_how(...)[0]`.

In `bin/kittymux`, make `_focused_socket` and `_target_socket` write one stderr line only when stderr is a terminal and the reason is `newest` or `focused`: `kittymux: acting on kitty <pid> (the newest one: not started inside a kitty)`, with the pid from `_socket_pid`. Commands run by a key never print it (no terminal), so there is no noise where nobody can read it.

- [ ] **Step 3: Run, commit**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`.

```bash
git add -A && git commit -m "sockets: a command that had to guess its kitty says which one"
```

---

## Self-review

- **Coverage:** review items 1, 2 (done), 4 → Task 3; 3 (`sessions restore`'s unguarded spawn) → Task 3, Step 5; 5 → Tasks 5 and 6; 6 → Task 2; 7 → Task 1; UX-05 → Task 2; UX-15 → Task 4; UX-06 → Task 6.
- **Left out, with reasons:** UX-12 (docs second source) and UX-08 (quiet-model confusion) were not verified against the code in this pass and change documentation or output wording, not correctness: they need their own look. Splitting `bin/kittymux` is not a task: Tasks 2 and 3 move the two things that most needed a home (messages, option parsing) into pure modules, and further splits happen when a command is next touched.
- **Names:** `_no_socket`, `no_socket_message`, `describe_failure`, `log_failure`, `recent_failures`, `take`, `UsageError`, `target_how`, `mux_own_socket`, `mux_socket_for_pid`, `mux_socket_dirs` are spelled the same wherever used.
- **Order:** Task 1 first (everything else assumes one contract); Task 2 needs `kittymux_bounded` from the durability plan; Tasks 3–6 are independent of each other.

## Execution

Branch `sockets`, one commit per task. Before the merge run the rigs `AGENTS.md` names for keys and sockets: `smoke_keys`, `smoke_spawn`, `smoke_panes`, `smoke_legacy_socket`, `smoke_peek`, `smoke_palette`, and read the CI result for both kitty versions.
