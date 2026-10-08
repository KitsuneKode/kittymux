# kittymux

Kitty-as-multiplexer config pack: tabs, panes, session restore, agent-aware
tab bar, sidebar overlay, and overlays for keys/usage/cwd. tmux stays for
remote work.

## Layout

- `kittymux.conf` — main config (included from the user's kitty.conf)
- `kittymux-keys.conf.tpl` — keybind template; `install.sh` renders
  `@KITTYMUX_HOME@` into a generated conf. **Edit the .tpl, never the output.**
- `bin/kittymux` — the CLI: `doctor`, `demo`, `hooks [--install|--remove]`, `dim`, `screenshot`, `upgrade`
  (re-link + reload every kitty twice + doctor), `layout`
  (per-instance bar layout: `mode full|compact|hidden|cycle`, `edge`,
  `width`, `pick`, `default`). State: `$KITTYMUX_STATE/layout-<pid>.json`
- `bin/mux-panel` — docks `sidebar-kit.py` as a Wayland layer-shell panel
  (`ctrl+alt+shift+b`): always-visible clickable sidebar, survives a hidden bar. Keyboard focus is `summoned` (`exclusive`, what `toggle` starts with) or `docked` (`on-demand`, click to type), remembered in `$KITTYMUX_STATE/panel-mode`; changed at runtime with
  `kitten @ resize-os-window --action=os-panel --incremental focus-policy=…`. The panel gives the grab back on Esc/Q/jump and after `IDLE_DOCK_S` without a key — an exclusive grab must never be able to trap typing (`python/kittymux_panelfocus.py`, pure, `tests/test_panelfocus.py`; layer-shell cannot run under Xvfb, so the grab itself is checked by hand on Hyprland)
- `bin/` — shell scripts (mux-*); shared helpers in `lib/mux.sh`, `lib/socket.sh`
- `python/kittymux_layout.py` — layout engine; loaded via `geninclude` so its
  output must come LAST in kitty.conf (it wins over earlier tab_bar_* lines)
- `python/tab_bar.py` — custom tab bar (two-line vertical rows, brand icons,
  compact rail rendering; helper modules `kittymux_*.py` reload every config load)
- `python/pane-state.py` — kitty `watcher`: hook status + titles →
  `$KITTYMUX_STATE/panes-<kittypid>.json`. Holds no logic that must survive an upgrade (see below).
- `python/kittymux_state.py` (pure) + `kittymux_scan.py` (in kitty) — THE status resolver: twice a second reads
  the bottom of each agent pane's screen, combines it with hook state, publishes `scan-<kittypid>.json`.
  Every consumer reads that merged view via `kittymux_agents.load_panes/merge_scan` → `resolve_status`.
  Order: limited > waiting > working > done > idle; a state needs positive evidence (silence ≠ waiting).
- `python/kittymux_theme.py` / `kittymux_agents.py` / `kittymux_deck.py` — pure helper modules
  (no kitty imports; unit-tested in `tests/`). Theme tokens derive from live kitty colours; symlinked
  into the config dir by `install.sh`. Never hardcode a palette in `tab_bar.py`/`sidebar-kit.py`.
- `python/kittymux_ui.py` (pure) — the ONE place a cell-drawn surface learns what a card, gauge, chip, tab, keycap or chart looks like: a `Kit(palette, cells, rounded)` returns LINES of styled spans, each exactly the width asked for
  (`fit_line`), from glyphs kitty draws itself (half-block cards with quadrant corners, lower-half-block gauges, Powerline round caps). Every colour is a `Palette` token (`card`, `card_hi`, `track`, `on_accent` live in `kittymux_theme._surfaces`,
  the calm/warm/hot ramp reuses `done`/`waiting`/`alert`); text is `ink`ed to 4.5:1 on whatever it sits on; program/provider text is `kittymux_place.clean`ed. Shape rule: pills for chips/tabs/toggles, one chamfered radius for cards and buttons, square keycaps.
- `python/kittymux_meters.py` (pure) — ONE model for every provider's usage: rows → `quota | counter | state | spend` meters (numeric sidecars `rem_s window_s tok cached sess turns ago_s state plan status lines ai_pct` when a collector
  gives them, label/text heuristics otherwise, so an old `agent-usage.json` still draws). Views draw by KIND, never by provider name. History is read only from `_daily_version == 2` entries: older ones are rolling totals, never one day's burn.
- `python/kittymux_usageview.py` + `python/kittymux_inboxview.py` (pure) — the panel's Usage and Inbox views: lines plus click regions (`View.tiles`, `InboxView.chips/cards/buttons`); `sidebar-kit.py` places them (strip, header, footer keycaps, the
  resize handle) and owns keys, mouse and refresh. Narrow panels degrade in tiers (the share outlives the countdown; the filter chips go full words → glyphs → bare glyphs; buttons lose their key hints). The Inbox never types into an agent: Jump runs
  `kittymux inbox jump`, Dismiss only changes the event's status. `tests/shot_panel.sh` + `tools/demo_world.py` render and drive the real panel on synthetic data.
- `python/kittymux_agentsview.py` (pure) — the panel's Agents rows: `title_row` / `context_row` (2 lines per tab, the deck's `Item` heights, so `row_at`/`pane_at` still hold), `pane_row`, `header_row`, `summary_row`, and `action_bar` (clickable keycaps: `(key, label, token)`,
  tokens are the key the click presses; a hint has no token and no region). One bright thing per row; needs-you = stripe + tint; PR/ports only when lit; a one-cell gap before every mark and number (`tests/test_agentsview.py::GapTests` — a 26-column render found it). `sidebar-kit._footer` records each button's
  cells, `on_mouse_move` lights the one under the pointer, `on_click` runs `_press(token)` (the same handler as the key). Order buttons by importance: a narrow panel drops from the right. `tests/shot_agents.sh` + `tools/demo_agents.py` draw it; `tests/stress_panel.sh` drives the real panel and checks memory/fds/threads/idle CPU.
- `python/kittymux_titles.py` (pure) — what a tab is CALLED, for the bar AND the panel (one rule, never two): `tidy(raw, agent, project)` cleans a window title (control chars, markdown, quotes, trailing punctuation), treats the agent's product name and
  assistant-sounding replies (`looks_like_reply`: first-person/apology/"here's" openers; interjections like "okay"/"yes" only with punctuation after them, so "Okay button styles" stays a title) as NOT a title and shows the PROJECT instead; `shorten` cuts at a word.
  Switch: `titles` (`kittymux features off titles`). The panel keeps `RowData.raw_title` for the `/` search. `tab_bar._tidy_title` is the one bar call (3 sites + the `_title_keys` cache signature).
- `python/kittymux_helpview.py` (pure) — the panel's `?` card (keys + mouse of the current view; the key list is data, `tests/test_helpview.py` checks every named key is one the panel handles). `kittymux_deck.wrap_words` wraps prose at spaces (`wrap_detail` splits characters: for paths).
  A split tab's panes are listed only for tab ids in `Snapshot.open_tabs` (`sidebar-kit._open`; `deck.flatten(…, open_tabs)`): toggled by `▸`/`▾` clicks, `→ ← o`; NEVER by hover or by a state change (the list must not move under the pointer).
- `python/kittymux_palette.py` (pure) + `python/palette-kit.py` + `kittymux palette|act` (`ctrl+alt+shift+space`) — the command palette: `build(tabs, pick rows)` → items in groups (Needs you, Inbox, Tabs, Agents, Actions; `extra` rows — new agents past the
  first four, split variants — only show for a query), ranked by `score`, drawn with the shared kit. The kitten ONLY CHOOSES: `handle_result` runs `kittymux act JSON` from kitty (`boss.run_background_process`, so the CLI's parent is kitty and `_own_kitty_socket` works) AFTER
  the overlay is gone (a focus change made while it was open would be undone when it closes). `act` re-validates with `kittymux_palette.validate_action` (ids are ints, journal keys match one shape, agents must be installed, `run` ids are a fixed whitelist
  of kittymux argvs): never add an op there without extending the validator and `tests/test_palette.py`'s refusal list. `tests/smoke_palette.sh` drives it with real keys and mouse.
- `python/kittymux_ledger.py` (pure) — the wait ledger: how long agents waited on you, from an inbox event's `t0` (first appeared) to its `ack_t` (first looked at; both are optional fields `kittymux_inbox.fold` keeps, schema
  version unchanged), a wait counting at most `CAP_S` toward a total. A card at the bottom of the panel's Inbox view and `kittymux inbox ledger`. It says "how fast you got to each agent", never "how long the answer took".
- `python/kittymux_features.py` (pure) + `kittymux features [list | on|off NAME | preset minimal|default|full]` — the switchboard for the optional pieces of the bar: `folder`, `hue`, `collide`, `panetitle`, `motion` are live (`motion` off = `state_glyph(animate=False)`, a still frame; the scanner's spin timer, the panel's `_schedule_spin` and the bar all read it, the bar once per pass); `sheet`,
  `hover` are planned (saved, nothing reads them — the CLI says so). Precedence: env `KITTYMUX_<NAME>` > flag file `<name>-off|-on` in `$KITTYMUX_STATE` > default; the bar resolves it once per pass
  (`tab_bar._features`). With `folder` off the bar draws the line it always drew — keep that path as it was.
- `python/kittymux_prompts.py` (pure) + `kittymux_scan.scan_prompt` — a PLAIN terminal waiting on you (sudo/doas/su/pkexec password, ssh/git login, pacman/paru/apt `[Y/n]`): the LAST screen line must match a rule, and either be wording only that tool prints (`[sudo] password for X:`) or appear while that program leads the pty
  (`fg_job`: the foreground group is not the shell's own; only then is the screen read). Fixed event text (`rule.say`; the matched line holds a user name/host and is never stored, logged or shown), announced via `_announce` after `PROMPT_SETTLE` (1 s), cleared (inbox `ack`) when the prompt goes, a window's first scan never announces.
  It never touches the tab's verdict (that is agent-only: `has_agent`). Switches `sudo`, `loginprompt`, `pkgprompt` in kittymux_features. Adding a program or pattern = a `Rule` in `RULES` + a test in `tests/test_prompts.py`; `tests/smoke_prompts.sh` drives a real kitty.
- `python/kittymux_sockets.py` also owns the **legacy socket link** (`legacy_link`, `prune_links`, `dedupe`; scanner `_socket_link`, once per kitty and on reload, switch `socketlink`): the socket lives in `$XDG_RUNTIME_DIR` (private) but scripts written for `listen_on unix:/tmp/mykitty` look ONLY at
  `/tmp/mykitty-<pid>` — the day the socket moved, every one of the user's own scripts (scratch tab, nvim/hypr/zsh/kitty config chords, font toggle, snapshot…) silently found no kitty, and a key-bound background script has nowhere to print an error. The link is made only for kitty's own `<name>-<pid>` socket, never over
  anything that exists, and dead ones are pruned. Discovery (`_sockets()`, `lib/socket.sh`) lists a socket and its link ONCE (`dedupe`, by realpath) or every agent would show twice. NEVER move a socket, a flag file or a path other tools read without checking who reads it (`grep -rn mykitty ~/.config`), and say so in `doctor`.
- `python/kittymux_timers.py` — EVERY timer kittymux gives kitty (`add_timer`) goes through `kittymux_timers.add(__name__, "func", interval, repeats)`: a callable that is ONE object for the life of the process and looks the function up by name when it fires. Why: kitty runs due timers from a snapshot (glfw `dispatchTimers`) and drops its reference when a callback
  removes another due timer; a function that a re-executed module no longer holds is then FREED while kitty still calls it → SIGSEGV in `python_timer_callback` (coredump 2026-10-07 22:57; `tests/smoke_timers.sh` reproduces it with a raw pair and proves the fix). A timer callback must also ignore a tick whose id is not the live one (`scan_all`, `_spin_tick`, `_watchdog`, `_trail`).
  Never pass kitty a lambda/closure/module function directly, never remove or replace a timer without this module.
- `site/` — the documentation site (TanStack Start + Fumadocs + shadcn; tokens in `site/src/styles/tokens.css`, contrast-tested). `docs/` stays the ONLY source of prose: `site/scripts/sync-docs.mjs` validates and copies it; `tools/export_facts.py` exports keys/agents/states/features from the product's own parsers; `tools/build-site-assets.sh` regenerates the screenshots from the repo's rigs. In `site/`: `bun run check` (sync + tests + build + crawl), `bun run axe` (accessibility, overflow, search), `bun run budget`. Not deployed. See `site/README.md`.
- `python/kittymux_place.py` (pure) — the folder line under a vertical tab: `facts` (project / worktree / inner / where / branch), `layout` (what fits: branch goes first, then the path, then the icon; the worktree outranks the
  path; the project name is only ever middle-truncated), `place_room` (the room pieces drawn AFTER it keep), `style` (one bright element per row), and the title rules `redundant` / `worktree_named` / `colliding`.
  `kittymux_theme.project_hue` is a stable, calm per-project tint (SHA-1 slots, never `hash()`), kept clear of the state colours and ≥ 4.5:1 on the row. The bar compares what is DRAWN — `tab.name or tab.title`
  with the agent prefix stripped — never the raw window title. `KITTYMUX_BAR_DUMP=1` writes `$KITTYMUX_STATE/bar-dump.json` — per tab: the folder line AND the title row as drawn (a test hook for `tests/smoke_place.sh`, `smoke_titles.sh`).
  Text from a program or a directory name is `kittymux_place.clean`ed everywhere it is drawn (kitty's own title sanitiser lets ESC through). An agent whose window title is only its product name (`kittymux_agents.is_default_title`)
  is shown as its project; `kittymux resume-prompt` titles its window while it asks and clears the title before the exec.
- `python/kittymux_panetitle.py` + `python/window_title_bar.py` — the folder line in kitty's per-pane title bars (kitty ≥ 0.49.2). kitty loads `window_title_bar.py` ONCE per process, so it is a trampoline into
  `kittymux_panetitle.draw` (reloaded by tab_bar.py like the other helpers). `kittymux_layout.gated_conf` emits `window_title_template` with `{custom or title}`: an empty hook result (switch off, failure, no directory)
  falls back to kitty's own title, never a blank bar. Colours derive from the bar's REAL fg/bg (`window_title_bar_*` else the tab colours) and `kittymux_theme.ensure_contrast` turns the other way on mid-tone
  backgrounds. `KITTYMUX_PANETITLE_DUMP=1` records what each pane drew (`tests/smoke_panetitle.sh`).
- `tests/shot_panes.sh` — the pane-guide screenshots (`assets/panes-*.png`: layout, `ctrl+alt+e` digits, six `alt+shift+l`, `alt+shift+=`), taken with REAL key events in a private kitty; asserts the widths it claims (50 → 70 → 50/50 columns). Re-run after changing a pane key or the look of kitty borders.
- `tests/shot_bar.sh` — a screenshot of the bar (dark|light, any width, rail) with synthetic repos; `tests/profile_bar.sh` — draw cost with N tabs (compare two trees; the folder line costs ~0.02 ms/draw at 23 tabs).
- `assets/notify/` (built by `tools/build-notify-icons.py`) — one PNG per agent for notifications; `docs/brand/` — the mascot
  brief and image-model prompts (`tools/build-brand.py` derives sizes from `assets/brand/mascot.png`); `docs/notifications.md` — the
  notification flow, security model and limits. Icons are chosen from OUR table only, never from agent output.
- `python/kittymux_openref.py` (pure) + `bin/mux-open-ref` + `open-actions.conf.tpl` — clickable `path/file.py:42[:7]`: kitty ≥ 0.49.2
  `detect_url_regex` finds it, open-actions runs `mux-open-ref` (validated, never a shell, must be an existing regular file) → `$VISUAL`/`$EDITOR` at the line
- `bin/mux-keys.py` — the `ctrl+alt+/` keymap overlay: parsed live from the rendered conf + extras for the deck/mouse/CLI; scrollable, searchable,
  1–3 columns by width; pure helpers (`filter_sections`, `build_body`, `parse_input`, `step`) are unit-tested
- `bin/mux-notify` — one desktop notification with a "Jump to it" action (focuses the window via kitty
  remote control, then `hyprctl`); started detached by the scanner, lives ≤ 30 s
- `python/kittymux_barsize.py` — bar sizing + the `TabBar.tab_id_at` hit-test wrapper (installed by `tab_bar.py`)
- `python/kittymux_launcher.py` (pure) + `kittymux spawn|pick|reopen|notify|snooze` — docs/launcher.md: agents spawned into a tab (before the `!scratch` tab) or split via `kitty @ launch`; `pick` builds rows (needs-you longest-waiting first → running → closed → new) for rofi/fuzzel/fzf; the focused kitty is chosen BEFORE the menu opens; `assets/agent-risk.json` (flags read from each CLI's `--help`) marks agents started without approvals; pin/settle are journal flags (`pinned`, `settled`, `flags_ts`) merged BY `flags_ts` in `flush` (a stale scanner copy must not erase a user's pin), settled = closed and untouched 3 days or settled by hand
- `python/kittymux_changes.py` + `kittymux changes|checkpoint` — what an agent changed: the scanner (`_checkpoint`) runs a detached `kittymux checkpoint start|finish` on idle/done→working and working→waiting/limited/done/idle (never on first sight); snapshots via a TEMP index + private object dir (`changes-objects/`), cached in `changes-<kittypid>.json`; shown by the bar on a done tab, `pick` rows and the CLI. Never run git on kitty's main thread; never write into the user's repo
- `python/kittymux_fanout.py` + `kittymux fanout` + `assets/agent-prompt.json` — one prompt to several agents, one git worktree/branch/tab each: all-or-nothing creation with rollback, never reuses an existing path/branch, the prompt is ONE argv element in each CLI's verified form (read from its `--help`; never guess a form), `compare` diffs each worktree against the base via kittymux_changes (read-only), `clean` is a dry run without `--yes` and keeps dirty worktrees without `--force`
- `python/kittymux_join.py` (pure) + `python/join-kit.py` + `kittymux join` (`ctrl+alt+shift+j`) — move a tab's panes into another tab as splits, keeping their shape. `plan` orders the windows and says for each which
  already-placed pane it goes next to (from the source tab's real pixel geometry); the kitten moves them with kitty's own `Tab.detach_window` → `attach_windows(next_to=, horizontal=, after=)` (what its drag-and-drop uses; `detach-window
  --target-tab` pane by pane splits ONE pane again and again: 15/7/7-column slivers) and pushes the first pane to the tab's edge (`move_to_screen_edge`) so the block gets a whole side. Splits layout only: another layout places windows
  itself. The picker (hover/click/keys, side, tab-or-pane) runs in the kitten's own process; the move runs in kitty (`handle_result`). Row widths come from `row_budget` (title, then folder, the pane count goes first).
- `docs/index.mdx` + `docs/users/` + `docs/developer/` (+ `meta.json`, `feature-status.yaml`, `promotion-manifest.yaml`, `troubleshooting-symptoms.yaml`) — the published docs, written for a TanStack Start + Fumadocs site (frontmatter `title`/`description`, `/docs/...` links, `/assets/...` images, only Fumadocs components). The status tables on `users/what-you-can-do.mdx` are GENERATED from `feature-status.yaml` by `tools/docs_status.py` (`--check` in the tests). `tests/test_docs.py` guards frontmatter, navigation, links and anchors, MDX safety, every `ctrl+alt` chord a page names being bound, and the CLI reference covering every command. A change to a command, a key or the feature YAML updates the docs in the same commit.
- `docs/` (flat `*.md`) — `compatibility.md` (which agent markers are verified), `audit-*.md`, `launch-checklist.md`; the source notes `promotion-manifest.yaml` maps to published pages
- `bin/mux-status` — agent hooks → `kittymux_status` window user var → recorded by `pane-state.py`
- `python/sidebar-kit.py` — `kitten` overlay: sidebar with real hover/click
  + live pane preview (bound `ctrl+alt+b`)
- `python/peek-kit.py` — the right-click peek card for one tab (kitten over the active window, opened by
  `kittymux_barsize._open_peek`; `kitty @ kitten --match id:W peek-kit.py <tab id>`). `kittymux peek [TAB_ID | --waiting]` (`ctrl+alt+shift+q`) opens it from the keyboard: the pane to show it over is `$KITTY_WINDOW_ID` when that is a real pane
  of this kitty, else the FOCUSED pane (a key-bound `launch --type=background` gets the id of its own hidden window, which no `--match id:` finds); `--waiting` = `kittymux_launcher.needs_you_target` over `build_rows` (the order `pick` uses), this kitty only
- `python/collectors/` — per-provider usage collectors (claude/codex/cursor/devin)
- `tools/build-icons.py` — builds the PUA icon font the glyphs live in
- `install.sh` — symlinks/copies into `~/.config/kitty`, renders the tpl

## Status & attention contract

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

## Rules

- **No credential — real or credential-SHAPED — in the repository, ever** (tests, docs, fixtures, commit messages). A real token once reached a public commit because a test fixture was copied from a process
  listing. Never copy a value out of tool output, `ps`, `env`, logs or the user's data into a file: build sample values at run time from filler (`"sbp_" + "x" * 24`), and use obviously synthetic ids
  (`0a1b2c3d-0000-4000-8000-000000000001`, `calm-otter`) — not session ids, names or paths from the user's machine. `tests/test_no_secrets.py` and the CI gitleaks job enforce it; if something does get in, rotate it first, then
  remove it from history with the *smallest* rewrite (the commits are GPG-signed: `git filter-repo` re-writes every SHA and drops every signature — amend the one commit and force-push with a lease instead).
- No hardcoded palettes (theme tokens come from kitty's live colours); no module-level timer state; never read silence as waiting.
- Recommend `allow_remote_control socket-only` + `listen_on unix:${XDG_RUNTIME_DIR}/mykitty` everywhere (README, install hint, doctor, error messages); every smoke rig runs under `socket-only` — never write a rig or doc that needs `yes`. Printed output that may be pasted (`sessions list/history --json`) goes through `kittymux_journal.redact_argv`.
- **A test must never touch another kitty on the machine.** The author is usually typing in a live kitty while tests run, and `kitty @ launch` follows focus: a rig once spawned fake agents (and, via a different PATH, the REAL `claude`) into the live kitty, which also polluted the real journal. Rigs: set `KITTYMUX_SOCKET_DIRS=$RUN` for their own kitty and end with a tripwire that compares every OTHER kitty's window count (see `smoke_spawn.sh`). Code: a command started inside a kitty acts on THAT kitty (`_own_kitty_socket`), never on 'the focused one'; focus-guessing is only for launchers started outside every kitty.
- Never restart the user's live kitties. Work in an isolated worktree INSIDE the repo — `git worktree add .worktrees/<name> -b <name> main`
  (`.worktrees/` is git-ignored, and editors/agents scoped to this folder can see it) — test with the smoke rigs, merge to `main`, then apply
  to live by reload only (`kittymux upgrade`); record `kitty @ ls` window counts before/after. `main` is what live kitties load, so never
  leave it half-edited.
- Icons come from real brand marks: `assets/icons/*.svg` → `tools/build-icons.py` (append-only codepoints; fits non-square
  viewBoxes by their longest side). Devin's mark is Cognition's own; Antigravity's is the Google mark.
- A glyph added to the icon font reaches a RUNNING kitty only after a restart (it loads fonts once): draw a new glyph only when
  `kittymux_agents.glyph_font_loaded()` says that kitty started after the installed font (see the mascot in the bar header).
  The mascot glyph (E0F9) is traced from `assets/brand/mascot.png` by `tools/trace-mascot.py` → `assets/icons/kittymux.svg`.
- Never move the user's focus unasked. A bell → `window_alert_on_bell` → xdg-activation request is turned into a focus change (and a workspace switch) by compositors with Hyprland's `misc:focus_on_activate`;
  `kittymux_layout.attention_conf` (geninclude) switches kitty's alert off and `kittymux_scan._alert` skips the bell when `hypr_focus_on_activate()` is true (override: `attention-on`). Focus moves only on a user
  action (click, `inbox jump`, `ctrl+alt+y`, a notification action). Tests that touch this must not depend on the compositor running them (patch `hypr_focus_on_activate`).
- Options that only exist in newer kitty (`detect_url_regex`, `custom_shaders`) NEVER go in `kittymux.conf`: an older or still-running kitty reports a
  config error at every reload. They are emitted by `kittymux_layout.gated_conf(version, …)` (the geninclude), keyed on the version of the kitty process asking
  (`kitty.constants.version` — a kitty updated under a running session still reports its old version, which is exactly what we want). Opt-in looks
  (`kittymux dim`) are flag files in `$KITTYMUX_STATE`, never default-on. Custom shaders also need `slangc` installed (`have_slangc`).
- Keys: every new chord is checked against ALL of: our template, `kittymux.conf`, the user's own kitty confs (modifier ORDER differs: `ctrl+shift+alt+r` is `ctrl+alt+shift+r` — `test_no_chord_is_bound_twice…` normalises) and the window manager, and tried with REAL key events (`smoke_spawn.sh`). Also: kept-quiet is not lost — mute/snooze (`kittymux_scan._quiet_reason`) suppress popups and bells but every event still reaches the inbox. Keys: every new chord is checked against the window manager (`hyprctl binds -j`; `kittymux doctor` does all chords, `test_template_avoids_the_keys_hyprland_takes_with_ctrl_alt`
  pins the known-taken `ctrl+alt` letters: a s f c x p w m + arrows/minus/equal). Hyprland sees a global chord first; `ctrl+alt+p` once shipped and was dead on arrival.
- Overlay UIs (`launch --type=overlay`): one keypress must close them. Never `sys.stdin.read(n)` for a fixed n (a lone Esc blocks until n bytes arrive — it took 3 presses to
  quit); read what is there with `select`/`os.read`, parse sequences, treat a lone ESC as Escape. The key that opens an overlay is still bound while it has focus, so give the
  overlay a title and add `map --when-focus-on title:<t> <same chord> close_window`, or the chord stacks another overlay.
- Anything that changes a key updates `kittymux-keys.conf.tpl` AND the README key table in one commit.

## Conventions

- Runtime state under `$KITTYMUX_STATE` else `$XDG_STATE_HOME/kittymux`;
  panes/usage caches are per-kitty-PID (`panes-<pid>.json`).
- Python files run under kitty's bundled interpreter — `kitty.*` and
  `kittens.*` are importable there, not under system python.
- `# key — description` comments in the conf feed `bin/mux-keys.py` (the
  `ctrl+alt+/` overlay). Keep the comment format so docs never drift.
- Ownership: kitty owns tabs/panes/sessions; the WM owns OS-window borders
  and global chords — check `hyprctl binds` before taking a `ctrl+alt+` key.
- **kitty caches watcher modules per path for the life of the process** — `on_load` and `pane-state.py` run once.
  Anything that must pick up an upgrade on `load_config` lives in a `kittymux_*.py` helper: `tab_bar.py` (re-run on every config reload) refreshes EVERY kittymux module the process has imported, dependencies first (`kittymux_reload.reload_all` — a hand-kept list
  missed the helpers imported lazily on first use, so a day-old inbox/sockets module served a new scanner), then restarts what runs on timers: `kittymux_scan.restart()`, `kittymux_barsize.install()`.
- Long-lived state (timer ids etc.) lives in `sys.modules["_kittymux_scan_rt"]`, never in plain module
  globals — a reload re-executes the file and would forget a live timer (→ stacked timers = leak).
- **A look is verified by looking.** Before and after a visual change render the bar with `tests/shot_bar.sh` (and the panel with `tests/shot_panel.sh`, narrow too: a 26-column panel found three layout bugs unit tests missed) (dark AND light, the 30-column bar and the narrowest one) and read the PNG — unit tests did not catch a hue
  palette of four near-identical greens that sat next to the "done" colour. A tint stays quieter than the state colours; the name is the one bright thing on a row.
- **Redraw = three calls**: `tm.update_tab_bar_data()`, `tm.mark_tab_bar_dirty()`, then `mark_os_window_dirty(id)` +
  `wakeup_main_loop()`. The first two only update cells; without the last two kitty does not render until the
  cursor blinks (a 10 fps spinner ran at ~1 fps on an idle window). Use `kittymux_scan.refresh_bar`.
- `sys.path`: a module's OWN directory must win over the config dir (insert config first, own last),
  or tests/rigs silently import the installed copy instead of the code under test.
- `kittymux_barsize` keeps its drag/button state in `sys.modules["_kittymux_barsize_rt"]`: changing the width makes kitty
  re-run `tab_bar.py` (→ reloads helper modules) in the middle of a drag, and module globals would be wiped (the first
  motion applied a width, the second found no drag). Same rule as the scanner.
- Redraw cost: kitty redraws the whole vertical bar tab by tab (~10×/s while an agent works). Shared lookups (palette, merged pane state, verdict roll-ups, keyboard mode, usage alert, native-edge check)
  are memoised PER PASS (`tab_bar._per_pass`, reset when tab 1 is drawn): 6.0 → 2.1 ms with 23 tabs. Don't add per-tab `os.stat`/file reads/subprocesses to the draw path; add a `@_per_pass` helper. The spinner
  ticks unfocused OS windows at half rate. `_flush` does not even serialise verdicts on a tick where no verdict changed.
- Tab clicks (kitty 0.49.2 `TabManager.handle_tab_bar_mouse`): a left PRESS only arms a drag; the tab is activated on the left RELEASE and only if `MouseEvents.is_click` holds — press+release within
  `click_interval`, **< 5 px apart**, same tab — while a drag needs `drag_threshold` (we set 14 so a wobbly click is not a drag). Movement of 5–14 px was therefore neither: the click silently did nothing
  (real mice/touchpads wobble this much, more on a scaled display; scripted clicks never do). `kittymux_barsize._tap_before/_tap_after` record the press and, when kitty did not act, activate the tab under a rule
  that matches the drag threshold (≤ max(5, drag_threshold) px, ≤ 1.5 s, same tab, no drag started). A middle-click on a tab running an agent is swallowed (kitty closes tabs on middle-click, and only asks if
  `confirm_os_window_close` says so). Smoke tests MUST click with wobble (`tests/smoke_click.sh`): a perfect click hides this whole class of bug.
- Bar drag-resize (`kittymux_barsize`): per mouse event `apply_width(final=False)` re-lays-out the bar and ONLY the visible tab; the release (or the watchdog /
  an error, via `_end_capture(finalize=True)`) applies `final=True` once for every tab. Events inside the pacing window are NOT dropped: `next_apply` arms one
  trailing timer that applies the pointer's latest width (the old code left the bar stuck until release after a fast burst). Why not relayout every tab per event:
  kitty itself retains ~100 objects (~14 MB per 1000) per option-change+relayout of 23 tabs (measured identical in a vanilla kitty), so touching one tab is 28× less.
  The pointer over the tab bar is ALWAYS a hand: kitty picks it in C for the whole bar rect, sends our code no hover and ignores OSC 22 there — a resize cursor over the bar
  edge is not possible (only real window dividers and the docked panel get one).
- Native divider (kitty ≥ 0.49.2, `kittymux_barsize._install_native_edge`): we wrap `kitty.borders.set_borders_rects` to add (a) two coloured `Border` rects — colour `(rgb << 8) | BorderColor.window_bg`, exact
  pixels, drawn by kitty's GPU border renderer in the pane padding next to the bar — and (b) one invisible hit rect (`border_type` < 0 = left edge, > 0 = right) over them. kitty hit-tests it IN C
  (`mouse_region`): hover → native `sb_h_double_arrow`, press → `Boss.drag_resize_start` (we answer for our rect), then `drag_resize_update/_end` until release, cursor restored by C. C only runs
  border hit-tests when the tab has 2+ visible windows, and the cursor over the tab bar rect is ALWAYS a hand (`in_tab_bar` → `POINTER_POINTER`) and the bar gets no motion events ("expensive and useless"
  in `handle_tab_bar_mouse`). So: split tabs get the arrow, single-pane tabs the bar-side grab zone. Wrappers must delegate to module-level functions by name (a reload re-executes this module in place);
  they never raise; the hook costs ~35 µs per border refresh and retains nothing. `L.edge_geometry` is the pure geometry; `tests/smoke_native.sh` reads the real X cursor and pixels.
- The divider (cell fallback: padding < 10 px, or a kitty we have not verified) is two hairlines in the bar's last two columns (`tab_bar.SEP_COLS`, `SEP_EIGHTS`); content stays left of them. The resize hit area is `kittymux_layout.in_grab_zone`: centred on
  the seam between them (`DIVIDER_CELLS`), ±`GRAB_CELLS` — exactly those two columns — so it never steals a click meant for a tab; the collapse button stops where it starts.
  Right-edge bars still draw the divider on the screen-side (outer) edge: a known limitation, not mirrored yet.
- The header row's `«`/`»` is a button: `kittymux_barsize._handle` consumes its press+release and toggles
  full ↔ rail via a saved layout + `load_config_file`. Build the toggled layout from the LIVE bar when nothing was saved.
- kitty caps every vertical tab's HEIGHT at `tab_title_max_lines` (kittymux.conf sets 4): a tab that draws more rows spills into
  the spacer row (no gap, no hairline, wrong extent). The first tab's header (2 rows) + title + subtitle must fit in the cap —
  `kittymux_layout.header_rows` degrades to a 1-row header when the cap is 3.
- kitty ≥ 0.49.2 reorders dragged tabs by INSERTION (`TabBar.tab_insertion_target_at`, drop marker, `TabBeingDropped(tab_id, tab_ids)`);
  our 0.49.1 drag patches check `kittymux_barsize.native_insert_drag()` and stand down (only `_drop_spans` is nudged so the first tab's
  header does not count). Never touch `TabBeingDropped` without checking its fields.
- Tab drag-and-drop (0.49.1): kitty's first `on_tab_drop_move` of a drag has x=y=0 and seeds the dragged tab at the END (it jumped to the
  top of a vertical bar); `kittymux_barsize.make_on_tab_drop_move` seeds the real order, and `make_tab_id_at` applies
  `kittymux_layout.drag_target` (a tab counts only past its midpoint) so unequal tab heights cannot cascade swaps.
- Vertical-bar hit testing: kitty's tab extents skip the spacer line between tabs; `kittymux_barsize` wraps
  `TabBar.tab_id_at` (`kittymux_layout.snap_tab_id`) so drag-sorting and clicks on the gap resolve to the nearer tab.
- Python kittens are `exec`'d, not imported — no `__file__`, use
  `KITTY_CONFIG_DIRECTORY`; `styled()` wants `Color` objects, not ints/strings.

## Verify

- `python3 -m unittest discover -s tests` and `bash tests/test_mux_status.sh && bash tests/test_socket_lib.sh`.
- Real-kitty smoke tests (Xvfb, private config/socket, SKIP if tools are missing): `bash tests/smoke_state.sh`
  (states from screens, spinner frame rate on an idle window, spacer-row click) and `bash tests/smoke_reload.sh`
  (a running kitty upgraded under itself must draw cleanly after two reloads; `SMOKE_KEEP_STALE=1` must FAIL).
  `bash tests/smoke_sidebar.sh` (collapse/expand button, right-click peek, edge drag with real mouse events),
  `bash tests/smoke_drag.sh` (tab drag-to-reorder with real pointer events — kitty's DnD works under Xvfb),
  `bash tests/smoke_resume.sh` (fake agents → `sessions save` → a second kitty restores them: claude started with `--resume <id>` and its flags, a lone opencode with `-c`, ambiguous droids as saved; autosave + pruning),
  `bash tests/smoke_spawn.sh` (spawn by CLI and by real keys, pick through a fake rofi, reopen, mute/snooze),
  `bash tests/smoke_fanout.sh` (one prompt → three fake agents in three real worktrees in a real kitty, each CLI's own prompt form, compare/clean, main checkout untouched),
  `bash tests/smoke_changes.sh` (a fake agent edits a real git repo: baseline at run start, summary at run end, dirty-before and ignored files excluded, repo untouched),
  `bash tests/smoke_socket.sh` (`allow_remote_control socket-only` refuses a printed escape sequence — `yes` obeys it, the control — and the `$XDG_RUNTIME_DIR` socket is discovered),
  `bash tests/smoke_inbox.sh` (real OSC 99 notifications from an agent pane → typed inbox events, the pane follows a completion, focus acknowledges),
  `bash tests/smoke_click.sh` (tab clicks with wobble and slowness; a middle-click spares an agent tab),
  `bash tests/smoke_native.sh` (kitty ≥ 0.49.2: the native divider's pixels, the real X cursor name over it, a native drag, the single-pane fallback),
  `bash tests/smoke_resize.sh` (a fast pointer burst: the bar edge reaches the pointer, every tab re-flows on release),
  `bash tests/smoke_panes.sh` (`ctrl+alt+1..9`, `ctrl+alt+0` = last pane and the `ctrl+alt+e` overview agree on pane numbers; `alt+1..9` / `alt+0` jump tabs; `alt+shift+h/l` resize ~3 columns and `alt+shift+=` equalizes; ends with a focus tripwire on every OTHER kitty; `ctrl+alt+PgUp/Home/End` scroll — real key events),
  `bash tests/smoke_prompts.sh` (a script printing sudo's prompt, a copy of bash named pacman/ssh: one fixed-text event each, cleared by answering, acknowledged when looked at, the switch silences it),
  `bash tests/smoke_legacy_socket.sh` (the socket in a private runtime dir, a key bound to a script that looks ONLY at <legacy dir>/mykitty-$PPID opens its tab; control: with `socketlink` off it does not; dead links are pruned),
  `bash tests/smoke_place.sh` (the folder line: twins, hidden duplicates, worktrees, a split's room, every switch on its own, all-off = the old line),
  `bash tests/smoke_panetitle.sh` (the folder line in pane title bars: bold on the focused pane, own title appended only when new, an empty title, tab renames, the switch),
  `bash tests/smoke_titles.sh` (what a tab is CALLED: fresh shell, named/renamed/cleared tab, program titles, agents with and without a conversation title, a stale title, the resume prompt, hostile/long/blank/path titles),
  `bash tests/smoke_join.sh` (a three-pane tab joins a two-pane tab: all panes present, the big-pane + stack shape kept, no pane narrower than 18 columns, same-tab/missing-tab/bad input change nothing, a tall-layout target works) and
  `bash tests/smoke_join_ui.sh` (the picker with real key and mouse events: chord, one Esc, no stacking, filter, side, tab/pane, hover, Enter, left click joins, right click does not),
  `bash tests/smoke_palette.sh` (the command palette with real keys and mouse: chord opens/closes, typing filters, esc clears then closes, Enter/click focus a tab or jump to an event, fixed actions run, hostile `act` payloads are refused; tripwire on other kitties),
  `bash tests/smoke_peek.sh` (quick look with real keys: nothing waiting opens nothing, the card is about the longest-waiting agent's tab, the chord again closes it, one Esc stays, ⏎ jumps),
  `python3 -m unittest tests.test_docs` (the published docs: links, chords, CLI coverage, status table, voice) and
  `bash tests/smoke_demo.sh` (`kittymux demo` opens every showcase tab — the front door must stay healthy),
  `bash tests/smoke_keys.sh` (the keymap overlay: one Esc/q/the chord closes it, no stacking, typing filters),
  `bash tests/smoke_openref.sh` (ctrl+shift+click on `src/app.py:42:7` opens `$EDITOR +42`; kitty ≥ 0.49.2),
  `bash tests/smoke_extras.sh` (`kittymux screenshot`; `kittymux dim` when `slangc` exists),
  `bash tests/smoke_workflows.sh` (two kitty instances with overlapping IDs: scratch isolation, target PID verification,
  unnamed-session attention jumps) and
  `bash tests/test_install.sh` (fresh-$HOME install → reinstall → config valid → uninstall; needs only kitty).
  They need modules as real copies in ONE config dir — a rig that mixes repo and config dirs hides real bugs.
- Kitten UI can be screenshotted offscreen: Xvfb + `env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa
  LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=:99 kitty -o linux_display_server=x11 …`, then `xdotool windowsize` (forces a
  first redraw) and `import -window root out.png`.

- `python3 -m py_compile` on touched python; `bash -n` on shell.
- Reload a live kitty: `kitty @ --to unix:/tmp/mykitty-* action load_config_file`.
- Scratch instance for UI tests:
  `kitty --class X --listen-on unix:/tmp/X --session file` then
  `kitty @ --to unix:/tmp/X ls` / `get-text` to inspect without screenshots.
- README's key table must stay in sync with the .tpl.
- `docs/testing.md` separates automated edge-case coverage from manual compatibility checks; never promote a
  mocked provider response or an Xvfb run into a claim of live-provider / compositor verification.
