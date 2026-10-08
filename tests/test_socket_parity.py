"""The shell and Python resolvers answer "which kitty" from the same rules. They are two implementations on purpose (key-bound shell scripts must not start
python for this), so this table is what keeps them from drifting again: the same sockets, the same environment, the same answer."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "python"))
import kittymux_sockets as S  # noqa: E402

LIB = os.path.join(ROOT, "lib", "socket.sh")


class Rig:
    """Real sockets in temporary directories; `python` and `shell` ask the two resolvers the same question."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.socks = []

    def dir(self, name):
        return os.path.join(self.tmp.name, name)

    def make(self, directory, name):
        os.makedirs(directory, exist_ok=True)
        s = socket.socket(socket.AF_UNIX)
        path = os.path.join(directory, name)
        s.bind(path)
        self.socks.append(s)
        time.sleep(0.02)                                   # distinct mtimes: "newest" must be decidable
        return path

    def close(self):
        for s in self.socks:
            s.close()
        self.tmp.cleanup()

    def python(self, dirs, env, ppid):
        def own():
            return S.own(dirs, S.is_owned_socket, env, ppid)
        return own() or "", S.target(own, dirs, S.is_owned_socket, env) or ""

    def shell(self, dirs, env):
        full = {"PATH": os.environ["PATH"], "KITTYMUX_SOCKET_DIRS": ":".join(dirs), **env}

        def ask(fn):
            p = subprocess.run(["bash", "-c", f'source "{LIB}"; {fn}'], env=full, capture_output=True, text=True)
            return p.stdout if p.returncode == 0 else ""
        return ask("mux_own_socket"), ask("mux_resolve_socket")


class ParityTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)

    def agree(self, dirs, env, expect_own, expect_target):
        ppid = os.getpid()                                  # a bash -c started by this process has this pid as its parent
        py = self.rig.python(dirs, env, ppid)
        sh = self.rig.shell(dirs, env)
        self.assertEqual(py, sh, "python and shell disagree")
        self.assertEqual(py, (expect_own, expect_target))

    def test_the_kitty_that_started_us_beats_a_newer_one(self):
        run = self.rig.dir("run")
        mine = self.rig.make(run, f"mykitty-{os.getpid()}")
        self.rig.make(run, "mykitty-4243")
        self.agree([run], {}, "unix:" + mine, "unix:" + mine)

    def test_kitty_pid_names_the_kitty_when_the_parent_is_not_one(self):
        run = self.rig.dir("run")
        older = self.rig.make(run, "mykitty-4242")
        self.rig.make(run, "mykitty-4243")
        self.agree([run], {"KITTY_PID": "4242"}, "unix:" + older, "unix:" + older)

    def test_an_owned_listen_on_hint_is_used_before_kitty_pid(self):
        run = self.rig.dir("run")
        hinted = self.rig.make(run, "mykitty-4244")
        self.rig.make(run, "mykitty-4242")
        self.agree([run], {"KITTY_LISTEN_ON": "unix:" + hinted, "KITTY_PID": "4242"}, "unix:" + hinted, "unix:" + hinted)

    def test_a_stale_listen_on_hint_is_ignored(self):
        run = self.rig.dir("run")
        real = self.rig.make(run, "mykitty-4242")
        self.agree([run], {"KITTY_LISTEN_ON": "unix:" + os.path.join(run, "gone"), "KITTY_PID": "4242"}, "unix:" + real, "unix:" + real)

    def test_started_outside_every_kitty_the_answer_is_the_newest(self):
        run = self.rig.dir("run")
        self.rig.make(run, "mykitty-4242")
        newest = self.rig.make(run, "mykitty-4243")
        self.agree([run], {}, "", "unix:" + newest)

    def test_the_first_directory_wins_for_a_kitty_with_a_socket_in_two(self):
        private, shared = self.rig.dir("private"), self.rig.dir("shared")
        a = self.rig.make(private, "mykitty-4242")
        self.rig.make(shared, "mykitty-4242")
        self.agree([private, shared], {"KITTY_PID": "4242"}, "unix:" + a, "unix:" + a)

    def test_nothing_anywhere_is_nothing(self):
        empty = self.rig.dir("empty-but-real")
        os.makedirs(empty)
        self.agree([empty], {}, "", "")


if __name__ == "__main__":
    unittest.main()
