"""Small graphics/input protocol layer for the experimental pixel deck (no GUI imports)."""
import base64
import os
import re


class Input:
    def __init__(self):
        self.pending = b""

    def feed(self, data):
        self.pending += data
        events = []
        while self.pending:
            buf = self.pending
            if buf.startswith(b"\x1b_G"):
                end = buf.find(b"\x1b\\", 3)
                if end < 0:
                    break
                events.append(("graphics", buf[3:end]))
                self.pending = buf[end + 2:]
            elif buf.startswith(b"\x1b["):
                match = re.match(rb"\x1b\[<([0-9]+);([0-9]+);([0-9]+)([Mm])", buf)
                if match:
                    events.append(("mouse", *(int(match[i]) for i in (1, 2, 3)), match[4]))
                    self.pending = buf[match.end():]
                else:
                    # Consume other complete CSI sequences, retain partial mouse reports.
                    match = re.match(rb"\x1b\[[0-?]*[ -/]*[@-~]", buf)
                    if not match:
                        break
                    self.pending = buf[match.end():]
            elif buf == b"\x1b" or buf == b"\x1b_":
                break
            else:
                events.append(("key", buf[:1]))
                self.pending = buf[1:]
        if len(self.pending) > 4096:
            self.pending = b""
        return events


class Graphics:
    """An image at -2, a tiny shared spinner animation at -1. All state is per window.

    Linux SHM objects remain ours until kitty consumes them. Keep their names for
    cleanup on rejection/exit; never unlink immediately after writing the command.
    Direct transfer is portable and works when /dev/shm is unavailable.
    """
    def __init__(self, out, transport="auto"):
        self.out = out
        self.transport = ("shm" if os.path.isdir("/dev/shm") else "direct") if transport == "auto" else transport
        self.serial = 0
        self.pending = set()
        self.size = None
        self.place = None          # (col, row, z) of the root image; a size-stable update keeps it
        self.upload_bytes = 0
        self.spinner_ready = False

    def command(self, keys, payload=""):
        self.out.write(f"\x1b_G{keys};{payload}\x1b\\")

    @staticmethod
    def validate(data, w, h):
        if not (0 < w <= 10000 and 0 < h <= 10000) or len(data) != w * h * 4:
            raise ValueError("RGBA dimensions or data size are invalid")

    def upload(self, keys, data, w, h):
        self.validate(data, w, h)
        self.upload_bytes += len(data)
        header = f"{keys},f=32,s={w},v={h},q=1"
        if self.transport == "shm":
            self.pending = {p for p in self.pending if os.path.exists(p)}
            if len(self.pending) >= 128:
                raise RuntimeError("kitty has not consumed shared-memory frames")
            self.serial += 1
            name = f"/kmx-deck-{os.getpid()}-{self.serial}"
            path = "/dev/shm" + name
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_EXCL, 0o600)
            self.pending.add(path)
            try:
                view = memoryview(data)
                while view:
                    written = os.write(fd, view)
                    if not written:
                        raise OSError("short shared-memory write")
                    view = view[written:]
            finally:
                os.close(fd)
            self.command(f"{header},t=s,S={len(data)}", base64.b64encode(name.encode()).decode())
            self.out.flush()
        else:
            encoded = base64.b64encode(data).decode()
            for offset in range(0, len(encoded), 4096):
                chunk = encoded[offset:offset + 4096]
                more = int(offset + 4096 < len(encoded))
                self.command(f"{header},t=d,m={more}" if offset == 0 else f"m={more}", chunk)

    def show(self, data, w, h, col=1, row=1, z=-2):
        self.validate(data, w, h)
        place = (int(col), int(row), int(z))
        if self.size == (w, h) and self.place == place:
            # Updating root frame data preserves placements. Reusing a=T deletes
            # them first (kitty graphics.c handle_add_command).
            self.upload("a=f,i=1,r=1,X=1", data, w, h)
        else:
            if place == (1, 1, -2):
                self.out.write("\x1b[H")
            else:
                self.out.write(f"\x1b[{place[1]};{place[0]}H")
            self.upload(f"a=T,i=1,p=1,C=1,z={place[2]}", data, w, h)
            self.size = w, h
            self.place = place
        self.out.flush()

    def spinner(self, frames, size, positions, cell, gap, z=-1):
        if not frames or not positions:
            return
        if not self.spinner_ready:
            self.upload("a=t,i=10", frames[0], size, size)
            self.command(f"a=a,i=10,r=1,z={gap}")
            for frame in frames[1:]:
                self.upload(f"a=f,i=10,X=1,z={gap}", frame, size, size)
            # stopped (s=1): kitty never runs its frame loop for it. A playing animation, even with a 3 s gap, kept the panel's
            # kitty rendering continuously (about a quarter of a core under software GL); the caller steps it with `step`.
            self.command("a=a,i=10,s=1,c=1")
            self.spinner_ready = True
        self.command("a=d,d=i,i=10")  # keep frame data; replace only placements
        cw, ch = cell
        for placement, (x, y) in enumerate(positions, 1):
            col, row = int(x // cw), int(y // ch)
            self.out.write(f"\x1b[{row + 1};{col + 1}H")
            self.command(f"a=p,i=10,p={placement},C=1,z={int(z)},X={round(x - col * cw)},Y={round(y - row * ch)},q=1")
        self.out.flush()

    def step(self, frame: int) -> None:
        """Show ring frame `frame` (1-based) on every placement: one command, one repaint, no running animation."""
        if not self.spinner_ready:
            return
        self.command(f"a=a,i=10,c={max(1, int(frame))}")
        self.out.flush()

    def clear_spinner(self):
        """Drop spinner placements. The frame data stays, so the next `spinner` call does not upload it again."""
        if not self.spinner_ready:
            return
        self.command("a=d,d=i,i=10")
        self.out.flush()

    def close(self):
        for iid in (1, 10):
            self.command(f"a=d,d=I,i={iid},q=2")
        self.out.flush()
        for path in self.pending:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        self.pending.clear()
        self.spinner_ready = False
        self.size = None
        self.place = None


def rgba_of(surf) -> bytes:
    """Native premultiplied cairo ARGB32 to the protocol's straight RGBA (f=32)."""
    import sys
    from PIL import Image
    surf.flush()
    return Image.frombuffer("RGBA", (surf.get_width(), surf.get_height()), bytes(surf.get_data()),
                            "raw", "BGRa" if sys.byteorder == "little" else "aRGB",
                            surf.get_stride(), 1).tobytes()
