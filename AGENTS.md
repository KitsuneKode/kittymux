# kittymux

Kitty-as-multiplexer config pack: tabs, panes, session restore, an agent-aware tab bar, a sidebar and a docked panel, and overlays for keys, usage and
folders. It is a config layer for kitty, not a daemon. tmux stays for remote work.

## Who this file is for

**Coding agents and people changing this repository.** It is short on purpose: what you must know before you edit anything. The detail is in
`docs/agents/`, one page per area, and you read a page when you touch that area (the table below says which).

It is **not** for people using kittymux (that is `README.md` and the published docs), for release notes (`CHANGELOG.md`), or for proposals
(`docs/superpowers/`). If you are about to put user-facing prose here, put it in `docs/` instead.

## What lives where

| File | For | Holds | Update it when |
|---|---|---|---|
| `AGENTS.md` (this file) | agents | the contract: rules that were paid for, workflow, the "read before you change" table | a rule is learned or a workflow changes |
| `docs/agents/layout.md` | agents | the module map: which file owns what | you add, move or split a module |
| `docs/agents/status-contract.md` | agents | states, who decides "done", restore, the inbox, usage numbers, limits | you touch the scanner, resolver, inbox, sessions or notifications |
| `docs/agents/conventions.md` | agents | how kitty behaves underneath us, and the rules that follow | you learn something about kitty that cost time |
| `docs/agents/verify.md` | agents | every test and rig, what it proves, how CI differs | you add a rig or a check |
| `README.md` | users | tour, install, the key table | a key or a command changes (same commit) |
| `docs/index.mdx`, `docs/users/`, `docs/developer/` | users, contributors; published to the site | the published guides | a command, key or feature changes (same commit; `test_docs` guards it) |
| `docs/*.md` (flat) | maintainers | audits, compatibility facts, launch checklist | a marker is verified against a live agent |
| `CHANGELOG.md` | users | what changed, under `[Unreleased]` | any user-visible change |
| `docs/superpowers/specs`, `plans` | maintainers | proposals and plans. **Not the truth about the code**: read the status line at the top | you start or finish one |
| `site/README.md` | whoever deploys | how the docs site is built, checked and deployed | the build or deploy changes |

When a page and the code disagree, the code and this file win; fix the page.

## Read before you change, run after

| You are changing | Read first | Run (besides the unit tests) |
|---|---|---|
| agent status, the scanner, limits, "done" | `docs/agents/status-contract.md` | `smoke_state`, `smoke_inbox`, `smoke_prompts`; check a real screen (see the contract) |
| notifications, the inbox, prompts, bells | `status-contract.md`; the "never move focus" rule below | `smoke_inbox`, `smoke_prompts`, `smoke_spawn` |
| sessions, resume, the journal | `status-contract.md` (restore) | `smoke_resume`, `smoke_exit_save` |
| the tab bar, bar size, layout, the divider | `docs/agents/conventions.md` | `shot_bar` (look at it), `smoke_sidebar`, `smoke_native`, `smoke_resize`, `smoke_click`, `smoke_drag`, `smoke_reload` |
| the panel, the deck, peek, the palette | `layout.md` (the panel bullets), `conventions.md` | `shot_panel` (narrow too), `smoke_sidebar`, `smoke_peek`, `smoke_palette`, `test_panel_focus`, `stress_panel` |
| a key or a chord | the "Keys" rule below | `smoke_keys`, `smoke_spawn`, `smoke_panes`, the keymap tests; update `kittymux-keys.conf.tpl` AND the README table |
| a timer, a reload path, a socket | `layout.md` (timers, reload, sockets) | `smoke_timers`, `smoke_reload`, `smoke_legacy_socket`, `soak_kitty` |
| the docs or the site | `docs/developer/docs-maintenance.mdx`, `site/README.md` | `python3 -m unittest tests.test_docs`, and in `site/`: `bun run check`, `axe`, `budget`, `cls` |
| a rig or CI | `docs/agents/verify.md` (CI is a different machine) | the rig itself, and read the CI result |
| anything | the Rules section below | `python3 -m unittest discover -s tests`, `py_compile` on touched Python, `bash -n` on shell |

## How work flows

1. **Isolate.** `git worktree add .worktrees/<name> -b <name> main`; never edit `main` in place (live kitties load it).
2. **Test first where a test can see the bug**, and give a rig a control that must fail (it proves the rig can see).
3. **Look at anything visual**: render it, read the PNG, light and dark, narrow.
4. **Merge** to `main` with a fast-forward, then **reload live kitties only** (`kittymux upgrade`); record `kitty @ ls` window counts before and after. Never restart a live kitty.
5. **Open the PR for review, drafts included.** CodeRabbit reads `.coderabbit.yaml` and this file and comments on every PR to `main` (drafts too). Answer or fix each finding before the merge; a finding you disagree with gets a one-line reply saying why. CI has to be green as well: they check different things.
6. **Pushing `main` deploys the docs site**: the Vercel project `kittymux` builds `site/` on every push (previews on other branches are private). Do not push what you would not publish. Nothing else is deployed by a push.
7. **Say what you did not verify.** A mocked response or an Xvfb run is not a live-provider or a compositor check, and the docs must not claim it.

## Definition of done

- Behaviour change: a test that failed before and passes now; docs and `CHANGELOG.md` updated in the same commit; the README key table if a key changed.
- Visual change: before and after pictures read, both themes, the narrowest width.
- No credential-shaped value anywhere (tests enforce it).
- CI green, or the red step named and explained. A red `unit` hides the rigs behind it.

## Rules

- **No credential — real or credential-SHAPED — in the repository, ever** (tests, docs, fixtures, commit messages). A real token once reached a public commit because a test fixture was copied from a process
  listing. Never copy a value out of tool output, `ps`, `env`, logs or the user's data into a file: build sample values at run time from filler (`"sbp_" + "x" * 24`), and use obviously synthetic ids
  (`0a1b2c3d-0000-4000-8000-000000000001`, `calm-otter`) — not session ids, names or paths from the user's machine. `tests/test_no_secrets.py` and the CI gitleaks job enforce it; if something does get in, rotate it first, then
  remove it from history with the *smallest* rewrite (the commits are GPG-signed: `git filter-repo` re-writes every SHA and drops every signature — amend the one commit and force-push with a lease instead).
- No hardcoded palettes (theme tokens come from kitty's live colours); no module-level timer state; never read silence as waiting.
- Recommend `allow_remote_control socket-only` + `listen_on unix:${XDG_RUNTIME_DIR}/mykitty` everywhere (README, install hint, doctor, error messages); every smoke rig runs under `socket-only` — never write a rig or doc that needs `yes`. Printed output that may be pasted (`sessions list/history --json`) goes through `kittymux_journal.redact_argv`.
- **A test must never touch another kitty on the machine.** The author is usually typing in a live kitty while tests run, and `kitty @ launch` follows focus: a rig once spawned fake agents (and, via a different PATH, the REAL `claude`) into the live kitty, which also polluted the real journal. Rigs: set `KITTYMUX_SOCKET_DIRS=$RUN` for their own kitty and end with a tripwire that compares every OTHER kitty's window count (see `smoke_spawn.sh`). Code: a command started inside a kitty acts on THAT kitty (`_own_kitty_socket`), never on 'the focused one'; focus-guessing is only for launchers started outside every kitty.
- Never restart the user's live kitties. Work in an isolated worktree INSIDE the repo — `git worktree add .worktrees/<name> -b <name> main`
  (`.worktrees/` is git-ignored, and editors/agents scoped to this folder can see it) — test with the smoke rigs, merge to `main`, then apply
  to live by reload only (`kittymux upgrade`); record `kitty @ ls` window counts before/after. `main` is what live kitties load, so never
  leave it half-edited.
- Icons come from real brand marks: `assets/icons/*.svg` → `tools/build-icons.py` (append-only codepoints; fits non-square
  viewBoxes by their longest side). Devin's mark is Cognition's own; Antigravity's is the Google mark.
- A glyph added to the icon font reaches a RUNNING kitty only after a restart (it loads fonts once): draw a new glyph only when
  `kittymux_agents.glyph_font_loaded()` says that kitty started after the installed font (see the mascot in the bar header).
  The mascot glyph (E0F9) is traced from `assets/brand/mascot.png` by `tools/trace-mascot.py` → `assets/icons/kittymux.svg`.
- Never move the user's focus unasked. A bell → `window_alert_on_bell` → xdg-activation request is turned into a focus change (and a workspace switch) by compositors with Hyprland's `misc:focus_on_activate`;
  `kittymux_layout.attention_conf` (geninclude) switches kitty's alert off and `kittymux_scan._alert` skips the bell when `hypr_focus_on_activate()` is true (override: `attention-on`). Focus moves only on a user
  action (click, `inbox jump`, `ctrl+alt+y`, a notification action). Tests that touch this must not depend on the compositor running them (patch `hypr_focus_on_activate`).
- Options that only exist in newer kitty (`detect_url_regex`, `custom_shaders`) NEVER go in `kittymux.conf`: an older or still-running kitty reports a
  config error at every reload. They are emitted by `kittymux_layout.gated_conf(version, …)` (the geninclude), keyed on the version of the kitty process asking
  (`kitty.constants.version` — a kitty updated under a running session still reports its old version, which is exactly what we want). Opt-in looks
  (`kittymux dim`) are flag files in `$KITTYMUX_STATE`, never default-on. Custom shaders also need `slangc` installed (`have_slangc`).
- Keys: every new chord is checked against ALL of: our template, `kittymux.conf`, the user's own kitty confs (modifier ORDER differs: `ctrl+shift+alt+r` is `ctrl+alt+shift+r` — `test_no_chord_is_bound_twice…` normalises) and the window manager, and tried with REAL key events (`smoke_spawn.sh`). Also: kept-quiet is not lost — mute/snooze (`kittymux_scan._quiet_reason`) suppress popups and bells but every event still reaches the inbox. Keys: every new chord is checked against the window manager (`hyprctl binds -j`; `kittymux doctor` does all chords, `test_template_avoids_the_keys_hyprland_takes_with_ctrl_alt`
  pins the known-taken `ctrl+alt` letters: a s f c x p w m + arrows/minus/equal). Hyprland sees a global chord first; `ctrl+alt+p` once shipped and was dead on arrival.
- Overlay UIs (`launch --type=overlay`): one keypress must close them. Never `sys.stdin.read(n)` for a fixed n (a lone Esc blocks until n bytes arrive — it took 3 presses to
  quit); read what is there with `select`/`os.read`, parse sequences, treat a lone ESC as Escape. The key that opens an overlay is still bound while it has focus, so give the
  overlay a title and add `map --when-focus-on title:<t> <same chord> close_window`, or the chord stacks another overlay.
- Anything that changes a key updates `kittymux-keys.conf.tpl` AND the README key table in one commit.


The detail behind every rule above lives in `docs/agents/`: `layout.md`, `status-contract.md`, `conventions.md`, `verify.md`.
