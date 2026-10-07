# 010 — Final save without a closing-socket race

User approved implementation on 2026-10-07. Supersedes the detached remote-control autosave sketch.

Capture native session text synchronously with `Boss.serialize_state_as_session` on **confirmed application quit only**. No RPC, git, CLI probes, waits or subprocess output collection on kitty's main thread. Temporarily mark exact agent IDs identified while processes are alive, clear stale resume metadata, serialize, and restore all original vars in finally. Unknown IDs never become guessed resumes. Native capture includes all tabs/OS windows, splits and current directories.

Hand text to a detached offline CLI writer through an inherited anonymous file descriptor. The worker needs no kitty socket: use existing verified resume rewriting and prompt wrapper, then atomically publish a private autosave. A timestamp/lock check prevents a slower periodic save from replacing a newer exit capture. Keep pending writes private and out of `restore last` candidates; final session is published only after rewrite succeeds. On failure, keep the previous valid save.

Register the callback on `global_watchers().on_quit` from the reloaded scanner helper, using runtime-held ownership and replacing the previous callback on reload. No cached watcher edit required. Gate missing native methods, honor autosave-off/env, never abort a quit or save a cancelled confirmation. Record static outcomes without session text.

Acceptance: cancellation/off switches/no API fail safely; two reloads leave exactly one callback; private real kitty exit captures a pane/layout mutation less than 20s before quit; final save works after its socket disappears and parses with kitty; no live kitty touched. Tests cover rewrite/worker failure and newer-save ordering. This handles the documented application-quit path; uncatchable kills remain periodic-save recovery.

Implementation complete. Verification and application boundaries: [execution record](../docs/audit-2026-10-07-plan-review.md).
