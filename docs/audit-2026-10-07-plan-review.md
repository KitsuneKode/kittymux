# Verified plan review and scope decisions

Reviewed plans 007–012 against current kittymux and installed kitty 0.49.2 on 2026-10-07. The original audit plans belong to a separate review and are preserved on main. This records implementation decisions rather than treating every proposal as a confirmed bug.

## Fixes included

- **007 / B1:** When an agent exits into a shell in a still-open pane, the authoritative scanner verdict stops identifying an agent. The journal heartbeat now removes that pane's old session key and closes its record, making recovery possible. A temporary resume-identification miss while the scanner still identifies an agent keeps the key; clearing it at every identification miss would create false closures.
- **008 / B2–B3:** Removed the unused phantom `:N:` title-suffix parser and stopped producing the unreferenced `include-tab-bar.conf` artifact. Older managed artifacts remain recognized by uninstall. Overlay Python commands use `python3` from PATH.
- **008 / B5:** Both Claude and Devin collectors can lose a file during their mtime sorting pass. Sorting now tolerates that deletion; surviving files still contribute instead of failing the entire provider.
- **009 / B4:** If `/proc` is absent, cleanup keeps pane/scan/layout state and journal liveness remains unknown rather than assuming all processes died. Positive PIDs are required. This is conservative cleanup, not a claim of macOS support.

Regression checks reproduced stale journal records, both collector sorting races, and deletion under missing `/proc`; targeted checks pass after the fixes.

## Proposals that need a different contract

**010: final autosave.** Kitty's documented global watcher `on_quit` exists and distinguishes confirmation from the confirmed quit. However, spawning a detached `sessions autosave` after confirmation races the closing remote-control socket. It cannot guarantee the advertised fresh final save. Adding an `on_quit` function to the cached watcher also does not activate it in existing processes through a config reload. Keep the existing periodic/settled autosave until a reload-safe callback can capture kitty's native session synchronously before shutdown and hand off only the rewrite/write step. Cover cancel, confirmed exit, outstanding save and restored geometry before shipping.

**011: changes diff and diagnostics bundle.** A read-only diff over the existing private checkpoint trees is feasible, but is an independent feature. Disable external diff/textconv helpers and bound output. A diagnostics bundle must use an explicit allowlist of versions, feature flags, counts and static reasons. Raw scanner output, journal commands/titles/paths, inbox text, configs and environment are inappropriate defaults; stripping terminal controls is not redaction. Neither feature is needed to repair the reported pane/panel bugs, and neither is included in this change.

**012: shell consolidation.** Keep Python for in-process kitty hooks, rendering and the existing shared modules. External remote-control clients can use other languages; Python-only is not a universal restriction on every external program. A TypeScript rewrite adds a runtime without improving the native integration. Existing shell smoke coverage should not be called nonexistent. Consolidate individual quoting/JSON-heavy paths only after characterization tests establish behavior. TypedDict improves static checking but does not validate untrusted JSON by itself; use explicit bounded parsing at affected boundaries. Avoid a sweeping state-schema migration without a demonstrated consumer failure.

## Native UX and performance choices

Pane controls use kitty's native selection, swap, rotate and equalize actions. Snapshots use native pane groups, so overlays do not add fake panes. A map appears only when it represents every pane; otherwise the count/list remains truthful. Zoomed diagrams are omitted when hidden panes would receive inconsistent numbers. Previews show the selected pane's directory and use bounded workers with stale-result guards.

The persistent panel has Agents and Usage views, theme-derived surfaces, visible navigation, quota/reset details, snapshot age, scrolling and explicit refresh. Inspecting usage or previews does not move focus. Existing management actions keep the panel open; Q or the global toggle closes it. Separate Usage windows and the original picker remain available.

Native vertical tab bars receive no idle mouse motion callbacks. Real hover previews belong in the deck/panel; the bar offers right-click Peek and keyboard Peek. Kitty's C border hit-testing checks `num_visible_windows(t) > 1`, which explains the native resize cursor only on split tabs. The single-pane bar-side grip remains usable. Do not create a fake pane or patch the installed kitty binary to force a cursor.

Cached small maps measured roughly 39 times cheaper than rebuilding them in the local microbenchmark. This is a helper benchmark, not an overall application speedup. The status scanner retains native logical screen extraction to preserve marker parity. No new timer or per-tab subprocess is added to the rendering path.

## Primary references

- [Kitty custom kittens](https://sw.kovidgoyal.net/kitty/kittens/custom/)
- [Splits layout and native actions](https://sw.kovidgoyal.net/kitty/layouts/#the-splits-layout)
- [Kitty panel](https://sw.kovidgoyal.net/kitty/kittens/panel/)
- [Kitty 0.49.2 mouse implementation](https://github.com/kovidgoyal/kitty/blob/v0.49.2/kitty/mouse.c)
- [Performance options](https://sw.kovidgoyal.net/kitty/conf/#performance-tuning)

Local verification and live application are recorded separately in the implementation plan. Xvfb verifies the persistent UI; it does not establish Wayland layer-shell placement or global WM binding behavior.
