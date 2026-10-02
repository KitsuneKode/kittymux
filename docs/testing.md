# Testing without risking everyday sessions

Work in `.worktrees/dev` (or another isolated worktree), not in the checkout your kitty config links to.
Do not use your everyday config, socket, state directory or provider credentials as test fixtures.
A green unit suite is not proof of compositor support or of current vendor response formats.

## Fast regression gate

```sh
python3 -B -m unittest discover -s tests
bash tests/test_mux_status.sh && bash tests/test_socket_lib.sh
git diff --check
```

Run `bash -n` and `shellcheck -S error` for changed shell files, and `python3 -m py_compile`
for changed Python files. CI must invoke each shell test explicitly: passing a script as an
argument to another script does not execute it.

## Private real-kitty gate

Run from the isolated worktree, using the rigs' private config, sockets and state:

```sh
bash tests/test_install.sh
bash tests/smoke_state.sh
bash tests/smoke_sidebar.sh
bash tests/smoke_drag.sh
bash tests/smoke_resize.sh
bash tests/smoke_panes.sh
bash tests/smoke_reload.sh
bash tests/smoke_workflows.sh
bash tests/smoke_resume.sh     # save → restore: the prompt, Enter/n, --direct, autosave, the journal
bash tests/smoke_socket.sh     # allow_remote_control socket-only refuses in-band control (yes obeys it: the control); $XDG_RUNTIME_DIR socket works
bash tests/smoke_inbox.sh      # real OSC 99 notifications → typed inbox events
bash tests/smoke_click.sh      # tab clicks with wobble; middle-click spares an agent tab
bash tests/smoke_native.sh     # native divider: pixels, real X cursor, native drag (kitty >= 0.49.2)
for t in demo keys openref extras; do bash tests/smoke_$t.sh; done
```

The workflow rig starts two kitties with overlapping IDs. It verifies scratch identity before
closing anything, checks ownership through a custom socket name, and exercises an attention
jump with both session columns empty. Its compositor command is stubbed so it cannot change
your desktop focus. The other rigs check scanner/spinner behavior, mouse hit testing,
collapse/expand, peek, pane absorption, reordering and upgrade-under-a-running-kitty.

`SKIP` is not a pass. Record the reason and the kitty version. Run display-sharing rigs
sequentially (`smoke_sidebar.sh` and `smoke_drag.sh` currently choose from overlapping ranges).
Use `SMOKE_SHOT=<absolute path prefix>` with `smoke_sidebar.sh` to retain screenshots.

The reload detector itself must also be tested:

```sh
SMOKE_KEEP_STALE=1 bash tests/smoke_reload.sh
```

This must fail for the expected stale-module error, not for a setup error. All rigs should
remove only their own temporary instances in their EXIT cleanup; never kill processes by name.

## Edge-case matrix

| Boundary | Automated checks | Still needs environment-specific verification |
|---|---|---|
| Remote control | In-band escape-sequence control refused under `socket-only` (real kitty, with a positive control); missing/foreign sockets fail closed; parent beats stale inherited env; explicit targets and fd handles | Custom runtime paths and restricted `/proc` installations |
| Scratch tabs | Overlapping instance IDs, stale/legacy flags, wrong OS window, changed launch identity; real two-instance test | Concurrent scratch commands and user moving panes during validation |
| Sessions and agent jumps | Regex characters/leading hyphens, empty TSV fields, inactive-tab focus flags, send contract; real anonymous-session jump | Many parked sessions across multiple monitors/compositor workspaces |
| Scanner and attention | Debounce, focus acknowledgement, hook-only completion, handled requests, startup replay suppression, timer reload lifecycle | Agent TUI wording/version changes; verify a real screen before changing patterns |
| Previews and resize | Single-flight work, A→B→A, reordered callbacks, slow same-pane refresh, shutdown, final release beyond throttle, unsaved right edge | Real layer-shell panel resizing on each supported compositor |
| Usage HUD | Provider failure/refresh, malformed credentials/responses, failure cooldown, exact counters, local-midnight/DST boundaries | Opt-in live responses from each vendor/account type |
| Credential transport | Fake credentials absent from argv; real curl against a loopback fixture; escaping/newline rejection | System proxy/TLS policies and credential rotation if old argv was captured |
| Restore prompt | Hostile/stale records (flag-like ids, mismatched programs, oversized or non-string argv), keys incl. a lone Esc, no tty, missing binary, `a` resume-all — through a real pty; real kitties restore through the prompt | Each real agent's `--resume` against a real conversation (only its `--help` is probed; run `kittymux sessions check`) |
| Agent journal | Fold/prune bounds, two-kitty merge, 4-process concurrent writes, scanner heartbeat/coalescing, closed windows, off switch; live kitty records its agents | Session ids for agents that expose none (Devin, opencode, cursor, agy: recorded without an id) |
| Persistence | Private bytes before replacement, failed writes preserve prior data, symlinks not followed | Simultaneous HUDs can still be last-writer-wins for history observations |

Tests use fake credentials, temporary state and synthetic provider responses. Localhost transport
verification exercises curl's actual config parser; it does not contact a vendor.

## Before applying a tested branch

1. Check `main` and the worktree for unrelated edits. Do not stash or overwrite another agent's work.
2. Incorporate new `main` commits into the isolated branch, resolve conflicts there, and repeat the gates.
3. A local edit to a file changed by the branch is a rollout blocker. Have its owner reconcile it first.
4. Record OS-window/tab/pane counts for every owned live kitty socket, without dumping pane text.
5. Only after a clean fast-forward, run the **main checkout's** `bin/kittymux upgrade` (never restart).
6. Compare counts and check `~/.local/state/kittymux/tab_bar-error.log` (or the configured state path).
   If counts differ, investigate; do not close or recreate windows to make the numbers match.

## Launch evidence

See `compatibility.md` for verified versions/agents and `notifications.md` for daemon and privacy limits.
Keep GitHub CI results, release tags, live-provider checks and compositor checks separate from local test results.
A demo should use synthetic panes and private state: redact project paths, prompts and account details.
