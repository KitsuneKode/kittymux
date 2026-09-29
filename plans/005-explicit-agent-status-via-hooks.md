# Plan 005: Replace the "title went quiet" status guess with explicit agent status (hooks → user var → watcher)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8681a7d..HEAD -- python/ bin/ kittymux-keys.conf.tpl README.md`
> Plans 001–004 touch `python/tab_bar.py` and `python/sidebar-kit.py` — they should be DONE first; re-read both
> files fully before starting.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (touches the in-process watcher; failures must degrade to the old heuristic, never break kitty)
- **Depends on**: plans/003-vertical-tab-bar-redesign.md, plans/004-sidebar-deck-fixes-and-grouping.md
- **Category**: direction / bug
- **Planned at**: commit `8681a7d`, 2026-09-29

## Why this matters

Every surface (tab bar, deck, agent picker) shows "working" for any tab whose foreground process is an agent CLI,
and flips it to "waiting" when the pane *title* has not changed for 15 s (`_STALE_AFTER = 15.0`). Consequences: a
freshly launched agent sitting at its prompt reads "working"; a long silent tool call reads "waiting"; and because
kitty only redraws the tab bar on events, the 15 s timeout may not even flip on screen until something else redraws
it. Agent CLIs can *tell us* what they are doing via hooks. This plan adds an explicit, cheap status channel —
a `kittymux_status` **window user variable** set by a tiny `bin/mux-status` command that agent hooks call — recorded by
the existing watcher and consumed by the bar/deck, with the old heuristic kept as fallback for agents without hooks.
It's the foundation for an "attention queue" (jump to next waiting agent).

## Current state

- `python/pane-state.py` — kitty `watcher` (global; wired by `watcher …/pane-state.py` in
  `kittymux-keys.conf.tpl`). Keeps `_state[window.id] = {title, ts_title, ts_cmd, cmd, running, focused, at_prompt}`;
  callbacks `on_title_change`, `on_cmd_startstop`, `on_focus_change`, `on_close`; flushes JSON atomically to
  `$KITTYMUX_STATE/panes-<kitty pid>.json` (`_flush`, `os.replace`). Timestamps use `time.monotonic()`.
- `python/tab_bar.py` — `_agent_waiting(tab_id)` compares `time.monotonic() - ts_title > 15`; `draw_tab` labels
  `waiting` vs `working` from it; `_agent_info(tab_id)` finds the agent process.
- `python/sidebar-kit.py` — `Row.status` uses the same 15 s rule (`_STALE_AFTER`).
- `bin/mux-agents.sh` (inline python) and `bin/mux-cwd.sh` (inline python, ~line 134) use the same rule; they are
  **out of scope here** (see Maintenance).
- Kitty facts (from https://sw.kovidgoyal.net/kitty/launch/ watcher docs): watchers can define
  `on_set_user_var(boss, window, data)` where `data` has `key` and `value`; `kitten @ set-user-vars --match id:N NAME=VALUE`
  sets a user var on a window; global watchers may also define `on_tab_bar_dirty`. Programs can also set user vars by
  writing the escape `ESC ] 1337 ; SetUserVar=NAME=<base64 value> BEL` to their tty.
- Agent hook facts: **Claude Code** hooks (in `settings.json` → `"hooks"`): events `UserPromptSubmit` (turn started),
  `Notification` (needs the user: permission prompt / idle), `Stop` (turn finished). **Codex CLI** supports a `notify`
  program in `~/.codex/config.toml` invoked on turn completion with a JSON argument — *verify current syntax via docs
  (Context7 `resolve-library-id` "codex cli"/OpenAI Codex) before documenting; if unverifiable, document Claude Code only.*
- Env facts: kitty exports `KITTY_WINDOW_ID` (and `KITTY_LISTEN_ON` when `listen_on` is configured) to child processes.

Conventions: shell scripts — `bin/mux-*`, `#!/usr/bin/env bash`, `set -u`/`set -euo pipefail`, helper lib `lib/mux.sh`;
state in `$KITTYMUX_STATE`; README key/feature docs must stay accurate; `AGENTS.md` Layout list gets new files.

## Design (implement exactly)

**Status vocabulary**: `working` (turn running), `waiting` (needs the user), `done` (turn finished, unread), `idle` (cleared).

**Writer** — `bin/mux-status <state> [ignored extra args…]` (extra args tolerated because some agents append a JSON payload):
1. Validate `<state>` ∈ {working, waiting, done, idle}; else exit 2.
2. Preferred path: write the OSC 1337 SetUserVar escape (`kittymux_status=<state>`, base64 value) to `/dev/tty`
   (works with no socket, also over ssh). Test hook: `--print` writes the escape to stdout instead.
3. Fallback if `/dev/tty` is unwritable: `kitty @ --to "$KITTY_LISTEN_ON" set-user-vars --match "id:$KITTY_WINDOW_ID" kittymux_status=<state>`
   (skip silently if either env var is missing).
4. Always exit 0 for runtime failures (a hook must never block the agent); exit 2 only for bad usage.

**Recorder** — `pane-state.py`: add `on_set_user_var`: for `key == "kittymux_status"` set
`e["status"] = value` and `e["ts_status"] = time.monotonic()`, flush (force), and mark that window's tab bar dirty
(`tab = window.tabref(); tm = tab.tab_manager_ref(); tm.mark_tab_bar_dirty()` inside `try/except Exception: pass`).
Also in `on_focus_change` (focused=True): if `e.get("status") == "done"` → set `e["status"] = "idle"` (read = cleared).
Register the new callback in `_attach` (the list is `ws.on_set_user_var`).

**Resolver** — pure function `resolve_status(entry: dict | None, has_agent: bool, now: float, stale_after: float = 15.0) -> str`
in `python/kittymux_agents.py` (created by plan 002):
- no agent process in the pane → `""` (explicit status is ignored once the agent exits, so a crash can't leave a ghost)
- explicit `status` present → return that value verbatim (`working` / `waiting` / `done` / `idle`); callers treat `idle` as "no marker"
- else heuristic: `ts_title` older than `stale_after` → `"waiting"`, else `"working"`.
Both `tab_bar.py` and `sidebar-kit.py` call it instead of their private copies of the 15 s rule.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Unit tests | `python3 -m unittest discover -s tests -v` | all pass |
| Syntax | `python3 -m py_compile python/*.py` ; `bash -n bin/mux-status` | exit 0 |
| Shellcheck | `shellcheck -S warning bin/mux-status` | exit 0 |
| Writer dry-run | `bin/mux-status --print working \| od -c \| head` | output begins `033 ] 1 3 3 7 ; S e t U s e r V a r = k i t t y m u x _ s t a t u s =` followed by the base64 of `working` (`d29ya2luZw==`) and a BEL (`\a`) |
| Scratch kitty | `kitty --class kmx-t --listen-on unix:/tmp/kmx-t -o allow_remote_control=yes --watcher $PWD/python/pane-state.py &` | window |
| Read user var | `kitty @ --to unix:/tmp/kmx-t ls \| python3 -c "import json,sys;[print(w['id'],w.get('user_vars')) for o in json.load(sys.stdin) for t in o['tabs'] for w in t['windows']]"` | shows `kittymux_status` |

## Scope

**In scope**: `bin/mux-status` (create), `python/pane-state.py`, `python/kittymux_agents.py` (add `resolve_status`),
`python/tab_bar.py`, `python/sidebar-kit.py`, `tests/test_agents.py` (extend), `README.md` (new "Agent status hooks"
section + layout tree), `AGENTS.md` (layout list), `install.sh` (only `chmod +x` already covers `bin/*` — no change expected),
`plans/README.md` status.

**Out of scope**: editing the user's `~/.claude/settings.json` or `~/.codex/config.toml` (document the snippet;
never edit their files), `bin/mux-agents.sh`, `bin/mux-cwd.sh`, `bin/mux-usage.py`, the keymap `.tpl`.

## Git workflow

- Branch: `advisor/005-agent-status-hooks`
- Commit per step; style e.g. `status: mux-status writer + on_set_user_var recorder`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: `resolve_status` with tests first

Extend `tests/test_agents.py` (unittest) with cases: no agent → `""` even if `status="working"`; explicit
`waiting` wins over a fresh `ts_title`; explicit `done`; missing entry + agent → `"working"`; entry with
`ts_title` older than 15 s and no explicit status → `"waiting"`; `ts_title == 0` and no status → `"working"`.
Implement in `python/kittymux_agents.py`.

**Verify**: `python3 -m unittest discover -s tests -v` → all pass.

### Step 2: `bin/mux-status` writer

Create it per the Writer design (bash, ≤ 60 lines, `--print` test mode, base64 via `printf %s "$state" | base64 -w0`).
`chmod +x`.

**Verify**: `bash -n bin/mux-status` → 0; `shellcheck -S warning bin/mux-status` → 0;
`bin/mux-status --print done | od -c` shows the expected OSC bytes; `bin/mux-status bogus; echo $?` → `2`;
`bin/mux-status --print done extra '{"json":1}'; echo $?` → `0`.

### Step 3: Recorder in the watcher

Add `on_set_user_var` and the focus-clear rule to `python/pane-state.py`; register in `_attach`; extend `_entry`
defaults with `"status": "", "ts_status": 0.0`. Keep every callback body wrapped so an exception can never propagate.

**Verify** (scratch kitty; use `--watcher` as in the table, never the user's live windows):
1. `kitty @ --to unix:/tmp/kmx-t launch --type=window …` a shell, then inside it run `bin/mux-status working`.
2. `cat $KITTYMUX_STATE/panes-<scratch kitty pid>.json | python3 -m json.tool` shows that window with `"status": "working"`.
3. `kitty @ … ls` shows `user_vars.kittymux_status == "working"`.
4. Run `bin/mux-status done`, focus the window (`kitty @ focus-window --match id:N` from another window), re-read the JSON:
   `status` is `idle`.

### Step 4: Consume it in the tab bar and the deck

- `tab_bar.py`: replace `_agent_waiting`'s internals with `resolve_status(entry, has_agent=bool(info), now=time.monotonic())`
  → `status` string; derive `waiting`/`working`/`done` for the marks/subtitle (plan 003 spec: dot colour by state;
  `done` uses the `done` token; `idle`/`""` no dot). Keep unread-output (`●` from kitty's own activity flag) as a
  separate signal.
- `sidebar-kit.py`: `Row.status` from the same function; show `done` in the `done` colour.

**Verify**: py_compile → 0; unit tests pass; in the scratch kitty with `-o tab_bar_edge=left` run the sequence
`mux-status working` → `waiting` → `done` in a pane whose foreground process argv0 is `claude` and confirm (screenshot
via `grim` if a display exists, else `get-text` of the deck overlay) that the tab row's dot/subtitle change within ~1 s of each
call **without any other interaction** (this proves the tab-bar-dirty mark works). If the bar only updates after
pressing a key, the redraw hook is wrong → STOP condition.

### Step 5: Docs (do not touch the user's agent configs)

`README.md`: new "Agent status hooks" section with:
- what the states mean and the fallback behaviour;
- the Claude Code snippet (user pastes into `~/.claude/settings.json`):

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "~/kittymux/bin/mux-status working" }] }],
    "Notification":     [{ "hooks": [{ "type": "command", "command": "~/kittymux/bin/mux-status waiting" }] }],
    "Stop":             [{ "hooks": [{ "type": "command", "command": "~/kittymux/bin/mux-status done" }] }]
  }
}
```

- the Codex `notify` snippet **only if** you verified its syntax (Suggested toolkit); otherwise a one-line "Codex: not yet documented".
Add `bin/mux-status` to the README/AGENTS layout lists.

**Verify**: `git diff --stat` — only in-scope files; the snippet parses: `python3 -c 'import json,sys,re;…'` on the extracted block → exit 0.

## Test plan

- Unit: `resolve_status` cases (Step 1). Model after `tests/test_agents.py` from plan 002.
- Script: `--print` mode assertions (Step 2) — add them as `tests/test_mux_status.sh` (plain bash, exits non-zero on failure)
  and run: `bash tests/test_mux_status.sh` → exit 0.
- Integration: scratch-kitty sequence (Steps 3–4), reported in the final message.

## Done criteria

- [ ] `python3 -m unittest discover -s tests` exits 0 (new `resolve_status` tests included)
- [ ] `bash tests/test_mux_status.sh` exits 0
- [ ] `python3 -m py_compile python/*.py` and `bash -n bin/mux-status` exit 0; `shellcheck -S warning bin/mux-status` exits 0
- [ ] `grep -n "_STALE_AFTER\|> 15" python/tab_bar.py python/sidebar-kit.py` → no private copies of the 15 s rule remain
- [ ] Scratch-kitty status sequence verified without manual redraw (Step 4)
- [ ] No files outside scope modified; nothing under `~/.claude` or `~/.codex` touched
- [ ] `plans/README.md` status row updated

## STOP conditions

- `on_set_user_var` is not invoked (Step 3) or `user_vars` is absent in `ls` — report kitty version and observed behaviour.
- Marking the tab bar dirty via `window.tabref()/tab_manager_ref()/mark_tab_bar_dirty()` raises or doesn't redraw —
  report the exception; do **not** invent a polling loop inside the watcher without asking.
- The escape sequence is swallowed (e.g. running inside tmux) — document as a known limitation; do not add passthrough hacks.
- Any change would require editing the user's agent configs.

## Maintenance notes

- Deferred: `bin/mux-agents.sh` and `bin/mux-cwd.sh` still use the 15 s heuristic inline — port them to
  `resolve_status` (e.g. `python3 -c` importing `kittymux_agents` from `$KITTYMUX_HOME/python`) so all surfaces agree.
- Follow-up feature this enables: "jump to next waiting agent" (one keybind + a tiny script over the panes JSON).
- Reviewer: confirm the watcher can't throw into kitty; confirm `idle`/`done` clearing on focus feels right (done clears on *any* focus of that window);
  confirm `mux-status` never blocks (no network, no sleeps).
- Statuses persist until changed; an agent that crashes without a `Stop` hook is covered because the resolver ignores
  explicit status when no agent process is in the pane.
