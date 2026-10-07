# 011 — `kittymux changes --diff` patch view + `kittymux doctor --bundle` (adopted from T3 Code)

Two small adoptions from `~/Projects/osc/t3code` that fit kittymux's shape (config layer, no
daemon). Both are additive CLIs; nothing existing changes behaviour.

## Item A — diff view for a checkpoint (T3's CheckpointDiffQuery)

What T3 Code does: per agent turn it keeps two trees (before/after) and answers both
`getTurnDiff` (one turn) and `getFullThreadDiff` (cumulative) as an actual patch — numstat
alone was judged insufficient for review.

Where kittymux already is: `kittymux_changes` snapshots each repo at run start/finish into a
private object dir with a temp index (`snapshot`, `_tree_of`, `numstat`, `summarize`) and
prints `files / +add / −del`. The trees are already stored — producing the real diff is only
`git diff --cached`-style plumbing between two stored trees, zero new writes to the user's
repo (keep the never-write-into-repo invariant; T3 writes hidden refs — we deliberately do
NOT adopt that part).

**Step:** add `kittymux changes [--window W] [--diff] [--patch]` (name bikesheddable):
- locate the window's latest `(base_tree, snap_tree)` pair in `changes-<pid>.json` exactly as
  the summary path does today;
- run `git diff <base> <snap>` (and optionally `--stat`) inside the same private
  `GIT_OBJECT_DIRECTORY`/`GIT_INDEX_FILE` harness `numstat` uses — extend the existing
  helper rather than spawning raw git;
- bound output (e.g. `--stat` first; `--patch` capped ~8k lines with a note when truncated);
- surface `--diff` in `kittymux pick`'s detail view if cheap, else skip (note in plan).

Acceptance: `changes --diff` on a real run prints the actual patch for the completed run;
works when the repo was mid-worktree, on a detached HEAD, and for binary files (numstat `-`).
Tests extend `tests/` change-tracking tests using the existing temp-repo fixtures.

## Item B — `kittymux doctor --bundle` (T3's diagnostics + observability page)

What T3 Code does: one command produces a support artifact — versions, config summary,
recent trace lines — so bug reports carry the same facts every time.

Where kittymux already is: `kittymux doctor` reports live state to the terminal; the
decision log (`decisions-<pid>.jsonl`, bounded, sanitized) and `scan-<pid>.json` already
contain the "why" a maintainer needs. Today a bug report means asking the user to paste
files by hand.

**Step:** `kittymux doctor --bundle [DIR]` writes `kittymux-doctor-<ts>.tar.gz` (or a plain
dir when `--no-tar`) containing only already-sanitized artifacts:
- `doctor` text output itself;
- `kitty --version`, platform/Wayland/compositor line;
- tails of `decisions-<pid>.jsonl` (last ~200 lines) and `scan-<pid>.json`;
- `agent-sessions.json` **redacted** through `kittymux_journal.redact_argv`;
- NOT `panes-<pid>.json` titles/messages, NOT `inbox.jsonl` bodies, NOT any screen text —
  private-mode rules still apply (`KITTYMUX_NOTIFY_PRIVATE`/`notify-private` empties bodies;
  respect them: bundle must never exceed what private mode would show);
- a `MANIFEST.txt` listing what was included and what was deliberately excluded.

Acceptance: bundle is self-contained, ≤ ~1 MB, contains no credential-shaped values (run the
existing redaction test over the manifest too), and `tar tzf` lists only expected paths.
Docs: `kittymux doctor --help` line + `docs/` troubleshooting pointer.

## Steps

1. Worktree `.worktrees/diff-and-bundle`; two commits (A, B).
2. `python3 -m unittest discover -s tests`; `python3 -m py_compile` touched files;
   `bash tests/test_mux_status.sh`; `git diff --check`.
3. CHANGELOG `Unreleased` entries for both commands; README CLI table row if the docs test
   requires every command documented (check `tests/test_docs.py` rules first — it covers CLI
   reference completeness).

## Risks / STOP conditions

- STOP on any change that writes objects/refs into the user's repository — snapshots stay in
  the private `changes-objects/` dir; if `git diff` between two trees proves to need a
  checkout, use `GIT_INDEX_FILE`/`GIT_OBJECT_DIRECTORY` plumbing (`read-tree` into the temp
  index) exactly as `numstat` does, or ship `--stat` only and defer `--patch`.
- STOP if the bundle would include any file that can hold screen text or window titles —
  extend redaction instead of shipping more files.
- The `pick` UI integration (A) is optional scope — cut it if it fights `kittymux_launcher`'s
  row model.

Effort: M · Priority: P3 · Files: `python/kittymux_changes.py`, `bin/kittymux` (CLI),
possibly `python/kittymux_launcher.py`, `python/kittymux_journal.py` (reuse redaction),
tests, docs.
