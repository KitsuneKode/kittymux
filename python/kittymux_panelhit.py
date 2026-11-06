"""Pure hit-testing for the docked panel body (row 0–1 are header + tab strip).

Body content lines map to screen rows starting at ``BODY_TOP`` (2). Scroll moves
which lines appear there; clicks on screen rows 0–1 must never act on body items
that scrolled off above the visible window."""
from __future__ import annotations

BODY_TOP = 2


def line_to_screen_y(line_y: int, scroll: int) -> int:
    return line_y - scroll + BODY_TOP


def screen_to_line_y(screen_y: int, scroll: int) -> int:
    return screen_y - BODY_TOP + scroll


def hit_body_lines(y: int, scroll: int, line_y0: int, line_y1: int) -> bool:
    """Half-open line interval, any column in the body."""
    if y < BODY_TOP:
        return False
    ly = screen_to_line_y(y, scroll)
    return line_y0 <= ly < line_y1


def hit_in_body(x: int, y: int, scroll: int, x0: int, x1: int, line_y0: int, line_y1: int) -> bool:
    """``line_y1`` is exclusive (half-open interval), like view region tuples."""
    if y < BODY_TOP:
        return False
    ly = screen_to_line_y(y, scroll)
    return x0 <= x < x1 and line_y0 <= ly < line_y1


def hit_body_row(x: int, y: int, scroll: int, x0: int, x1: int, line_y: int) -> bool:
    sy = line_to_screen_y(line_y, scroll)
    return y >= BODY_TOP and y == sy and x0 <= x < x1


def screen_span_for_lines(line_y0: int, line_y1: int, scroll: int) -> tuple[int, int] | None:
    """Clip a body line range to screen rows that are inside the body. ``line_y1`` exclusive."""
    sy0 = line_to_screen_y(line_y0, scroll)
    sy1 = line_to_screen_y(line_y1, scroll)
    if sy1 <= BODY_TOP:
        return None
    return max(BODY_TOP, sy0), sy1
