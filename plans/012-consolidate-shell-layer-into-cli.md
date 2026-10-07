# 012 — Incremental Python workflow consolidation

User approved implementation and plan correction on 2026-10-07. Python remains appropriate for native hooks and shared modules. External RC clients may use other languages; a universal Python-only claim was inaccurate. Existing shell smoke tests remain valuable. TypedDict alone does not validate JSON.

1. Add bounded JSON readers and typed validated kitty context objects at actual CLI/panel/workflow boundaries. Keep compatible JSON bytes and ignore unknown fields; reject invalid IDs, bool-as-int, malformed roots and oversize inputs. Do not migrate every stable state reader solely for uniformity.
2. Centralize owned socket resolution with existing inside-this-kitty semantics. Explicit invalid target never falls back; discovery confinement and owner checks survive. Reuse CLI and Python workflow callers while leaving the dependency-free status hook/socket shell boundary available.
3. Port session lookup, exact argv save action, live-session list/current/cycle selection into pure/testable helpers and CLI-backed shell shims. Preserve history ordering, session regex escaping, overlay-parent context and active-session autosave semantics. Existing fzf orchestration/presentation stays shell; no broad picker rewrite.
4. Port nav/newtab/scratch orchestration to validated Python contexts/argv. Scratch close validates owner, title, launch identity and private state file (including symlink/ownership guards). Scratch remains last; unknown parent windows never target another kitty. Keep original scripts as exec shims so keys do not change.

Acceptance: meaningful characterization tests and private real kitty workflow smoke pass; hostile/control-character paths stay single argv elements; stale scratch records cannot close an unrelated tab; other kitty counts remain unchanged. Shared shell helpers shrink without changing their callers or adding a runtime. Remaining fzf-specific presentation and install/panel/hook/smoke glue stay shell by design.

Implementation complete. Verification and application boundaries: [execution record](../docs/audit-2026-10-07-plan-review.md).
