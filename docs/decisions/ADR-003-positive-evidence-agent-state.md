# ADR-003: Positive-Evidence Agent State Resolution

## Status
Accepted

## Date
2026-11-21

## Context
Terminal coding agents expose inconsistent status signals: some emit hooks (Claude Code, OpenCode), some draw TUI footers and permission dialogs (Claude, Codex, Devin, Cursor Agent, Antigravity, Gemini, Amp, Droid), and others only update window titles. Treating silence as "waiting" produces constant false alerts while an agent is thinking or finished, and quoted prompt text in scrollback can masquerade as a live dialog.

## Decision
- **Single ordered resolver (`python/kittymux_state.py`)**: Every UI surface consumes the single resolved verdict with priority `limited > waiting > error > working > done > idle`.
- **Positive evidence only**: Silence never implies `waiting`. `done` means *unseen* completion and clears to `idle` as soon as the pane is focused. Usage/quota exhaustion (`limited`) is distinct from `waiting`.
- **Bottom-of-screen tail classification (`_TAIL_LINES = 14`)**: Only the bottom 14 non-empty lines are scanned for `SCREEN_AGENTS`, where live footers and prompts render.
  - For `waiting`, scan top-to-bottom so a prompt's question above its options is captured as the reason; for `limited`/`working`, scan bottom-to-top for the most recent live status line.
  - Strip box borders/quote bars (`_BOX`), skip menu chrome (`_HINT_RE`, `_OPTION_RE`) unless a numbered line ends in `?`, and join wrapped question lines starting with lowercase text so notifications display the actual question rather than `"Enter to select"`.
- **Stale-output suppression**:
  - Agents that swap their input placeholder when idle (e.g., Devin's `"Ask Devin to build features"` vs `"Guide Devin while it works"`) or draw idle-only footers (Antigravity's `"? for shortcuts"`, OpenCode's `"Build · ... OpenCode ·"`) invalidate any `working` or `waiting` text printed *above* that idle composer unless explicit dialog chrome (`_DIALOG_CHROME_RE`) appears at or below the match.
  - Any `limited` or `waiting` match with a live `working` marker *below* it (and no dialog chrome) is treated as stale scrollback.
- **Debounce and hook-lifecycle windows**:
  - `_MARKER_GRACE = 1.5s`: bridges one-frame TUI repaint gaps.
  - `_HOOK_GRACE = 4.0s`: holds hook-reported `working` before the TUI draws its first spinner.
  - `_TITLE_FRESH = 6.0s`: fallback busy signal for non-screen agents.
  - `_HOOK_DONE_FRESH = 30.0s`: ignores stale `done`/idle hook user vars that outlive a previous agent run.
  - `_TURN_ABANDONED = 180.0s`: clears a hook-announced turn if interrupted (e.g., Esc fires no Stop hook) and quiet for 3 minutes.
  - `_HOOK_WAIT_FRESH = 300.0s`: bounds hook-only `waiting` when no prompt appears on screen.
- **Hook turn ownership & idle notices**:
  - When a hook announces a turn (`UserPromptSubmit`), only a `Stop` hook marks completion — screen silence between tool calls does not infer `done` (`done_source = "agent"` vs inferred `"screen"`).
  - Resumed work records `handled_wait_ts` so an already-answered hook permission prompt does not re-trigger `waiting`.
  - Claude's ~60s idle notification (`"waiting for your input"`) is excluded by `is_request()` so idleness never becomes a permanent `waiting` alert; when no completion was reported yet, it acts as an unseen `done` notice.
- **OpenCode plugin isolation (`integrations/opencode/kittymux-agent-state.js`)**:
  - Reports through `bin/mux-status` only when `KITTY_WINDOW_ID` is set; all spawn/reporting errors are swallowed so kittymux can never block or crash OpenCode.
  - Permission prompts are phrased as `"Allow <what>?"` so `is_request()` classifies them as needing attention.
  - Subagent sessions (`childSessions`) do not override the parent pane's working/done state, but their `permission.asked` and `question.asked` events still surface as `waiting`.

## Alternatives Considered

### Treating terminal silence after a timeout as "waiting"
- Pros: Requires no per-agent TUI patterns.
- Cons: Fires constantly while models think or after a user simply leaves an idle prompt open.
- Rejected: Destroys trust in notifications and the inbox.

### Per-surface state heuristics (bar, panel, inbox each resolving independently)
- Pros: Decoupled consumers.
- Cons: Surfaces disagree on whether a pane is working, waiting, or done.
- Rejected: `kittymux_state.resolve` is the sole resolver.

## Consequences
- New agent TUIs must be verified against live captures before adding screen regexes (`docs/agents/status-contract.md`).
- Every verdict carries a static `why` string for `kittymux explain` without causing churn in published state files.
