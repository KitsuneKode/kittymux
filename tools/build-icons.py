#!/usr/bin/env python3
"""build-icons.py — compile assets/icons/*.svg into kittymux-icons.ttf.

Each icon lands on a Plane-16 Private-Use codepoint (U+10EA01+) so it can
never collide with Nerd Font or text glyphs. Add a row to ICONS + drop the
SVG in assets/icons/, rerun, reinstall.

Output: assets/kittymux-icons.ttf — install to ~/.local/share/fonts and
point kitty's `symbol_map` at it (install.sh does both).
"""

import re
import sys
from pathlib import Path

from fontTools import fontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path import parse_path

ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "assets" / "icons"
OUT = ROOT / "assets" / "kittymux-icons.ttf"

FAMILY = "kittymux icons"
UPM = 2048
SCALE = 0.9          # icon occupies 90% of em height — reads well in a tab
ASCENT, DESCENT = int(UPM * 0.8), -int(UPM * 0.2)

# codepoint -> svg filename (without .svg). Keep stable: append only.
ICONS = [
    (0x10EA01, "claude"),
    (0x10EA02, "openai"),      # codex CLI
    (0x10EA03, "cursor"),
    (0x10EA04, "googlegemini"),
    (0x10EA05, "opencode"),
    (0x10EA06, "amp"),
    (0x10EA07, "devin"),       # authored hexagon below
    (0x10EA08, "claudecode"),
    (0x10EA09, "anthropic"),
]

# Cognition's mark is a pointy-top hexagon — authored, 24×24 space.
DEVIN_HEXAGON = (
    "M12 2 L20.66 7 L20.66 17 L12 22 L3.34 17 L3.34 7 Z"
)


def svg_path(name: str) -> str:
    if name == "devin":
        return DEVIN_HEXAGON
    svg = (ICONS_DIR / f"{name}.svg").read_text()
    m = re.search(r'd="([^"]+)"', svg)
    if not m:
        raise SystemExit(f"no path data in {name}.svg")
    return m.group(1)


def glyph_for(path_d: str, name: str):
    """Draw an SVG path (24×24, y-down) into a TT glyph, bounds-centered
    horizontally in the advance and flipped to font y-up."""
    s = (UPM * SCALE) / 24
    base = (s, 0, 0, -s, 0, ASCENT)
    bp = BoundsPen(None)
    parse_path(path_d, TransformPen(bp, base))
    bounds = bp.bounds
    # recenter horizontally inside the UPM advance
    xoff = (UPM - (bounds[2] - bounds[0])) / 2 - bounds[0] if bounds else 0
    pen = TTGlyphPen(None)
    qpen = Cu2QuPen(pen, max_err=1.0)
    parse_path(path_d, TransformPen(qpen, (
        s, 0, 0, -s, xoff, ASCENT)))
    return pen.glyph(), (0, bounds[1], UPM, bounds[3]) if bounds else bounds


def main() -> None:
    fb = fontBuilder.FontBuilder(UPM, isTTF=True)
    order = [".notdef"] + [f"icon-{cp:x}" for cp, _ in ICONS]
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({cp: f"icon-{cp:x}" for cp, _ in ICONS})

    glyphs, metrics = {}, {}
    glyphs[".notdef"] = TTGlyphPen(None).glyph()
    metrics[".notdef"] = (0, 0)
    for cp, name in ICONS:
        gname = f"icon-{cp:x}"
        glyph, bounds = glyph_for(svg_path(name), name)
        glyphs[gname] = glyph
        lsb = int(bounds[0]) if bounds else 0
        metrics[gname] = (UPM, lsb)

    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    fb.setupNameTable({"familyName": FAMILY, "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=ASCENT, sTypoDescender=DESCENT,
                usWinAscent=ASCENT, usWinDescent=-DESCENT)
    fb.setupPost()
    fb.setupDummyDSIG()
    fb.save(OUT)
    print(f"wrote {OUT} with {len(ICONS)} icons")


if __name__ == "__main__":
    sys.exit(main())
