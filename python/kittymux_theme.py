# kittymux theme tokens — every UI colour derives from the live kitty theme.
#
# Pure Python, plain 0xRRGGBB ints, NO kitty imports: importable from the tab
# bar (inside kitty), the sidebar kitten (separate process) and unit tests.
# Tag colours with kitty's as_rgb() ONLY at the draw call site.

import os
import re
from dataclasses import dataclass


def blend(fg: int, bg: int, w: float) -> int:
    """Mix fg over bg with weight w for fg (0 → bg, 1 → fg)."""
    w = max(0.0, min(1.0, w))
    out = 0
    for shift in (16, 8, 0):
        f, b = (fg >> shift) & 0xFF, (bg >> shift) & 0xFF
        out |= int(round(f * w + b * (1 - w))) << shift
    return out


# Tailwind-style tone scale: a shade is the base darkened toward black (500 = the base itself; 950 is nearly black) or, below 500,
# lightened toward white. Derived from the live theme's own colours, so every theme gets a matching pair, never a fixed grey.
_SHADE_TOWARD = {50: (0xFFFFFF, 0.90), 100: (0xFFFFFF, 0.80), 200: (0xFFFFFF, 0.62), 300: (0xFFFFFF, 0.40), 400: (0xFFFFFF, 0.20),
                 500: (0, 0.0), 600: (0, 0.20), 700: (0, 0.40), 800: (0, 0.60), 900: (0, 0.75), 950: (0, 0.88)}


def shade(base: int, level: int) -> int:
    """`base` at Tailwind tone `level` (50…950): 700 is a firm mid-dark, 950 close to black."""
    target, w = _SHADE_TOWARD.get(level, (0, 0.0))
    return blend(target, base, w)


def dim(rgb: int, factor: float = 0.55) -> int:
    r, g, b = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
    return (int(r * factor) << 16) | (int(g * factor) << 8) | int(b * factor)


def _lin(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(rgb: int) -> float:
    r, g, b = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a: int, b: int) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def ensure_contrast(fg: int, bg: int, minimum: float = 3.0) -> int:
    """Nudge fg away from bg (toward white on dark, black on light) until the
    WCAG contrast ratio reaches `minimum`. Unchanged if already sufficient."""
    if contrast(fg, bg) >= minimum:
        return fg
    target = 0xFFFFFF if luminance(bg) < 0.5 else 0x000000
    for step in range(1, 21):
        cand = blend(target, fg, step * 0.05)
        if contrast(cand, bg) >= minimum:
            return cand
    return target


@dataclass(frozen=True)
class Palette:
    bg: int
    fg: int
    text: int
    muted: int
    faint: int
    bar: int          # sidebar background (a step off the pane background)
    line: int         # separators between sidebar and panes
    surface: int      # hover / subtle fill
    surface_hi: int   # selected / active row fill
    accent: int
    working: int
    waiting: int      # needs the user
    done: int         # finished / unread output
    alert: int
    info: int
    border: int = 0   # the divider between sidebar and panes: kitty's own pane-border colour, so it reads as a split
    sep_700: int = 0  # the divider is two hairlines: this one (tone 700 of the theme's mid-grey) at the bar's inner edge…
    sep_950: int = 0  # …and this one (tone 950, nearly black) right next to it, towards the panes


def _parse_hex(value: str) -> int | None:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
    return int(m.group(1), 16) if m else None


def parse_kitty_colors(text: str) -> dict[str, int]:
    """Parse `kitty @ get-colors` output (`name #rrggbb` per line)."""
    out: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        val = _parse_hex(parts[1])
        if val is not None:
            out[parts[0]] = val
    return out


def from_colors(c: dict[str, int]) -> Palette:
    """Build the palette from kitty colours: keys `background`, `foreground`,
    optional `active_border_color`, `inactive_border_color`, `color1`..`color15`. Never raises."""
    fg = c.get("foreground", 0xDDDDDD)
    bg = c.get("background", 0x000000)

    def ansi(n: int, fallback: int) -> int:
        return ensure_contrast(c.get(f"color{n}", fallback), bg, 3.0)

    override = _parse_hex(os.environ.get("KITTYMUX_ACCENT", ""))
    accent = override if override is not None else c.get(
        "active_border_color", c.get("color12", fg))
    return Palette(
        bg=bg, fg=fg, text=fg,
        muted=blend(fg, bg, 0.62),
        faint=blend(fg, bg, 0.40),
        bar=blend(fg, bg, 0.05),
        line=blend(fg, bg, 0.24),
        surface=blend(fg, bg, 0.07),
        surface_hi=blend(fg, bg, 0.15),
        accent=ensure_contrast(accent, bg, 3.0),
        working=ansi(12, fg),
        waiting=ansi(11, fg),
        done=ansi(10, fg),
        alert=ansi(9, fg),
        info=ansi(12, fg),
        border=ensure_contrast(c.get("inactive_border_color", blend(fg, bg, 0.24)), bg, 1.5),
        sep_700=shade(blend(fg, bg, 0.5), 700),
        sep_950=shade(blend(fg, bg, 0.5), 950),
    )


def colors_from_options(o, background: int, as_int) -> dict[str, int]:
    """The colour dict `from_colors` wants, read from kitty's live options object `o` (inside kitty: no subprocess). `background` is the bar's
    own background (kitty's tab_bar_background or background); `as_int` turns kitty's Color into 0xRRGGBB. Never raises."""
    try:
        colors = {"background": background, "foreground": as_int(o.foreground)}
        abc = o.active_border_color
        if abc is not None:
            colors["active_border_color"] = as_int(abc)
        ibc = o.inactive_border_color
        if ibc is not None:
            colors["inactive_border_color"] = as_int(ibc)
        for n in range(1, 16):
            colors[f"color{n}"] = int(o.color_table[n]) & 0xFFFFFF
        return colors
    except Exception:
        return {}


def _hex(c: int) -> str:
    return f"#{c & 0xFFFFFF:06x}"


def fzf_args(p: Palette) -> list[str]:
    """fzf `--color` args (one per list item) matching the palette."""
    pairs = (
        ("bg", p.bg), ("bg+", p.surface_hi), ("fg", p.muted), ("fg+", p.text),
        ("hl", p.accent), ("hl+", p.accent), ("info", p.faint), ("prompt", p.info),
        ("pointer", p.accent), ("marker", p.done), ("spinner", p.waiting),
        ("header", p.faint), ("border", p.line), ("label", p.info),
        ("preview-bg", p.bar), ("preview-border", p.line),
    )
    return [f"--color={name}:{_hex(value)}" for name, value in pairs]


def palette_from_kitty(to: str | None = None) -> Palette:
    """Palette from the running kitty (`kitty @ get-colors`). `to` defaults to
    $KITTY_LISTEN_ON; on any failure returns the kitty-default palette (never raises)."""
    import subprocess
    target = to or os.environ.get("KITTY_LISTEN_ON")
    cmd = ["kitty", "@"] + (["--to", target] if target else []) + ["get-colors"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
        colors = parse_kitty_colors(out.stdout) if out.returncode == 0 else {}
    except Exception:
        colors = {}
    return from_colors(colors)


def shell_vars(p: Palette) -> str:
    """`NAME=hex` assignments (no #) for shell overlays: eval "$(… --shell)"."""
    pairs = (("C_BORDER", p.line), ("C_PATH", p.accent), ("C_BR", p.done), ("C_SEP", p.faint),
             ("C_DIR", p.info), ("C_DIM", p.faint), ("C_TXT", p.text), ("C_OK", p.done),
             ("C_WARN", p.waiting), ("C_BAD", p.alert))
    return "; ".join(f"{name}={value & 0xFFFFFF:06x}" for name, value in pairs)


def main(argv: list[str]) -> int:
    """`kitty @ get-colors | kittymux_theme.py --fzf|--shell` (colours on stdin)."""
    import sys
    if "--fzf" in argv or "--shell" in argv:
        palette = from_colors(parse_kitty_colors(sys.stdin.read()))
        print("\n".join(fzf_args(palette)) if "--fzf" in argv else shell_vars(palette))
        return 0
    print("usage: kittymux_theme.py --fzf|--shell  (reads `kitty @ get-colors` on stdin)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
