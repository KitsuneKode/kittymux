import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class PaneControlsTests(unittest.TestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location("pane_controls", ROOT / "python/pane-kit.py")
        mod = importlib.util.module_from_spec(spec)
        handler = types.ModuleType("kittens.tui.handler")
        handler.result_handler = lambda **kw: lambda fn: fn
        with patch.dict(sys.modules, {"kittens.tui.handler": handler}):
            spec.loader.exec_module(mod)
        return mod

    def test_native_actions_and_target_identity(self):
        m = self.load()
        for choice, expected in (("h", ("move_window", "left")), ("r", ("layout_action", ("rotate", ()))),
                                 ("s", ("layout_action", ("rotate", ("180",)))), ("e", ("layout_action", ("equalize", ()))),
                                 ("a", ("swap_with_window", None))):
            tab = Mock()
            window = types.SimpleNamespace(id=7, tabref=lambda: tab)
            boss = Mock(window_id_map={7: window})
            m.handle_result([], "", 7, boss)
            args, kw = boss.choose.call_args
            self.assertEqual(kw["window"], window)
            args[1](choice)
            tab.set_active_window.assert_called_once_with(window)
            method, arg = expected
            getattr(tab, method).assert_called_once_with(*(() if arg is None else arg if isinstance(arg, tuple) else (arg,)))

    def test_closed_target_and_escape_do_not_move_anything(self):
        m = self.load()
        tab = Mock()
        window = types.SimpleNamespace(id=7, tabref=lambda: tab)
        boss = Mock(window_id_map={7: window})
        m.handle_result([], "", 7, boss)
        callback = boss.choose.call_args.args[1]
        callback("")
        tab.set_active_window.assert_not_called()
        boss.window_id_map.clear()
        callback("h")
        tab.move_window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
