# 010 — Save a final session snapshot on kitty quit (`on_quit` watcher)

## Context

Autosave (`python/kittymux_scan.py::_maybe_autosave`) snapshots the session at most every
15 min (`AUTOSAVE_PERIOD`) plus on settled window-set changes. If the user closes kitty right
before the next tick, `sessions restore last` resurrects a state up to ~15 minutes stale —
new tabs, moved panes and freshly spawned agents are lost even though kitty asked "are you
sure?" seconds earlier.

kitty's **documented** global-watcher callback `on_quit(boss, window, data)` exists for
exactly this (kitty docs, `watcher`/`launch` page): it is called twice — once before the quit
confirmation (`data["confirmed"] == False`) and once after confirmation (`True`) — and
setting `data["aborted"] = True` can even cancel the quit. `python/pane-state.py` is already a
global watcher (registered via `watcher` in `kittymux-keys.conf.tpl`), so adding `on_quit`
there needs no new plumbing.

## Improvement

On `on_quit` with `data.get("confirmed")` true (and on the pre-confirm call only if there is
no confirmation path — decide in implementation), kick one final `kittymux sessions autosave`
so the "last" snapshot is as fresh as the user's last second.

Design constraints (kitty is quitting — keep it cheap and non-blocking):

- Reuse `_maybe_autosave`'s spawn path: detached `kittymux sessions autosave` with
  `KITTYMUX_TARGET` set, `start_new_session=True`, stdio to DEVNULL. Do **not** run
  `save_as_session` on kitty's main thread during teardown — the remote-control socket may
  already be closing, and a synchronous save could slow or break quit.
- The detached subprocess races kitty's shutdown: if the socket dies first, the save fails
  and nothing is worse than today. Acceptable — this is best-effort on top of the 15-min
  cadence, not a guarantee. (A stronger variant: call kitty's in-process
  `save_as_session`-equivalent Boss API directly and rewrite launch lines in-process —
  evaluate in the worktree; prefer it only if it's provably safe during teardown.)
- Respect `KITTYMUX_AUTOSAVE=0` / `autosave-off` exactly like `_maybe_autosave` — refactor
  the enable check into something `pane-state.py` can call without duplicating env/file
  logic (pane-state intentionally holds minimal logic: put the quit handler in
  `kittymux_scan` and call `ks.on_quit(...)` from the watcher, mirroring `ks.poke`).

## Steps

1. Worktree `.worktrees/quit-autosave`.
2. `python/pane-state.py`: add `def on_quit(boss, window, data)` — delegate to
   `kittymux_scan.on_quit(boss, data)` inside a try/except (watcher must never raise;
   exceptions in watchers are printed to stderr but let's not spam on quit).
3. `python/kittymux_scan.py`: add `on_quit(boss, data)` — if autosave enabled and
   `data.get("confirmed")` is not False (verify the exact flag semantics against installed
   kitty source `kitty/boss.py` quit path before choosing), spawn the detached
   `kittymux sessions autosave` once. Guard with a `_RT` flag so the two `on_quit` calls
   don't double-spawn.
4. Tests: extend the scanner tests to call `on_quit` with a fake boss/data and assert a
   spawn attempt is made once, honours the off switch, and tolerates a dead socket (Popen
   failure → swallowed).
5. Docs: `docs/sessions.md` one line — "a final snapshot is attempted when kitty quits".
   Changelog under `Unreleased` per CONTRIBUTING.

## Acceptance criteria

- Quitting a kitty whose socket is still alive produces a `sessions/last` file newer than
  the previous autosave (verify in a scratch kitty: `--class kmx-t`, own socket, own
  `KITTYMUX_STATE`, own `KITTY_CONFIG_DIRECTORY` — never the user's live kitty).
- `KITTYMUX_AUTOSAVE=0` / `autosave-off` suppresses it.
- The quit itself is never slowed or blocked (spawn is detached; no `wait`, no join).
- `python3 -m unittest discover -s tests` passes.

## Risks / STOP conditions

- STOP if `on_quit` in the installed kitty version does not deliver `confirmed` as
  documented — check `kitty/boss.py` first; if kitty pre-0.49 lacks the callback entirely,
  `hasattr`/`getattr` guard keeps this a no-op there (document the minimum version).
- Do not write user vars, session files, or screen text in the quit path beyond what
  `sessions autosave` already does.
- Never mark `data["aborted"]` — we observe quits, we don't manage them.

Effort: S · Priority: P2 · Files: `python/pane-state.py`, `python/kittymux_scan.py`, test,
`docs/sessions.md`, CHANGELOG.
