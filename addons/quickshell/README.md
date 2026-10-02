# kittymux inbox for Quickshell (sample, untested)

A minimal [Quickshell](https://quickshell.org) panel showing the kittymux inbox: a badge with the unread count (red when something needs you) and a list; click an
entry to jump to that agent's window.

**Status: a sample written against kittymux's documented contract ([docs/inbox.md](../../docs/inbox.md)). Quickshell is not installed on the author's machine, so
the QML has not been run. The contract — `inbox-snapshot.json` and `kittymux inbox jump/ack` — is the supported, tested part; adjust the QML to your Quickshell version.**

```sh
quickshell -p ~/Projects/kittymux/addons/quickshell      # or copy shell.qml into ~/.config/quickshell/
```

It does three things, all through the public contract:
1. `FileView` on `$KITTYMUX_STATE/inbox-snapshot.json` (default `~/.local/state/kittymux/`), reloading when the file changes;
2. renders `events` (newest first): glyph by `severity`, `agent`, `kind`, `tab`, `body`, a countdown for `limit` events;
3. on click runs `kittymux inbox jump <id>` (focuses the window and marks it read); a small × runs `kittymux inbox ack <id>`.

Ideas that fit the same contract: a Hyprland keybind running `kittymux inbox jump` (the most pressing unread), a waybar module reading `unread`/`needs_you` from the snapshot with `jq`.
