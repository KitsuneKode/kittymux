"""Tests for kittymux_skill, `kittymux skill`, `kittymux tabs`, and `kittymux settings preset pixel`."""
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import kittymux_skill as SK  # noqa: E402
import kittymux_switches as SW  # noqa: E402


def load_cli():
    loader = importlib.machinery.SourceFileLoader("kittymux_skill_cli_test", str(ROOT / "bin" / "kittymux"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class SkillTests(unittest.TestCase):
    def test_install_and_remove_only_touch_kittymux_managed_files(self):
        with tempfile.TemporaryDirectory() as home:
            written, skipped = SK.install(home)
            self.assertEqual(len(written), 3)
            self.assertEqual(skipped, [])
            for p in written:
                self.assertIn(SK.MARKER, p.read_text(encoding="utf-8"))
            # Idempotent reinstall
            written2, skipped2 = SK.install(home)
            self.assertEqual(len(written2), 3)
            self.assertEqual(skipped2, [])
            # Replace one file with user-authored content: never overwritten or removed
            custom = written[0]
            custom.write_text("# my custom skill\n", encoding="utf-8")
            written3, skipped3 = SK.install(home)
            self.assertEqual(len(written3), 2)
            self.assertEqual(skipped3, [custom])
            self.assertEqual(custom.read_text(encoding="utf-8"), "# my custom skill\n")
            removed, left = SK.remove(home)
            self.assertEqual(len(removed), 2)
            self.assertEqual(left, [custom])
            self.assertTrue(custom.exists())

    def test_load_live_tabs_drops_dead_pids(self):
        with tempfile.TemporaryDirectory() as sdir:
            doc = {
                "version": 1,
                "windows": [
                    {"kitty_pid": os.getpid(), "host": "devbox", "tabs": [{"title": "api", "state": "working"}]},
                    {"kitty_pid": 99999999, "host": "gone", "tabs": [{"title": "old", "state": "idle"}]},
                ],
            }
            (Path(sdir) / "tabs.json").write_text(json.dumps(doc), encoding="utf-8")
            live = SK.load_live_tabs(sdir)
            self.assertEqual(len(live), 1)
            self.assertEqual(live[0]["host"], "devbox")


class PixelPresetAndTabsCLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = load_cli()

    def test_settings_preset_pixel_turns_on_pxbar_and_deckpx(self):
        with tempfile.TemporaryDirectory() as sdir, patch.dict(os.environ, {"KITTYMUX_STATE": sdir}, clear=False), \
             patch.object(self.cli, "_nudge_bars", return_value=(0, 0)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = self.cli.settings_cmd(["preset", "pixel"])
            self.assertEqual(rc, 0)
            self.assertTrue(SW.enabled("pxbar", sdir, {}))
            self.assertTrue(SW.enabled("deckpx", sdir, {}))
            self.assertIn("preset pixel", buf.getvalue())

    def test_tabs_cmd_json_outputs_live_snapshot(self):
        with tempfile.TemporaryDirectory() as sdir, patch.dict(os.environ, {"KITTYMUX_STATE": sdir}, clear=False):
            doc = {"version": 1, "windows": [{"kitty_pid": os.getpid(), "host": "devbox", "tabs": [{"title": "web", "state": "waiting"}]}]}
            (Path(sdir) / "tabs.json").write_text(json.dumps(doc), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = self.cli.tabs_cmd(["--json"])
            self.assertEqual(rc, 0)
            parsed = json.loads(buf.getvalue())
            self.assertEqual(parsed["windows"][0]["tabs"][0]["title"], "web")

    def test_skill_cmd_print_outputs_skill_markdown(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.cli.skill_cmd(["--print"])
        self.assertEqual(rc, 0)
        self.assertIn("kittymux tabs --json", buf.getvalue())
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(self.cli.skill_cmd(["--bogus"]), 2)


if __name__ == "__main__":
    unittest.main()
