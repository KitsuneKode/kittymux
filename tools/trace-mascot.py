#!/usr/bin/env python3
"""trace-mascot.py — turn the mascot into a single-colour glyph: assets/icons/kittymux.svg.

The mascot's silhouette (everything that is not the flat background), with its eyes and smile cut out, traced to a
smooth outline. tools/build-icons.py then puts it in the icon font, so the tab bar can draw the mascot as text.
Needs numpy, scipy and Pillow. No external tracer: the outline is found by following pixel edges, simplified
(Douglas-Peucker) and rounded (Chaikin corner cutting).

  tools/trace-mascot.py [assets/brand/mascot.png] [--preview out.png]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
N = 384                      # working resolution


def masks(img: Image.Image):
    rgb = np.asarray(img.convert("RGB").resize((N, N), Image.LANCZOS)).astype(float)
    bg = rgb[4, N - 5]                                                # top-right corner: pure background
    body = np.linalg.norm(rgb - bg, axis=2) > 38
    body = ndimage.binary_fill_holes(ndimage.binary_opening(body, iterations=2))
    lab, n = ndimage.label(body)
    if n > 1:
        body = lab == (1 + int(np.argmax(ndimage.sum(body, lab, range(1, n + 1)))))
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    local = ndimage.gaussian_filter(lum, 22)
    feature = (lum < local - 20) & body                               # small, darker than their surroundings: eyes, smile
    ys = np.arange(N)[:, None]
    feature &= ys < N * 0.72                                          # the face, not the shading of the body
    feature = ndimage.binary_opening(feature, iterations=1)
    lab, n = ndimage.label(feature)
    keep = np.zeros_like(feature)
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if (lab[sl] == i).sum() >= 60 and not (h > 2.5 * w and h > 60):      # not the long seam between the two face colours
            keep |= lab == i
    keep = ndimage.binary_dilation(keep, iterations=1)
    return body, keep


def loops(mask: np.ndarray):
    """Closed boundary loops of a binary mask, as lists of (x, y) pixel-corner points (inside on the left)."""
    h, w = mask.shape
    m = np.pad(mask, 1)
    edges = {}
    for y in range(1, h + 1):
        for x in range(1, w + 1):
            if not m[y, x]:
                continue
            X, Y = x - 1, y - 1
            if not m[y - 1, x]:
                edges[(X, Y)] = (X + 1, Y)           # top edge, left to right
            if not m[y, x + 1]:
                edges[(X + 1, Y)] = (X + 1, Y + 1)   # right edge, downwards
            if not m[y + 1, x]:
                edges[(X + 1, Y + 1)] = (X, Y + 1)   # bottom edge, right to left
            if not m[y, x - 1]:
                edges[(X, Y + 1)] = (X, Y)           # left edge, upwards
    out = []
    while edges:
        start = next(iter(edges))
        pts, cur = [start], edges.pop(start)
        while cur != start:
            pts.append(cur)
            cur = edges.pop(cur)
        out.append(pts)
    return out


def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    a, b = np.array(pts[0], float), np.array(pts[-1], float)
    d = b - a
    norm = np.hypot(*d) or 1.0
    dist = [abs(d[0] * (p[1] - a[1]) - d[1] * (p[0] - a[0])) / norm for p in pts[1:-1]]
    i = int(np.argmax(dist)) + 1
    if dist[i - 1] > eps:
        return rdp(pts[: i + 1], eps)[:-1] + rdp(pts[i:], eps)
    return [pts[0], pts[-1]]


def smooth(pts, rounds=3):
    p = np.array(pts, float)
    for _ in range(rounds):
        nxt = np.roll(p, -1, axis=0)
        q = np.empty((len(p) * 2, 2))
        q[0::2], q[1::2] = 0.75 * p + 0.25 * nxt, 0.25 * p + 0.75 * nxt
        p = q
    return p


def area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def main(argv):
    preview = Path(argv[argv.index("--preview") + 1]) if "--preview" in argv else None
    rest = [a for a in argv if a != "--preview" and (preview is None or Path(a) != preview)]
    src = Path(rest[0]) if rest else ROOT / "assets" / "brand" / "mascot.png"
    body, holes = masks(Image.open(src))
    final = ndimage.gaussian_filter((body & ~holes).astype(float), 1.6) > 0.5
    polys = []
    for pts in loops(final):
        if len(pts) < 24:
            continue
        # simplify an open copy of the loop, close it, then round it
        far = int(np.argmax(np.hypot(*(np.array(pts, float) - np.array(pts[0], float)).T)))      # a closed loop: split it first
        simp = rdp(pts[: far + 1], 1.1)[:-1] + rdp(pts[far:] + [pts[0]], 1.1)[:-1]
        if len(simp) >= 3:
            polys.append(smooth(simp))
    polys.sort(key=lambda p: -abs(area(p)))
    ys, xs = np.nonzero(final)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    scale = 24.0 / max(x1 - x0, y1 - y0)
    d = []
    for i, p in enumerate(polys):
        # the outline runs one way, every hole the other, so nonzero fill leaves the holes empty
        outer = i == 0
        want_positive = True if outer else False
        if (area(p) > 0) != want_positive:
            p = p[::-1]
        q = (p - [x0, y0]) * scale
        d.append("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in q) + " Z")
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><title>kittymux</title><path d="{" ".join(d)}"/></svg>\n'
    (ROOT / "assets" / "icons" / "kittymux.svg").write_text(svg)
    print(f"wrote assets/icons/kittymux.svg: {len(polys)} outlines (1 body + {len(polys) - 1} cut-outs), {sum(len(p) for p in polys)} points")
    if preview is not None:
        from PIL import ImageDraw
        out = preview
        im = Image.new("RGB", (480, 480), "white")
        dr = ImageDraw.Draw(im)
        for i, p in enumerate(polys):
            q = [((x - x0) * 480 / max(x1 - x0, y1 - y0), (y - y0) * 480 / max(x1 - x0, y1 - y0)) for x, y in p]
            dr.polygon(q, fill="black" if i == 0 else "white")
        im.save(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
