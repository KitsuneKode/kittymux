# Hardening validation — 2026-10-01

Work performed in `.worktrees/dev`, branch `dev`. The hardening commit was rebased onto
`main` commit `3dfa66e`, preserving the concurrent mascot/font work, Codex screen patterns,
stale-hook expiry and five-second completion-notification settling. Subsequent collector
follow-ups preserve Devin's omitted-zero quota behavior and retain old history counters
under `_legacy_counters` rather than deleting their values.

## Fixed boundaries

- Session regex escaping and the project sorter's stdin wiring.
- Owned-socket discovery: checked fallback, parent over stale inherited env, fail-closed callers.
- Scratch tracking: per-socket-instance namespace, OS/tab/window/launch identity verification;
  unsafe legacy flags are ignored. Existing legacy scratch tabs are not automatically closed.
- Agent TSV parsing with empty session fields; inactive-tab panes are not treated as currently focused.
- Usage refresh after failure, elapsed-clock versus quota semantics, safe curl stdin transport,
  unsuccessful-request cooldown, atomic/private cache replacement and exact dated Claude counters.
- Devin transcript modification time is activity evidence only; cumulative session totals are not
  persisted as exact daily burn. Omitted proto3 zero quotas with reset timestamps still show exhausted.
- Panel target identity from real child-process ownership, including custom socket names and vanished children.
- Bounded/generation-ordered previews, slow same-pane refreshes, nonblocking resize submission,
  final-width persistence and the live right-edge drag case.
- Startup attention replay, hook-only completion acknowledgement and superseded permission hooks.
- CI actually runs both shell suites and now includes the two-instance workflow smoke rig.

## Results

This batch was exercised with **kitty 0.49.1**. It was not rerun on 0.49.2 in this session;
GitHub CI has not been triggered by this work.

| Gate | Result |
|---|---|
| `python3 -B -m unittest discover -s tests` | 364 tests passed |
| `bash tests/test_mux_status.sh` | Passed |
| `bash tests/test_socket_lib.sh` | Passed |
| `shellcheck -S error` on changed shell files | Passed |
| `bash -n` on changed shell files | Passed |
| Python compilation on changed Python files | Passed |
| `git diff --check` | Passed |
| `bash tests/test_install.sh` | Passed: fresh temporary HOME, install/reinstall/config/doctor/uninstall |
| `bash tests/smoke_state.sh` | Passed: screen states, split attention, unseen completion, spinner and spacer click |
| `bash tests/smoke_sidebar.sh` | Passed: collapse/expand, peek, absorption and edge resize with actual pointer events |
| `bash tests/smoke_drag.sh` | Passed: actual-pointer tab reordering |
| `bash tests/smoke_reload.sh` | Passed: two reloads, three private tabs intact, no post-reload bar errors |
| `bash tests/smoke_workflows.sh` | Passed: two real instances with overlapping IDs, scratch isolation, custom-socket owner and anonymous-session jump |
| `SMOKE_KEEP_STALE=1 bash tests/smoke_reload.sh` | Expected failure: stale helper lacks `NEEDS_YOU`; detector is effective |
| Real curl against loopback fake-credential fixture | Passed within the unit suite; no vendor requests |

Existing tests emit unclosed-file `ResourceWarning`s in ordinary runs; these are not new runtime
leaks discovered in this batch. Retained UI screenshots are git-ignored under `.validation/`.

## Live-session safety

No live kitty was restarted, reloaded, upgraded, or otherwise mutated by this work. Read-only
owned-socket snapshots before and after the private test runs were unchanged:

| Socket | OS windows | Tabs | Panes |
|---|---:|---:|---:|
| `/tmp/mykitty-2165171` | 1 | 2 | 4 |
| `/tmp/mykitty-4062` | 6 | 20 | 23 |

Main's uncommitted `python/collectors/devin.py` edit remains intact. Since the branch also changes
that file, merging/reloading was deliberately not attempted. Its owner must reconcile the edit
before rollout; then incorporate any newer main commits into dev, rerun the gates, fast-forward
main and use main's `bin/kittymux upgrade`, with fresh before/after counts.

## Remaining verification limits

- No live vendor/account requests; response shape and marker compatibility need real, sanitized evidence.
- No real Wayland layer-shell panel resize run in this batch; worker/event behavior is unit-tested,
  and real target-process verification is tested under Xvfb.
- No macOS, additional compositor, or alternate notification-daemon verification.
- Concurrent scratch invocations and concurrent history observations are not transactional:
  the former can leave an extra scratch tab, the latter can be last-writer-wins. Identity checks
  protect unrelated tabs, but do not imply full multi-command serialization.
- No release tag, push, PR, publication, or social post was made.

See `testing.md` for reproducible gates and `social-launch.md` for draft launch material.
