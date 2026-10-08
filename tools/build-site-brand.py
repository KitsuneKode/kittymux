#!/usr/bin/env python3
"""build-site-brand.py — the site's brand files, derived from the one master mascot (assets/brand/mascot.png). Never edits the master.

  python3 tools/build-site-brand.py            writes site/public/brand/* and the favicons

  mascot-cutout.webp/png   the kitten without its blue background (alpha recovered from the colour distance to the flat background, edges un-mixed so no blue fringe)
  mascot-avatar-{64,128}.png   the master, square, as an avatar tile (keeps its own blue field: this IS the app-icon look)
  favicon-32.png, favicon-64.png, apple-touch-icon.png (180), icon-192.png, icon-512.png   from the avatar
  og.png   1200x630 link-preview card: the brand's own social card, cropped (the cat grows out of the lower-left corner)

The cutout keeps the master's cropped lower-left edges: place it where an edge meets the edge of something (a window, a section), as the social card does.
Needs Pillow + numpy.
"""
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "brand" / "mascot.png"
OUT = ROOT / "site" / "public" / "brand"


def cutout(img: Image.Image, size: int) -> Image.Image:
    rgb = img.convert("RGB").resize((size, size), Image.LANCZOS)
    a = np.asarray(rgb).astype(np.float32)
    bg = np.median(np.concatenate([a[:6, :6].reshape(-1, 3), a[:6, -6:].reshape(-1, 3)]), axis=0)      # the flat field, from two top corners
    d = np.sqrt(((a - bg) ** 2).sum(axis=2))
    # fully background below LO, fully the kitten above HI; the ramp is the antialiased edge
    LO, HI = 10.0, 46.0
    alpha = np.clip((d - LO) / (HI - LO), 0.0, 1.0)
    alpha = alpha * alpha * (3 - 2 * alpha)                                                           # smoothstep
    # un-mix the edge: pixel = a*fg + (1-a)*bg  =>  fg = (pixel - (1-a)*bg) / a
    safe = np.maximum(alpha, 1e-3)[..., None]
    fg = np.clip((a - (1 - alpha)[..., None] * bg) / safe, 0, 255)
    fg = np.where(alpha[..., None] > 0.02, fg, a)
    out = np.dstack([fg, alpha * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img = Image.open(SRC)
    cut = cutout(img, 640)
    cut.save(OUT / "mascot-cutout.png", optimize=True)
    cut.save(OUT / "mascot-cutout.webp", quality=90, method=6)
    rgb = img.convert("RGB")
    for s in (64, 128):
        rgb.resize((s, s), Image.LANCZOS).save(OUT / f"mascot-avatar-{s}.png", optimize=True)
    pub = ROOT / "site" / "public"
    for name, s in (("favicon-32.png", 32), ("favicon-64.png", 64), ("apple-touch-icon.png", 180), ("icon-192.png", 192), ("icon-512.png", 512)):
        rgb.resize((s, s), Image.LANCZOS).save(pub / name, optimize=True)
    card = Image.open(ROOT / "assets" / "brand" / "social-preview.png").convert("RGB")                  # 1280x640 -> 1200x630
    w, h = card.size
    card.crop((0, 5, w, h - 5)).resize((1200, 630), Image.LANCZOS).save(pub / "og.png", optimize=True)
    print("wrote", ", ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
