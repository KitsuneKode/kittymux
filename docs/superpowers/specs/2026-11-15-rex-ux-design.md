# Rex-inspired kittymux UI

Status: approved direction (user: “okay go ahead do those”), implemented on the feature branch; qualification and review in progress.

Make the existing native pixel panel a consistent home for Agents, Usage and Inbox. Keep Kitty as the terminal and preserve the scanner, meter and inbox contracts. No new daemon, provider polling loop, automatic agent input, or live restart.

## Approach

Extend the existing Cairo/Pango graphics renderer and transport. Usage gets provider cards with explicit remaining quota, reset/pace information and the existing freshness/details data. Inbox gets summary pills, deliberate expansion to the bounded full message, keyboard and pointer parity, Jump, Dismiss and Undo. Preserve selection by event ID. Keep cell fallbacks and the existing `deckpx` switch. A second graphical client would duplicate state and retain attach-placement problems; terminal-wide cross-pane glass is outside this change.

Fix canonical IDs after inbox merges and retain unread attention in the bounded snapshot rather than allowing read history to displace it. Errors show their bodies. Expanded detail never acknowledges or focuses an agent; only Jump does. Existing mute/snooze/privacy policy remains authoritative.

Pane controls are an explicit optional Kitty 0.50 window dock, scoped to their parent pane: split right/down, zoom, move to tab and guarded close. They use the same existing actions as the CLI/keys and do not add a global chord. Older running Kitty processes get a clear unsupported result and no invalid config. Never infer version from the installed binary when acting on an existing process.

Use live theme colors, bounded caches, fixed hit regions, static feedback with motion disabled, and no high-frequency decorative animation. Collapsing the bar retains its existing attention count. Existing project/attention grouping and command palette are reused rather than duplicated.

## Acceptance

- Regression tests fail on the old error-body, merged-ID, selection and snapshot behavior, then pass.
- Pixel Usage and Inbox work in dark/light at 26 and 38 columns, including empty/error/stale/long-message states; all controls remain reachable by keyboard and pointer.
- Native graphics and direct-transfer fallback leave no retained images when switching views/quitting.
- Pane controls target their parent after focus changes, obey closeguard, and never act on another Kitty.
- All unit tests, syntax checks and applicable private rigs pass; screenshots are read. Hosted CI and compositor/provider limits are stated separately.
- Update docs and Unreleased notes with shipped behavior. PR review/CI precede integration; live changes use reload only with window-count checks.
