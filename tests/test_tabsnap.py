"""tabs.json: every tab of every running kitty, for the kittymux client (docs/inbox.md)."""
import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_tabsnap as T  # noqa: E402

COLORS = {"background": 0x111114, "foreground": 0xE8E8EA, "active_border_color": 0xD98CB3,
          **{f"color{n}": c for n, c in zip(range(1, 16), (0xE06C75, 0x98C379, 0xE5C07B, 0x61AFEF, 0xC678DD, 0x56B6C2, 0xABB2BF,
                                                           0x5C6370, 0xE06C75, 0x98C379, 0xE5C07B, 0x61AFEF, 0xC678DD, 0x56B6C2, 0xFFFFFF))}}


def win(wid, active=False, agent="", state="", **kw):
    return {"window_id": wid, "active": active, "cwd": "", "agent": agent, "state": state, **kw}


def spec(tabs, osw=1, focused=True, colors=None):
    return {"os_window_id": osw, "wm_class": "kitty", "focused": focused, "colors": colors or {}, "tabs": tabs}


class TabsnapTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def doc(self):
        with open(T.path_for(self.dir)) as f:
            return json.load(f)

    def publish(self, specs, pid=4035, now=100.0, alive=lambda p: True):
        return T.publish(self.dir, pid, specs, now, alive=alive, home="/home/calm-otter")

    def test_every_tab_is_listed_even_without_an_agent(self):
        self.assertTrue(self.publish([spec([{"tab_id": 1, "title": "shell", "active": True, "windows": [win(5, True)]},
                                            {"tab_id": 2, "title": "api", "windows": [win(6, True, "claude", "working", progress=0.42)]}])]))
        doc = self.doc()
        self.assertEqual(doc["version"], 1)
        tabs = doc["windows"][0]["tabs"]
        self.assertEqual([t["title"] for t in tabs], ["shell", "api"])
        self.assertEqual([t["index"] for t in tabs], [1, 2])
        self.assertEqual(tabs[0]["state"], "")
        self.assertIsNone(tabs[0]["since"])
        self.assertTrue(tabs[0]["active"])
        self.assertEqual((tabs[1]["agent"], tabs[1]["brand"], tabs[1]["state"], tabs[1]["progress"]), ("claude", "claude", "working", 0.42))
        self.assertEqual(tabs[1]["action"], {"op": "jump", "pid": 4035, "w": "6"})
        self.assertEqual(stat.S_IMODE(os.stat(T.path_for(self.dir)).st_mode), 0o600)

    def test_the_pane_that_asks_speaks_for_the_tab_and_a_muted_one_only_when_alone(self):
        self.publish([spec([{"tab_id": 3, "title": "t", "windows": [
            win(7, True, "claude", "working"), win(8, False, "codex", "waiting", reason="Allow edit?"),
            win(9, False, "gemini", "waiting", muted=True)]}])])
        tab = self.doc()["windows"][0]["tabs"][0]
        self.assertEqual((tab["agent"], tab["state"], tab["question"], tab["needs_you"], tab["panes"]), ("codex", "waiting", "Allow edit?", True, 3))
        self.assertEqual(tab["agent_window"], 8)
        self.assertEqual(tab["action"]["w"], "7")                 # a click goes to the pane you left the tab on
        self.publish([spec([{"tab_id": 3, "title": "t", "windows": [win(9, True, "gemini", "waiting", muted=True)]}])])
        tab = self.doc()["windows"][0]["tabs"][0]
        self.assertTrue(tab["muted"])
        self.assertFalse(tab["needs_you"])
        self.assertEqual(self.doc()["needs_you"], 0)

    def test_since_holds_while_the_state_holds(self):
        tab = lambda st: [spec([{"tab_id": 1, "title": "t", "windows": [win(5, True, "claude", st)]}])]   # noqa: E731
        self.publish(tab("working"), now=100.0)
        self.publish(tab("working"), now=150.0)
        self.assertEqual(self.doc()["windows"][0]["tabs"][0]["since"], 100.0)
        self.publish(tab("done"), now=160.0)
        self.assertEqual(self.doc()["windows"][0]["tabs"][0]["since"], 160.0)

    def test_an_unchanged_document_is_not_rewritten(self):
        s = [spec([{"tab_id": 1, "title": "t", "windows": [win(5, True)]}])]
        self.assertTrue(self.publish(s, now=1.0))
        self.assertFalse(self.publish(s, now=2.0))

    def test_other_kitties_are_kept_while_alive_and_dropped_when_gone(self):
        self.publish([spec([{"tab_id": 1, "title": "a", "windows": [win(5, True)]}])], pid=11)
        self.publish([spec([{"tab_id": 1, "title": "b", "windows": [win(5, True)]}])], pid=22)
        self.assertEqual(sorted(w["kitty_pid"] for w in self.doc()["windows"]), [11, 22])
        self.publish([spec([{"tab_id": 1, "title": "b2", "windows": [win(5, True)]}])], pid=22, alive=lambda p: False)
        self.assertEqual([w["kitty_pid"] for w in self.doc()["windows"]], [22])

    def test_the_palette_and_project_hue_come_from_the_live_theme(self):
        pal = T.palette_of(COLORS)
        self.assertEqual(set(pal), set(T._PALETTE))
        self.assertTrue(all(len(v) == 7 and v.startswith("#") for v in pal.values()))
        self.assertEqual(T.palette_of({}), {})
        self.assertEqual(T._hue("", COLORS), "")
        self.assertRegex(T._hue("calm-otter", COLORS), r"^#[0-9a-f]{6}$")

    def test_a_bar_that_covers_the_terminal_is_not_published(self):
        # The window is 1762x1378 and the terminal still starts at x=0: the reported bar is not a bar.
        covered = T.geometry_of({"vw": 1762, "vh": 1378, "width": 1762, "height": 1378,
                                  "bar": [0, 0, 308, 1378], "central": [0, 0, 1762, 1378]})
        self.assertIsNone(covered["bar"])
        self.assertEqual(covered["edge"], "")
        # The terminal starts where the bar ends: this one is real.
        reserved = T.geometry_of({"vw": 1762, "vh": 1378, "width": 1762, "height": 1378,
                                   "bar": [0, 0, 308, 1378], "central": [308, 0, 1762, 1378]})
        self.assertEqual(reserved["bar"], [0, 0, 308, 1378])
        self.assertEqual(reserved["edge"], "left")
        self.assertFalse(T.bar_reserves_space([0, 0, 0, 0], [0, 0, 1762, 1378]))

    def test_a_busy_lock_is_skipped_not_waited_for(self):
        import fcntl
        s = [spec([{"tab_id": 1, "title": "t", "windows": [win(5, True)]}])]
        fd = os.open(os.path.join(self.dir, "tabs.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)                         # another kitty is mid-write
            self.assertIsNone(self.publish(s))                     # None: not written, try again; it returned at once
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self.assertTrue(self.publish(s))

    def test_an_oversized_file_is_not_parsed(self):
        with open(T.path_for(self.dir), "w") as f:
            f.write('{"windows": [' + " " * (T.MAX_BYTES + 10) + "]}")
        self.assertEqual(T._read(T.path_for(self.dir)), [])
        self.assertTrue(self.publish([spec([{"tab_id": 1, "title": "t", "windows": [win(5, True)]}])]))
        self.assertEqual(len(self.doc()["windows"]), 1)

    def test_junk_is_dropped_never_raised(self):
        self.assertTrue(self.publish([None, {"os_window_id": "x"}, spec([{"tab_id": None}, {"tab_id": 2, "windows": []},
                                                                         {"tab_id": 4, "title": "\x1b[31mred", "windows": [win(1, True)]}])]))
        tabs = self.doc()["windows"][0]["tabs"]
        self.assertEqual([t["tab_id"] for t in tabs], [4])
        self.assertNotIn("\x1b", tabs[0]["title"])
        self.assertFalse(T.publish(self.dir, -1, [], 1.0))


if __name__ == "__main__":
    unittest.main()
