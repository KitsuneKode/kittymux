import os
import socket
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_sockets as S  # noqa: E402


class TargetHowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.socks = []
        self.addCleanup(lambda: [s.close() for s in self.socks])

    def sock(self, name):
        s = socket.socket(socket.AF_UNIX)
        path = os.path.join(self.tmp.name, name)
        s.bind(path)
        self.socks.append(s)
        time.sleep(0.02)                                          # distinct mtimes: "newest" must be decidable
        return path

    def test_target_says_how_it_chose(self):
        older, newer = self.sock("mykitty-100"), self.sock("mykitty-200")
        dirs = [self.tmp.name]
        self.assertEqual(S.target_how(lambda: None, dirs, S.is_owned_socket, {}), ("unix:" + newer, "newest"))
        self.assertEqual(S.target_how(lambda: "unix:" + older, dirs, S.is_owned_socket, {}), ("unix:" + older, "own"))
        self.assertEqual(S.target_how(lambda: None, dirs, S.is_owned_socket, {"KITTYMUX_TARGET": "unix:" + older}), ("unix:" + older, "explicit"))
        self.assertEqual(S.target_how(lambda: None, [], S.is_owned_socket, {}), (None, "none"))

    def test_a_bad_explicit_target_is_none_not_a_fallback(self):
        self.sock("mykitty-200")
        self.assertEqual(S.target_how(lambda: None, [self.tmp.name], S.is_owned_socket, {"KITTYMUX_TARGET": "unix:/nope"}), (None, "none"))

    def test_target_still_returns_only_the_socket(self):
        newer = self.sock("mykitty-200")
        self.assertEqual(S.target(lambda: None, [self.tmp.name], S.is_owned_socket, {}), "unix:" + newer)


if __name__ == "__main__":
    unittest.main()
