#!/usr/bin/env python3
"""build-notify-icons.py — one PNG per agent for desktop notifications (assets/notify/<agent>.png).

A notification should wear the logo of the agent that sent it. Each icon is the agent's mark, in its
brand colour, on a dark rounded plate (readable on light and dark notification themes), drawn from the
bundled icon font. If assets/brand/mascot.png exists, a small round badge of the mascot sits in the
corner, so a notification reads "kittymux, relaying <agent>". Without it, no badge.

  tools/build-notify-icons.py            # rebuild all (needs Pillow)
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
import kittymux_agents  # noqa: E402

SIZE = 256
PLATE = (30, 30, 46)            # a dark plate, so every brand colour reads
OUT = ROOT / "assets" / "notify"
MASCOT = ROOT / "assets" / "brand" / "mascot.png"


def plate() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=SIZE // 5, fill=PLATE + (255,))
    return img


def badge(img: Image.Image) -> None:
    if not MASCOT.is_file():
        return
    d = 96
    m = Image.open(MASCOT).convert("RGBA").resize((d, d), Image.LANCZOS)
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d - 1, d - 1), fill=255)
    ring = Image.new("RGBA", (d + 12, d + 12), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, d + 11, d + 11), fill=PLATE + (255,))
    x = SIZE - d - 6
    img.alpha_composite(ring, (x - 6, x - 6))
    img.paste(m, (x, x), mask)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(ROOT / "assets" / "kittymux-icons.ttf"), 150)
    made = []
    for name, agent in sorted(kittymux_agents.AGENTS.items()):
        if ord(agent.glyph[0]) < 0xE000:               # plain-symbol fallbacks (aider, crush) have no logo
            continue
        img = plate()
        d = ImageDraw.Draw(img)
        box = d.textbbox((0, 0), agent.glyph, font=font)
        x = (SIZE - (box[2] - box[0])) // 2 - box[0]
        y = (SIZE - (box[3] - box[1])) // 2 - box[1]
        d.text((x, y), agent.glyph, font=font, fill=((agent.brand >> 16) & 255, (agent.brand >> 8) & 255, agent.brand & 255, 255))
        badge(img)
        img.save(OUT / f"{name}.png", optimize=True)
        made.append(name)
    if MASCOT.is_file():
        m = Image.open(MASCOT).convert("RGBA").resize((SIZE, SIZE), Image.LANCZOS)
        mask = Image.new("L", (SIZE, SIZE), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=SIZE // 5, fill=255)
        out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        out.paste(m, (0, 0), mask)
        out.save(OUT / "kittymux.png", optimize=True)
        made.append("kittymux")
    print(f"wrote {len(made)} icons to {OUT}: {', '.join(made)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
