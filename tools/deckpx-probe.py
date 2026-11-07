#!/usr/bin/env python3
"""Private X11 deck probe. Run under a user/mount namespace with a fresh /tmp.

Example: unshare -rm sh -c 'mount -t tmpfs -o size=1g tmpfs /tmp && python3 tools/deckpx-probe.py OUT'
Only the newly-created kitty socket is contacted. No installed config is loaded.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess as sp
import time
import tempfile


def run(*args, **kw):
    return sp.check_output(args, text=True, **kw).strip()


def ticks(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return int(fields[11]) + int(fields[12])


def other_children():
    # Do not send even read-only remote-control requests to a live kitty. Count
    # its direct children instead; this is a process tripwire, not a window API.
    ans = {}
    for p in Path("/proc").glob("[0-9]*"):
        try:
            if (p / "comm").read_text().strip() == "kitty":
                children = (p / "task" / p.name / "children").read_text().split()
                # Background helpers are transient; a window's foreground child
                # has a controlling tty. Only compare that count.
                count = 0
                for pid in children:
                    try:
                        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
                        count += int(fields[4]) != 0
                    except OSError:
                        pass
                ans[int(p.name)] = count
        except (OSError, ProcessLookupError):
            pass
    return ans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--label", default="before")
    ap.add_argument("--kit-arg", action="append", default=[])
    ap.add_argument("--case", action="append", default=[])
    ap.add_argument("--video", action="store_true", help="sample spinner pixels at 60 Hz for two seconds")
    ap.add_argument("--exit-key", choices=("q", "Escape"), default="q")
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = a.out.resolve() / a.label
    out.mkdir(parents=True, exist_ok=True)
    before = other_children()
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith(("KITTY", "WAYLAND", "HYPR")):
            env.pop(key)
    env.update(LIBGL_ALWAYS_SOFTWARE="1", __GLX_VENDOR_LIBRARY_NAME="mesa")
    rfd, wfd = os.pipe()
    xvfb = sp.Popen(["Xvfb", "-displayfd", str(wfd), "-screen", "0", "1200x1000x24", "-nolisten", "tcp"],
                    pass_fds=(wfd,), stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    os.close(wfd)
    env["DISPLAY"] = ":" + os.read(rfd, 32).decode().strip()
    os.close(rfd)
    results = []
    try:
        for theme, width in (("dark", 363), ("light", 363), ("dark", 261), ("light", 261)):
            if a.case and f"{theme}-{width}" not in a.case:
                continue
            case = out / f"{theme}-{width}"
            case.mkdir(exist_ok=True)
            # Socket paths are limited to about 107 bytes. Artifact paths can be long.
            runtime = Path(tempfile.mkdtemp(prefix="deckpx-run-"))
            conf = case / "theme.conf"
            conf.write_text("background #1a1b26\nforeground #c0caf5\n" if theme == "dark" else
                            "background #eff1f5\nforeground #4c4f69\ncolor10 #40a02b\ncolor11 #df8e1d\ncolor12 #1e66f5\n")
            case_env = dict(env, XDG_RUNTIME_DIR=str(runtime), KITTYMUX_SOCKET_DIRS=str(runtime),
                            KITTYMUX_STATE=str(case / "state"), XDG_CONFIG_HOME=str(case / "config"),
                            XDG_CACHE_HOME=str(case / "cache"), XDG_DATA_HOME=str(case / "data"))
            sock = "unix:" + str(runtime / "sock")
            log = open(case / "kitty.log", "w")
            kitty = sp.Popen(["kitty", "--config", "NONE", "--class", "kmx-deckpx-probe", "--listen-on", sock,
                              "-o", "allow_remote_control=socket-only", "-o", "linux_display_server=x11",
                              "-o", "confirm_os_window_close=0", "-o", "window_padding_width=0",
                              "-o", "remember_window_size=no", "-o", f"initial_window_width={width}",
                              "-o", "initial_window_height=800", "-o", "cursor_blink_interval=0",
                              "-o", f"include={conf}", "python3", str(root / "bin/deckpx-kit.py"),
                              "--scale", str(4 / 3), "--theme", str(conf), "--stats", str(case / "stats.txt"),
                              *a.kit_arg], env=case_env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if (runtime / "sock").exists() or kitty.poll() is not None:
                        break
                    time.sleep(.1)
                rc = lambda *args: run("kitty", "@", "--to", sock, *args, env=case_env)
                wid = run("xdotool", "search", "--class", "kmx-deckpx-probe", env=case_env).splitlines()[0]
                x = lambda *args: run("xdotool", *map(str, args), env=case_env)
                x("windowsize", wid, width + 1, 800)
                x("windowsize", wid, width, 800)
                time.sleep(1)
                child = json.loads(rc("ls"))[0]["tabs"][0]["windows"][0]["pid"]
                sample = (ticks(kitty.pid), ticks(child), time.monotonic())
                time.sleep(4)
                elapsed = time.monotonic() - sample[2]
                hz = os.sysconf("SC_CLK_TCK")
                cpu = [(ticks(p) - old) / hz / elapsed * 100 for p, old in zip((kitty.pid, child), sample[:2])]
                changes = None
                if a.video:
                    raw = sp.check_output(["ffmpeg", "-v", "error", "-f", "x11grab", "-framerate", "60",
                                           "-video_size", "1200x1000", "-i", env["DISPLAY"], "-t", "2",
                                           "-vf", "crop=24:24:316:158", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], env=case_env)
                    frames = [raw[i:i + 1728] for i in range(0, len(raw), 1728)]
                    changes = sum(left != right for left, right in zip(frames, frames[1:]))
                    (case / "spinner.rgb").write_bytes(raw)
                shot = lambda name: run("import", "-window", wid, str(case / f"{name}.png"), env=case_env)
                shot("normal")
                x("mousemove", "--window", wid, 100, 442)
                time.sleep(.25)
                shot("hover")
                x("click", 1)
                time.sleep(.25)
                shot("click")
                x("windowsize", wid, 300, 720)
                time.sleep(.3)
                shot("resize")
                x("windowfocus", wid)
                x("key", a.exit_key)
                kitty.wait(timeout=10)
                result = dict(theme=theme, width=width, seconds=elapsed, kitty_cpu=cpu[0], client_cpu=cpu[1],
                              spinner_changes_2s=changes,
                              stats=(case / "stats.txt").read_text().strip())
                results.append(result)
                print(json.dumps(result), flush=True)
                if "errors=" in result["stats"]:
                    fields = dict(pair.split("=", 1) for pair in result["stats"].split())
                    assert fields["errors"] == "0", "graphics errors"
                    assert int(fields["hovers"]) >= 1 and int(fields["clicks"]) == 1, "mouse input was not delivered"
                    assert int(fields["frames"]) >= 4, "idle resize failed to redraw"
            finally:
                if kitty.poll() is None:
                    kitty.terminate()
                    kitty.wait(timeout=10)
                log.close()
                (runtime / "sock").unlink(missing_ok=True)
                # Kitty can create other private runtime files; leave only these,
                # in the namespace that disappears when the rig finishes.
        after = other_children()
        assert all(after.get(pid) == count for pid, count in before.items()), "other kitty process counts changed"
        (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print("Other kitty child-count tripwire unchanged", flush=True)
    finally:
        xvfb.terminate()
        xvfb.wait(timeout=10)


if __name__ == "__main__":
    main()
