# Verification: every test and rig

What each check proves and when to run it. A failing rig is information about the rig AND the code: read the rule about rigs in AGENTS.md before trusting or changing one.

Part of the agent guide: start at [AGENTS.md](../../AGENTS.md) (the rules and the "read before you change" table); this page is the reference for one area.

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

## Also

- `bash tests/smoke_exit_save.sh` (a confirmed quit saves a layout changed less than the periodic settle time ago),
  `bash tests/smoke_pane_ux.sh` (native pane actions and the persistent Agents/Usage views, real keys in a private kitty) and
  `bash tests/smoke_workflow_argv.sh` (private native argv, scratch placement, stale-identity regressions).
- `bash tests/test_panel_focus.sh` (`mux-panel summon|dock|toggle` against a fake `kitten`, and the real kitten's option name). The layer-shell grab itself cannot run under Xvfb: it is checked by hand on Hyprland, for seconds, with an unconditional `mux-panel dock` in the same command.
- `bash tests/soak_kitty.sh [CYCLES]` (minutes; not in CI): windows come and go, the config reloads, and kitty's memory, fds, threads and zombies are measured. Run it after changing `kittymux_scan`, `kittymux_barsize` or `tab_bar`.
- Pictures (read the PNG, do not only run them): `tests/shot_bar.sh`, `shot_panel.sh`, `shot_usage.sh`, `shot_agents.sh`, `shot_panes.sh`, `shot_plain_tabs.sh` (the "before" for the docs site), `profile_bar.sh` (draw cost), `probe_*.sh` (one-off probes of kitty behaviour).
- The docs site (`site/`, with bun): `bun run check` (sync, unit tests, typecheck, build, crawl), `bun run axe` (accessibility in both themes, overflow at 320–1440, search, a click through the docs on a host with no server, no console errors under the CSP), `bun run budget` (first-visit JavaScript and requests that leave the site), `bun run cls` (layout shift on every page, theme and width, a slow first visit included; it must stay at 0).

## CI is a different machine

`.github/workflows/ci.yml` runs the Python tests, the shell tests, shellcheck and the smoke rigs on `ubuntu-24.04` against kitty 0.49.1 and 0.49.2; `site.yml` builds and checks the site. Differences that have bitten:

- The runner's **shellcheck is 0.9.0**, your machine's is newer: 0.9 reads `BG=#eff1f5;` as a comment. Quote hex colours (`BG='#eff1f5'`). To reproduce: `pip install shellcheck-py==0.9.0.6`.
- A rig must not assume **pid 1 is dead**, that `/tmp` is empty, or that a window manager exists: on a runner pid 1 is a live init.
- The `smoke` job is skipped when `unit` fails, so a red `unit` hides every rig behind it. Read the first failing step, fix, and expect the next one to surface.
- A new rig is added to `ci.yml` in the same commit; `tests/test_agents_doc.py` fails when a script in `tests/` is in neither this page nor an allowlist.
