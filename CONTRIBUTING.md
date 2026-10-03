# Contributing

Thanks for helping. kittymux is small on purpose: a config layer for kitty, not a daemon. Read [AGENTS.md](AGENTS.md) first — it is the working contract (rules, invariants, how state is decided,
the kitty internals we depend on). It is written for coding agents and is just as useful for people.

## Set up

```sh
git clone https://github.com/KitsuneKode/kittymux && cd kittymux
git worktree add .worktrees/my-change -b my-change main      # work in a worktree; never edit what your kitty loads
cd .worktrees/my-change
python3 -m unittest discover -s tests && bash tests/test_mux_status.sh && bash tests/test_socket_lib.sh
```

Real-kitty tests (Xvfb, private config and socket; they SKIP if a tool is missing) are listed in [docs/testing.md](docs/testing.md). Run the ones your change touches, e.g.
`bash tests/smoke_state.sh`. They never touch your kitty, config or state. **`SKIP` is not a pass.**

## Before you open a PR

- One concern per PR; plain-language, conventional-style title (`fix(bar): …`, `feat(sessions): …`).
- Tests for the behaviour you changed. For anything a human can feel (clicks, drags, keys) use the real-kitty rigs with **real events** — a perfect scripted click hides whole bug classes.
- `python3 -m py_compile` on touched Python, `bash -n` and `shellcheck -S error` on touched shell, `git diff --check`.
- Keys: a new chord is checked against your window manager (`kittymux doctor`) and updates `kittymux-keys.conf.tpl` **and** the README key table together.
- Docs: update the README and the `docs/users/` page a user would read (`python3 -m unittest tests.test_docs` checks links, chords and the CLI reference; `python3 tools/docs_status.py` regenerates the status table); don't append a changelog paragraph — add a line under *Unreleased* in [CHANGELOG.md](CHANGELOG.md).
- No credentials in the repo — not real, not key-looking. Build sample secrets at run time from filler; use synthetic ids. `tests/test_no_secrets.py` and CI's gitleaks job enforce it (details in AGENTS.md).
- Never claim more than you verified: a mocked provider response or an Xvfb run is not live-provider or compositor verification (say which you did).

## Adding an agent

1. **Status markers** — check a real screen (`kitty @ get-text --match id:N` → `kittymux_state.classify_screen`), then add the marker and a test; record it in `docs/compatibility.md`.
2. **Resume** — add an entry to `assets/resume-agents.json` from what the CLI's own `--help` shows (never a flag you did not read there); see "Adding an agent" in [docs/sessions.md](docs/sessions.md).
3. **Icon** — a real brand mark as SVG in `assets/icons/`, then `tools/build-icons.py` (append-only codepoints).

## Security

Report vulnerabilities privately — see [SECURITY.md](SECURITY.md). Changes that touch what we read from terminals, files we write, sockets, or anything we execute need a test with hostile input.
