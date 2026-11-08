#!/usr/bin/env python3
"""Experimental pixel deck; run as the program of a private kitty window.

Kitty steps the working rings every few seconds; the client sleeps until input or resize.
q / Esc quits. Clicks select demo rows; they do not focus real kitty windows.
"""
import argparse
import fcntl
import importlib.util
import math
import os
import select
import signal
import struct
import sys
import termios
import time
import tty

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))
import kittymux_theme as th  # noqa: E402
import kittymux_decktransport as dt  # noqa: E402
import kittymux_switches as switches  # noqa: E402


def winsize():
    return struct.unpack("HHHH", fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, bytes(8)))


def rgba_bytes(surf):
    """Native premultiplied cairo ARGB32 to protocol straight RGBA (f=32)."""
    from PIL import Image
    surf.flush()
    return Image.frombuffer("RGBA", (surf.get_width(), surf.get_height()), bytes(surf.get_data()),
                            "raw", "BGRa" if sys.byteorder == "little" else "aRGB",
                            surf.get_stride(), 1).tobytes()


def graphics_available(out, fd):
    """Probe directly first, even without a shared filesystem."""
    out.write("\x1b_Ga=q,i=999,f=24,s=1,v=1;AAAA\x1b\\")
    out.flush()
    parser = dt.Input()
    deadline = time.monotonic() + .7
    while time.monotonic() < deadline:
        readable, _, _ = select.select([fd], [], [], max(0, deadline - time.monotonic()))
        if not readable:
            break
        data = os.read(fd, 4096)
        if not data:
            break
        for event in parser.feed(data):
            if event == ("graphics", b"i=999;OK"):
                return True
    return False


def spinner_frames(dp, pal, scale, count=None):
    """The working ring's stepped arcs (kittymux_deckpx.ring_frames); kitty plays them every STEP_MS."""
    size, surfs = dp.ring_frames(pal, scale)
    return size, [rgba_bytes(surf) for surf in surfs]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scale", type=float, default=float(os.environ.get("KITTYMUX_DECK_SCALE", "1")))
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--stats")
    ap.add_argument("--theme", help="kitty colours file; defaults to KITTYMUX_THEME")
    ap.add_argument("--animation", choices=("native", "client"), default="native")
    ap.add_argument("--transport", choices=("auto", "shm", "direct"), default="auto")
    ap.add_argument("--reduced-motion", action="store_true", help="still spinner; also honours KITTYMUX_MOTION")
    ap.add_argument("--demo-state", choices=("mixed", "idle"), default="mixed")
    ap.add_argument("--glass", type=float, default=.84, help="sheet alpha, 0 to 1; blur belongs to the compositor")
    a = ap.parse_args()
    if not math.isfinite(a.scale) or a.scale <= 0 or not math.isfinite(a.fps) or not 1 <= a.fps <= 60:
        ap.error("scale must be positive and finite; fps must be between 1 and 60")
    if not math.isfinite(a.glass) or not 0 <= a.glass <= 1:
        ap.error("glass must be between 0 and 1")
    try:
        import kittymux_deckpx as dp
    except ImportError:
        print("Pixel deck needs Python cairo, PyGObject, Pango and Rsvg; use the standard sidebar instead.")
        return
    spec = importlib.util.spec_from_file_location("deckpx_demo", os.path.join(ROOT, "tools", "deckpx-demo.py"))
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    model = demo.demo_model()
    if a.demo_state == "idle":
        for item in (*model.agents, *model.spaces):
            item.state = "idle"
    theme = a.theme or os.environ.get("KITTYMUX_THEME", "")
    with open(theme) if theme and os.path.exists(theme) else open(os.devnull) as f:
        pal = th.from_colors(th.parse_kitty_colors(f.read()))

    out, fd = sys.stdout, sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setraw(fd)
    shower = dt.Graphics(out, a.transport)
    entered = False
    wake_r = wake_w = None
    old_wakeup = old_handler = None
    frames = hovers = clicks = errors = 0
    render_ms = render_only_ms = convert_ms = 0.0
    t0 = time.monotonic()
    W = H = 0
    try:
        if not graphics_available(out, fd):
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
            print("Pixel graphics unavailable. Demo agents:")
            for ag in model.agents:
                print(f"  {ag.title}: {ag.state}")
            return
        out.write("\x1b[?1049h\x1b[?25l\x1b[?1003h\x1b[?1006h\x1b[?1016h")
        entered = True
        out.flush()
        # A signal alone does not wake select: Python retries it (PEP 475).
        wake_r, wake_w = os.pipe()
        for pipe in (wake_r, wake_w):
            os.set_blocking(pipe, False)
        old_handler = signal.signal(signal.SIGWINCH, lambda *_: None)
        old_wakeup = signal.set_wakeup_fd(wake_w)
        frame, resources, parser = dp.Frame(), dp.Resources(), dt.Input()
        motion = not a.reduced_motion and switches.enabled("motion")
        native = motion and a.animation == "native"
        size, spin_frames = spinner_frames(dp, pal, a.scale) if native else (0, [])
        hits = []
        dirty = resized = True
        while True:
            if resized:
                resized = False
                rows, cols, W, H = winsize()
                dirty = True
            animating = motion and not native and any(item.state == "working" for item in (*model.agents, *model.spaces))
            if dirty and W and H:
                hits.clear()
                t = time.perf_counter()
                frame.phase = (time.monotonic() * .9) % 1 if motion else .15
                slots = [] if native else None
                surf = dp.render(model, pal, W / a.scale, H / a.scale, a.scale, frame, glass=a.glass, hits=hits,
                                 resources=resources, spinners=slots)
                rt = time.perf_counter()
                data = rgba_bytes(surf)
                ct = time.perf_counter()
                shower.show(data, surf.get_width(), surf.get_height())
                if native:
                    positions = [(round(cx * a.scale - size / 2), round(cy * a.scale - size / 2))
                                 for cx, cy, _radius, _color in slots]
                    shower.spinner(spin_frames, size, positions, (W / cols, H / rows), dp.STEP_MS)
                render_only_ms += (rt - t) * 1000
                convert_ms += (ct - rt) * 1000
                render_ms += (time.perf_counter() - t) * 1000
                frames += 1
                dirty = False
            timeout = .03 if parser.pending == b"\x1b" else (1 / a.fps if animating else None)
            readable, _, _ = select.select([fd, wake_r], [], [], timeout)
            if not readable:
                if parser.pending == b"\x1b":
                    break
                dirty = animating
                continue
            if wake_r in readable:
                os.read(wake_r, 4096)
                resized = True
            if fd not in readable:
                continue
            data = os.read(fd, 4096)
            if not data:
                break
            for event in parser.feed(data):
                if event[0] == "key":
                    if event[1] in (b"q", b"\x03"):
                        return
                    continue
                if event[0] == "graphics":
                    if not event[1].endswith(b";OK"):
                        errors += 1
                        raise RuntimeError("kitty rejected a graphics command: " + event[1].decode(errors="replace"))
                    continue
                _, b, x, y, kind = event
                lx, ly = x / a.scale, y / a.scale
                hover = next((idx for k, idx, hx, hy, hw, hh in hits
                              if not b & 256 and k == "agent" and hx <= lx < hx + hw and hy <= ly < hy + hh), None)
                if hover != frame.hover:
                    frame.hover, dirty = hover, True
                    hovers += 1
                if kind == b"M" and b == 0 and hover is not None:
                    for i, ag in enumerate(model.agents):
                        ag.active = i == hover
                    dirty = True
                    clicks += 1
    finally:
        if entered:
            shower.close()
            out.write("\x1b[?1016l\x1b[?1006l\x1b[?1003l\x1b[?25h\x1b[?1049l")
            out.flush()
        if old_wakeup is not None:
            signal.set_wakeup_fd(old_wakeup)
        if old_handler is not None:
            signal.signal(signal.SIGWINCH, old_handler)
        for pipe in (wake_r, wake_w):
            if pipe is not None:
                os.close(pipe)
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        if a.stats:
            elapsed = time.monotonic() - t0
            with open(a.stats, "w") as f:
                f.write(f"frames={frames} seconds={elapsed:.2f} fps={frames / elapsed:.1f} "
                        f"render_ms_avg={render_ms / max(1, frames):.2f} size={W}x{H} "
                        f"paint_ms={render_only_ms / max(1, frames):.2f} convert_ms={convert_ms / max(1, frames):.2f} "
                        f"upload_bytes={shower.upload_bytes} hovers={hovers} clicks={clicks} errors={errors}\n")


if __name__ == "__main__":
    main()
