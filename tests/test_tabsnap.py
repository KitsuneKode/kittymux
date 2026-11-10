"""tabs.json: the bar's tab rows, written only when a visible field changed, and never half-written."""
import itertools
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_palette as P  # noqa: E402
import kittymux_place as Place  # noqa: E402
import kittymux_tabsnap as S  # noqa: E402

HOME = "/home/calm"
REPO = "/home/calm/work/calm-otter"


def tab(**over):
    facts = over.pop("facts", Place.Facts("calm-otter", "", "src", "", "main"))
    row = dict(tab_id=3, index=1, active=True, title="Port the configs", program="zsh", has_agent=True,
               agent="claude", facts=facts, folder=True, cwd=REPO, home=HOME, hue=0xA3D4A0, state="working",
               ts_state=1000.0 - 240, now=1000.0, panes=2, window_id=19, kitty_pid=4035, progress=("set", 42))
    row.update(over)
    return S.build_tab(**row)


def window(pid=4035, osw=1, **over):
    row = tab(kitty_pid=pid, **over)
    return {"kitty_pid": pid, "os_window_id": osw, "wm_class": "kitty", "focused": True,
            "session": "calm-otter", "tabs": [row]}


class RowTests(unittest.TestCase):
    def test_states_progress_hue_and_the_home_tilde(self):
        row = tab()
        self.assertEqual(list(row), list(S._TAB_FIELDS))
        self.assertEqual(row["title"], "Port the configs")
        self.assertEqual(row["subtitle"], "calm-otter/src  main")
        self.assertEqual(row["project"], "calm-otter")
        self.assertEqual(row["branch"], "main")
        self.assertEqual(row["cwd"], "~/work/calm-otter")
        self.assertEqual(row["hue"], "#a3d4a0")
        self.assertEqual(row["state"], "working")
        self.assertEqual(row["age"], "4m")
        self.assertEqual(row["progress"], {"state": "set", "pct": 42})
        self.assertFalse(row["needs_you"])
        self.assertEqual(row["agent"], "claude")
        self.assertEqual(row["brand"], "claude")
        self.assertEqual(row["panes"], 2)
        self.assertEqual(row["action"], P.validate_action({"op": "jump", "pid": 4035, "w": "19"}))

        for state, needs in (("waiting", True), ("limited", True), ("error", False), ("done", False), ("idle", False)):
            got = tab(state=state, progress=None, hue=None)
            self.assertEqual(got["state"], state)
            self.assertEqual(got["needs_you"], needs)
            self.assertIsNone(got["progress"])
            self.assertIsNone(got["hue"])
        self.assertEqual(tab(state="unread")["state"], "idle")
        self.assertEqual(tab(state="")["state"], "idle")
        self.assertIsNone(tab(progress=("nope", 3))["progress"])
        self.assertEqual(tab(progress=("indeterminate", 0))["progress"], {"state": "indeterminate", "pct": 0})

        home = tab(title="~", program="zsh", has_agent=False, agent="", facts=Place.Facts("~", "", "", "", ""),
                   cwd=HOME, hue=None, state="", progress=None, panes=1)
        self.assertEqual(home["title"], "Home")
        self.assertEqual(home["subtitle"], "zsh")
        self.assertEqual(home["cwd"], "~")
        self.assertEqual(home["state"], "idle")
        self.assertEqual(home["age"], "")
        self.assertIsNone(home["hue"])
        self.assertIsNone(home["progress"])
        self.assertFalse(home["needs_you"])
        # an agent in home keeps the place rule: the program is not drawn in its place
        agent_home = tab(title="~", program="zsh", facts=Place.Facts("~", "", "", "", ""), cwd=HOME, state="working")
        self.assertEqual(agent_home["title"], "Home")
        self.assertEqual(agent_home["subtitle"], "")
        self.assertEqual(agent_home["agent"], "claude")

    def test_show_program_matches_the_bar(self):
        """The draw path's old condition, as a truth table, so the file and the pixels cannot drift."""
        def drawn(has_agent, has_place, home_only, place_is_folder):
            return (not has_agent) and ((not has_place) or (home_only and place_is_folder))

        for bits in itertools.product((False, True), repeat=4):
            self.assertEqual(S.show_program(*bits), drawn(*bits), bits)
        self.assertEqual(S.display_title("~"), "Home")
        self.assertEqual(S.display_title("  ~  "), "Home")
        self.assertEqual(S.display_title("Port the configs"), "Port the configs")


class CoalesceTests(unittest.TestCase):
    def test_at_most_one_write_per_gap_and_the_trailing_update_is_kept(self):
        gate = S.Gate()
        self.assertEqual(gate.gap, 0.25)
        writes, armed = [], []

        def write(item):
            writes.append(item)

        def arm(delay):
            armed.append(delay)
            return True

        self.assertEqual(S.submit(gate, "a", 10.0, write, arm), "write")
        self.assertEqual(writes, ["a"])
        self.assertEqual(S.submit(gate, "b", 10.1, write, arm), "arm")
        self.assertEqual(writes, ["a"])
        self.assertEqual(len(armed), 1)
        self.assertAlmostEqual(armed[0], 0.15)
        self.assertEqual(S.submit(gate, "c", 10.2, write, arm), "hold")
        self.assertEqual(len(armed), 1)
        self.assertEqual(gate.fire(10.25), "c")
        write("c")
        self.assertEqual(writes, ["a", "c"])
        self.assertEqual(S.submit(gate, "d", 10.30, write, arm), "arm")
        self.assertEqual(len(armed), 2)
        self.assertEqual(gate.fire(10.50), "d")
        write("d")
        self.assertEqual(S.submit(gate, "e", 10.75, write, arm), "write")
        self.assertEqual(writes, ["a", "c", "d", "e"])

    def test_a_timer_that_cannot_be_armed_still_writes_the_pending_update(self):
        gate = S.Gate()
        writes = []
        S.submit(gate, "a", 0.0, writes.append, lambda delay: True)
        self.assertEqual(S.submit(gate, "b", 0.1, writes.append, lambda delay: False), "write-now")
        self.assertEqual(writes, ["a", "b"])


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.alive = lambda pid: pid in (4035, 4036)

    def pub(self, pid=4035, osw=1, now=1793780700.0, **over):
        return S.publish(self.dir, pid, [window(pid, osw, **over)], now, alive=self.alive)

    def doc(self):
        with open(S.path_for(self.dir), encoding="utf-8") as handle:
            return json.load(handle)

    def test_a_repeat_is_not_a_write_and_the_file_is_private(self):
        self.assertTrue(self.pub())
        doc = self.doc()
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["windows"][0]["tabs"][0]["title"], "Port the configs")
        self.assertEqual(stat.S_IMODE(os.stat(S.path_for(self.dir)).st_mode), 0o600)
        with mock.patch("kittymux_tabsnap.os.replace") as replace:
            self.assertFalse(self.pub(now=1793780800.0))
        replace.assert_not_called()
        self.assertEqual(self.doc()["t"], 1793780700.0)
        self.assertTrue(self.pub(title="Home", now=1793780800.0))
        self.assertEqual(self.doc()["windows"][0]["tabs"][0]["title"], "Home")

    def test_other_kitties_stay_and_a_dead_one_goes(self):
        self.pub(4035, osw=1)
        self.pub(4036, osw=2, now=1793780710.0)
        got = [(w["kitty_pid"], w["os_window_id"]) for w in self.doc()["windows"]]
        self.assertEqual(got, [(4035, 1), (4036, 2)])
        self.alive = lambda pid: pid == 4036
        self.pub(4036, osw=2, title="Review the parser", now=1793780720.0)
        self.assertEqual([(w["kitty_pid"], w["os_window_id"]) for w in self.doc()["windows"]], [(4036, 2)])

    def test_this_kitty_replaces_only_its_own_windows(self):
        self.pub(4035, osw=1)
        self.pub(4036, osw=2, now=1793780710.0)
        self.pub(4035, osw=3, now=1793780720.0)
        got = [(w["kitty_pid"], w["os_window_id"]) for w in self.doc()["windows"]]
        self.assertEqual(got, [(4035, 3), (4036, 2)])

    def test_a_dead_pid_already_in_the_file_is_dropped(self):
        os.makedirs(self.dir, mode=0o700, exist_ok=True)
        with open(S.path_for(self.dir), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "t": 1, "windows": [
                {"kitty_pid": 1073741824, "os_window_id": 1, "wm_class": "kitty", "focused": False,
                 "session": "", "tabs": []}]}, handle)
        self.assertTrue(S.publish(self.dir, 4035, [window()], 1793780700.0, alive=lambda pid: False))
        self.assertEqual([w["kitty_pid"] for w in self.doc()["windows"]], [4035])

    def test_a_failed_replace_leaves_the_previous_file_and_the_temporary_is_gone(self):
        self.assertTrue(self.pub())
        with open(S.path_for(self.dir), encoding="utf-8") as handle:
            old = handle.read()

        def boom(src, dst):
            with open(src, encoding="utf-8") as handle:
                text = handle.read()
            parsed = json.loads(text)
            self.assertEqual(parsed["version"], 1)
            self.assertEqual(parsed["windows"][0]["tabs"][0]["state"], "waiting")
            raise OSError("disk full")

        with mock.patch("kittymux_tabsnap.os.replace", side_effect=boom):
            self.assertFalse(self.pub(state="waiting", now=1793780710.0))
        with open(S.path_for(self.dir), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), old)
        self.assertFalse([n for n in os.listdir(self.dir) if n.endswith(".tmp")])
        self.assertEqual(json.loads(old)["windows"][0]["tabs"][0]["state"], "working")

    def test_a_bad_pid_does_not_create_the_file(self):
        self.assertFalse(S.publish(self.dir, True, [window()], 1.0, alive=self.alive))
        self.assertFalse(os.path.exists(S.path_for(self.dir)))


if __name__ == "__main__":
    unittest.main()
