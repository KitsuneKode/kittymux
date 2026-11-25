# Architecture Decision Records

Non-obvious technical decisions, constraints, and trade-offs extracted from the codebase.

| ID | Title | Status | Areas |
|---|---|---|---|
| [ADR-001](ADR-001-private-sockets-and-runtime-dir.md) | Private Owned Kitty Sockets and Runtime Directory | Accepted | `lib/socket.sh`, `lib/mux.sh` |
| [ADR-002](ADR-002-geninclude-layout-and-version-gating.md) | Per-Instance Layout and Version-Gated Config via `geninclude` | Accepted | `python/kittymux_layout.py`, `install.sh` |
| [ADR-003](ADR-003-positive-evidence-agent-state.md) | Positive-Evidence Agent State Resolution | Accepted | `python/kittymux_state.py`, `integrations/opencode/kittymux-agent-state.js` |
| [ADR-004](ADR-004-pixel-bar-column-zero-shader-channel.md) | Pixel Tab Bar Column-0 Row Map and Shader Channel | Accepted | `assets/shaders/*.slang` |
| [ADR-005](ADR-005-quickshell-client-tokens-and-motion.md) | Quickshell Client Architecture, Live Theme Tokens, and Calm Motion | Accepted | `client/` |
| [ADR-006](ADR-006-keymap-parsing-and-session-focus.md) | Read-Only Keymap Parsing and Session/Hyprland Focus Contracts | Accepted | `python/kittymux_keymap.py`, `lib/mux.sh` |
