#!/usr/bin/env python3
"""font_fallback.py — metric-matched fallback @font-face for a web font, so the swap from fallback to web font does not move the text (layout shift).

  python3 tools/font_fallback.py FONT.woff2 [FALLBACK.ttf]      (fallback default: Liberation Sans, which has Arial's metrics)

Prints size-adjust / ascent-override / descent-override / line-gap-override. size-adjust is the ratio of average advance widths over English
letter frequencies (so a paragraph wraps in the same places); the vertical overrides keep the line box the same height. Needs fontTools + brotli.
"""
import subprocess
import sys

from fontTools.ttLib import TTFont

FREQ = {"e": 12.7, "t": 9.1, "a": 8.2, "o": 7.5, "i": 7.0, "n": 6.7, "s": 6.3, "h": 6.1, "r": 6.0, "d": 4.3, "l": 4.0, "c": 2.8, "u": 2.8, "m": 2.4,
        "w": 2.4, "f": 2.2, "g": 2.0, "y": 2.0, "p": 1.9, "b": 1.5, "v": 1.0, "k": 0.8, " ": 18.0}


def avg_width(font: TTFont) -> float:
    cmap, hmtx, upm = font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm
    total = sum(FREQ.values())
    return sum(hmtx[cmap[ord(c)]][0] / upm * w for c, w in FREQ.items() if ord(c) in cmap) / total


def metrics(font: TTFont):
    h, upm = font["hhea"], font["head"].unitsPerEm
    return h.ascent / upm, abs(h.descent) / upm, h.lineGap / upm


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    web = TTFont(sys.argv[1])
    path = sys.argv[2] if len(sys.argv) > 2 else subprocess.run(["fc-match", "Liberation Sans", "-f", "%{file}"], capture_output=True, text=True).stdout
    fb = TTFont(path)
    size_adjust = avg_width(web) / avg_width(fb)
    a, d, g = metrics(web)
    print(f"size-adjust: {size_adjust * 100:.2f}%;")
    print(f"ascent-override: {a / size_adjust * 100:.2f}%;")
    print(f"descent-override: {d / size_adjust * 100:.2f}%;")
    print(f"line-gap-override: {g / size_adjust * 100:.2f}%;")
    return 0


if __name__ == "__main__":
    sys.exit(main())
