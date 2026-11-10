# The inbox — one place for everything that wants your attention

kittymux turns every important thing an agent does into a **typed event** in one shared, private store, decides separately whether it also
pops up, and exposes the result as a stable file + CLI so other tools (a Quickshell panel, waybar, a script) can build on it.

## Where events come from, most authoritative first

| Source | What it is | Confidence |
|---|---|---|
| `agent` | what the agent announced **itself**: its own OSC 9/99/777 desktop notification, captured natively from kitty's notification pipeline (`NotificationManager.is_notification_filtered` receives it with the window it came from, before our `filter_notification` rule drops the agent's own popup), or its Stop/Notification hook | high |
| `hook` | the agent's hooks (`mux-status`: UserPromptSubmit/PostToolUse/Notification/Stop/SessionEnd) | high |
| `screen` | positive evidence read off the pane's screen (a permission prompt, usage-limit text, a busy marker that went quiet) | `low` for a completion (an inference), `high` otherwise |

An agent notification is classified from **what it said** (`kittymux_inbox.classify_text`); anything it does not recognise is `info`, never guessed into a
completion. Claude's "waiting for your input" is its idle notice (it finished a minute ago), kept as `info` with `tag: idle-notice`, not a new completion.

## Event kinds

| kind | severity | meaning | popup |
|---|---|---|---|
| `permission` | needs-you | an approval prompt (Allow this command? Do you want to proceed?) | yes |
| `question` | needs-you | the agent asks you something | yes |
| `limit` | warn | usage/rate limit reached; `reset_at` is parsed from "resets in 2h 30m" / "resets at 5pm" when present | yes, once per agent per reset |
| `done` | info | a run finished | **only if the agent said so itself** (hook / its own notification) after ≥ 15 s of work, or if inferred from the screen alone after ≥ 60 s; shorter screen-only finishes are inbox + bar only |
| `error` | warn | the agent reported a failure | yes when it is an OSC 7501 status report (the message is the body); a failure only mentioned in other text stays inbox only |
| `info` | info | anything else the agent said | inbox only |

The same occurrence reported by several sources inside 45 s is **one** event (`sources: ["agent","screen"]`, `count` > 1) and **one** popup. Focusing a window
acknowledges everything it reported (`status: read`). `kittymux explain` shows, per decision, why a popup was or was not shown.

`sources` (plural) is who reported the event: `agent`, `hook` or `screen`. `source` (singular) is what the event is about: `agent` for an agent, `tool` for a
password or yes/no prompt (`sudo`, `ssh`, `git`, `pacman`, `paru`, a login). A sudo prompt is therefore `sources: ["screen"]` and `source: "tool"`, with `agent`
set to the program name. An event written before this field has no `source`; treat that as an agent. Adding the field did not change `version`.

## Files (state dir: `$KITTYMUX_STATE` or `~/.local/state/kittymux`, all mode 0600)

- `inbox.jsonl` — append-only operations, safe for several kitty processes to write at once (`O_APPEND`, plus a lock for compaction): `{"op":"add",…}`, `{"op":"ack",…}`, `{"op":"clear"}`, `{"op":"restore","ids":[…]}` (undoes a dismissal: the event is unread again and forgets its `ack_t`; events that are not dismissed are left alone; an older reader ignores the op). Compacted past 256 KB.
- **`inbox-snapshot.json`** — the folded view, rewritten atomically after every change. **This is what a widget watches.** Schema version 1:

```json
{"version": 1, "updated": 1790000000.0, "unread": 2, "needs_you": 1,
 "events": [ {"id": "18f3a…-4321-7", "t": 1790000000.0, "pid": 4321, "w": "77", "kind": "permission", "severity": "needs-you",
              "agent": "claude", "tab": "Kitty lightweight tm", "title": "claude needs permission", "body": "Claude needs your permission to use Bash",
              "sources": ["agent", "screen"], "source": "agent", "confidence": "high", "status": "unread", "count": 2},
             {"kind": "limit", "reset_at": 1790009000, "…": "…"} ] }
```

`events` is newest first (at most 60). `pid` + `w` identify the kitty process and window. In **private mode** (`notify-private`) `body` is empty.
`id` is stable. New fields may be added; consumers must ignore unknown ones (bumping `version` only for breaking changes). Two optional fields come from folding the log: `t0`, when the
event first appeared (`t` moves to the newest report of a merged event), and `ack_t`, when it first stopped being unread (you focused its window, read or dismissed it). `kittymux inbox ledger`
turns them into how long agents waited on you.

## agents.json — who is working, without parsing a menu

`$KITTYMUX_STATE/agents.json` (or `~/.local/state/kittymux/agents.json`) is the live list a shell panel watches when it wants every agent in every running kitty.
The scanner writes it: each kitty replaces only its own rows and keeps rows whose process is still alive. Mode `0600`. Rewritten atomically (a temporary file, then
rename) and only when the document apart from `t` changed, so a poll does not rewrite the file every tick. Schema version **1**.

```json
{"version": 1, "t": 1793780793.0, "agents": [
  {"key": "w4035.20", "kitty_pid": 4035, "window_id": 20, "agent": "codex", "brand": "openai", "source": "agent",
   "state": "limited", "since": 1793780600.0, "title": "Review the parser", "tab_title": "parser",
   "cwd": "~/work/calm-otter", "project": "calm-otter", "session": "calm-otter", "question": null,
   "progress": null, "limit_reset": 1793784393, "error": null, "action": {"op": "jump", "pid": 4035, "w": "20"}, "muted": false},
  {"key": "w4035.19", "kitty_pid": 4035, "window_id": 19, "agent": "claude", "brand": "claude", "source": "agent",
   "state": "working", "since": 1793780700.0, "title": "Port the configs", "tab_title": "calm-otter",
   "cwd": "~/work/calm-otter", "project": "calm-otter", "session": "calm-otter", "question": null,
   "progress": 0.42, "limit_reset": null, "error": null, "action": {"op": "jump", "pid": 4035, "w": "19"}, "muted": false}
], "counts": {"working": 1, "waiting": 0, "done": 0, "idle": 0, "limited": 1, "error": 0}, "needs_you": 1}
```

| Field | Meaning |
|---|---|
| `version` | `1`. A new field keeps this number. A rename, a removal, or a change of meaning bumps it. |
| `t` | When this document was built, epoch seconds. Not a reason to reread the rows. |
| `key` | `w<kitty_pid>.<window_id>`. Stable for the life of that window. |
| `kitty_pid`, `window_id` | The kitty process and the window. `window_id` is an integer. |
| `agent` | The CLI name (`claude`, `codex`, …). |
| `brand` | Basename of the SVG in `assets/icons`, from `kittymux_agents.brand_of` (one table). `codex` is `openai`, `gemini` is `googlegemini`, `droid` is `factorydroid`, `vibe` is `mistralvibe`, `agy` is `antigravity`, `cursor-agent` is `cursor`. Empty when we have no mark (`aider`, `crush`). Notify PNGs stay named by the agent. |
| `source` | `agent` on every row. Tool prompts are not rows; they are inbox events with `source: tool`. |
| `state` | A status-contract name: `limited`, `waiting`, `error`, `working`, `done`, `idle`. The usage-limit state is `limited`. An older note called it `limit`; that string is not used here. |
| `since` | Epoch seconds when the row entered this `state`. A title or progress change does not move it. |
| `title`, `tab_title` | The window title, cleaned the way the bar cleans it, and the tab's own title. |
| `cwd` | The window's directory, with the home directory written as `~`. |
| `project` | The git project, or the folder name when the directory is not a repository. Empty when the directory is unknown. |
| `session` | The kitty session name, or `""`. |
| `question` | The prompt, when `state` is `waiting`. Otherwise `null`. |
| `progress` | OSC 9;4 as a fraction from 0 to 1 when the program reported an amount. `null` when it did not, including an indeterminate report. |
| `limit_reset` | Epoch seconds when a `limited` row lifts, when that time is known. Otherwise `null`. |
| `error` | The message when `state` is `error`. Otherwise `null`. |
| `action` | The object `kittymux act` accepts: `{"op":"jump","pid":<int>,"w":"<digits>"}`. |
| `muted` | `true` when you muted this agent (`kittymux mute`, `m` or a right-click in the panel). It is still listed and its `state` is still true, but it sends no popup or bell and does not need you: a shell should show it quietly and leave it out of any "needs you" badge. Added in version 1. |
| `counts` | How many rows are in each state. The keys are always `working`, `waiting`, `done`, `idle`, `limited`, `error`. Muted rows count in their state. |
| `needs_you` | How many rows ask for you: `waiting` or `limited`, and not `muted`. The number for a badge. Added in version 1. |

Rows are ordered by importance (`limited`, `waiting`, `error`, `working`, `done`, `idle`), then by `key`. An empty `agents` array means no known agent is in the foreground of a kitty that is still running. `panes-<pid>.json` and `scan-<pid>.json` are not this list: each is one kitty process, and `{}` means that process currently has nothing to report.

## tabs.json — every tab, for a client drawn outside kitty

`$KITTYMUX_STATE/tabs.json` lists every tab of every running kitty, with or without an agent: what a client needs to draw the tab strip (the kittymux client,
kuwai's Agents tab). The scanner writes it beside `agents.json` and the same way: each kitty replaces only its own entries and keeps those of kitties that are still
alive, mode `0600`, atomic, and only when the document apart from `t` changed. Schema version **1**.

```json
{"version": 1, "t": 1793780793.0, "needs_you": 1, "windows": [
  {"key": "o4035.1", "kitty_pid": 4035, "os_window_id": 1, "wm_class": "kitty", "focused": true, "session": "",
   "palette": {"bg": "#101014", "fg": "#e6e6ea", "muted": "#959599", "faint": "#66666a", "accent": "#c792ea",
               "working": "#82aaff", "waiting": "#ffcb6b", "done": "#c3e88d", "alert": "#f07178"},
   "tabs": [
     {"tab_id": 2, "index": 1, "active": true, "title": "Review the parser", "cwd": "~/work/calm-otter", "project": "calm-otter",
      "branch": "main", "hue": "#96cfb8", "panes": 2, "agent": "codex", "agent_window": 12, "brand": "openai", "state": "waiting",
      "since": 1793780600.0, "progress": null, "question": "Allow edit to parser.rs?", "limit_reset": null, "muted": false,
      "needs_you": true, "action": {"op": "jump", "pid": 4035, "w": "11"}}]}]}
```

| Field | Meaning |
|---|---|
| `windows[]` | One kitty OS window each, ordered by `key` (`o<kitty_pid>.<os_window_id>`). `focused`: the OS window kitty last focused. |
| `title` | The OS window's title (what the window manager shows), to tell one kitty's windows apart. |
| `geometry` | Where the bar is, for a client that draws over it: `vw`, `vh` (framebuffer pixels), `width`, `height` (logical), `scale`, `edge` (`left`, `right`, `top`, `bottom`), `bar` [left, top, right, bottom] in framebuffer pixels (`null` when the bar is hidden), `cell` [width, height], `opacity`. `null` when kitty could not say. Republished when a window is resized. |
| `palette` | The kitty theme's tokens (`kittymux_theme.from_colors`, `bar` is the bar's own background) as `#rrggbb`: draw with these, never with typed colours. |
| `tabs[]` | In the bar's order; `index` counts from 1. `active`: the active tab of that OS window. |
| `project`, `branch`, `hue` | The git project (or folder) and branch of the tab's active pane, and the project's colour as the bar gives its space. |
| `panes` | How many panes the tab has. |
| `agent`, `brand`, `state`, `since`, `progress`, `question`, `limit_reset`, `muted` | From the pane that speaks for the tab: the one that needs you, then one in error, then one working, then the rest; a muted agent speaks only when nothing else in the tab does. Empty `agent` and `state` when no pane runs an agent. Field meanings as in `agents.json`. |
| `agent_window` | That pane's window id: what `kittymux mute --pid <kitty_pid> --window <agent_window>` mutes. `null` without an agent. |
| `needs_you` | The tab asks for you (`waiting` or `limited`, not muted). The top-level `needs_you` counts these tabs. |
| `action` | `kittymux act` jumps to the tab's active pane. |

A client that draws over a kitty's vertical bar tells that kitty with `kittymux client attach KITTY_PID OWNER_PID` (`bar-attached-<pid>`, the same record as the panel's cover): while the owner lives, the bar keeps its place and background and draws no tabs.

A kitty that exits last leaves its entries behind (no other kitty is left to prune them): a client checks that `kitty_pid` still runs before it draws them.

## Notification hints

`bin/mux-notify` already set `x-kittymux-pid` and `x-kittymux-window`. It also sets these, when the value is a short token:

| Hint | Value |
|---|---|
| `x-kittymux-event` | The inbox event id, so a shell can `kittymux inbox jump ID` or `ack` that id. |
| `x-kittymux-agent` | The agent or the tool (`sudo`, `pacman`, …). |
| `x-kittymux-brand` | The `assets/icons` basename. Omitted when we have no mark. |
| `x-kittymux-state` | `working`, `waiting`, `limited`, `error`, `done` or `idle`. |
| `x-kittymux-source` | `agent` or `tool`. |

Invoking the notification's Jump action focuses that window and, when `x-kittymux-event` was set, acknowledges that window's events. That is the same end state as `kittymux inbox jump ID` (focus, then ack by window and pid). A notification with no event id only focuses, as before. The click does not shell out to `inbox jump`: a private kitty's socket is not named `mykitty-<pid>`, and the helper was given the socket directly.

## CLI (what an add-on calls)

```
kittymux inbox [--all] [--json] [--limit N]    list unread (or all) newest first; --json prints the snapshot
kittymux inbox ack ID… | --all                 mark read
kittymux inbox clear [--all]                   dismiss unread (or everything)
kittymux inbox jump [ID]                       focus the window (kitty remote control + hyprctl); no ID = the most pressing unread one; marks it read
kittymux inbox watch                           one JSON line per NEW event (a convenience for scripts)
kittymux inbox ledger [--json]                 how long agents waited on you (first appeared → first looked at); today, this week, median, longest
```

## Building an add-on

A shell panel needs only: **watch `inbox-snapshot.json`** for events, **`agents.json`** for who is working and **`tabs.json`** for the tab list, render those, and run `kittymux inbox jump ID` / `ack ID` (or the row's `action`) on click. See
[`addons/quickshell/`](../addons/quickshell/README.md) — a minimal Quickshell sample following exactly this contract. It is **not tested here** (Quickshell is not installed on the
author's machine); the contract above is what is tested (`tests/test_inbox.py`, `tests/smoke_inbox.sh`).

## Cost and bounds

Events are rare (a state change, a notification): a few small appends a minute at most, nothing per scanner tick. The log is bounded by bytes (256 KB, compacted to the newest 200 events), the
snapshot by count (60), and the in-kitty "unread windows" set by the number of windows. Nothing here retains screen text.
