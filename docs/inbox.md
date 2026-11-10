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
   "progress": null, "limit_reset": 1793784393, "error": null, "action": {"op": "jump", "pid": 4035, "w": "20"}},
  {"key": "w4035.19", "kitty_pid": 4035, "window_id": 19, "agent": "claude", "brand": "claude", "source": "agent",
   "state": "working", "since": 1793780700.0, "title": "Port the configs", "tab_title": "calm-otter",
   "cwd": "~/work/calm-otter", "project": "calm-otter", "session": "calm-otter", "question": null,
   "progress": 0.42, "limit_reset": null, "error": null, "action": {"op": "jump", "pid": 4035, "w": "19"}}
], "counts": {"working": 1, "waiting": 0, "done": 0, "idle": 0, "limited": 1, "error": 0}}
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
| `counts` | How many rows are in each state. The keys are always `working`, `waiting`, `done`, `idle`, `limited`, `error`. |

Rows are ordered by importance (`limited`, `waiting`, `error`, `working`, `done`, `idle`), then by `key`. An empty `agents` array means no known agent is in the foreground of a kitty that is still running. `panes-<pid>.json` and `scan-<pid>.json` are not this list: each is one kitty process, and `{}` means that process currently has nothing to report.

## tabs.json — the bar's tabs, without drawing them again

`$KITTYMUX_STATE/tabs.json` (or `~/.local/state/kittymux/tabs.json`) is the tab list a shell draws beside kitty. `agents.json` is agents only; this file is every tab, including a plain shell. The vertical bar writes it from the same title, place line, state, age and progress it draws. Each kitty replaces only its own windows and drops a window whose kitty pid is no longer alive. Mode `0600`. Rewritten atomically (a temporary file, then rename). A pass that changes nothing but `t` does not replace the file. Writes are coalesced to at most one every 250 ms per kitty, and the last change in that window is written when the interval ends. Schema version **1**.

```json
{"version": 1, "t": 1793780793.0, "windows": [
  {"kitty_pid": 4035, "os_window_id": 1, "wm_class": "kitty", "focused": true, "session": "calm-otter",
   "tabs": [
     {"tab_id": 3, "index": 1, "active": true, "title": "Home", "subtitle": "zsh", "project": "~",
      "hue": null, "branch": "", "cwd": "~", "agent": "", "brand": "", "state": "idle", "age": "",
      "progress": null, "panes": 1, "needs_you": false, "action": {"op": "jump", "pid": 4035, "w": "19"}},
     {"tab_id": 4, "index": 2, "active": false, "title": "Port the configs", "subtitle": "calm-otter/src  main",
      "project": "calm-otter", "hue": "#a3d4a0", "branch": "main", "cwd": "~/work/calm-otter",
      "agent": "claude", "brand": "claude", "state": "working", "age": "4m",
      "progress": {"state": "set", "pct": 42}, "panes": 2, "needs_you": false,
      "action": {"op": "jump", "pid": 4035, "w": "20"}}
   ]}
]}
```

| Field | Meaning |
|---|---|
| `version` | `1`. A new field keeps this number. A rename, a removal, or a change of meaning bumps it. |
| `t` | When this document was built, epoch seconds. Not a reason to reread the rows. |
| `kitty_pid` | The kitty process that owns the OS window. |
| `os_window_id` | That process's OS window. |
| `wm_class` | The window class kitty set (`kitty`, unless the window was started with another). |
| `focused` | True when this is the OS window kitty considers focused. |
| `session` | The focused session in that OS window, or `""`. |
| `tabs` | That window's tabs, in bar order. `index` starts at 1. |
| `tab_id`, `active` | The tab, and whether it is the active tab of its OS window. |
| `title` | The tidied title the bar uses. A bare `~` is `Home`, the same substitution the bar draws. |
| `subtitle` | The place line's words (project, path, branch, separated as the bar separates them) or, when the bar draws the program instead, that program (`zsh`). No icons and no colour codes. |
| `project`, `branch`, `cwd` | The bar's project name, git branch, and directory with home written as `~`. `project` is `~` in the home directory. Empty when unknown. |
| `hue` | The project hue the bar uses, `#rrggbb`, or `null` when hue is off or the tab has no directory. |
| `agent`, `brand` | The CLI name, and the `assets/icons` basename from `kittymux_agents.brand_of`. Both `""` when the tab is not an agent. |
| `state` | A status-contract name: `limited`, `waiting`, `error`, `working`, `done`, `idle`. A tab with no agent is `idle`. The bar's `unread` mark is not a state here. |
| `age` | How long the bar says the tab has been in this state (`4m`, `2h`, `3d`, or `↻12m` when a limit lifts). `""` under a minute, and for `idle`. |
| `progress` | OSC 9;4 as the bar draws it: `{"state":"set","pct":42}`. `state` is `set`, `paused`, `error` or `indeterminate`. `pct` is 0–100. `null` when nothing is reported. |
| `panes` | How many panes the tab has. |
| `needs_you` | True for `waiting` and `limited`. |
| `action` | The object `kittymux act` accepts, aimed at the tab's focused window: `{"op":"jump","pid":<int>,"w":"<digits>"}`. |

Windows are ordered by `kitty_pid`, then `os_window_id`. An empty `windows` array means no kitty that is still running has published a tab. `agents.json` stays the agent list; this file does not replace it.

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
