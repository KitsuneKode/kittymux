# Trying the new features

Two ways, depending on whether you want to touch your real sessions.

## 1. The demo — safe, everything works (kitty 0.49.2)

```sh
kittymux demo          # an isolated window: its own config and state, your kitty.conf is never touched
```

It opens ten tabs. What to do in each:

| Tab | Try | You should see |
|---|---|---|
| **panes** (4 panes) | `ctrl+alt+e` | a digit drawn on every pane; press one and that pane takes focus |
| | `ctrl+alt+shift+1` … `4` | focus jumps straight to pane N (same numbers as the overlay) |
| | `ctrl+alt+shift+x`, then a digit | swap the focused pane with that one |
| | `ctrl+alt+d` | the focused pane becomes its own tab |
| | `ctrl+alt+shift+h`, then drag a pane's title bar onto the bar | the split moves into that tab (or onto empty space → its own tab); press the key again to hide titles |
| **file-refs** | `ctrl+shift+click` on `src/app.py:42:7` | your editor opens at line 42 (`$VISUAL`/`$EDITOR`); a made-up path opens nothing |
| **scrollback** (500 lines) | `ctrl+alt+PgUp` / `PgDn` | the view moves a page back / forward |
| | `ctrl+alt+Home` / `End` | oldest output / back to the live screen |
| | `ctrl+alt+[` / `]` | jump between shell prompts |
| **claude / codex / antigravity / droid / review** | look at the bar | `!` waiting, a spinner while working, `⊘` limited; the split tab shows its layout picture |
| any | `ctrl+alt+/` | the keymap overlay: **just type** to search (`pane`, `scroll`, `deck`…), arrows or wheel to scroll, **one** `esc` closes (the first `esc` clears a search), pressing `ctrl+alt+/` again also closes |
| any | `ctrl+alt+b` | the deck: hover for a live preview, `/` to search, `t` promote a pane to a tab, `a` absorb a tab as splits |

The bar itself:

- **Resize:** drag the bar's right edge. Try a fast flick and stop: the edge must land exactly under the pointer, not trail behind it. Drag with the pointer far outside the bar too — it stays captured.
- **Divider:** two hairlines side by side, a lighter one at the bar and a near-black one beside it (~4 px total).
- **Collapse:** click `«` (header) → slim rail; `»` expands. `ctrl+alt+backslash` cycles sidebar → rail → hidden.
- **Peek:** right-click a tab.
- **Cursor:** over the bar it is always a hand — kitty decides that, we cannot change it. The docked panel (`ctrl+alt+shift+b`) does show a resize cursor on its edge.

From a shell pane **inside the demo** (so the commands target the demo, not your real kitty):

```sh
kittymux screenshot            # → ~/Pictures/kittymux-<time>.png (mode 0600)
kittymux dim on                # unfocused panes dim; needs the shader-slang package. `dim off` to undo
kittymux layout pick           # fzf list of bar layouts
kittymux doctor                # install check, incl. window-manager key conflicts
```

Close the window and the demo is gone.

## 2. Your real kitties

Your running kitties keep the binary they started with. If kitty was updated while they ran (`kittymux doctor` says so), they still *are* 0.49.1 — and kittymux deliberately does not enable 0.49.2-only options there.

| Feature | In a running (old-binary) kitty | After you restart it |
|---|---|---|
| No false "finished" notifications, answered-permission fix | works (the scanner reloaded) | works |
| `ctrl+alt+e`, `ctrl+alt+shift+1..9`, scroll keys, keymap overlay | works (keys are re-read on reload) | works |
| Bar resize catching up with the pointer, two-tone divider, header fix | works (modules reload) | works |
| `kittymux` on your PATH | works | works |
| Clickable `file:line`, `kittymux dim`, `kittymux screenshot` | **off** (needs the 0.49.2 process) | works |
| Native tab-insertion drag + drop marker | **off** | works |

To restart safely: save sessions (`ctrl+alt+shift+s`), quit that kitty, start it again. Then `kittymux doctor` should have no "was updated while it was running" warning.

One thing only you can do: `kittymux hooks --install` adds `PostToolUse`/`SessionEnd` to `~/.claude/settings.json` (backup first). It makes Claude itself report "tool finished, still working" and "session ended", which is what stops a quiet screen being mistaken for "finished". `kittymux doctor` tells you when it is missing.

## If something does not work

`kittymux doctor` first. Then, for the bar: `KITTYMUX_DEBUG=1` writes drag errors to `~/.local/state/kittymux/barsize-debug.log`. A missing key is almost always the window manager: `kittymux doctor` lists chords Hyprland binds that kittymux also uses.
