# kittymux

An agent-aware workspace layer for [kitty](https://sw.kovidgoyal.net/kitty/).
Named sessions, per-project tab groups, git-aware tab bar, usage HUDs for
agent CLIs — as a *config layer*, not a daemon.

- **Zero daemon.** Everything is a shell script, one Python tab bar, and
  kitty's remote-control API. State is plain files.
- **Session-native.** Tabs belong to named sessions; parking hides them,
  restoring brings them back — checkpointed automatically on every switch.
- **Agent-aware.** Tab glyphs show which agent lives where (`✳` claude,
  `❋` codex, `⬡` devin …); a usage HUD reads local provider state.
- **Honest data.** No fabricated percentages — collectors show real local
  numbers or say "unavailable". Network access is opt-in.

## Install

```sh
git clone <repo> ~/kittymux
~/kittymux/install.sh
```

The installer verifies deps (`kitty`, `jq`, `python3`, `fzf`, `git`),
backs up `kitty.conf`, adds three `include` lines, and symlinks
`tab_bar.py`. Nothing is overwritten. Reload with `ctrl+shift+alt+r`.

Add a remote-control socket if you don't have one:

```conf
listen_on unix:/tmp/mykitty
```

## The mental model

```
OS window ──┬── session: work      (visible — bar shows these tabs only)
            ├── session: research  (parked — alive, hidden, auto-saved)
            └── session: misc      (parked)
```

- **Session** = a named group of tabs for one project/workspace.
- Switching sessions *parks* the current one — tabs and processes stay
  alive — and **auto-checkpoints** it to disk if it was saved before.
- `ctrl+shift+space` opens **Kitty Home**: one picker for every session
  op — jump, restore, create, rename, delete.

## Keymap spine

| Keys | Action |
|---|---|
| `ctrl+shift+space` | Kitty Home — all session ops |
| `ctrl+alt+,` / `ctrl+alt+.` | prev / next session |
| `ctrl+alt+shift+a` | last session |
| `ctrl+alt+t` / `+shift` | new tab beside / at end |
| `shift+←` / `shift+→` | prev / next tab (session-scoped) |
| `ctrl+alt+1..9` | jump to tab N |
| `ctrl+alt+h j k l` | pane nav · `ctrl+alt+o` last pane |
| `ctrl+alt+enter` | split horizontal · `+shift` vertical |
| `ctrl+alt+d` / `+shift` | pane → new tab / chooser |
| `ctrl+alt+z` / `=` | zoom pane / equalize |
| `ctrl+alt+i` (×2) | cwd pill → detail card (copy path/branch) |
| `ctrl+alt+u` | agent usage HUD |
| `ctrl+alt+a` | cycle focus between agent panes |
| `ctrl+alt+shift+e` | tab bar bottom → left → right |
| `ctrl+alt+shift+s` | save session now |

When tmux is focused, every `ctrl+alt*` chord passes through untouched.

## Agent usage collectors

`python/collectors/*.py` — one file per provider, auto-discovered:

```python
def collect() -> dict:       # pure local reads, no spawns
def live(cached) -> dict:    # optional, only when KITTYMUX_USAGE_LIVE=1
```

Ships with codex (rollout rate-limit snapshots), claude (reconstructed
5h billing window + weekly burn), cursor (plan + AI-lines share), devin
(session/token activity). Add your own by dropping a file in — a broken
collector can never kill the HUD.

With `KITTYMUX_USAGE_LIVE=1`, collectors that expose `live()` also fetch
real quotas, cached ≥5min: claude via the OAuth usage endpoint, cursor via
`DashboardService/GetCurrentPeriodUsage` (monthly auto/api model pools +
spend), devin via `SeatManagementService/GetUserStatus` (daily/weekly
quota + overage balance). Network is strictly opt-in — everything works
offline.

## Layout

```
kittymux/
├── kittymux.conf          # options (path-free)
├── kittymux-keys.conf.tpl # keybinds → rendered by install.sh
├── install.sh
├── lib/mux.sh             # session model + remote-control plumbing
├── bin/mux-*              # sessionizer, nav, cycle, jump, save, HUDs…
└── python/
    ├── tab_bar.py         # custom tab bar
    └── collectors/        # usage plugins (_common.py shared helpers)
```

State lives in `${XDG_STATE_HOME}/kittymux` (`0700`, files `0600`).
Override with `KITTYMUX_STATE`. Optional vars: `KITTYMUX_PROJECTS`
(picker root), `KITTYMUX_USAGE_LIVE=1` (opt-in network quota fetch).

## Uninstall

Remove the three `include` lines from `kitty.conf`, the
`~/.config/kitty/tab_bar.py` symlink, and `~/.local/state/kittymux`.
