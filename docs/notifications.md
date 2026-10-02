# Notifications: what happens, what we changed, what could go wrong

## Who sends what

| Source | Path | Shown by kittymux? |
|---|---|---|
| **kittymux** ("needs you", "hit a limit", "finished") | the scanner reads the agent's screen → `bin/mux-notify` → `notify-send` | yes — the one notification per event |
| **The agent itself** (Claude Code's "waiting for your input", Codex, Devin…) | the agent writes an OSC 9 / 99 / 777 escape → kitty turns it into a desktop notification | **dropped** by `filter_notification` in `kittymux.conf` |
| **kitty's own** (`notify_on_cmd_finish`, config reload) | kitty itself | untouched (kitty's logo, kitty's click-to-focus) |
| **Any other program** in a terminal (a build tool, a script) | OSC escapes | untouched unless its *title* starts with an agent name |

## What changed, and what we broke

Before kittymux filtered anything, each event could notify **twice**: once from the agent (via kitty, source
`kitty`, title "Claude Code") and once from kittymux. Two fixes, and one regression we then fixed:

1. **Duplicates.** kittymux owns notifications now. The rule drops notifications whose title (or app name) starts
   with a known agent name. kitty re-reads `filter_notification` on config reload, so no restart is needed.
2. **Regression: the logo.** kittymux's first notifications used a generic terminal icon, so they no longer looked
   like "from Claude" / "from Codex", and the kitty logo was gone too. Now every notification wears **its agent's
   mark** (`assets/notify/<agent>.png`, built by `tools/build-notify-icons.py`; with a mascot present a small
   mascot badge sits in the corner). Unknown agents get kittymux's mascot, else the `kitty` icon from your theme.
3. **Click behaviour.** kitty's native notifications focus the window when clicked. Ours carry a "Jump to it"
   action (`bin/mux-notify` → `kitty @ focus-window` → `hyprctl`), which lands on the pane that is asking.
   With dunst the action is middle-click (or `dunstctl action`); other daemons differ.

## When is something "finished"? (false completions)

A notification that says "finished" while the agent is still working is worse than none. The rules (all unit-tested in
`tests/test_state.py`, resolver in `python/kittymux_state.py`):

1. **The agent's own word wins.** When a hook announced the turn (Claude's `UserPromptSubmit`), only its `Stop` hook ends it.
   A quiet screen between tool calls, a repaint, a status line that reworded itself, or an Esc interrupt is not a completion.
   (`PostToolUse` tells us a tool call ended and work continues; `SessionEnd` clears leftovers.) Agents without hooks
   (Devin, Gemini, …) are judged by the screen alone: busy marker gone for 5 s after ≥ 15 s of work.
2. **A permission request you answered is not "done".** It is why the agent paused. Claude's idle notice ("waiting for your input")
   counts as a completion only if none was reported yet this turn, so it can never produce a second one.
3. **Prose is not a prompt.** `(y/n)` or "usage limit reached" inside the agent's own reply, above a live spinner, is ignored; a real
   dialog (it has `esc to cancel` / `(esc)` chrome) still wins even with a spinner drawn nearby.
4. **Unknown duration, no notification.** A completion is announced only when we saw it work ≥ 15 s.

`kittymux explain` shows, per pane, the reason for its current state and the recent decisions — including every notification that was held back and why. Run `kittymux hooks --install` once (it backs up `~/.claude/settings.json`) and `kittymux doctor` tells you if an event is missing.
What this cannot know: whether an agent's *own* terminal notification (OSC 9/99) slips past the title/app filter — those are dropped by
`filter_notification` only when they name a known agent.

## A notification must never move your focus

A bell in an unfocused window makes kitty ask the window manager for attention (`window_alert_on_bell`; on Wayland an xdg-activation request). Some compositors answer that by **focusing the window and
switching workspace** — Hyprland with `misc:focus_on_activate = true`. Then every bell becomes a forced focus change: kittymux's own "needs you" hint, but also an agent's terminal bell or a failed tab-complete.
That was the "it suddenly jumps to that window" bug. Now:

- when the compositor would do that (kittymux reads Hyprland's option when kitty loads its config), kittymux emits `window_alert_on_bell no` and does not ring its own bell;
- `kittymux doctor` says so; `kittymux explain` records each skipped bell and why;
- the only things that move focus are things you do: a click, `kittymux inbox jump`, `ctrl+alt+y`, or invoking a notification's "Jump to it" action.

Override: `touch ~/.local/state/kittymux/attention-on` (or `KITTYMUX_ATTENTION=1`) to keep attention requests on anyway; `bell-off` / `KITTYMUX_BELL=0` switches kittymux's own bell off everywhere.
Other compositors (sway's `focus_on_window_activation`, KDE/GNOME focus-stealing prevention) are not inspected: if a bell steals focus there, set `window_alert_on_bell no` in your kitty.conf.

## The inbox (everything, typed, de-duplicated)

Popups are one delivery channel of a larger system: every important event is recorded as a typed event in the inbox (`kittymux inbox`, [inbox.md](inbox.md)) from the most authoritative source
available — the agent's own notification first. The rules above (who may pop up, when a "finished" counts) are applied by `kittymux_scan._announce`; `kittymux explain` shows the outcome of each.

## Security and privacy measures

- **Untrusted text.** The notification body can come from the agent's screen (a permission prompt, a command).
  It is stripped of control characters, length-bounded (title 60, body 120), and markup-escaped (`& < >`), since
  many daemons render Pango markup. `notify-send` is called with `--` so text starting with `-` is never an option.
- **No shell.** Every subprocess is an argv list; nothing is interpolated into a shell command.
- **The helper validates its own argv** (it will take arguments from anyone who can run it): window id and pid must
  be digits, urgency one of low/normal/critical, category `[A-Za-z0-9._-]`, socket `unix:…` only.
- **Icons are never taken from agent output.** The scanner picks the icon from *our* agent table; the helper accepts
  only a `.png` that resolves (symlinks and `..` resolved) inside this checkout's `assets/`, or a bare icon-theme
  name. Anything else becomes the `kitty` icon. Tests cover traversal, symlink escapes and injection strings.
- **"Finished" must settle.** A completion notifies only after the pane has stayed finished for 5 s (a blink of the status line, a repaint
  or a popup is not a completion), after ≥ 15 s of work, once. A hook `done`/idle-`waiting` counts only while it is < 30 s old: window
  user variables outlive the agent that set them, and a leftover one used to make a busy Codex look finished the moment its
  status line blinked.
- **Rate limits.** One notification per window per 10 s, and a global cap of 5 per 10 s, so output that flips many
  windows in one kitty instance cannot flood the desktop. The burst budget is shared across that instance's panes,
  not across independent kitty processes. A first-seen window never notifies or rings the bell (startup cannot replay history).
- **Bounded processes.** Each notification helper lives at most 30 s, in its own session; at most ~15 per kitty instance can exist.
- **Private mode.** The body can contain what is on your screen (a command, a path), and some daemons keep a
  history or show notifications on the lock screen. `touch ~/.local/state/kittymux/notify-private` (or
  `KITTYMUX_NOTIFY_PRIVATE=1`) reduces every notification to "<agent> needs you" with a generic line.
- **Files.** `scan-<pid>.json` (which holds the same short reason text) is mode 0600 in a 0700 directory.
- **Off switches:** `notify-off` / `KITTYMUX_NOTIFY=0` (all), `notify-done-off` (finished only), `bell-off` (urgency).

## Known limits (honest list)

- **The filter is by title, not by window.** kitty's `filter_notification` cannot see which window sent a
  notification, so a non-agent program that titles its notification "Claude …" or "Codex …" is dropped too.
  (A `notifications.py` could scope it, but kitty loads that file only at start, so it needs a restart.)
- **Events we do not detect are lost.** If an agent notifies about something the screen scanner cannot see, nobody
  shows it. Delete the `filter_notification` line to get the agents' own notifications back (you will see doubles).
- **Notification text is screen text.** Private mode is opt-in; the default shows the question ("Approve: rm -rf x?").
- **Daemon differences.** Tested with dunst on Hyprland. The "Jump to it" action needs a daemon with action support;
  without it you get the text and icon only. Icons need PNG support (all common daemons have it).
- **The control socket.** The jump action talks to kitty's own socket (`listen_on`). If it lives in world-writable
  `/tmp`, other local users could squat the name; `kittymux doctor` warns about this.
- **The budget drops silently.** The 6th notification inside 10 s is not shown (the bar still shows the state).
- **Not tested:** macOS, GNOME's notification daemon, KDE, mako, swaync.
