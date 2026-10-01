#!/usr/bin/env python3
"""build-brand.py — derive the mascot's working sizes from the one master image.

  tools/build-brand.py [assets/brand/mascot.png] [--out DIR]

Writes mascot-512/256/128/64/32.png next to the master, plus two checks for the "readable at 32 px" rule:
check-32.png (the mascot at 32 px, shown at 8x so you can judge it) and check-silhouette.png (the same,
reduced to black on white — if it is not recognisable there, the shape is too detailed).
Needs Pillow. The master is never modified.
"""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SIZES = (512, 256, 128, 64, 32)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else None
    if out is not None and out.as_posix() in args:
        args.remove(out.as_posix())
    src = Path(args[0]) if args else ROOT / "assets" / "brand" / "mascot.png"
    if not src.is_file():
        print(f"no master image at {src} — generate one with docs/brand/mascot-prompts.md first", file=sys.stderr)
        return 1
    out = out or src.parent
    out.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGBA")
    if img.width != img.height:
        print(f"warning: the master is {img.width}x{img.height}; square is expected", file=sys.stderr)
        side = min(img.size)
        img = img.crop(((img.width - side) // 2, (img.height - side) // 2, (img.width + side) // 2, (img.height + side) // 2))
    for s in SIZES:
        img.resize((s, s), Image.LANCZOS).save(out / f"mascot-{s}.png", optimize=True)
    small = img.resize((32, 32), Image.LANCZOS)
    small.resize((256, 256), Image.NEAREST).save(out / "check-32.png")
    # silhouette = what differs from the background (the corner opposite the mascot is pure background)
    rgb = small.convert("RGB")
    bg = rgb.getpixel((0, 0)) if rgb.getpixel((0, 0)) == rgb.getpixel((31, 0)) else rgb.getpixel((31, 0))   # a top corner is background
    mask = Image.new("L", (32, 32), 255)
    for y in range(32):
        for x in range(32):
            if sum(abs(a - b) for a, b in zip(rgb.getpixel((x, y)), bg)) > 60:
                mask.putpixel((x, y), 0)
    mask.resize((256, 256), Image.NEAREST).save(out / "check-silhouette.png")
    print(f"wrote {', '.join(f'mascot-{s}.png' for s in SIZES)} + check-32.png, check-silhouette.png to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
