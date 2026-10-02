# Sessions that come back — with their agents' conversations

kitty already has excellent session support; kittymux builds on it rather than replacing it, and adds the one thing it cannot know: **which conversation each
agent window was in**.

## What kitty does natively (and we use as is)

| kitty feature | what it gives you | how kittymux uses it |
|---|---|---|
| `save_as_session --use-foreground-process` | tabs, windows, exact split layout (`set_layout_state`), titles, per-tab cwd, the foreground command of every window | the one saver: `kittymux sessions save` and the save key call it; we never reimplement serialization |
| `--var=` in saved `launch` lines | kitty serialises **window user variables** into the file | we mark each agent window with its agent / session id just before saving, so the file is self-describing (no window-id matching) |
| `goto_session`, `close_session`, `startup_session`, `kitty --session` | switch/restore/close sessions | `kittymux sessions restore` uses `goto_session` inside kitty, `kitty --session` otherwise |
| session file syntax (`layout`, `cd`, `launch --cwd/--env/--var`, `new_tab`, `focus`, …) | declarative project layouts | our templates are plain kitty session files |
| `{session_name}` in `tab_title_template` | the session in the tab title | the bar already shows it |

kitty alone restores an agent window as a **fresh** `claude`/`codex`: layout and cwd come back, the conversation does not.

## What kittymux adds

1. **Resume.** Before kitty saves, `kittymux sessions prepare` marks every agent window with `kittymux_agent`, `kittymux_resume` (`exact`/`latest`/`none`) and, when
   known, `kittymux_sid`. After kitty writes the file, `kittymux sessions rewrite` turns each agent's saved command into its resume command, keeping every flag it was started with
   (`claude --dangerously-skip-permissions --model opus` → `… --resume <id>`) and stripping stale hook state. Nothing is guessed: see "How the session id is found".
   **A restored window asks first** (see below) — it never silently re-enters a conversation.
2. **Autosave — the last state of things.** The scanner saves this kitty (`autosave-<pid>.kitty-session`, newest 5 kept) when the set of windows changes and has settled for 20 s (at most
   once a minute) and at least every 15 minutes. `kittymux sessions restore last` brings the newest back. Off: `touch ~/.local/state/kittymux/autosave-off` or `KITTYMUX_AUTOSAVE=0`.
3. **Templates.** `kittymux sessions new api --template agent --agent claude --cwd ~/code/api` writes a ready session (an agent with a shell beside it). Shipped: `plain`, `agent`, `duo`
   (two agents + a shell), `review` (agent + the working-tree diff + a shell). Your own `~/.config/kittymux/templates/<name>.kitty-session` wins. Every template is checked against kitty's own parser in the tests.
4. **The restore prompt.** In the saved file an agent window's command is `kittymux resume-prompt --info <json>` (the json carries the agent, the session id, the original command
   and the resume command). The window shows what it would resume and what the journal knows about it, then waits for one key:

   ```
   claude was running here — resume session 0a1b2c3d?
     ~/code/api
     last active 12m ago · 7 runs finished · 1h20m of work · tab “api work”
     Enter resume   n new conversation   s shell   a resume all   i commands
   ```

   `Enter`/`r` resume (every flag you started it with) · `n` a new conversation (the original command) · `s`/`Esc` a plain shell · `a` resume this and every other waiting prompt for the next 2 minutes ·
   `i` show both commands. The prompt then **replaces itself** (`exec`) with your answer, so the agent is the window's foreground process exactly as if you had typed it. Skip the question:
   `KITTYMUX_RESUME=auto`, or `touch ~/.local/state/kittymux/resume-auto`, or write the resume command straight into the file with `sessions save --direct`. The record is validated (a session file is
   editable): only string commands whose program matches, an id that is a plain token; anything else opens a shell. No tty to ask → the original command. A missing agent binary → a shell.
5. **The journal — nothing is lost between saves.** The scanner keeps `agent-sessions.json`: one record per agent session (agent, session id when the agent exposes it, directory, tab title, the
   command with its flags, first/last seen, last state, runs finished, time spent working, whether it is open). It is updated on every state change and at least once a minute while the agent
   runs (a session id that appears late, a `cd`, a renamed tab), written at most every 5 s, merged under a lock so several kitties share it, bounded (300 records, 90 days), private (0600).
   `kittymux sessions history [--since 7d]` is the insight view (sessions, runs, work time, per agent); `kittymux sessions recover [NAME] [--since 6h]` builds a session file with a tab per agent
   conversation that was active recently and is not running now (a crash, a closed kitty) — each comes back through the prompt. Off: `touch ~/.local/state/kittymux/journal-off` or `KITTYMUX_JOURNAL=0`.
6. **`kittymux sessions list`** shows what a save would do for each agent window, and why. **`kittymux sessions check`** probes each installed CLI's own `--help` for the flags we use.

## Commands

```
kittymux sessions list [--json]                         agent windows in this kitty: exact / latest / new, the command each would resume with, and why
kittymux sessions save [NAME] [--all] [--direct]        save the focused OS window (--all: every one) as NAME (default saved-<time>); agents come back asking (--direct: resuming at once)
kittymux sessions history [--since 7d] [--json]         every agent session recorded while kitty ran: runs, work time, running or closed
kittymux sessions recover [NAME] [--since 6h]           a session file with a tab per recently active agent conversation that is no longer running
kittymux sessions restore [NAME|last] [--new-window]    goto_session inside kitty; a new kitty otherwise (or with --new-window)
kittymux sessions new NAME [--template T] [--agent A] [--agent2 B] [--cwd DIR] [--force]
kittymux sessions templates                             the available templates
kittymux sessions check                                 probe each installed agent CLI's --help for the resume flags it needs
kittymux sessions rewrite FILE | --recent               rewrite an already saved file (the save key does this for you)
```

`ctrl+alt+shift+s` (the existing save key) now does prepare → kitty's save → rewrite.

## How the session id is found — and what happens when it cannot be

| Agent | Exact id | "Latest" fallback | Resume command | Verified |
|---|---|---|---|---|
| Claude Code | **yes** — Claude's own registry `~/.claude/sessions/<pid>.json` (`sessionId`, checked against the process start time so a reused pid cannot match) | `--continue` (its help: per directory) | `claude … --resume <id>` | yes |
| Codex | when the process holds its `rollout-…-<uuid>.jsonl` open | `codex resume --last` (its help: `--all` disables cwd filtering, so it is per directory) | `codex [flags] resume <id>` | yes |
| grok | not exposed | `--continue` ("most recent session for the current working directory") | `grok … --resume <id or title>` | yes |
| droid | not exposed | `-r --last` ("most recent session in the current folder") | `droid -r <id>` | yes |
| Devin | **yes** — the session's name *is* its id (`calm-otter`): a running window's `devin acp` child holds `~/.local/share/devin/cli/session_locks/<id>.lock` open (same process group; the lock file holds that pid). Checked on two live windows against `devin list --format json`. | `-c` (scope not stated) | `devin -r <id>` | yes |
| opencode | a bare TUI exposes none (title is a static "OpenCode", only a log file open); one **started with `-s <id>`** keeps it on its command line. Otherwise: `opencode session list --format json` (the CLI is the contract; the database schema is not) → the directory's newest session **touched since this window's process started** | `-c` (scope not stated) | `opencode -s <id>` | yes |
| cursor-agent | no id while it runs before a first message; chats live at `~/.config/cursor/chats/<md5 of the directory>/<chat uuid>/store.db`: the directory's newest chat **touched since the process started**; or `--resume <id>` on its command line | `--continue` (scope not stated) | `cursor-agent --resume <id>` | yes (layout seen on disk; md5 mapping checked against 2 real directories) |
| Antigravity (`agy`) | no conversation file is held open before the first message; `~/.gemini/antigravity-cli/cache/last_conversations.json` maps a directory to its last conversation id (`conversations/<uuid>.db`): used when that conversation was **touched since the process started**; or `--conversation <id>` on its command line | `--continue` (scope not stated) | `agy --conversation <id>` | yes (files seen on disk) |
| Gemini, Amp | not installed here | from public docs, enabled only if the probe passes | | no |

"Verified" = the flag is in that CLI's own `--help` on the author's machine; on yours, `kittymux sessions check` probes again (cached 12 h per executable) and an agent whose help does
not show the flags is **not** rewritten. The rules that keep this safe:

- **Exact beats latest.** Claude and Devin get their real ids; any agent started on an id (`-s`, `--resume <id>`, `--conversation <id>`) keeps it. opencode, Cursor and agy get the directory's
  conversation **only if this window's agent touched it** (its files or its own list changed after the process started) and it is the only window of that agent in that directory — a window that
  never had a conversation is restored as a new session instead of being pointed at an older one that merely sorts first. Where it cannot look (the CLI is missing, an unknown layout) the old rule applies.
  Everything else gets "latest" only when it cannot attach the wrong conversation: for agents whose help says "latest" is per directory, when it is the only window of that agent in that
  directory; for agents that do not say, only when it is the single window of that agent.
- **Never one conversation twice.** Two windows of one agent in one directory with no exposed ids are restored **as saved** (a new conversation each), not both as `--continue`.
- **Ids are validated** (`[A-Za-z0-9][A-Za-z0-9._:-]*`, so never an option); the saved line is rebuilt as separate arguments, never through a shell.
- **Flags you started with are kept**, the agent's old resume/continue flags are removed first so none is doubled, and a prompt argument is never replayed (a Codex started with a prompt or
  as `codex exec` is left alone).
- What does **not** come back: the agent *process* (it restarts), its in-flight tool calls, scrollback, shell state. The conversation does.

### Adding an agent (or fixing a definition)

Definitions are data: `assets/resume-agents.json` (shipped) and `~/.config/kittymux/resume.json` (yours; same shape, an entry replaces the shipped one). For a CLI whose
`--help` shows `--resume <id>` and `--continue`:

```json
{ "myagent": {
    "latest_scope": "unstated",
    "exact": ["--resume", "{id}"], "latest": ["--continue"],
    "strip_with_value": ["--resume"], "strip": ["--continue"],
    "helpers": ["mcp", "login"],
    "probe": { "args": ["--help"], "expect": ["--resume", "--continue"] } } }
```

`form: "subcommand"` is for `agent [flags] resume <id>` (Codex). `names` are aliases for the binary. `helpers` are subcommands that are not the interactive agent. Then run
`kittymux sessions check`: it confirms the flags exist in the installed CLI before anything is rewritten. `kittymux doctor` lists installed agents that still have no definition.

## Privacy and files

Everything lives under `~/.local/state/kittymux/` (0700; files 0600): `sessions/*.kitty-session`, `resume-check.json`, `agent-sessions.json` (the journal), `resume-all-until` (the "resume all" window). A session file holds directories, commands, titles and session ids
(not conversation content). The conversations themselves stay where each agent keeps them. The journal records a command **with its flags**, exactly as `/proc` already shows it to your
other processes — don't pass secrets as command-line flags (use the agent's own config or environment).
