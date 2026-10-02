# Spawn, pick, reopen, mute — getting to any agent, and starting one, fast

Four small commands on one idea: **a tab is a thread of work**, so starting one, finding the one that needs you, bringing back one you closed and quieting the noise should each be one keystroke.
(The thread model is borrowed from [T3 Code](https://github.com/pingdotgg/t3code): an attention-ordered list, a way back for everything you close, and snooze.)

## Start an agent: `kittymux spawn`

```sh
kittymux spawn claude                    # a new tab, in the current directory
kittymux spawn codex --vsplit            # a split next to this pane (--hsplit: below)
kittymux spawn claude,codex,devin        # several at once, one tab each
kittymux spawn c x d u o a g             # one-letter names: claude codex devin cursor opencode agy grok
```

The agent starts in the focused window's directory, a new tab goes **before** the `!scratch` tab (so scratch stays last), and the window carries `kittymux_agent` so a later save restores it with its conversation.
Only known agents that are installed are started (the name is never a path or an option); anything else is refused with the reason.

Keys (`kittymux-keys.conf.tpl`): `ctrl+alt+shift+o`, then **`c`** claude · **`x`** codex · **`d`** devin · **`u`** cursor · **`o`** opencode · **`a`** agy · **`g`** grok → a new tab; with `shift` → a split on the right.
Any other key cancels (so does 3 s of silence). For an agent in its **own git worktree**, use `ctrl+alt+shift+g` (`mux-agent-new`).
Not here yet: sending the same prompt to several agents at once — an agent's prompt argument differs per CLI, and typing into a TUI that may not be ready is fragile; it needs per-agent definitions the way resume has them.

## Get anywhere: `kittymux pick`

One searchable list. Most pressing first:

| Row | Meaning | Enter |
|---|---|---|
| `◆ claude  api — Approve: run the tests?   12m` | something needs you, **longest-waiting first** | jump to that window, mark it read |
| `✓ …` | finished, unseen | jump |
| `◐ devin  …   working` / `· codex …` | every running agent in every kitty, needs-you states first | jump |
| `↺ claude  api   ~/code/api   closed 3h ago · 7 runs` | a conversation that was running and is not (from the [journal](sessions.md)) | reopen it in a new tab — it asks before resuming |
| `+ new claude   tab · ~/code/api` / `split right` | start an agent | spawn |

A row of an agent started **without approvals** (`--dangerously-skip-permissions`, `--yolo`, `--auto`, `--permission-mode dangerous`, … — only flags each CLI documents, see `assets/agent-risk.json`) carries `⚠ no approvals`.

```sh
kittymux pick                      # inside kitty: fzf in an overlay (ctrl+alt+v, leader v) — rofi/fuzzel when fzf is missing
kittymux pick --menu rofi          # from anywhere: a rofi window; alt+a marks the selected event read without jumping
kittymux pick --menu fuzzel
kittymux pick --list | --json      # the rows as text / as data (every row has its action) — a Quickshell or waybar widget can use this
```

**Reach any agent from anywhere**: bind it in your window manager. Hyprland (check the chord is free first: `hyprctl binds -j`):

```
bind = SUPER, A, exec, kittymux pick --menu rofi
```

The focused kitty is decided *before* the menu opens (a menu takes the keyboard focus), so "new claude" starts in the directory you were just in. Runs in ~0.1 s; the menu itself is rofi's.

### The rofi look

`kittymux pick --menu rofi` wears kittymux: a header with the mascot, a search bar, one row per item with **its agent's icon** (the notification marks, which carry the mascot badge), an accent rail on the selected row
(the same `▎` as the tab bar), needs-you rows in the *waiting* colour and working rows in the *working* colour. **Every colour is read from your live kitty theme** when the menu opens (nothing is hardcoded), so it
follows theme switches; the theme is written 0600 to `~/.local/state/kittymux/rofi-kittymux.rasi`. `--no-theme` (or `KITTYMUX_ROFI_THEME=user`) leaves your own rofi theme in charge. Needs rofi 2.x (Wayland-native).

## Pin and settle: keep the list about *now*

Borrowed from T3 Code's thread lifecycle. Two flags on a conversation's journal record, so they outlive the tab:

- **Pin** (`alt+p` in the picker, `kittymux pin [KEY | --window ID]`): the conversation stays at the **top** of `pick` with a `★`, whether it is running or closed, and is **never aged out** of the journal (the 90-day and 300-record limits skip it). Toggle with `alt+p` again or `kittymux unpin`.
- **Settle** (`alt+s`, `kittymux settle KEY`): fold a closed conversation away. A closed conversation also **settles itself** after 3 days untouched (`KITTYMUX_SETTLE_DAYS`, 1–365). Settled ones leave the default list and sit behind one row — `⋯ 4 settled conversations — show` (or `kittymux pick --all`);
  nothing is deleted. `alt+s` on a settled row brings it back; pinning one does too.

`ack` / `pin` / `settle` refresh the list and ask again, so you can tidy several in a row. Pinning does not reorder the *tab bar* (kitty has no pinned tabs) — it is about what `pick` offers you.

## What did the agent change? `kittymux changes`

When an agent's run starts (idle → working) kittymux remembers the state of the repository around that window; when it ends (or needs you) it diffs again. You get **`7 files +142 −30`** and the biggest files:

```sh
kittymux changes                 # this window: 7 files +142 −30   since its run started 12m ago, then the files
kittymux changes --files --json  # every file / machine-readable
kittymux changes --all           # the cached summary of every window in this kitty (no git, instant)
```

It also shows on a **finished tab** in the bar (`✓` state, the summary leads the second row) and as `Δ 7 files +142 −30` on that agent's row in `pick` — so you see what a long run did *before* you jump to it.

- **Only the agent's work.** The baseline is taken when the run starts, so a file that was already dirty is not counted; ignored files (`.gitignore`) are not counted; untracked new files are.
- **Your repository is never written to.** The snapshot uses a temporary index and a private object directory under `~/.local/state/kittymux/changes-objects/` (your repo's objects are read-only alternates): no new objects in `.git`, no index change, no refs, no locks.
  Git runs with no terminal, the file-system monitor and external diff/textconv programs off, a 25 s timeout and low priority, in a detached helper — never on kitty's main thread; a repository git itself distrusts (`safe.directory`) is skipped.
  Stores are bounded (a week, 512 MB). Off: `KITTYMUX_CHANGES=0` or `touch ~/.local/state/kittymux/changes-off`.
- **Limits.** The baseline is taken on the scanner's next tick (≤ 2 s after the run starts): edits in that first moment count as before. If kittymux was not watching when the run started (a kitty restart mid-run) the summary compares with `HEAD` and says so. Not a git repository → nothing is shown. Cost on a huge monorepo is one `git add -A` per run start/end.

## Fan-out: one task, several agents

```sh
cd ~/code/api
kittymux fanout "fix the login redirect bug; keep the tests green" claude,codex,devin --name login
kittymux fanout compare login     # what each did, relative to the same base commit
kittymux fanout clean login --yes # tidy up (keeps a worktree with uncommitted work unless --force)
```

Each agent gets its **own git worktree and branch** (`<repo>/.worktrees/login-claude`, branch `login-claude`, all from one base commit — `--base REF`, default `HEAD`) and its own tab titled `claude · login`, with the prompt already
given, so they cannot overwrite each other and you can compare real results. `compare` diffs each worktree against the base **whether the agent committed or not** (untracked new files included) — `claude 7 files +142 −30 · codex 3 files +40 −2 · devin no changes` —
and reads only: your main checkout is never touched. `fanout list` shows past fan-outs.

How the prompt is given is **per CLI and read from each one's own `--help`** (`assets/agent-prompt.json`): claude / codex / cursor-agent / grok / droid take it as the last argument, devin after `--`, opencode as `--prompt`, agy as `--prompt-interactive`.
An agent with no verified form is refused, never guessed; add yours in `~/.config/kittymux/prompt.json`. The prompt is one argument (no shell ever sees it, so quotes and `$()` are just text), at most 8000 characters, and cannot start with `-`.
Note that a prompt on a command line is visible to other local users in `ps` for as long as the agent runs — don't put secrets in it.

It refuses to run outside a git repository, with an existing name/branch/path (it never reuses someone's work), or without a kitty to open the tabs in; it creates all the worktrees or none (a failure part-way removes what it made).

## Bring back what you closed: `kittymux reopen`

`ctrl+alt+shift+u` (leader `y`) or `kittymux reopen` reopens the agent conversation closed last, in a new tab in its directory, through the same prompt as any restore. It reads the [journal](sessions.md), so it also works for
a crash or a closed kitty. `kittymux pick` lists the last eight (↺ rows).

## Quiet things down: `kittymux notify`, `kittymux snooze`

```sh
kittymux notify mute 1h        # no popups, no bells for an hour (up to 30 days)
kittymux notify status         # on / muted for another 42m / off, bells, unread in the inbox
kittymux notify unmute
kittymux notify off | on       # the existing switches (notify-off file)
kittymux notify done off|on    # only "finished" popups
kittymux snooze 2h             # THIS agent window only (run inside it; or --window ID); --clear ends it
```

Muting quiets the **interruption**, never the news: every event still goes to the [inbox](inbox.md), shows in the bar and in `pick`, and `kittymux explain` says "muted"/"snoozed" for the ones that did not pop up.
A snooze is stored in the private state dir (`snoozes-<kitty pid>.json`, 0600, capped at 30 days) — deliberately **not** a window variable: any program in a window can set its own variables with an escape
sequence, so an agent could otherwise silence the very popup that says it wants something. The mute file is `notify-mute-until` (0600). A corrupt or absurd value never silences anything for good.

## A status-bar badge: waybar (no Quickshell needed)

```
kittymux inbox --waybar        →  {"text": "◆ 2", "tooltip": "◆ claude api — Approve: run the tests? (12m)\n…", "class": "needs-you"}
```

```jsonc
// ~/.config/waybar/config.jsonc — a custom module; add "custom/kittymux" to a modules list
"custom/kittymux": { "exec": "kittymux inbox --waybar", "return-type": "json", "interval": 5, "on-click": "kittymux pick --menu rofi", "hide-empty-text": true }
```

Empty when nothing is unread (the module hides); `◆ N` when N agents need you (class `needs-you`, style it in waybar's CSS); `✓ N` for finished-unseen. Click opens the picker.

## When would you want Quickshell?

| You want… | Use |
|---|---|
| find / jump to / start / reopen an agent, instantly | **rofi** (`pick`) — already done; a transient menu is the right shape |
| a glanceable count of what needs you, always visible | **waybar** module above (you already run waybar) |
| a persistent panel or notification centre with live updates, inline actions (jump, mark read, mute 1h), animated popups that replace dunst, a dashboard of every agent on a second monitor | **Quickshell** — the only one of these that is a real UI toolkit |

Start with rofi + waybar; add Quickshell when you catch yourself wanting a *panel that stays open* or *notifications that belong to kittymux*. On Arch it is in `extra`: `sudo pacman -S quickshell` (0.3.x; no AUR needed).
`addons/quickshell` has a starting point that reads `inbox-snapshot.json` (untested until Quickshell is installed — the data contract is `kittymux pick --json` / `kittymux inbox --json`).

## What this is not (yet)

- A persistent GUI: Quickshell is not installed on the author's machine, so the sample in `addons/quickshell` stays untested; `kittymux pick --json` is the contract a widget would use.
- Pin / settle (auto-fold finished threads after N days) and per-turn diffs — see the roadmap notes in the changelog.
