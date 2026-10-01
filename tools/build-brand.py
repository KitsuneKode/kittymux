#!/usr/bin/env python3
"""build-brand.py — derive the mascot's working sizes from the one master image.

  tools/build-brand.py [assets/brand/mascot.png] [--out DIR]

Writes mascot-512/256/128/64/32.png next to the master, plus two checks for the "readable at 32 px" rule:
check-32.png (the mascot at 32 px, shown at 8x so you can judge it) and check-silhouette.png (the same,
reduced to black on white — if it is not recognisable there, the shape is too detailed).
Also writes social-preview.png (1280x640, GitHub's social card) and agents-wall.png (every agent icon in assets/notify)
when those icons exist. Needs Pillow. The master is never modified.
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SIZES = (512, 256, 128, 64, 32)


def _font(style: str, size: int) -> ImageFont.FreeTypeFont:
    for family in ("JetBrains Mono", "DejaVu Sans Mono"):
        try:
            path = subprocess.run(["fc-match", f"{family}:{style}", "-f", "%{file}"], capture_output=True, text=True,
                                  timeout=5).stdout.strip()
            if path:
                return ImageFont.truetype(path, size)
        except (OSError, subprocess.SubprocessError):
            continue
    return ImageFont.load_default()


def social_preview(img: Image.Image, out: Path) -> None:
    """1280x640: the mascot on its own background (it grows out of the lower-left corner), the name and one line."""
    w, h = 1280, 640
    rgb = img.convert("RGB")
    bg = rgb.getpixel((rgb.width - 4, 4))                       # the background is solid; a top corner is pure background
    card = Image.new("RGB", (w, h), bg)
    card.paste(rgb.resize((h, h), Image.LANCZOS), (0, 0))
    d = ImageDraw.Draw(card)
    ink = rgb.getpixel((int(rgb.width * 0.12), int(rgb.height * 0.45)))     # the cream half of the face
    d.text((700, 190), "kittymux", font=_font("ExtraBold", 112), fill=ink)
    d.text((704, 330), "agent-aware workspace for kitty", font=_font("Regular", 27), fill=tuple(int(c * 0.82 + b * 0.18) for c, b in zip(ink, bg)))
    notify = sorted((ROOT / "assets" / "notify").glob("*.png"))
    keep = [p for p in notify if p.stem in ("claude", "codex", "devin", "droid", "antigravity", "gemini", "cursor", "opencode")]
    for i, p in enumerate(keep[:8]):
        icon = Image.open(p).convert("RGBA").resize((64, 64), Image.LANCZOS)
        card.paste(icon, (704 + i * 68, 430), icon)
    card.save(out, optimize=True)


def agents_wall(out: Path) -> None:
    files = sorted(p for p in (ROOT / "assets" / "notify").glob("*.png") if p.stem != "kittymux")
    if not files:
        return
    cols = 6
    rows = (len(files) + cols - 1) // cols
    cell = 160
    wall = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 0))
    for i, p in enumerate(files):
        icon = Image.open(p).convert("RGBA").resize((cell - 16, cell - 16), Image.LANCZOS)
        wall.alpha_composite(icon, ((i % cols) * cell + 8, (i // cols) * cell + 8))
    wall.save(out, optimize=True)


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
    social_preview(img, out / "social-preview.png")
    agents_wall(out / "agents-wall.png")
    print(f"wrote {', '.join(f'mascot-{s}.png' for s in SIZES)} + check-32.png, check-silhouette.png, social-preview.png, agents-wall.png to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
