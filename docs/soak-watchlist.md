# Soak watch-list

Use kittymux normally for two or three days before adding anything. Everything below has passed in a private test kitty on
made-up data. Only your own machine, your own agents and your own hands can confirm it. Keep this file open; tick a line when
you have seen it behave, and write down anything that felt off **at the moment it happens** (what you pressed, what you
expected, what you got).

Started: ____  ·  Rollback point if something is badly wrong: `git reset --hard 02360ac` then `kittymux upgrade`
(the commit before the panel redesign, number keys and title work).

## Every day

- [ ] **Open and close the panel from another app** with Super+N. It opens on the left edge, slides in, takes keyboard focus
  when you click it, and closing it gives the focus back to what you were doing.
- [ ] **Look at the tab list with real agents running.** Each tab reads as what it is about. Note any tab called by the wrong
  project, and any title that looks cut in an odd place.
- [ ] **A real "needs you".** When an agent asks something, the row gets the stripe, the tint and a `needs you` age. Jump to it
  with `⏎`, with a click, and with `ctrl+alt+y`. The age keeps counting.
- [ ] **A real "done".** It appears only when an agent really finished while you were elsewhere, and clears when you look.
  A false "done" or a missed "waiting" is the worst kind of bug here: write it down with the time.

## Keys (your hands will tell you)

- [ ] `ctrl+alt+1..9` focuses the pane you expect (the digits `ctrl+alt+e` draws). `ctrl+alt+0` is the last pane.
- [ ] `alt+1..9` still jumps tabs. `alt+0` is the last real tab (never the scratch tab).
- [ ] `alt+shift+h/j/k/l` resizes about three columns a press, and `alt+shift+=` makes the splits even again.
- [ ] Nothing you used to press by habit now does something surprising (note the chord if so).

## The panel with a mouse or touchpad

- [ ] Click the `▸` in front of a split tab: its panes appear. Click `▾`: they go. Hovering over rows never opens anything,
  and an agent starting to ask does not move the list under your pointer.
- [ ] The buttons under the list (`jump`, `find`, `join`, `detach`) light up under the pointer and do what their key does.
  A slightly wobbly click still works.
- [ ] `?` shows the keys of the view you are in; any key or click closes it. Try it in Agents, Usage and Inbox.
- [ ] Inbox: `x` dismisses and the footer offers `z undo` for a few seconds; `z` brings the card back.
- [ ] Usage: numbers are believable. A provider whose last report is old says `sample 3h ago`; a quota window that has already
  reset says `window reset`, not its old percentage.

## Once, when it suits you

- [ ] **Restart kitty** (not now if anything important is running). Your config edits (`allow_remote_control socket-only`, the
  socket in `$XDG_RUNTIME_DIR`) and the icon font only reach a *new* kitty. Afterwards run `kittymux doctor`: the two
  remote-control warnings should be gone, and the only warning left should be the nine `alt+N` lines you chose to keep.
- [ ] After the restart, do a quick pass of everything above once more.

## Known and not fixed

- `tests/smoke_place.sh` fails on `main` (it did before any of this work). It is the folder line under a tab; the rig reads the
  bar's dump file while it is being rewritten. It does not affect what you see.
- The `grip` branch has uncommitted work (resize-grip changes and `tests/smoke_grip.sh`). Nothing here depends on it.
- Not verified on a real compositor other than yours: the layer-shell panel on sway, river or niri.

## Where to write things down

One line each, newest at the bottom:

```
YYYY-MM-DD HH:MM · what I did · what I expected · what happened
```
