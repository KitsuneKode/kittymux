# kittymux

Kitty-as-multiplexer config pack: tabs, panes, session restore, agent-aware
tab bar, sidebar overlay, and overlays for keys/usage/cwd. tmux stays for
remote work.

## Layout

- `kittymux.conf` — main config (included from the user's kitty.conf)
- `kittymux-keys.conf.tpl` — keybind template; `install.sh` renders
  `@KITTYMUX_HOME@` into a generated conf. **Edit the .tpl, never the output.**
- `bin/kittymux` — the CLI: `doctor`, `demo`, `hooks [--install|--remove]`, `upgrade`
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
- `bin/mux-notify` — one desktop notification with a "Jump to it" action (focuses the window via kitty
  remote control, then `hyprctl`); started detached by the scanner, lives ≤ 30 s
- `python/kittymux_barsize.py` — bar sizing + the `TabBar.tab_id_at` hit-test wrapper (installed by `tab_bar.py`)
- `docs/` — `compatibility.md` (which agent markers are verified), `audit-*.md`, `launch-checklist.md`
- `bin/mux-status` — agent hooks → `kittymux_status` window user var → recorded by `pane-state.py`
- `python/sidebar-kit.py` — `kitten` overlay: sidebar with real hover/click
  + live pane preview (bound `ctrl+alt+b`)
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

A tab shows its panes rolled up (`kittymux_agents.tab_verdict`), not just the active pane. When the user is
elsewhere (agent not focused): tab glyph, header badges `! N  ✓ N` (all tabs), a desktop notification for needs-you
and for runs ≥ 15 s that finish, a WM urgency bell for needs-you only, `ctrl+alt+y` to jump. Off switches
(`notify-off`, `notify-done-off`, `bell-off` files / `KITTYMUX_NOTIFY`, `KITTYMUX_NOTIFY_DONE`, `KITTYMUX_BELL`) are in the README.
A window seen for the first time never notifies (a scanner restart must not replay old completions).
Markers are verified against live sessions per agent in `docs/compatibility.md` — check a real screen
(`kitty @ get-text --match id:N` → `kittymux_state.classify_screen`) before adding or changing one.

## Rules

- No hardcoded palettes (theme tokens come from kitty's live colours); no module-level timer state; never read silence as waiting.
- Never restart the user's live kitties. Work in the `feature/roadmap` worktree, test with the smoke rigs, apply to live by
  reload only (`kittymux upgrade`); record `kitty @ ls` window counts before/after. `main` is what live kitties load.
- Icons come from real brand marks: `assets/icons/*.svg` → `tools/build-icons.py` (append-only codepoints; fits non-square
  viewBoxes by their longest side). Devin's mark is Cognition's own; Antigravity's is the Google mark.
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
- Vertical-bar hit testing: kitty's tab extents skip the spacer line between tabs; `kittymux_barsize` wraps
  `TabBar.tab_id_at` (`kittymux_layout.snap_tab_id`) so drag-sorting and clicks on the gap resolve to the nearer tab.
- Python kittens are `exec`'d, not imported — no `__file__`, use
  `KITTY_CONFIG_DIRECTORY`; `styled()` wants `Color` objects, not ints/strings.

## Verify

- `python3 -m unittest discover -s tests` and `bash tests/test_mux_status.sh tests/test_socket_lib.sh`.
- Real-kitty smoke tests (Xvfb, private config/socket, SKIP if tools are missing): `bash tests/smoke_state.sh`
  (states from screens, spinner frame rate on an idle window, spacer-row click) and `bash tests/smoke_reload.sh`
  (a running kitty upgraded under itself must draw cleanly after two reloads; `SMOKE_KEEP_STALE=1` must FAIL).
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
