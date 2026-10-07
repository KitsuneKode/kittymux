# 012 — Consolidate the shell workflow layer into `bin/kittymux` (language strategy)

## Why this plan exists

Audit question: "can kittymux be rewritten in TypeScript / a better language?" Verified answer
against kitty 0.49.2 source and docs:

- **Kitty-bound code must be Python.** `tab_bar.py`, `window_title_bar.py`, watcher modules
  (`on_set_user_var`, `on_cmd_startstop`, `on_quit`, …), custom kittens (`kittens.tui`
  Handler/`handle_result`), and `.py` geninclude files (run via `runpy` inside kitty's own
  interpreter — `kitty/conf/utils.py:208-238`) are all Python-only extension points. Custom
  kittens cannot be Go/TS/Rust; kitty's internal Go kittens are builtin-only. (~5.6k lines:
  tab_bar, pane-state, sidebar-kit, join-kit, peek-kit, scan, barsize, layout, panetitle.)
- **The "free" Python is mostly not free either.** `bin/kittymux` already imports ~9 pure
  modules (agents, changes, fanout, features, inbox, journal, keymap, launcher, quiet,
  resume…). Those same modules are imported by the in-kitty code. Moving the CLI to Go/TS
  means re-implementing ~9k lines of shared logic or shelling back to `python3` — either way
  the language change buys nothing.
- **The genuinely portable surface is the shell layer** (~5.2k lines: `lib/mux.sh` 992 +
  `bin/mux-*`): no kitty-API imports, no shared-module imports — only `kitty @` remote
  control, fzf, and JSON munging done via 16+ embedded `python3` heredocs.

## Recommendation (senior call)

Do NOT rewrite in TypeScript/Go/Rust. **The best move is consolidating shell → Python inside
the existing CLI.** Rationale:

1. TypeScript/Bun/Deno adds a third runtime (kitty ships Python anyway; python3 is already a
   hard dep), cannot touch a single kitty API, and would duplicate the shared pure modules.
2. Go is the only credible "better language" here — kitty itself ships `kitten` as a Go
   binary — but only if the goal were a single-binary distribution, which conflicts with how
   kittymux is loaded (symlinked `.py` files + geninclude + watcher must stay `.py`). Keep as
   a documented option for a future thin-CLI-over-state-files if distribution ever demands it:
   the `*-*.json` state files are already the ABI (versioned inbox schema v1, journal v1).
3. The actual risk isn't the language — it's that ~5k lines of the workflow layer are in
   **untested bash** with quoting/`%q` hazards and JSON parsed by embedded Python heredocs.
   Moving it into `bin/kittymux` keeps one runtime, gains `unittest` coverage for free, and
   deletes the shell↔Python JSON boundary.
4. The typed-contracts benefit people reach for TS for is cheap in Python: formalize the
   state-file schemas (`panes-*`, `scan-*`, `inbox`, `agent-sessions`, `layout-*`) as
   `dataclass`/`TypedDict` loaders — plan item below.

## Scope (incremental — do in order, each is shippable alone)

1. **Typed state schemas (foundation).** `python/kittymux_files.py` (new, pure):
   `dataclass` loaders for `panes-<pid>.json`, `scan-<pid>.json`, `layout-*.json`,
   `agent-sessions.json`, `inbox-snapshot.json` — the JSON ABI every consumer reads.
   Readers migrate to `load_panes(path) -> PanesFile` instead of raw `json.load`. Keeps
   backward tolerance: unknown keys ignored, missing keys defaulted (schemas are the
   contract, not the enforcement).
2. **Port `lib/mux.sh` session functions → `bin/kittymux session-*` subcommands.** Candidates
   by size/risk: `find_os_window_for_session`, `cycle_live_session_name_for_window`,
   `save_session_file_for_window`, the sessionizer list builders (the `python3 -` heredocs —
   there are ~16 — become real functions). Each port keeps the bash function as a one-line
   `kittymux` shim so callers (`mux-sessionizer`, `mux-cycle.sh`, `mux-save.sh`) work
   unchanged during migration; shims removed only in a final pass.
3. **Port the remaining `mux-*` logic that isn't pure presentation.** `mux-nav.sh`,
   `mux-newtab.sh`, `mux-scratch.sh` logic → `kittymux nav|newtab|scratch`; the `.sh` files
   become `exec kittymux …` stubs (like `mux-edge.sh` already is). fzf pickers
   (`mux-sessionizer`, `mux-movetab.sh`, `mux-send.sh`) stay interactive fzf — but their
   list-building/formatting moves into testable Python that fzf merely displays (same
   pattern as `kittymux_launcher.build_rows`/`menu_command`).
4. **Keep shell only where it earns it**: install/uninstall, `mux-status` (must be a tiny
   dependency-free script agents call from hooks — keep bash + OSC escapes), `fzf-style.sh`,
   `mux-panel` (compositor glue), smoke rigs.

## Steps

1. Worktree `.worktrees/cli-consolidation`. Step order above; commit per ported function
   group.
2. For each port: unittest for the pure part first (temp dirs, fake `ls` JSON — the suite
   already has these fixtures), then the CLI wiring, then shrink the bash to a shim.
3. Docs: README key/command tables and `docs/users/` where command names change (shim layer
   means most user-facing names don't). `tests/test_docs.py` guards CLI-reference coverage.
4. Never regress: every `kitty_remote` call must keep socket ownership checks
   (`lib/socket.sh` semantics → port `mux_owned_socket`/`mux_resolve_socket` to Python FIRST
   as `kittymux_socket.py`, with `tests/test_socket_lib.sh`-equivalent coverage).

## Acceptance criteria

- `bin/kittymux` exposes the ported functionality; shell callers still work via shims.
- `python3 -m unittest discover -s tests`, `bash tests/test_mux_status.sh`,
  `bash tests/test_socket_lib.sh` pass; new Python gets `py_compile`; shrunken `.sh` passes
  `bash -n` + `shellcheck -S error`.
- `lib/mux.sh` shrinks substantially (target: session helpers gone); the `python3 -` heredoc
  count in `lib/mux.sh` + `bin/mux-*` drops toward zero.
- No new runtime dependencies (still: kitty, python3, bash, fzf, jq optional).

## Risks / STOP conditions

- STOP if a port changes a state-file shape read by another consumer — the JSON files are
  the ABI; loaders must accept today's bytes.
- STOP rather than removing `bin/mux-status` or `lib/socket.sh` trust checks — both are
  security boundaries (agent hooks must never fail; sockets must be owned).
- Do not port the fzf UI itself (keybinds, --bind actions) — fzf stays; only the data prep
  moves.
- Don't touch `kittymux-keys.conf.tpl` binding targets until shims are proven — remap keys
  only in the final pass, and update README's key table in the same commit (AGENTS.md rule).

Effort: M-L (break into the 4 stages) · Priority: P3 · Files: `lib/mux.sh`, `bin/mux-*`,
`bin/kittymux`, new `python/kittymux_files.py` + `python/kittymux_socket.py`, tests, docs.
