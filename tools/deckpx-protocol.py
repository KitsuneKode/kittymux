#!/usr/bin/env python3
"""Exercise the installed kitty C parser without contacting any running kitty.

Run: kitty +runpy 'import runpy,sys; runpy.run_path(sys.argv[1], run_name="__main__")' tools/deckpx-protocol.py
Set XDG_CACHE_HOME to a private writable directory (kitty's graphics disk cache).
This proves parser/storage semantics, not GPU presentation or compositor behavior.
"""
import base64
import json
import os
from pathlib import Path

from kitty.fast_data_types import Screen


def main():
    screen = Screen(None, 24, 80)

    def parse(data):
        if isinstance(data, str):
            data = data.encode()
        view = screen.test_create_write_buffer()
        screen.test_commit_write_buffer(data, view)
        screen.test_parse_written_data()

    def command(keys, data=b""):
        parse(f"\x1b_G{keys};{base64.b64encode(data).decode()}\x1b\\")

    def image(i=42):
        return screen.grman.image_for_client_id(i)

    pixel = bytes((255, 0, 0, 128))
    command("a=T,i=42,p=1,f=32,s=1,v=1,z=-1", pixel)
    assert image()["refs.count"] == 1 and image()["data"] == pixel
    command("a=f,i=42,r=1,X=1,f=32,s=1,v=1", bytes((0, 255, 0, 255)))
    assert image()["refs.count"] == 1
    command("a=t,i=42,f=32,s=1,v=1", pixel)
    assert image()["refs.count"] == 0
    command("a=p,i=42,p=1,z=-1")
    assert image()["refs.count"] == 1
    command("a=f,i=42,f=32,s=1,v=1,z=33", bytes((0, 0, 255, 255)))
    assert len(image()["extra_frames"]) == 1
    command("a=c,i=42,r=2,c=1,w=1,h=1,C=1")
    assert image()["data"] == bytes((0, 0, 255, 255))
    command("a=a,i=42,r=1,z=33,s=3,v=1")
    assert image()["animation_state"] == 3

    shm = Path(f"/dev/shm/kmx-probe-{os.getpid()}")
    try:
        shm.write_bytes(pixel)
        command("a=t,i=43,t=s,f=32,s=1,v=1,S=4", ("/" + shm.name).encode())
        assert image(43)["data"] == pixel and not shm.exists()
        # Failed reads are also unlinked once opened; dimension validation happens first.
        shm.write_bytes(b"x")
        command("a=t,i=44,t=s,f=32,s=1,v=1,S=4,q=2", ("/" + shm.name).encode())
        assert not shm.exists()
        shm.write_bytes(pixel)
        command("a=t,i=45,t=s,f=32,s=10001,v=1,S=4,q=2", ("/" + shm.name).encode())
        assert shm.exists()
    finally:
        shm.unlink(missing_ok=True)

    command("a=T,i=46,U=1,c=2,r=1,f=32,s=1,v=1", pixel)
    placeholder = "\U0010eeee\u0305\u0305\U0010eeee\u0305\u030d"
    parse("\x1b[2;1H\x1b[38;5;46m" + placeholder + "\x1b[39m")
    assert "\U0010eeee" in str(screen.line(1))
    # A real text scroll carries the placeholder line with it.
    parse("\x1b[24;1H\n")
    assert "\U0010eeee" in str(screen.line(0))
    assert image(46)["refs.count"] == 1
    parse("\x1b[5;1H\x1b]66;s=2;Heading\x1b\\")
    assert screen.cursor.x == 14  # seven letters occupy fourteen columns
    print(json.dumps(dict(shared_memory_unlinked=True, failed_read_unlinked=True,
                          rejected_dimensions_need_client_cleanup=True, root_frame_preserves_placement=True,
                          retransmit_drops_placement=True, replacement_placement=True,
                          compose=True, animation_state=3, placeholders_scroll=True,
                          osc66_columns=screen.cursor.x, storage_limit=screen.grman.storage_limit), indent=2))


if __name__ == "__main__":
    main()
