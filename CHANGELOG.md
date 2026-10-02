# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Versions follow [SemVer](https://semver.org/) once tagged; until then everything below is *Unreleased*.

## [Unreleased]

### Added
- **Sessions that come back with their conversations.** `kittymux sessions save|restore|list|new|check|history|recover`: kitty's own `save_as_session` plus the resume command of each agent window
  (`claude --resume <id>`, `codex resume <id>`, `devin -r <name>`, `opencode -s <id>`, `agy --conversation <id>`, `cursor-agent --resume <id>`, grok, droid), autosave, templates (`plain`, `agent`, `duo`, `review`).
  Each CLI's resume flags are probed against its own `--help`; ambiguous cases are restored as saved rather than opening one conversation twice. [docs/sessions.md](docs/sessions.md)
- **Restored agents ask before resuming** (`kittymux resume-prompt`: Enter resume · n new · s shell · a all · i commands). `KITTYMUX_RESUME=auto` skips the question.
- **Agent journal** — every agent session recorded as it runs (agent, session id, directory, command, runs, work time) in a private bounded file; `sessions history` for insights, `sessions recover` after a crash.
- **One event model / inbox** — typed events (permission, question, limit, done) from the agent's own notifications, hooks and the screen; one popup per occurrence; `kittymux inbox`; a documented contract for widgets ([docs/inbox.md](docs/inbox.md), `addons/quickshell`).
- **`kittymux explain`** — why every agent pane is in its state and every notification decision, with its reason.
- **Native divider** (kitty ≥ 0.49.2): drawn and hit-tested by kitty itself — the real resize arrow and drag in tabs with split panes.
- `kittymux dim`, `kittymux screenshot`, clickable `path/file.py:42:7` (kitty ≥ 0.49.2), `kittymux demo` showcase tabs, `docs/try-it.md`.
- `SECURITY.md`, `CONTRIBUTING.md`, issue and PR templates; `tests/smoke_socket.sh`.

- **Spawn, pick, reopen, mute** ([docs/launcher.md](docs/launcher.md)): `kittymux spawn claude,codex [--vsplit]` (keys: `ctrl+alt+shift+o` then `c x d u o a g`), `kittymux pick` (one searchable list — needs-you longest-waiting first, running agents, closed conversations, new agent — in fzf, rofi or fuzzel; `⚠ no approvals` marks agents started with approvals off), `kittymux reopen` (`ctrl+alt+shift+u`), `kittymux notify mute|status|unmute`, `kittymux snooze` (muting quiets popups and bells, never the inbox).

- **Bar insights**: beside the state glyph, how long a tab has been waiting / working / done-unseen (`1m !`, `1h ◐`, refreshed every 20 s); a red `⚠` on agents started with their approvals off; the armed-mode badge shows
  the right keys for `leader` and `spawn` (width-aware). **Rofi look**: mascot header, per-agent icons, accent rail, colours read from your live kitty theme. `kittymux inbox --waybar` for a status-bar module.

- **Pin and settle** (`kittymux pin|unpin|settle|unsettle`, `alt+p` / `alt+s` in `pick`): pinned conversations lead the list and are never aged out; closed ones untouched for 3 days settle away behind one "show settled" row. Flags merge by their own timestamp so the scanner cannot undo them.

### Changed
- Recommended kitty setup is now `allow_remote_control socket-only` + `listen_on unix:${XDG_RUNTIME_DIR}/mykitty`; `kittymux doctor` warns about `yes` and a `/tmp` socket. Every smoke test runs under `socket-only`.
- A completion notifies only with a known duration ≥ 15 s after a 5 s settle; a hook-announced turn ends only with the agent's own `Stop`. Screen-only completions need ≥ 60 s of work to pop up.
- Bar redraw 6.0 → 2.1 ms with 23 tabs; the spinner ticks unfocused windows at half rate; resize touches only the visible tab per event.

### Fixed
- The mascot glyph vanished from every running kitty after `kittymux upgrade`: the installer re-copied the (identical) icon font, and the bar hides the glyph when the font file is "newer than the kitty". The installer now copies
  only a changed font and the bar judges the font by content fingerprint, not timestamp.
- Tab clicks that silently did nothing (the 5–14 px gap between kitty's click rule and `drag_threshold`); a stray middle-click no longer closes an agent tab.
- Notifications that forced focus to the agent's window (compositor `focus_on_activate` + a bell): no bell is sent where it would steal focus.
- `packaging/PKGBUILD` now ships `open-actions.conf.tpl`.

### Security
- `kittymux pick` rendered raw window titles: a title with a newline/NUL/ESC/bidi override (any program can set one) could forge rows or shift the indexes a menu answers with. All shown text is sanitised and a row with a control
  character is refused at the menu boundary; `mux-agents.sh` scrubs the same characters. Snooze moved from a window variable (settable by any program in the window) to a private file. `uninstall --purge` refuses to delete
  a `KITTYMUX_STATE` that is `/`, your home or above it, a symlink, or not recognisably ours. A command started inside a kitty acts on that kitty, never on "the focused one". See [docs/audit-2026-10-02.md](docs/audit-2026-10-02.md).
- Secret-looking flag values are redacted from printed `sessions list` / `sessions history --json`; see [SECURITY.md](SECURITY.md) for the threat model.
