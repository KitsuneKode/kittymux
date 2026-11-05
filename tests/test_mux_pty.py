"""The relay end to end, in a pseudo-terminal this test owns (no kitty involved, nothing else touched)."""
import base64
import os
import pty
import select
import signal
import sys
import time
import unittest
from pathlib import Path

RELAY = str(Path(__file__).resolve().parent.parent / "bin" / "mux-pty")

CHILD = r'''
import os, select, sys, termios, tty
tty.setraw(0)
os.write(1, b"\x1b]7501;?\x1b\\\x1b[c")
got = b""
while select.select([0], [], [], 2)[0]:
    got += os.read(0, 1024)
    if got.endswith(b"\x1b\\"):
        break
os.write(1, b"reply=" + got.hex().encode() + b"\r\n")
os.write(1, b"\x1b]7501;state=blocked:kind=question:msg=UHJvY2VlZD8\x07")
os.write(1, "café ✓\r\n".encode())
import time; time.sleep(0.3)                       # a separate read: each report replaces the root record
os.write(1, b"\x1b]7501;state=done\x1b\\")
sys.exit(3)
'''


def run_under_pty(argv, seconds=6.0):
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp(argv[0], argv)
    out = b""
    end = time.time() + seconds
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    grace_end = time.monotonic() + 5
    while True:
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            break
        if time.monotonic() >= grace_end:
            os.kill(pid, signal.SIGKILL)
            _, status = os.waitpid(pid, 0)
            break
        time.sleep(0.05)
    return out, os.waitstatus_to_exitcode(status)


class RelayTests(unittest.TestCase):
    def test_probe_reply_passthrough_user_var_and_exit_code(self):
        out, code = run_under_pty([sys.executable, RELAY, "--", sys.executable, "-c", CHILD])
        self.assertEqual(code, 3)                                         # the command's own status
        reply = bytes.fromhex(out.split(b"reply=")[1].split(b"\r\n")[0].decode())
        self.assertTrue(reply.startswith(b"\x1b]7501;?"), reply)            # the relay answered the probe
        self.assertIn(b"\x1b]7501;state=blocked:kind=question:msg=UHJvY2VlZD8\x07", out)   # everything passes through
        self.assertIn("café ✓".encode(), out)
        vars_ = [base64.b64decode(v.split(b"\x07")[0]).decode()
                 for v in out.split(b"\x1b]1337;SetUserVar=kittymux_psp=")[1:]]
        self.assertTrue(any('"state":"blocked"' in v and "Proceed?" in v for v in vars_), vars_)
        self.assertIn('"state":"done"', vars_[-1])                          # done outlives the program

    def test_plain_output_clears_a_stale_summary(self):
        out, code = run_under_pty([sys.executable, RELAY, "--", "sh", "-c", "printf hi"])
        self.assertEqual(code, 0)
        self.assertIn(b"\x1b]1337;SetUserVar=kittymux_psp=\x07", out)

    def test_without_a_terminal_it_just_runs_the_command(self):
        import subprocess
        r = subprocess.run([sys.executable, RELAY, "--", "sh", "-c", "echo hi; exit 4"], capture_output=True, stdin=subprocess.DEVNULL)
        self.assertEqual((r.stdout, r.returncode), (b"hi\n", 4))


if __name__ == "__main__":
    unittest.main()
