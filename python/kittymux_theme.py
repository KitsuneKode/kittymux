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
    optional `active_border_color`, `color1`..`color15`. Never raises."""
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
    )


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
