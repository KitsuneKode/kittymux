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
2. **Autosave — the last state of things.** The scanner saves this kitty (`autosave-<pid>.kitty-session`, newest 5 kept) when the set of windows changes and has settled for 20 s (at most
   once a minute) and at least every 15 minutes. `kittymux sessions restore last` brings the newest back. Off: `touch ~/.local/state/kittymux/autosave-off` or `KITTYMUX_AUTOSAVE=0`.
3. **Templates.** `kittymux sessions new api --template agent --agent claude --cwd ~/code/api` writes a ready session (an agent with a shell beside it). Shipped: `plain`, `agent`, `duo`
   (two agents + a shell), `review` (agent + the working-tree diff + a shell). Your own `~/.config/kittymux/templates/<name>.kitty-session` wins. Every template is checked against kitty's own parser in the tests.
4. **`kittymux sessions list`** shows what a save would do for each agent window, and why. **`kittymux sessions check`** probes each installed CLI's own `--help` for the flags we use.

## Commands

```
kittymux sessions list [--json]                         agent windows in this kitty: exact / latest / new, the command each would resume with, and why
kittymux sessions save [NAME] [--all]                   save the focused OS window (--all: every one) as NAME (default saved-<time>), resumable
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
| Devin | not exposed | `-c` (scope not stated) | `devin -r <id>` | yes |
| opencode | not exposed | `-c` (scope not stated) | `opencode -s <id>` | yes |
| cursor-agent | not exposed | `--continue` (scope not stated) | `cursor-agent --resume <id>` | yes |
| Antigravity (`agy`) | not exposed | `--continue` (scope not stated) | `agy --conversation <id>` | yes |
| Gemini, Amp | not installed here | from public docs, enabled only if the probe passes | | no |

"Verified" = the flag is in that CLI's own `--help` on the author's machine; on yours, `kittymux sessions check` probes again (cached 12 h per executable) and an agent whose help does
not show the flags is **not** rewritten. The rules that keep this safe:

- **Exact beats latest.** Claude gets its real id. For the others, "latest" is used only when it cannot attach the wrong conversation: for agents whose help says "latest" is per directory,
  when it is the only window of that agent in that directory; for agents that do not say, only when it is the single window of that agent.
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

Everything lives under `~/.local/state/kittymux/` (0700; files 0600): `sessions/*.kitty-session`, `resume-check.json`. A session file holds directories, commands, titles and session ids
(not conversation content). The conversations themselves stay where each agent keeps them.
