# Security

## Reporting a vulnerability

Please report it **privately**: <https://github.com/KitsuneKode/kittymux/security/advisories/new> (GitHub private vulnerability reporting). Do not open a public issue for something
exploitable. Include what you saw, the kitty and kittymux versions (`kittymux version`, `kitty --version`), and a minimal way to reproduce it. I aim to answer within a week;
a fix and an advisory follow once it is confirmed. Only the latest release (and `main`) is supported.

## What kittymux is, security-wise

A *config layer* for kitty that runs **as you**, inside your kitty process, plus a few helper scripts. There is no server, no network listener, no always-on daemon. It reads pane text and
agent state **locally** and never transmits it (the optional usage collectors call each provider's own API with credentials you already have, and only when you turn them on).
Anything it shows or stores that came from a terminal is treated as **untrusted text** — an agent, a file you `cat` or a web page's output can write whatever it likes to a pane.

## Trust boundaries and what protects them

| Boundary | Risk | Control | Proof |
|---|---|---|---|
| Program output → kitty | an escape sequence in output controls kitty (read other panes, type into them) | we recommend `allow_remote_control socket-only` (in-band control is refused); `kittymux doctor` flags `yes` | `tests/smoke_socket.sh` shows `yes` obeys a printed escape sequence and `socket-only` refuses it |
| Control socket | a squatted or world-reachable socket in `/tmp` | recommend `listen_on unix:${XDG_RUNTIME_DIR}/mykitty` (private dir); we only ever talk to sockets **owned by you** | `tests/test_socket_lib.sh`, `tests/smoke_workflows.sh` |
| Terminal text → bar / notifications | control characters, markup injection (`<a href>`), option injection | stripped, bounded, markup-escaped; `notify-send --`; the icon comes only from our table or `assets/`, never from agent output | `tests/test_scan.py`, `bin/mux-notify` argument validation |
| Window titles → menus | a title (any program can set one) with a newline/NUL/ESC/bidi override forges rows or shifts the indexes a menu answers with | every field shown in `pick` goes through `kittymux_launcher.clean_text`; a row with a control character is refused at the menu boundary | `tests/test_launcher.py` (hostile titles, index = row) |
| Window variables → quiet | a program in a window sets `kittymux_snooze_until` to silence its own "needs you" popup | snooze lives in a private file, never a window variable; ends are capped at 30 days | `tests/test_quiet.py`, `tests/smoke_spawn.sh` |
| Agent output → what we run | an agent causing a command to run | we never execute text from a pane. Resume commands are rebuilt as argv from validated pieces (ids are plain tokens, never an option), never through a shell | `tests/test_resume.py` (hostile ids, records) |
| Session files | an edited file running something unexpected | a restored agent asks first; its record is validated (strings only, same program, plain-token id); anything else opens a shell. (A session file is already code you chose to launch — this is defence in depth.) | `tests/test_kittymux_cli.py::ResumePromptTests` |
| State on disk | other users reading titles, agent messages, commands | state dir `0700`, files we write `0600` from creation, atomic replace | `tests/test_install.sh`, `tests/test_journal.py`, doctor |
| Output that leaves the machine | a pasted `sessions list --json` leaking a token passed as a flag | secret-looking flag values and credential-shaped tokens are redacted from printed JSON/lists (the 0600 journal keeps the real command so recovery works) | `tests/test_journal.py::RedactionTests` |
| Fan-out prompts | a prompt becoming a shell command or an option of the agent | passed as ONE argv element, never through a shell; refused if it starts with `-`, contains NUL or is over 8000 chars; the agent's flag names come from a validated table; branch/worktree names are validated and an existing path or branch is never reused | `tests/test_fanout.py`, `tests/smoke_fanout.sh` (backticks stay text) |
| Running git in your repos | a hostile repository (config, hooks, filters, fsmonitor, external diff) making kittymux's background snapshot run something | detached low-priority helper; file-system monitor, external diff and textconv off; no terminal; `GIT_*` from our environment stripped; `safe.directory` honoured (a repo git distrusts is skipped); the repo is never written to (private object store) | `tests/test_changes.py` (repository untouched), `tests/smoke_changes.sh` |
| Destructive commands | `uninstall --purge` deleting a mistyped `KITTYMUX_STATE` (`/`, your home) | refused unless the directory is recognisably kittymux's; never follows a symlink | `tests/test_kittymux_cli.py::PurgeGuardTests` |
| Which kitty | a launcher acting on another instance (or a test rig on yours) | a command started inside a kitty targets that kitty; focus-following only outside every kitty | `LauncherTargetTests`, the tripwire in `smoke_spawn.sh` |
| Your Claude settings | a broken or widened `settings.json` | `hooks --install` backs up first, never overwrites a backup, touches only our entries; `--remove` undoes exactly that | `tests/test_kittymux_cli.py::HooksTests` |
| Focus | a notification stealing your focus | a bell is not sent where the compositor would turn it into a focus change; focus moves only on your action | `tests/test_attention_kitty.py` |

## Things to do yourself

- Use `allow_remote_control socket-only` and a socket in `$XDG_RUNTIME_DIR` (`kittymux doctor` checks both).
- Do not put secrets in a `fanout` prompt (it is a command-line argument, visible in `ps` while the agent runs).
- Do not pass secrets as command-line flags to anything: `ps` shows them to every local user, and kittymux's session files and journal record the command you started an agent with.
- Treat a session file from someone else like a script from someone else.

## Known limits

- It trusts the local user account. A process already running as you can read your state and drive your kitty; kittymux is not a sandbox.
- Screen-scraping states (`waiting`, `done`) are heuristics: a hostile program can imitate an agent's prompt. The bar is a convenience, not an authorization prompt — never approve something because a tab said so.
- Linux only (`/proc`). Verified against kitty 0.49.x; see [docs/compatibility.md](docs/compatibility.md).

History of what was audited and fixed: [docs/audit-2026-10-01.md](docs/audit-2026-10-01.md), [docs/hardening-validation-2026-10-01.md](docs/hardening-validation-2026-10-01.md).
