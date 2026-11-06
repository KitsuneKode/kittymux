#!/usr/bin/env python3
"""SPIKE: render the pixel deck to PNGs (dark/light × wide/narrow) over a blurred backdrop, and time a frame.

    tools/deckpx-demo.py OUT_DIR [--theme kitty-theme.conf] [--backdrop image] [--scale 1.333]

The backdrop is a stand-in for the compositor's blur behind a translucent kitty; it proves nothing about Hyprland.
Demo data is synthetic (no names or paths from a real machine)."""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
import kittymux_theme as th  # noqa: E402
import kittymux_deckpx as dp  # noqa: E402
from kittymux_agents import AGENTS  # noqa: E402

# A light theme for the light render (kitty's own default-ish light colours; demo input only).
LIGHT = {"background": 0xF7F7F8, "foreground": 0x2A2B30, "color9": 0xD23A3A, "color10": 0x2E9D57,
         "color11": 0xC98A00, "color12": 0x2F6FEB, "active_border_color": 0x2F6FEB, "inactive_border_color": 0xD5D6DA}


# The rigs' dark theme (tests/shot_panel.sh), so the sheet shows the state colours a real theme gives.
DARK = {"background": 0x1A1B26, "foreground": 0xC0CAF5, "color9": 0xF7768E, "color10": 0x9ECE6A, "color11": 0xE0AF68,
        "color12": 0x7AA2F7, "active_border_color": 0xF08FB8, "inactive_border_color": 0x414868}


def demo_model() -> dp.Model:
    b = lambda k: AGENTS[k].brand if k in AGENTS else 0x888888  # noqa: E731
    review = dp.Agent("pricing page review", "codex", b("codex"), "website", "2m", "working", progress=0.62, meta="#214",
                      can_open=True, opened=True, panes=2)
    review.children = [dp.Agent("tests", "claude", b("claude"), "website", state="waiting", row=1, pane=0),
                       dp.Agent("server", "shell", 0, "website", state="idle", row=1, pane=1)]
    spaces = [dp.Space("website", "main", current=True), dp.Space("core", "master"), dp.Space("plugins", "main"),
              dp.Space("service-api", "release/2.4")]
    agents = [
        dp.Agent("pricing page", "claude", b("claude"), "website", "4m", "done", current=True, meta=":3000"),
        review,
        dp.Agent("og tags", "claude", b("claude"), "website", "1m", "working", active=True),
        dp.Agent("docs nav", "claude", b("claude"), "website", "6m", "waiting"),
        dp.Agent("doc comments", "gemini", b("gemini"), "core", "8m", "working"),
        dp.Agent("migrations", "codex", b("codex"), "core", "1h", "error"),
        dp.Agent("readme", "opencode", b("opencode"), "plugins", "12m", "idle"),
        dp.Agent("service-api", "shell", 0, "service-api", "", "idle", meta=":8080"),
    ]
    for sp in spaces:
        sp.counts = dp.state_counts(a.state for a in agents if a.space == sp.name)
    return dp.Model(session="calm-otter", host="this machine", spaces=spaces, agents=agents)


def backdrop(path, w, h, dark):
    from PIL import Image, ImageFilter
    if path and os.path.exists(path):
        img = Image.open(path).convert("RGB")
        r = max(w / img.width, h / img.height)
        img = img.resize((int(img.width * r) + 1, int(img.height * r) + 1)).crop((0, 0, w, h))
        img = img.filter(ImageFilter.GaussianBlur(24))
    else:
        img = Image.new("RGB", (w, h), (40, 30, 60) if dark else (220, 225, 235))
    return img


def to_pil(surf):
    from PIL import Image
    w, h = surf.get_width(), surf.get_height()
    im = Image.frombuffer("RGBA", (w, h), bytes(surf.get_data()), "raw", "BGRa", surf.get_stride(), 1)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--theme")
    ap.add_argument("--backdrop")
    ap.add_argument("--scale", type=float, default=4 / 3)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    dark_colors = th.parse_kitty_colors(open(a.theme).read()) if a.theme else DARK
    from PIL import Image
    sheets = []
    for name, colors in (("dark", dark_colors), ("light", LIGHT)):
        pal = th.from_colors(colors)
        for width in (272, 196):
            surf = dp.render(demo_model(), pal, width, 600, a.scale, dp.Frame(hover=4, phase=0.0))
            fg = to_pil(surf)
            bg = backdrop(a.backdrop, fg.width, fg.height, name == "dark")
            # what sits behind the sidebar on screen: the blurred wallpaper under kitty's own translucent background
            bg = Image.blend(bg, Image.new("RGB", bg.size, ((pal.bg >> 16) & 255, (pal.bg >> 8) & 255, pal.bg & 255)), 0.55)
            bg.paste(fg, (0, 0), fg)
            fn = os.path.join(a.out, f"deck-{name}-{width}.png")
            bg.save(fn)
            sheets.append(bg)
            print(fn)
    # one contact sheet
    W = sum(s.width for s in sheets) + 24 * (len(sheets) + 1)
    H = max(s.height for s in sheets) + 48
    sheet = Image.new("RGB", (W, H), (24, 24, 28))
    x = 24
    for s in sheets:
        sheet.paste(s, (x, 24))
        x += s.width + 24
    sheet.save(os.path.join(a.out, "deck-sheet.png"))
    # frame budget: one full redraw at device scale (the spinner path redraws while anything works)
    pal = th.from_colors(dark_colors)
    n, t0 = 30, time.perf_counter()
    for i in range(n):
        dp.render(demo_model(), pal, 272, 900, a.scale, dp.Frame(phase=i / n))
    print(f"frame: {(time.perf_counter() - t0) / n * 1000:.1f} ms at {a.scale}x, 272x900 logical")


if __name__ == "__main__":
    main()
