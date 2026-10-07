# 011 — Checkpoint patches and safe diagnostics

User approved implementation on 2026-10-07. Keep both features in existing CLI/shared modules, no daemon or repo refs.

`changes --diff`: preserve base/current tree IDs with each summary, refresh through existing private snapshot path, and diff only validated SHA-1 tree IDs. Disable external diff/textconv, pager, colors and filesystem monitor; use private object directory with read-only alternates. Bound captured output at 256 KiB / 2000 lines, timeout and kill process group on overflow. Sanitize terminal controls in CLI output, retain legitimate diff whitespace. `--json --diff` explicitly returns patch metadata; reject ambiguous `--all --diff`. Tests cover dirty-before baseline, worktree, binary, malicious diff config, truncation and unchanged user repo.

`doctor --bundle [DIRECTORY]`: produce a private archive with a generated manifest and **allowlisted** structured diagnostics: versions, platform family/session type, boolean features, numeric published-instance/pane/state counts. No raw doctor output, configs, environment, socket paths, journal, titles, cwd, argv, IDs, notifications or screen/decision bodies. Ignore malformed/oversized files. Only generated fixed member names; no archive of arbitrary user files. Directory is explicit/default cwd; exclusive output creation and 0600 archive. Tests inject runtime-built credential shapes into every untrusted field and verify absence; bound archive size and unknown keys. Update CLI/published docs and feature matrix together.

Implementation complete. Verification and application boundaries: [execution record](../docs/audit-2026-10-07-plan-review.md).
