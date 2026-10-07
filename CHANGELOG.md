# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Versions follow [SemVer](https://semver.org/) once tagged; until then everything below is *Unreleased*.

## [Unreleased]

### Changed
- **`ctrl+alt+1..9` now focuses pane N** of the tab (the digit `ctrl+alt+e` draws on each pane). Tabs are on `alt+1..9`, which was already an alias for them. `ctrl+alt+shift+1..9` still works and does the same as `ctrl+alt+1..9`. The keymap overlay lists them under PANES as "focus pane".

### Added
- **Agents view redesign.** One bright thing per row (the title), a state mark at the right edge, a stripe and a faint warm tint on rows that need you, and detail (PR, ports) only on the picked or hovered row. Rows are drawn by a pure module, `kittymux_agentsview`, tested at every width in both themes.
- **Clickable buttons in every panel view.** A row of keycaps under the list (`⏎ jump`, `/ find`, `a join`, `t detach`; `r`/`d` in Usage; `⏎`/`x`/`tab` in Inbox) does what its key does when clicked, and lights up under the pointer. Narrow panels drop buttons from the right, so the most useful stay.
- **Usage numbers you can trust.** The Codex collector picks the newest limit *event* by its own timestamp (not the newest file name), reads only the tail of each rollout, uses the window length the event reports, and shows a window that has already ended as `window reset · no newer sample` instead of its old percentage. A provider's report older than ten minutes is dated on its card, and trend history is recorded at the time a snapshot describes and keyed by quota label (`5h`, `wk`), not by row position.
- **Usage trend and live age on the card** (ported from the first text dashboard): a 48-hour sparkline, the age and any failure of a live fetch, and `d` for source notes. The render is bounded however many rows a cache claims.
- **Dismiss can be undone.** In the panel's Inbox, `z` brings back what the last `x` or `X` hid; the footer offers it for 8 seconds and then drops the offer on its own. New inbox op `restore` (older readers ignore it).
- **`motion` switch** (`kittymux features off motion`, `KITTYMUX_MOTION=off`): the working spinner holds one still frame in the bar and the panel, and the 10 fps redraw timers stop. On by default.
- **Open the panel from anywhere**: a documented Hyprland bind and an optional `layerrule` for a slide-in from the screen edge (the panel's layer name is `kittymux-panel`).
- **Wait ledger**: how long agents waited on you, from when a permission or question event first appeared to when you first looked at it. A card in the panel's Inbox view (today, median, a week of bars, who is waiting now) and `kittymux inbox ledger [--json]`. The inbox fold keeps two new optional fields, `t0` and `ack_t` (schema version unchanged).
- **Command palette** (`ctrl+alt+shift+space`, `kittymux palette`): one searchable list, inside the kitty you are in, of what needs you, every tab, conversations to reopen, a new agent (with its provider's quota headroom; the first four CLIs show, type to find the rest) and a few fixed actions. Type to filter, `⏎` or a click does it. It only chooses: `kittymux act` re-validates the choice (a tab id, an installed agent, one of a fixed list) and acts after the overlay has closed.
- **Pick the agent that still has room.** The new-agent rows of `kittymux pick` show their provider's headroom (`◔ 5h 99% used`, `◔ limit hit, resets 3h 50m`) from the usage numbers the panel already keeps; nothing is fetched.
- **A new look for the panel: Usage and Inbox views.** A strip of pills switches Agents / Usage / Inbox (`a` `u` `i`, or click). Usage is a row of provider tiles (logo, worst share, a thin gauge) and one card for the pick: gauges that go green → amber → red with a tick for where an even spend would be and the time to reset, a big token number with a week of bars, state chips, and a seven-day heat strip. Inbox is every typed event as a card with Jump and Dismiss and four filters. One pure component kit (`kittymux_ui`) draws both from your live theme colours, and one meter model (`kittymux_meters`: quota, counter, state, spend) draws every provider, so a new provider needs no UI code. Collectors keep their text rows and gain numeric sidecars (`rem_s`, `window_s`, `tok`, `sess`, …). The usage overlay now also shows the elapsed-window line for Codex. [docs](docs/users/peek-deck-and-panel.mdx)
- **Every tab says where it is.** `project[:worktree]/inner  branch` under each vertical tab, the project name highlighted; a stable per-project hue from your theme's accent; tabs that look alike get their project emphasised. Each piece is its own switch — `kittymux features [on|off NAME | preset minimal|default|full]`.
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

- **What did the agent change?** (`kittymux changes`): `7 files +142 −30` since the run started, on a finished tab, on that agent's row in `pick`, and as a command. Snapshots use a temporary index and a private object store — your repository is never written to.

- **Fan-out** (`kittymux fanout "PROMPT" claude,codex,devin`): the same task to several agents at once, each in its own git worktree + branch + tab, with the prompt given in each CLI's own (verified) form; `fanout compare` shows what each did relative to the base, `fanout clean` tidies up.

- **Join a tab into another** (`ctrl+alt+shift+j`, `kittymux join`): all panes of a tab (or one pane) become splits of a tab you pick, keeping their shape. A list takes the keyboard and the mouse (type to filter, hover or arrows to choose, `⏎` or a click to join, `Tab` for the side, `ctrl+t` for tab or pane). The deck's `a` (pull a tab in) uses the same mover, which fixes panes arriving as 7-column slivers. [docs](docs/users/tabs-and-panes.mdx)
- **Quick look** (`ctrl+alt+shift+q`, `kittymux peek [TAB_ID | --waiting]`): the peek card of the agent that has waited on you longest, from the keyboard — read its question, `⏎` goes there, `esc` stays. [docs](docs/users/peek-deck-and-panel.mdx)
- **Your own shortcuts are left alone.** `ctrl+alt+shift+h k v z f x` stay unbound; the keymap overlay (`ctrl+alt+/`) lists your own kitty maps (**YOURS · KITTY**) and Hyprland's terminal and scratchpad binds (**YOURS · HYPRLAND**); `kittymux keys` and `kittymux doctor` report any chord both your config and kittymux define. Pane title bars are on `ctrl+alt+shift+c` and pane swap on `ctrl+alt+shift+y`. [docs](docs/users/your-own-shortcuts.mdx)
- **Docs tree for a docs site** (`docs/index.mdx`, `docs/users/`, `docs/developer/`, `meta.json`, `feature-status.yaml`, `promotion-manifest.yaml`, `troubleshooting-symptoms.yaml`) with drift tests (`tests/test_docs.py`) and a generated status table (`tools/docs_status.py`).

### Changed
- `ctrl+alt+enter` splits below and `ctrl+shift+enter` to the right; the README says so (it used to say "+shift").
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
