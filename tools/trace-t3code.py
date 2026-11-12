#!/usr/bin/env python3
"""trace-t3code.py — the T3 Code mark for the pixel tab bar: assets/icons/t3code.svg.

T3 Code's own app icon (the white "T3" over a night sky) with only the letters kept: the near-white pixels, the stars
dropped by size. Traced with trace-mascot.py's outline functions (pixel-edge loops, Douglas-Peucker, Chaikin).

  tools/trace-t3code.py [/usr/share/icons/hicolor/512x512/apps/t3code-nightly.png] [--preview out.png]
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("trace_mascot", ROOT / "tools" / "trace-mascot.py")
tm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tm)
N = 384
SRC = Path("/usr/share/icons/hicolor/512x512/apps/t3code-nightly.png")


def letters(img: Image.Image) -> np.ndarray:
    rgb = np.asarray(img.convert("RGB").resize((N, N), Image.LANCZOS)).astype(float)
    white = (rgb.min(axis=2) > 205)                           # the letters are near white; sky and clouds are not
    labels, n = ndimage.label(white)
    sizes = ndimage.sum(white, labels, range(1, n + 1))
    keep = np.isin(labels, [i + 1 for i, s in enumerate(sizes) if s > 400])    # stars are a few pixels
    return ndimage.gaussian_filter(keep.astype(float), 1.2) > 0.5


def main(argv):
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    rest = [a for a in argv if a != "--preview" and (preview is None or Path(a) != preview)]
    mask = letters(Image.open(Path(rest[0]) if rest else SRC))
    polys = []
    for pts in tm.loops(mask):
        if len(pts) < 24:
            continue
        far = int(np.argmax(np.hypot(*(np.array(pts, float) - np.array(pts[0], float)).T)))
        simp = tm.rdp(pts[: far + 1], 0.9)[:-1] + tm.rdp(pts[far:] + [pts[0]], 0.9)[:-1]
        if len(simp) >= 3:
            polys.append(tm.smooth(simp, rounds=2))
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    side = max(x1 - x0, y1 - y0)
    ox, oy = (side - (x1 - x0)) / 2, (side - (y1 - y0)) / 2      # centred in the square viewBox
    scale = 24.0 / side
    d = []
    for p in polys:
        q = (p - [x0 - ox, y0 - oy]) * scale
        d.append("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in q) + " Z")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><title>T3 Code</title>'
           f'<path fill-rule="evenodd" d="{" ".join(d)}"/></svg>\n')
    (ROOT / "assets" / "icons" / "t3code.svg").write_text(svg)
    print(f"wrote assets/icons/t3code.svg: {len(polys)} outlines")
    if preview is not None:
        from PIL import ImageDraw
        im = Image.new("RGB", (480, 480), "white")
        dr = ImageDraw.Draw(im)
        for p in polys:
            dr.polygon([((x - x0 + ox) * 480 / side, (y - y0 + oy) * 480 / side) for x, y in p], fill="black")
        im.save(preview)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
