# Status and attention contract

What every state means, who decides "done", how restore, the inbox, usage numbers and limits behave, and the invariants that keep them honest. Read it before touching the scanner, the resolver, notifications, sessions or the inbox.

Part of the agent guide: start at [AGENTS.md](../../AGENTS.md) (the rules and the "read before you change" table); this page is the reference for one area.

States, most important first — a state needs positive evidence, and silence is never "waiting":

| State | Evidence | Shown as |
|---|---|---|
| `limited` | "usage limit reached" / quota text on screen | `⊘`, alert colour |
| `waiting` | a permission/question prompt on screen, or a hook message that is a real request | `!`, bold, rail stripe |
| `working` | an activity marker on screen (`esc to interrupt`, Claude's `Verb… (6m 52s · ↓ tokens)`), or a hook inside its grace | animated spinner |
| `done` | it was busy and is not, or a Stop hook — *unseen*; focusing the pane clears it | dim `✓` |
| `idle` | an agent runs and nothing above applies | nothing |

**Who decides "done"** (false completions were the worst bug class — keep these invariants):
- A turn announced by a hook (`UserPromptSubmit`) ends only with the agent's own `Stop` hook. A quiet screen between tool calls, a repaint, or an
  Esc interrupt (no Stop fires) is never "finished"; `hook_turn` is dropped after `_TURN_ABANDONED` of silence. Agents without hooks are judged by the screen alone.
- A hook-`waiting` that is a real request (`is_request`) is never a completion, answered or not; only the idle notification ("waiting for your input") counts, and only
  if no completion was reported yet this turn (`completed`).
- Question/limit text on screen only counts when no activity hint is drawn BELOW it (stale prose above a live spinner), unless dialog chrome (`esc to cancel`, `(esc)`) is present.
- A completion notifies only with a KNOWN duration ≥ 15 s (`worked is not None`) and after the 5 s settle.
- Claude hooks installed by `kittymux hooks --install`: `UserPromptSubmit`/`PostToolUse` → working, `Notification` → waiting, `Stop` → done, `SessionEnd` → idle.
  `kittymux doctor` reports missing events. Change `HOOK_EVENTS`, README's snippet and the tests together.

**Restore asks; the journal remembers.** A rewritten agent window runs `kittymux resume-prompt --info <json>` (default; `--direct` writes the resume command) — never auto-resume without the user's switch (`KITTYMUX_RESUME=auto`,
`resume-auto`). The prompt validates the record (`kittymux_resume.parse_info`: a session file is editable), reads keys with `select`/`os.read` (a lone ESC = shell), and `exec`s the answer. `python/kittymux_journal.py` (pure) + the scanner
(`_journal_note` on state changes, `_journal_tick` heartbeat; coalesced non-blocking writes; state in `_RT.journal`) keep `agent-sessions.json`: bounded, 0600, lock-merged; `sessions history` / `recover` read it.
**Sessions resume agents** (`python/kittymux_resume.py` pure; `kittymux sessions`; docs/sessions.md): kitty's own `save_as_session --use-foreground-process` does the saving (never reimplement it); we mark agent
windows with user vars (`kittymux_agent/resume/sid` — kitty serialises `--var=` into the file) before the save and rewrite the saved `launch` lines after (`rewrite_session`, no window-id matching, idempotent). Agent
definitions are DATA (`assets/resume-agents.json` + `~/.config/kittymux/resume.json`) and each is probed against the installed CLI's `--help` (`sessions check`, cached 12 h) before it is used: never add a flag you did not
read in that CLI's help. Rules: exact id (Claude: `~/.claude/sessions/<pid>.json`, validated by process start time; Codex: open `rollout-…-<uuid>.jsonl`) beats `latest`; `latest` only where it cannot attach the wrong
conversation (`latest_scope: directory` + unique per directory, else single window of that agent); ids are validated (never start with `-`), commands rebuilt as argv; stale `kittymux_status/msg` vars are stripped. The scanner
autosaves (`_maybe_autosave`: baseline → settle 20 s → min gap 60 s → period 15 min; detached subprocess). Templates are plain kitty session files with `@NAME@`/`@Q:CWD@` placeholders, checked by kitty's own parser in tests.

**One event model** (`python/kittymux_inbox.py`, pure; docs/inbox.md): every needs-you / limit / completion is a typed event (`permission|question|limit|done|error|info`, severity, sources, confidence) in `inbox.jsonl`
(append-only ops, 0600, compacted at 256 KB) + `inbox-snapshot.json` (schema v1: what a widget watches). Sources by authority: `agent` (its own OSC 9/99/777 notification — captured by wrapping
`NotificationManager.is_notification_filtered`, which sees the finalised command + `channel_id` = window id before our `filter_notification` rule drops the agent's popup; or its hook), `hook`, `screen`.
`kittymux_scan._announce` is the ONE place that decides popup vs inbox-only: the inbox says whether the occurrence was already reported (45 s merge window → one popup per occurrence), and a `done` with
`confidence: low` (inferred from a quiet screen) pops up only after ≥ 60 s of work. Classification of agent text is conservative: unrecognised → `info`, "waiting for your input" → `idle-notice` (not a completion).
An agent-announced completion feeds the resolver like a Stop hook (`agent_done_ts`). Never log/store screen text beyond the bounded event body (empty in private mode). Adding a source or kind = update the
inbox schema doc, the tests, and keep `version` stable (consumers ignore unknown fields).

**Usage numbers say how old they are.** Collectors may return `sample_ts` (when the provider last reported); `kittymux_usageview` dates it, `kittymux_usagehistory` records a snapshot at THAT time (never "now") and keys a quota by a validated short label (`^[a-z0-9]{1,6}$`: it cannot carry a title or token), and a Codex window whose `resets_at` has passed is a `closed` state row, never its old percentage.

**A vanished window is on record.** `kittymux_scan.closed_events` writes a `closed` decision for each agent window that disappears (last state, seconds since seen, how many agent windows and how many from the same tab went together): several at once is a tab or OS window being closed by a key, the window manager or `kitty @`, not agents exiting. kitty itself keeps no such record, so this is the only evidence when a user reports "my tab disappeared".

**Every answer says why.** `kittymux_state.resolve` records a static, human `why` at each return (`_why`); the scanner publishes it in the verdict and writes every state change and every notification
outcome (`_notify` returns "sent" or why not) to the decision log (`_record`: a 300-event deque in `_RT` + `decisions-<pid>.jsonl`, 0600, rotated; `kittymux explain` reads it). A new state or a new
suppression rule MUST set a `why`/outcome, and a reason must be static text (no clocks or counters in it, or the published verdict changes every tick). Never log screen text.

**A usage limit is an episode with an end** (`kittymux_state.limit_hint/limit_reset`, t3code's `resetAt` idea): the scanner publishes `reset_at` in the verdict (the bottom-most hint on screen; a clock time resolves to the occurrence NEAREST now, since it never lasts over 12 h; a relative "in 2h" is taken ONCE per message, its epoch moves with the clock), the state ends at that time while the old message is still drawn (`why`: "its usage limit has reset…"),
the bar and panel show `↻12m` / "resets in 12m" instead of how long ago it hit (`state_age(…, reset_at=, wall=)`), and `_same_limit_episode` announces one episode once (a retry flips limited ⇄ working and used to pop up each time). No time on screen = limited until the screen changes. A busy marker ABOVE an idle composer is stale (`_IDLE_COMPOSER_RE`, Devin: "Ask Devin to build features").

A tab shows its panes rolled up (`kittymux_agents.tab_verdict`), not just the active pane. When the user is
elsewhere (agent not focused): tab glyph, header badges `! N  ✓ N` (all tabs), a desktop notification for needs-you
and for runs ≥ 15 s that finish, a WM urgency bell for needs-you only, `ctrl+alt+y` to jump. Off switches
(`notify-off`, `notify-done-off`, `bell-off` files / `KITTYMUX_NOTIFY`, `KITTYMUX_NOTIFY_DONE`, `KITTYMUX_BELL`) are in the README.
A window seen for the first time never notifies (a scanner restart must not replay old completions).
Markers are verified against live sessions per agent in `docs/compatibility.md` — check a real screen
(`kitty @ get-text --match id:N` → `kittymux_state.classify_screen`) before adding or changing one.
