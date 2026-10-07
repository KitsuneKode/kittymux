import os
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_sockets as S  # noqa: E402


class LinkTests(unittest.TestCase):
    """kitty's socket moved to $XDG_RUNTIME_DIR (private) but the user's own scripts look for /tmp/mykitty-<pid>: a link at the old path keeps them working."""

    def setUp(self):
        self.root = tempfile.mkdtemp(dir=os.environ.get("TMPDIR") or None)
        self.run, self.legacy = os.path.join(self.root, "run"), os.path.join(self.root, "tmp")
        os.mkdir(self.run, 0o700)
        os.mkdir(self.legacy)
        self.socks = []

    def tearDown(self):
        for s in self.socks:
            s.close()

    def sock(self, name="mykitty-4242"):
        path = os.path.join(self.run, name)
        s = socket.socket(socket.AF_UNIX)
        s.bind(path)
        self.socks.append(s)
        return path

    def test_a_socket_in_the_private_dir_gets_a_link_at_the_old_path(self):
        real = self.sock()
        out = S.legacy_link("unix:" + real, self.legacy)
        link = os.path.join(self.legacy, "mykitty-4242")
        self.assertEqual(out, "linked")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.readlink(link), real)
        self.assertTrue(os.path.exists(link) and S.is_owned_socket(link))      # a script's `[[ -S ]]` follows the link

    def test_asking_again_changes_nothing(self):
        real = self.sock()
        S.legacy_link("unix:" + real, self.legacy)
        self.assertEqual(S.legacy_link("unix:" + real, self.legacy), "already linked")

    def test_something_else_at_the_path_is_never_replaced(self):
        real = self.sock()
        other = os.path.join(self.legacy, "mykitty-4242")
        open(other, "w").write("not ours")
        self.assertIn("left alone", S.legacy_link("unix:" + real, self.legacy))
        self.assertEqual(open(other).read(), "not ours")
        os.unlink(other)
        os.symlink("/nonexistent/elsewhere", other)                              # a link somewhere else (another user's plant) is not replaced either
        self.assertIn("left alone", S.legacy_link("unix:" + real, self.legacy))
        self.assertEqual(os.readlink(other), "/nonexistent/elsewhere")

    def test_nothing_to_do_when_the_socket_is_already_in_the_old_place(self):
        real = os.path.join(self.legacy, "mykitty-4242")
        s = socket.socket(socket.AF_UNIX)
        s.bind(real)
        self.socks.append(s)
        self.assertEqual(S.legacy_link("unix:" + real, self.legacy), "not needed")

    def test_only_kittys_own_naming_and_real_unix_sockets_are_linked(self):
        for bad in ("", "unix:", "tcp:127.0.0.1:1", "unix:relative/mykitty-1", "unix:@abstract", "fd:3", None):
            self.assertIn(S.legacy_link(bad, self.legacy), ("not a unix socket path",), bad)
        plain = os.path.join(self.run, "notpid")
        s = socket.socket(socket.AF_UNIX)
        s.bind(plain)
        self.socks.append(s)
        self.assertIn("name", S.legacy_link("unix:" + plain, self.legacy))        # kitty names it <name>-<pid>: anything else is somebody else's
        self.assertIn("not a socket", S.legacy_link("unix:" + os.path.join(self.run, "mykitty-9"), self.legacy))   # missing
        regular = os.path.join(self.run, "mykitty-77")
        open(regular, "w").close()
        self.assertIn("not a socket", S.legacy_link("unix:" + regular, self.legacy))
        self.assertEqual(os.listdir(self.legacy), [])

    def test_a_hostile_name_cannot_escape_the_legacy_dir(self):
        evil = os.path.join(self.run, "..", "mykitty-1")
        S.legacy_link("unix:" + evil, self.legacy)
        self.assertEqual(sorted(os.listdir(self.root)), ["run", "tmp"])

    def test_an_unwritable_dir_is_a_reason_not_a_crash(self):
        real = self.sock()
        self.assertIn("could not", S.legacy_link("unix:" + real, os.path.join(self.root, "missing", "dir")))

    def test_dead_links_are_pruned_and_nothing_else_is(self):
        live = self.sock("mykitty-1")
        S.legacy_link("unix:" + live, self.legacy)
        gone = os.path.join(self.run, "mykitty-2")
        os.symlink(gone, os.path.join(self.legacy, "mykitty-2"))                  # its kitty exited: the target is gone
        os.symlink("/nonexistent/x", os.path.join(self.legacy, "mykitty-3"))      # dangling but not into our dir: not ours to remove
        open(os.path.join(self.legacy, "mykitty-4"), "w").close()                 # a regular file
        removed = S.prune_links(self.legacy, self.run)
        self.assertEqual(removed, ["mykitty-2"])
        self.assertEqual(sorted(os.listdir(self.legacy)), ["mykitty-1", "mykitty-3", "mykitty-4"])

    def test_one_kitty_is_listed_once_whichever_path_finds_it(self):
        real = self.sock()
        S.legacy_link("unix:" + real, self.legacy)
        link = os.path.join(self.legacy, "mykitty-4242")
        self.assertEqual(S.dedupe([link, real]), [link])                          # first spelling wins, order kept
        self.assertEqual(S.dedupe([real, link, "/nonexistent/z"]), [real, "/nonexistent/z"])


if __name__ == "__main__":
    unittest.main()
