# Plan 006 spike report — persistent `kitten panel` sidebar

**Status: PARTIAL (Step 1 only). Steps 2–5 need the operator to approve docking a layer-shell
surface on their live Hyprland session.**

## Step 1 — real interface (`kitten panel --help`, kitty 0.49.1)

Verbatim option names relevant to a docked sidebar:

- `--edge [=top]` (background, bottom, center, center-sized, left, none, right, top)
- `--layer [=bottom]` (background, bottom, overlay, top)
- `--lines [=1]`, `--columns [=1]`, `--margin-top/left/bottom/right [=0]`
- `--exclusive-zone [=-1]` — reserves screen space on Wayland (wlr-layer-shell); help text says it
  is ignored for `--edge` values `center`/`none`
- `--override-exclusive-zone [=no]`
- `--focus-policy [=not-allowed]` — keyboard focus behaviour (needs to allow on-demand focus for keys)
- `--hide-on-focus-loss [=no]`, `--grab-keyboard [=no]`
- `--single-instance/-1`, `--listen-on`, `--toggle-visibility`, `--start-as-hidden`, `--detach`
- `--output-name`, `--name/--os-window-tag`, `--override/-o`

Implications (from docs only, not yet observed):
- A left-docked panel with `--exclusive-zone` should make Hyprland shrink tiled windows beside it.
- `--toggle-visibility` + `--single-instance` give a show/hide keybind without respawning.
- `--focus-policy` must be relaxed for keyboard use; mouse hover/click is independent.
- The deck must target the *main* kitty's socket (a panel is a separate kitty instance) — the deck
  kitten currently talks to "the kitty it runs in"; needs a `--to` argument (small change in
  `sidebar-kit.py`'s `_rc`).

## Still to answer (need operator approval to dock a panel)

Q2 space reservation on Hyprland scrolling layout, Q3 workspace/layer behaviour + `hyprctl layers`,
Q4 hover/click inside the panel, Q5 cross-instance focus + workspace switching, Q6 idle CPU/RSS.

## Verdict

Not yet decidable. Promising on paper; needs a 30-minute supervised trial.
