# Status and attention contract

What every state means, who decides "done", how restore, the inbox, usage numbers and limits behave, and the invariants that keep them honest. Read it before touching the scanner, the resolver, notifications, sessions or the inbox.

Part of the agent guide: start at [AGENTS.md](../../AGENTS.md) (the rules and the "read before you change" table); this page is the reference for one area.

States, most important first — a state needs positive evidence, and silence is never "waiting":

| State | Evidence | Shown as |
|---|---|---|
| `limited` | "usage limit reached" / quota text on screen | `⊘`, alert colour |
| `waiting` | a permission/question prompt on screen, a hook message that is a real request, or a turn that ENDS asking you (the agent's own last reply: `bin/mux-status` turns a Stop/notify whose `last_assistant_message` / `last-assistant-message` ends in a question into `waiting` with that sentence; Claude and Codex only, hook-less agents stay `done`) | `!`, bold, rail stripe |
| `error` | the agent reported `error` over OSC 7501; the message is kept. A quiet screen is not a completion, and a screen that still looks busy does not hide it. A prompt or a usage limit on screen still outranks it | `✕`, alert colour |
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
- An OSC 7501 `error` is never a completion and never a "done" notification. It is an inbox event of kind `error` and, when you are not looking and not muted, a notification that keeps the message. A later, different report is announced again; the same report is not, including when it returns after a prompt or a limit. A text-only error already in the inbox does not swallow that popup. A mute or `notify-off` holds the popup; the event still reaches the inbox. A failure only mentioned in other text stays inbox-only. The words shown are the OSC reason, then the hook message.
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

**Muted** (`kittymux_quiet.mutes-<kitty pid>.json`: window ids, set by `kittymux mute`, `m` or a right-click in the panel; pruned as windows close) is not a state: the state stays
true everywhere. A muted window gets no popup and no bell (`kittymux_quiet.quiet_reason`, the same path as snooze), never counts as "needs you" (`kittymux_deck.asks`, the panel's chip, a
space's roll-up, `agents.json`'s `needs_you`), and is drawn quietly with a bell-slash. Its events still reach the inbox. `agents.json` rows carry `muted` (additive, version 1).

**Closing a busy agent** (`python/close-kit.py`, rules in `kittymux_closeguard`): a close key on a pane or tab whose agent is `working`, `waiting` or `limited` shows a one-line question for
`CONFIRM_S` (4 s) on the tab's row in the bar (`tab_bar._close_ask`, short form) and on the pane title bar when kitty draws one (`kittymux_panetitle.close_question`, full form); the same key again closes. No dialog, no overlay, no focus change, no Escape (Escape belongs to the agent). Nothing busy closes exactly as kitty would.

`sources` (who reported it: `agent`, `hook`, `screen`) is not `source` (what it is about). `source` is `agent` or `tool`. A sudo/ssh/git/pacman/paru/login prompt is an inbox event with `source: tool` and `agent` set to that program; it is not an agent row. Old events omit `source`. The field is additive: inbox `version` stays 1.

**The shell's list** (`python/kittymux_agentsnap.py`, pure; the scanner calls `publish` from `scan_all`, `poke` and `ensure_started`): `$KITTYMUX_STATE/agents.json`, schema version 1, mode 0600, one document for every running kitty. Each process replaces only its own rows and keeps a row whose kitty pid is still alive (`/proc`). The file is rewritten only when the serialized document minus `t` changes. States are the names in the table above (`limited`, never `limit`). Every row has `source: agent`. `action` is a `jump` that `kittymux_palette.validate_action` accepts. The icon basename is `kittymux_agents.brand_of` — one table, the SVG in `assets/icons`, not the notify PNG name. Shape, the version rule and the notification hints are `docs/inbox.md`.

**The shell's tabs** (`python/kittymux_tabsnap.py`, pure; `kittymux_scan.py` publishes once per pass): `$KITTYMUX_STATE/tabs.json`, schema version 1, mode 0600, every tab of every running kitty, not only agents, with the kitty theme's palette and, for a client drawn over the bar, its geometry. A tab's agent, state, `since`, progress, question and limit come from the pane that speaks for it (needs you, then error, then working, then the rest; a muted agent last). `action` jumps to the tab's active pane. Each process replaces only its own entries and keeps those of live kitties; the file is replaced only when the document minus `t` changes. Shape and the version rule are `docs/inbox.md`.

**`panes-<pid>.json` and `scan-<pid>.json` are that kitty process only.** `{}` means this process has no watcher entries and no known agent in the foreground group. A shell-only kitty, a short-lived helper, or agents that are running in a different kitty process all publish `{}`. That is not a merged "who is working" feed and not a missed agent. Do not invent rows to fill it. `agents.json` is the merged feed. `smoke_state` already shows that a kitty which is actually running an agent publishes a verdict.

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
A jump focuses the window and its tab in kitty, then exactly the OS window holding it (`kittymux_wmfocus.focus_address`, by address): never `focuswindow pid:`, which picks any of the kitty's OS windows and can switch another monitor's workspace. The same helper is what the agent picker, `focus_os_window_by_id` and `focus_moved_window` call. Hyprland 0.57 takes `hl.dsp.focus({window = 'address:…'})`; an older Hyprland still takes `focuswindow address:`. Which dispatcher this compositor runs is read from a probe that names a fake address and must say the window was not found. The probe never names a real window.
(`notify-off`, `notify-done-off`, `bell-off` files / `KITTYMUX_NOTIFY`, `KITTYMUX_NOTIFY_DONE`, `KITTYMUX_BELL`) are in the README.
A window seen for the first time never notifies (a scanner restart must not replay old completions).
Markers are verified against live sessions per agent in `docs/compatibility.md` — check a real screen
(`kitty @ get-text --match id:N` → `kittymux_state.classify_screen`) before adding or changing one.
