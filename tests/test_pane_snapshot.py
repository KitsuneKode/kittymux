import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class SnapshotTests(unittest.TestCase):
    def test_snapshot_uses_native_geometry_and_never_exports_environment(self):
        spec = importlib.util.spec_from_file_location("pane_snapshot", Path(__file__).resolve().parents[1] / "python/pane-snapshot.py")
        mod = importlib.util.module_from_spec(spec)
        handler = types.ModuleType("kittens.tui.handler")
        handler.result_handler = lambda **kw: lambda fn: fn
        with patch.dict(sys.modules, {"kittens.tui.handler": handler}):
            spec.loader.exec_module(mod)
        child = types.SimpleNamespace(current_cwd="/work/demo", cwd="", foreground_processes=[{"cmdline": ["sh"]}])
        window = types.SimpleNamespace(id=7, title="demo", child=child, overlay_for=None,
                                       geometry=types.SimpleNamespace(left=0, top=0, right=100, bottom=100))
        group = types.SimpleNamespace(main_window_id=7, active_window_id=8, geometry=window.geometry, is_visible_in_layout=True)
        windows = types.SimpleNamespace(groups=[group], active_group=group)
        tab = types.SimpleNamespace(id=2, name="demo", title="demo", windows=windows)
        boss = types.SimpleNamespace(tab_for_id=lambda n: tab if n == 2 else None, window_id_map={7: window})
        data = json.loads(mod.handle_result(["kitten", "2"], "", 7, boss))
        self.assertEqual(data["rects"], [[7, 0, 0, 100, 100]])
        self.assertEqual(data["active_window_history"], [7])
        self.assertNotIn("env", data["windows"][0])
        self.assertEqual(json.loads(mod.handle_result(["kitten", "999"], "", 7, boss)), None)


if __name__ == "__main__":
    unittest.main()
