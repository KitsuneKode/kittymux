#!/usr/bin/env python3
"""SPIKE: show the pixel deck in a kitty window through the graphics protocol.

Runs as the program of a kitty window (the sidebar or the panel). Renders at the window's real pixel size
(TIOCGWINSZ), ships each frame as raw RGBA through POSIX shared memory (t=s: no base64, no zlib), double-buffers
two image ids so a frame never flickers, and takes hover from SGR-pixel mouse reports (?1016) — the hover kitty's
own tab bar can never get. Redraws only on input, resize, or while a spinner turns (event-driven, not a busy loop).

    deckpx-kit.py [--scale 1.333] [--fps 30] [--stats FILE]
q / Esc quits; a click on an agent row makes it the active one (the spike does not focus kitty windows)."""
import argparse
import base64
import fcntl
import os
import re
import select
import signal
import struct
import sys
import termios
import time
import tty

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import kittymux_theme as th  # noqa: E402
import kittymux_deckpx as dp  # noqa: E402

MOUSE = re.compile(rb"\x1b\[<(\d+);(\d+);(\d+)([Mm])")


def winsize():
    rows, cols, xpx, ypx = struct.unpack("HHHH", fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0" * 8))
    return rows, cols, xpx, ypx


def rgba_bytes(surf) -> bytes:
    """cairo ARGB32 (premultiplied, native BGRA) → straight RGBA, which is what f=32 means."""
    from PIL import Image
    w, h = surf.get_width(), surf.get_height()
    return Image.frombuffer("RGBA", (w, h), bytes(surf.get_data()), "raw", "BGRa", surf.get_stride(), 1).tobytes()


class Shower:
    def __init__(self, out):
        self.out, self.n, self.live = out, 0, None

    def show(self, data: bytes, w: int, h: int):
        self.n += 1
        iid = 1 + (self.n & 1)                       # two ids: place the new frame, then drop the old one
        name = f"/kmx-deck-{os.getpid()}-{self.n}"
        fd = os.open("/dev/shm" + name, os.O_CREAT | os.O_RDWR | os.O_EXCL, 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        payload = base64.standard_b64encode(name.encode()).decode()
        # kitty reads and unlinks the shm object; C=1 keeps the cursor still, q=2 silences replies, z=-1 under text
        self.out.write(f"\x1b[H\x1b_Ga=T,f=32,t=s,s={w},v={h},S={len(data)},i={iid},p=1,C=1,q=2,z=-1;{payload}\x1b\\")
        if self.live is not None:
            self.out.write(f"\x1b_Ga=d,d=I,i={self.live},q=2\x1b\\")
        self.live = iid
        self.out.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=float(os.environ.get("KITTYMUX_DECK_SCALE", "1")))
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--stats")
    ap.add_argument("--theme", help="kitty colours file (default: the conf kitty passes through KITTYMUX_THEME)")
    a = ap.parse_args()
    import importlib.util
    spec = importlib.util.spec_from_file_location("deckpx_demo", os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "deckpx-demo.py"))
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    model = demo.demo_model()
    theme = a.theme or os.environ.get("KITTYMUX_THEME", "")
    colors = th.parse_kitty_colors(open(theme).read()) if theme and os.path.exists(theme) else {}
    pal = th.from_colors(colors)

    out = sys.stdout
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setraw(fd)
    # alt screen, no cursor, any-motion mouse in SGR *pixel* coordinates
    out.write("\x1b[?1049h\x1b[?25l\x1b[?1003h\x1b[?1006h\x1b[?1016h")
    out.flush()
    shower = Shower(out)
    resized = [True]
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    frame = dp.Frame()
    hits: list = []
    dirty, t0, frames, render_ms = True, time.monotonic(), 0, 0.0
    W = H = 0
    try:
        while True:
            if resized[0]:
                resized[0] = False
                _r, _c, W, H = winsize()
                dirty = True
            animating = any(ag.state == "working" for ag in model.agents)
            if dirty and W and H:
                hits.clear()
                t = time.perf_counter()
                frame.phase = (time.monotonic() * 0.9) % 1.0
                surf = dp.render(model, pal, W / a.scale, H / a.scale, a.scale, frame, glass=0.0, hits=hits)
                shower.show(rgba_bytes(surf), surf.get_width(), surf.get_height())
                render_ms += (time.perf_counter() - t) * 1000
                frames += 1
                dirty = False
            timeout = 1 / a.fps if animating else None
            r, _, _ = select.select([fd], [], [], timeout)
            if not r:
                dirty = animating
                continue
            data = os.read(fd, 4096)
            if data in (b"q", b"\x1b"):
                break
            for m in MOUSE.finditer(data):
                b, x, y, kind = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
                lx, ly = x / a.scale, y / a.scale
                hover = next((idx for k, idx, hx, hy, hw, hh in hits
                              if k == "agent" and hx <= lx < hx + hw and hy <= ly < hy + hh), None)
                if hover != frame.hover:
                    frame.hover, dirty = hover, True
                if kind == b"M" and b == 0 and hover is not None:     # left press on a row
                    for i, ag in enumerate(model.agents):
                        ag.active = i == hover
                    dirty = True
    finally:
        out.write("\x1b_Ga=d,d=A,q=2\x1b\\\x1b[?1016l\x1b[?1006l\x1b[?1003l\x1b[?25h\x1b[?1049l")
        out.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        if a.stats:
            el = time.monotonic() - t0
            with open(a.stats, "w") as f:
                f.write(f"frames={frames} seconds={el:.2f} fps={frames / el:.1f} "
                        f"render_ms_avg={render_ms / max(1, frames):.2f} size={W}x{H}\n")


if __name__ == "__main__":
    main()
