# Draft: a resize pointer for a tab bar edge in a single-window tab

Status: **a draft for the kitty issue tracker, not filed.** It records what kittymux found in kitty 0.49.2 so the request can be made with evidence. See also the roadmap entry *The resize arrow on the bar edge of a single-pane tab* (`docs/developer/roadmap.mdx`).

## Title

Resize pointer over a custom divider when a tab has one window

## What I am building

A vertical tab bar (a `tab_bar.py` drawing a left-hand sidebar) with a draggable inner edge. On kitty 0.49.2 I draw the divider with two `Border` rects added through a wrapper around `kitty.borders.set_borders_rects`, plus one invisible hit rect (`border_type` set to the id of a window), and I answer `Boss.drag_resize_start`, `drag_resize_update` and `drag_resize_end` for it. In a tab with two or more windows this is excellent: the pointer over the divider is the native resize cursor and the drag is kitty's own.

## What happens with one window

In a tab with a single visible window the pointer over the same divider is not a resize cursor, and a press does not reach `drag_resize_start`. Reading `kitty/mouse.c` at v0.49.2:

1. `mouse_region()` only looks at a tab's border rects inside `if (detect_borders && num_visible_windows(t) > 1)` (line 1032). With one visible window the loop over `t->border_rects` never runs, so no `window_border` is reported and no resize shape is chosen.
2. Over the tab bar region itself, `update_mouse_pointer_shape()` (line 1161) and `mouse_event()` (line 1423) always set `POINTER_POINTER`, so a custom edge drawn inside the bar cannot show a resize cursor either. Python draw code has no hook for the shape.
3. A window's pointer shape comes from the program (OSC 22) or `default_pointer_shape`. It is per window, not per position, so a pane cannot show a different cursor over a strip of its own padding.

## Request, either of

- **A.** Run the border hit test when the tab has border rects with a non-zero `border_type`, not only when `num_visible_windows(t) > 1`.
- **B.** A supported way for tab bar drawing code to say "the pointer over this rectangle of the bar is shape X" (for example a method on the tab bar object that kitty calls with the pointer position, or a returned region list).

Either would let a custom sidebar offer the same native resize affordance in every tab, not only in tabs that happen to be split.

## Notes for the report

- `set_borders_rects` is not a public interface. A supported hook for extra border or hit rects would make this robust across releases.
- Repro for the current behaviour: kittymux `tests/smoke_native.sh` reads the real X cursor name over the divider in a split tab (a resize cursor) and in a single-pane tab (not a resize cursor).
- Checked against kitty 0.49.2 only.
