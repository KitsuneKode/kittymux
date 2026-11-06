"""Zoom fills the tab on both axes. On stack it sends nothing: layout_action there rings the bell."""
import json
import os
import socket
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "python"))
import kittymux_zoom as Z  # noqa: E402


class ZoomActionTests(unittest.TestCase):
    def test_splits_maximizes_both_axes(self):
        # kitty's plain `maximize` is horizontal only. This fails on that action.
        self.assertEqual(Z.zoom_actions("splits"), (
            ("layout_action", "maximize", "horizontal"),
            ("layout_action", "maximize", "vertical"),
        ))
        self.assertNotIn(("layout_action", "maximize"), Z.zoom_actions("splits"))

    def test_stack_sends_nothing(self):
        self.assertEqual(Z.zoom_actions("stack"), ())
        self.assertEqual(Z.zoom_actions("Stack"), ())
        self.assertEqual(Z.zoom_actions("stack:extra"), ())

    def test_an_unknown_layout_still_zooms(self):
        self.assertEqual(Z.zoom_actions(""), Z.ZOOM)
        self.assertEqual(Z.zoom_actions(None), Z.ZOOM)

    def test_active_layout_is_the_focused_os_windows_active_tab(self):
        ls = [
            {"id": 1, "is_focused": False, "tabs": [{"is_active": True, "layout": "stack"}]},
            {"id": 2, "is_focused": True, "tabs": [
                {"is_active": False, "layout": "stack"},
                {"is_active": True, "layout": "splits"},
            ]},
        ]
        self.assertEqual(Z.active_layout(ls), "splits")
        self.assertEqual(Z.active_layout([]), "")

    def test_no_focus_uses_the_last_focused_os_window(self):
        ls = [
            {"id": 1, "is_focused": False, "last_focused": False, "tabs": [{"is_active": True, "layout": "stack"}]},
            {"id": 2, "is_focused": False, "last_focused": True, "tabs": [{"is_active": True, "layout": "splits"}]},
        ]
        self.assertEqual(Z.active_layout(ls), "splits")

    def test_an_axis_already_maximized_is_not_toggled_off(self):
        self.assertEqual(Z.zoom_actions("splits", {"horizontal"}), (("layout_action", "maximize", "vertical"),))
        self.assertEqual(Z.zoom_actions("splits", {"vertical"}), (("layout_action", "maximize", "horizontal"),))
        self.assertEqual(Z.zoom_actions("splits", {"horizontal", "vertical"}), Z.ZOOM)

    def test_maximized_axes_follow_the_focused_windows_group(self):
        tab = {"windows": [{"id": 7, "is_active": True}], "groups": [{"id": 3, "windows": [7]}],
               "layout_state": {"maximized": [{"window_id": 3, "is_horizontal": True}]}}
        self.assertEqual(Z.maximized_axes(tab, 7), {"horizontal"})


class ZoomChordTests(unittest.TestCase):
    def test_both_chords_call_the_same_script(self):
        keys = (ROOT / "kittymux-keys.conf.tpl").read_text(encoding="utf-8")
        leader = (ROOT / "kittymux-leader.conf.tpl").read_text(encoding="utf-8")
        self.assertIn("map ctrl+alt+z           launch --type=background @KITTYMUX_HOME@/bin/mux-zoom.sh", keys)
        self.assertIn("ctrl+alt+z — zoom the focused pane", keys)
        self.assertIn("map --mode leader z launch --type=background @KITTYMUX_HOME@/bin/mux-zoom.sh", leader)
        for line in keys.splitlines():
            if line.startswith("map ctrl+alt+z"):
                self.assertNotIn("layout_action maximize", line)
        for line in leader.splitlines():
            if "leader z " in line:
                self.assertNotIn("layout_action maximize\n", line + "\n")
                self.assertNotRegex(line, r"layout_action maximize\s*$")


class ZoomScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mux-zoom-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        bindir = root / "bin"
        bindir.mkdir()
        mock = bindir / "kitty"
        mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "root = pathlib.Path(os.environ['MOCK_ROOT'])\n"
            "args = sys.argv[1:]\n"
            "(root / 'zoom-calls').open('a').write(json.dumps(args) + '\\n')\n"
            "if 'ls' in args:\n"
            "    layout = os.environ.get('MOCK_LAYOUT', 'splits')\n"
            "    wid = int(os.environ.get('MOCK_WID', '7'))\n"
            "    print(json.dumps([{'id': 1, 'is_focused': True, 'last_focused': True, 'tabs': [{'is_active': True, "
            "'layout': layout, 'windows': [{'id': wid, 'is_active': True, 'is_focused': True}]}]}]))\n"
            "elif 'action' in args:\n"
            "    raise SystemExit(int(os.environ.get('MOCK_ACTION_RC', '0')))\n"
            "else:\n"
            "    raise SystemExit('unexpected ' + ' '.join(args))\n"
        )
        mock.chmod(mock.stat().st_mode | stat.S_IEXEC)
        sock_path = root / "sock"
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(sock_path))
        self.addCleanup(sock.close)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("KITTY", "XDG_", "MOCK_"))}
        env.update(
            PATH=str(bindir) + os.pathsep + os.environ["PATH"],
            HOME=str(root),
            MOCK_ROOT=str(root),
            KITTYMUX_STATE=str(root / "state"),
            KITTYMUX_SOCKET_DIRS=str(root),
            XDG_RUNTIME_DIR=str(root),
            KITTY_LISTEN_ON="unix:" + str(sock_path),
        )
        self.env, self.root = env, root

    def _run(self, layout):
        self.env["MOCK_LAYOUT"] = layout
        result = subprocess.run(
            ["bash", str(ROOT / "bin" / "mux-zoom.sh")],
            cwd=ROOT, env=self.env, text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.root / "zoom-calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_stack_does_not_call_layout_action(self):
        calls = self._run("stack")
        actions = [c for c in calls if "action" in c]
        self.assertEqual(actions, [])
        self.assertTrue(any("ls" in c for c in calls))

    def test_splits_sends_both_axes(self):
        calls = self._run("splits")
        actions = [c[c.index("action"):] for c in calls if "action" in c]
        self.assertEqual(actions, [
            ["action", "--match", "id:7", "layout_action", "maximize", "horizontal"],
            ["action", "--match", "id:7", "layout_action", "maximize", "vertical"],
        ])

    def test_a_failed_action_is_a_notification(self):
        note = self.root / "bin" / "notify-send"
        note.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$MOCK_ROOT/notes\"\n")
        note.chmod(note.stat().st_mode | stat.S_IEXEC)
        self.env["MOCK_ACTION_RC"] = "1"
        result = subprocess.run(
            ["bash", str(ROOT / "bin" / "mux-zoom.sh")],
            cwd=ROOT, env=self.env, text=True, capture_output=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Zoom did not finish", (self.root / "notes").read_text())


if __name__ == "__main__":
    unittest.main()
