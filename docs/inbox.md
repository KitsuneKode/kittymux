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
| `error` | warn | the agent reported a failure | inbox only |
| `info` | info | anything else the agent said | inbox only |

The same occurrence reported by several sources inside 45 s is **one** event (`sources: ["agent","screen"]`, `count` > 1) and **one** popup. Focusing a window
acknowledges everything it reported (`status: read`). `kittymux explain` shows, per decision, why a popup was or was not shown.

## Files (state dir: `$KITTYMUX_STATE` or `~/.local/state/kittymux`, all mode 0600)

- `inbox.jsonl` — append-only operations, safe for several kitty processes to write at once (`O_APPEND`, plus a lock for compaction): `{"op":"add",…}`, `{"op":"ack",…}`, `{"op":"clear"}`. Compacted past 256 KB.
- **`inbox-snapshot.json`** — the folded view, rewritten atomically after every change. **This is what a widget watches.** Schema version 1:

```json
{"version": 1, "updated": 1790000000.0, "unread": 2, "needs_you": 1,
 "events": [ {"id": "18f3a…-4321-7", "t": 1790000000.0, "pid": 4321, "w": "77", "kind": "permission", "severity": "needs-you",
              "agent": "claude", "tab": "Kitty lightweight tm", "title": "claude needs permission", "body": "Claude needs your permission to use Bash",
              "sources": ["agent", "screen"], "confidence": "high", "status": "unread", "count": 2},
             {"kind": "limit", "reset_at": 1790009000, "…": "…"} ] }
```

`events` is newest first (at most 60). `pid` + `w` identify the kitty process and window. In **private mode** (`notify-private`) `body` is empty.
`id` is stable. New fields may be added; consumers must ignore unknown ones (bumping `version` only for breaking changes). Two optional fields come from folding the log: `t0`, when the
event first appeared (`t` moves to the newest report of a merged event), and `ack_t`, when it first stopped being unread (you focused its window, read or dismissed it). `kittymux inbox ledger`
turns them into how long agents waited on you.

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

A shell panel needs only: **watch `inbox-snapshot.json`**, render `events`, and run `kittymux inbox jump ID` / `ack ID` on click. See
[`addons/quickshell/`](../addons/quickshell/README.md) — a minimal Quickshell sample following exactly this contract. It is **not tested here** (Quickshell is not installed on the
author's machine); the contract above is what is tested (`tests/test_inbox.py`, `tests/smoke_inbox.sh`).

## Cost and bounds

Events are rare (a state change, a notification): a few small appends a minute at most, nothing per scanner tick. The log is bounded by bytes (256 KB, compacted to the newest 200 events), the
snapshot by count (60), and the in-kitty "unread windows" set by the number of windows. Nothing here retains screen text.
