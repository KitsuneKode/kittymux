# ADR-006: Read-Only Keymap Parsing and Session/Hyprland Focus Contracts

## Status
Accepted

## Date
2026-11-21

## Context
kittymux coexists with users' own kitty keybinds and Hyprland desktop shortcuts, and manages named kitty session groups across OS windows and Wayland workspaces. Silent keybind shadowing, destructive session switches, and Wayland workspace focus mismatches are common failure modes.

## Decision
- **Read-only keymap inspection (`python/kittymux_keymap.py`)**:
  - kittymux never rewrites user keybind files; it reads `kitty.conf`, its includes (excluding generated `include-tab-edge.conf` and `include-tab-bar.conf` in-order so trailing lines follow includes), and relevant Hyprland binds (stripping HyDE `[Category]` prefixes) to surface them in the keymap overlay and warn on clashes in `kittymux doctor` (where kittymux's later include silently shadows earlier user binds).
  - `# key — description` comments attach to the named chord rather than the following line; empty or decorative banner comments (`===`, `---`) reset pending descriptions so section headings do not attach to the first binding below them.
  - All config readers are pure Python and tolerant: malformed lines never raise.
- **Non-destructive session model (`lib/mux.sh`)**:
  - Sessions are named kitty session groups (`goto_session` / `session:` match) that coexist (parked/visible) in an OS window; switching or creating a session parks the current session rather than destroying it.
  - Autosave checkpoints only *verified* active saved sessions (never guessing or inventing filenames for anonymous workspaces) and runs *before* `goto_session` while the departing session is still visible (`save_as_session`'s `focused_os_window` match serializes only the visible group).
  - OS window titles mirror the active session name; clearing the title restores automatic app-driven tracking for anonymous workspaces.
  - Session creation templates load from `assets/templates/plain.kitty-session` (or user override under `~/.config/kittymux/templates/`), and Python helpers receive paths/session names as exact `argv` elements to prevent shell quoting bugs.
- **Wayland / Hyprland cross-OS-window focus (`lib/mux.sh`)**:
  - Kitty remote focus alone can leave the user on the source workspace under Wayland, and matching Hyprland clients solely by title can hit another kitty process or another OS window of the same process.
  - Focus resolution matches both this kitty's PID (from the socket peer) and a unique active-tab title, then dispatches through `python/kittymux_wmfocus.py` (which probes `hl.dsp.focus` vs `focuswindow` so Hyprland 0.57+ works alongside older releases).
- **Strict scratch tab validation (`lib/mux.sh`)**:
  - Scratch tab state validates OS window owner, title, window ID, and per-launch token against live `kitty @ ls`; legacy tab-id-only flag files are never accepted.

## Alternatives Considered

### Mutating user `kitty.conf` bindings automatically to resolve clashes
- Pros: Could prevent shadowing automatically.
- Cons: Surprises users and risks corrupting custom configs.
- Rejected: Read-only detection via `kittymux doctor` preserves user ownership.

### Focusing Hyprland windows by `pid:` alone
- Pros: No title matching needed.
- Cons: One kitty process can own multiple OS windows on different workspaces, so `pid:` focuses an arbitrary window.
- Rejected: PID + unique title + `kittymux_wmfocus.py` address dispatch is required.

## Consequences
- Kitty `.conf` / `.tpl` keybind files retain their `#` description comments as structured input for `kittymux_keymap.py` and are excluded from the code-comment linter.
- Cross-OS-window session switches and tab moves reliably follow the target window across Wayland workspaces.
