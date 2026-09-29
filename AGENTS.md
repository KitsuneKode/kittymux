# kittymux

Kitty-as-multiplexer config pack: tabs, panes, session restore, agent-aware
tab bar, sidebar overlay, and overlays for keys/usage/cwd. tmux stays for
remote work.

## Layout

- `kittymux.conf` — main config (included from the user's kitty.conf)
- `kittymux-keys.conf.tpl` — keybind template; `install.sh` renders
  `@KITTYMUX_HOME@` into a generated conf. **Edit the .tpl, never the output.**
- `bin/` — shell scripts (mux-*); shared helpers in `lib/mux.sh`
- `python/tab_bar.py` — custom tab bar (two-line vertical rows, brand icons)
- `python/pane-state.py` — kitty `watcher`: per-window activity →
  `$KITTYMUX_STATE/panes-<kittypid>.json` (drives waiting/busy marks)
- `python/kittymux_theme.py` / `kittymux_agents.py` / `kittymux_deck.py` — pure helper modules
  (no kitty imports; unit-tested in `tests/`). Theme tokens derive from live kitty colours; symlinked
  into the config dir by `install.sh`. Never hardcode a palette in `tab_bar.py`/`sidebar-kit.py`.
- `bin/mux-status` — agent hooks → `kittymux_status` window user var → recorded by `pane-state.py`
- `python/sidebar-kit.py` — `kitten` overlay: sidebar with real hover/click
  + live pane preview (bound `ctrl+alt+b`)
- `python/collectors/` — per-provider usage collectors (claude/codex/cursor/devin)
- `tools/build-icons.py` — builds the PUA icon font the glyphs live in
- `install.sh` — symlinks/copies into `~/.config/kitty`, renders the tpl

## Conventions

- Runtime state under `$KITTYMUX_STATE` else `$XDG_STATE_HOME/kittymux`;
  panes/usage caches are per-kitty-PID (`panes-<pid>.json`).
- Python files run under kitty's bundled interpreter — `kitty.*` and
  `kittens.*` are importable there, not under system python.
- `# key — description` comments in the conf feed `bin/mux-keys.py` (the
  `ctrl+alt+/` overlay). Keep the comment format so docs never drift.
- Ownership: kitty owns tabs/panes/sessions; the WM owns OS-window borders
  and global chords — check `hyprctl binds` before taking a `ctrl+alt+` key.
- Python kittens are `exec`'d, not imported — no `__file__`, use
  `KITTY_CONFIG_DIRECTORY`; `styled()` wants `Color` objects, not ints/strings.

## Verify

- `python3 -m unittest discover -s tests` and `bash tests/test_mux_status.sh`.
- Kitten UI can be screenshotted offscreen: Xvfb + `env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa
  LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=:99 kitty -o linux_display_server=x11 …`, then `xdotool windowsize` (forces a
  first redraw) and `import -window root out.png`. Config reload does NOT re-import `tab_bar.py` — restart the scratch kitty.

- `python3 -m py_compile` on touched python; `bash -n` on shell.
- Reload a live kitty: `kitty @ --to unix:/tmp/mykitty-* action load_config_file`.
- Scratch instance for UI tests:
  `kitty --class X --listen-on unix:/tmp/X --session file` then
  `kitty @ --to unix:/tmp/X ls` / `get-text` to inspect without screenshots.
- README's key table must stay in sync with the .tpl.
