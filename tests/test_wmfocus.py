import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_wmfocus as F  # noqa: E402

HYPR = {"HYPRLAND_INSTANCE_SIGNATURE": "test"}


def ls(*os_windows):
    """kitty @ ls: each OS window is (os_id, [(tab_id, active, [(win_id, active, title), …]), …])."""
    return [{"id": oid, "tabs": [{"id": tid, "is_active": tact,
                                  "windows": [{"id": w, "is_active": a, "title": t} for w, a, t in wins]}
                                 for tid, tact, wins in tabs]} for oid, tabs in os_windows]


class Fake:
    """A run() that answers kitty @ ls and hyprctl clients, and records everything it is asked to do.

    `lua` is what a probe of a fake address reports: True means the Lua expression says the window
    was not found (Hyprland 0.57), False means only the classic dispatcher does, None means neither.
    """

    def __init__(self, kitty_ls, clients, retitle=None, lua=True):
        self.kitty_ls, self.clients, self.retitle, self.lua, self.calls = kitty_ls, clients, retitle, lua, []

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        joined = " ".join(argv)
        if argv[:2] == ["hyprctl", "dispatch"] and F.PROBE_ADDRESS in joined:
            lua_probe = "hl.dsp.focus" in joined
            if (self.lua is True and lua_probe) or (self.lua is False and not lua_probe):
                return SimpleNamespace(returncode=0, stdout="", stderr="window not found")
            return SimpleNamespace(returncode=0, stdout="", stderr="')' expected near 'address'")
        if argv[:2] == ["kitty", "@"] and argv[4] == "ls":
            return SimpleNamespace(returncode=0, stdout=json.dumps(self.kitty_ls), stderr="")
        if argv[:3] == ["hyprctl", "clients", "-j"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps(self.clients), stderr="")
        if argv[:2] == ["kitty", "@"] and argv[4] == "set-window-title" and len(argv) == 8 and self.retitle:
            self.retitle(self, argv[7])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def dispatched(self):
        """Real focus dispatches. The probe names PROBE_ADDRESS and is not one of them."""
        return [a for a in self.calls if a[:2] == ["hyprctl", "dispatch"] and F.PROBE_ADDRESS not in " ".join(a)]


class PickTests(unittest.TestCase):
    def test_title_of_the_os_window_holding_the_window(self):
        data = ls((1, [(10, True, [(100, True, "~")])]),
                  (2, [(20, False, [(200, True, "build")]), (21, True, [(210, True, "agent")])]))
        self.assertEqual(F.os_window_title(data, 200), "agent")       # its OS window shows the active tab's title
        self.assertEqual(F.os_window_title(data, 100), "~")
        self.assertIsNone(F.os_window_title(data, 999))

    def test_one_client_is_unambiguous_several_need_the_title(self):
        one = [{"pid": 5, "address": "0xa", "title": "x"}]
        self.assertEqual(F.pick_address(one, 5, "anything"), "0xa")
        two = [{"pid": 5, "address": "0xa", "title": "~"}, {"pid": 5, "address": "0xb", "title": "agent"}]
        self.assertEqual(F.pick_address(two, 5, "agent"), "0xb")
        self.assertIsNone(F.pick_address(two, 5, "missing"))
        same = [{"pid": 5, "address": "0xa", "title": "zsh"}, {"pid": 5, "address": "0xb", "title": "zsh"}]
        self.assertIsNone(F.pick_address(same, 5, "zsh"))


class FocusTests(unittest.TestCase):
    def test_the_other_monitors_kitty_is_never_picked_by_pid(self):
        # The reported bug: one kitty, two OS windows; Hyprland lists the workspace-1 one first. Focusing the agent
        # on workspace 3 must name workspace 3's window, never `pid:` (which switched the other monitor to 1).
        data = ls((1, [(10, True, [(100, True, "~")])]),
                  (2, [(20, True, [(200, True, "agent")])]))
        clients = [{"pid": 42, "address": "0xws1", "title": "~"}, {"pid": 42, "address": "0xws3", "title": "agent"}]
        run = Fake(data, clients)
        with mock.patch.object(F.shutil, "which", return_value="/usr/bin/hyprctl"):
            self.assertTrue(F.focus("unix:/s", 200, 42, run=run, env=HYPR))
        self.assertEqual(run.dispatched(), [["hyprctl", "dispatch", "hl.dsp.focus({window = 'address:0xws3'})"]])
        self.assertFalse(any("pid:" in " ".join(a) for a in run.calls))
        self.assertTrue(any(F.PROBE_ADDRESS in " ".join(a) for a in run.calls))   # the dispatcher was read, not assumed

    def test_an_older_hyprland_still_gets_the_classic_dispatcher(self):
        # The Lua probe does not say "window not found"; the classic one does. The old code always sends Lua.
        data = ls((1, [(10, True, [(100, True, "agent")])]))
        run = Fake(data, [{"pid": 42, "address": "0xa", "title": "agent"}], lua=False)
        with mock.patch.object(F.shutil, "which", return_value="/usr/bin/hyprctl"):
            self.assertTrue(F.focus("unix:/s", 100, 42, run=run, env=HYPR))
        self.assertEqual(run.dispatched(), [["hyprctl", "dispatch", "focuswindow", "address:0xa"]])

    def test_no_dispatch_when_neither_probe_names_a_missing_window(self):
        data = ls((1, [(10, True, [(100, True, "agent")])]))
        run = Fake(data, [{"pid": 42, "address": "0xa", "title": "agent"}], lua=None)
        with mock.patch.object(F.shutil, "which", return_value="/usr/bin/hyprctl"):
            self.assertTrue(F.focus("unix:/s", 100, 42, run=run, env=HYPR))
        self.assertEqual(run.dispatched(), [])

    def test_kitty_focuses_first_so_the_tab_switches(self):
        data = ls((1, [(10, False, [(100, True, "other tab")]), (11, True, [(110, True, "agent")])]))
        run = Fake(data, [{"pid": 42, "address": "0xa", "title": "agent"}])
        with mock.patch.object(F.shutil, "which", return_value="/usr/bin/hyprctl"):
            F.focus("unix:/s", 110, 42, run=run, env=HYPR)
        self.assertEqual(run.calls[0], ["kitty", "@", "--to", "unix:/s", "focus-window", "--match", "id:110"])

    def test_lookalike_windows_are_told_apart_by_a_tag_and_the_title_is_handed_back(self):
        data = ls((1, [(10, True, [(100, True, "zsh")])]), (2, [(20, True, [(200, True, "zsh")])]))
        clients = [{"pid": 42, "address": "0xa", "title": "zsh"}, {"pid": 42, "address": "0xb", "title": "zsh"}]

        def retitle(fake, tag):          # the compositor sees the tagged title on window 200's OS window
            fake.clients = [clients[0], {"pid": 42, "address": "0xb", "title": tag}]
        run = Fake(data, clients, retitle=retitle)
        with mock.patch.object(F.shutil, "which", return_value="/usr/bin/hyprctl"):
            F.focus("unix:/s", 200, 42, run=run, env=HYPR, sleep=lambda s: None)
        self.assertEqual(run.dispatched(), [["hyprctl", "dispatch", "hl.dsp.focus({window = 'address:0xb'})"]])
        self.assertIn(["kitty", "@", "--to", "unix:/s", "set-window-title", "--match", "id:200"], run.calls)   # title handed back

    def test_no_guess_when_it_cannot_be_told(self):
        data = ls((1, [(10, True, [(100, True, "zsh")])]), (2, [(20, True, [(200, True, "zsh")])]))
        clients = [{"pid": 42, "address": "0xa", "title": "zsh"}, {"pid": 42, "address": "0xb", "title": "zsh"}]
        run = Fake(data, clients)                 # the tag never shows up
        with mock.patch.object(F.shutil, "which", return_value="/usr/bin/hyprctl"):
            F.focus("unix:/s", 200, 42, run=run, env=HYPR, sleep=lambda s: None)
        self.assertEqual(run.dispatched(), [])

    def test_without_hyprland_only_kitty_focuses(self):
        run = Fake(ls((1, [(10, True, [(100, True, "x")])])), [])
        self.assertTrue(F.focus("unix:/s", 100, 42, run=run, env={}))
        self.assertEqual(len(run.calls), 1)

    def test_bad_ids_do_nothing(self):
        run = Fake([], [])
        self.assertFalse(F.focus("unix:/s", "x", 42, run=run, env=HYPR))
        self.assertEqual(run.calls, [])


if __name__ == "__main__":
    unittest.main()
