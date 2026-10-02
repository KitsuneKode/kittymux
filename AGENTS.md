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
  (`ctrl+alt+shift+b`): always-visible clickable sidebar, survives a hidden bar
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
- `docs/` — `compatibility.md` (which agent markers are verified), `audit-*.md`, `launch-checklist.md`
- `bin/mux-status` — agent hooks → `kittymux_status` window user var → recorded by `pane-state.py`
- `python/sidebar-kit.py` — `kitten` overlay: sidebar with real hover/click
  + live pane preview (bound `ctrl+alt+b`)
- `python/peek-kit.py` — the right-click peek card for one tab (kitten over the active window, opened by
  `kittymux_barsize._open_peek`; `kitty @ kitten --match id:W peek-kit.py <tab id>`)
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

**Every answer says why.** `kittymux_state.resolve` records a static, human `why` at each return (`_why`); the scanner publishes it in the verdict and writes every state change and every notification
outcome (`_notify` returns "sent" or why not) to the decision log (`_record`: a 300-event deque in `_RT` + `decisions-<pid>.jsonl`, 0600, rotated; `kittymux explain` reads it). A new state or a new
suppression rule MUST set a `why`/outcome, and a reason must be static text (no clocks or counters in it, or the published verdict changes every tick). Never log screen text.

A tab shows its panes rolled up (`kittymux_agents.tab_verdict`), not just the active pane. When the user is
elsewhere (agent not focused): tab glyph, header badges `! N  ✓ N` (all tabs), a desktop notification for needs-you
and for runs ≥ 15 s that finish, a WM urgency bell for needs-you only, `ctrl+alt+y` to jump. Off switches
(`notify-off`, `notify-done-off`, `bell-off` files / `KITTYMUX_NOTIFY`, `KITTYMUX_NOTIFY_DONE`, `KITTYMUX_BELL`) are in the README.
A window seen for the first time never notifies (a scanner restart must not replay old completions).
Markers are verified against live sessions per agent in `docs/compatibility.md` — check a real screen
(`kitty @ get-text --match id:N` → `kittymux_state.classify_screen`) before adding or changing one.

## Rules

- No hardcoded palettes (theme tokens come from kitty's live colours); no module-level timer state; never read silence as waiting.
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
- Keys: every new chord is checked against the window manager (`hyprctl binds -j`; `kittymux doctor` does all chords, `test_template_avoids_the_keys_hyprland_takes_with_ctrl_alt`
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
  Anything that must pick up an upgrade on `load_config` lives in a helper module that `tab_bar.py` reloads
  (it IS re-run on every config reload) and restarts: `kittymux_scan.restart()`, `kittymux_barsize.install()`.
- Long-lived state (timer ids etc.) lives in `sys.modules["_kittymux_scan_rt"]`, never in plain module
  globals — a reload re-executes the file and would forget a live timer (→ stacked timers = leak).
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
  `bash tests/smoke_inbox.sh` (real OSC 99 notifications from an agent pane → typed inbox events, the pane follows a completion, focus acknowledges),
  `bash tests/smoke_click.sh` (tab clicks with wobble and slowness; a middle-click spares an agent tab),
  `bash tests/smoke_native.sh` (kitty ≥ 0.49.2: the native divider's pixels, the real X cursor name over it, a native drag, the single-pane fallback),
  `bash tests/smoke_resize.sh` (a fast pointer burst: the bar edge reaches the pointer, every tab re-flows on release),
  `bash tests/smoke_panes.sh` (`ctrl+alt+shift+1..9` and the `ctrl+alt+e` overview agree on pane numbers; `ctrl+alt+PgUp/Home/End` scroll — real key events),
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
