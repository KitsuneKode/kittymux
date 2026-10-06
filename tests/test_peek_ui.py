import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))


def load_peek():
    spec = importlib.util.spec_from_file_location("peek_ui", ROOT / "python/peek-kit.py")
    mod = importlib.util.module_from_spec(spec)
    attrs = {"kittens.tui.handler": dict(Handler=type("Handler", (), {"atomic_update": staticmethod(lambda f: f)}),
                                        kitten_ui=lambda **kw: lambda fn: fn, result_handler=lambda **kw: lambda fn: fn),
             "kittens.tui.loop": dict(Loop=Mock()),
             "kittens.tui.operations": dict(MouseTracking=types.SimpleNamespace(buttons_only=1), set_cursor_position=lambda *a: "", styled=lambda t, **kw: t),
             "kitty.fast_data_types": dict(wcswidth=len), "kitty.key_encoding": dict(EventType=types.SimpleNamespace(RELEASE="release")),
             "kitty.rgb": dict(Color=Mock()), "kitty.typing_compat": dict(BossType=object)}
    modules = {}
    for name, values in attrs.items():
        modules[name] = types.ModuleType(name)
        modules[name].__dict__.update(values)
    with patch.dict(sys.modules, modules), patch.object(sys, "argv", [str(ROOT / "python/peek-kit.py")]):
        spec.loader.exec_module(mod)
    return mod


class PeekTests(unittest.TestCase):
    def peek(self):
        m = load_peek()
        p = m.Peek(2)
        p.pal = types.SimpleNamespace(bar=0, text=1, faint=2, muted=3, line=4, waiting=5, working=6, alert=7, done=8, bg=0)
        p.screen_size = types.SimpleNamespace(cols=40, rows=35)
        p.write, p.flush = Mock(), Mock()
        p.card = {"state": "waiting", "agent": "", "tool": "", "title": "a" * 90, "reason": "",
                  "branch": "main", "cwd": "/work/" + "path/" * 20, "panes": [], "tail": ["screen"],
                  "shown_title": "chosen pane", "focus_id": 7, "tab_id": 2, "rects": []}
        return m, p

    def test_state_survives_long_title_and_full_details_can_be_scrolled(self):
        m, p = self.peek()
        p.draw_screen()
        writes = [a.args[0] for a in p.write.call_args_list]
        self.assertIn("waiting", writes[1] if writes[0] == "\x1b[2J" else "".join(writes[:2]))
        self.assertTrue(all(len(s) <= 40 for s in writes[1:]))
        self.assertIn("chosen pane", "".join(writes))

    def test_selected_preview_uses_its_own_directory_and_branch(self):
        m, p = self.peek()
        tab = {"title": "split", "active_window_history": [7],
               "windows": [{"id": 7, "title": "first", "cwd": "/work/first"},
                           {"id": 8, "title": "second", "cwd": "/work/second"}], "rects": []}
        with patch.object(m, "_rc", side_effect=[json.dumps(tab), "second screen"]), \
             patch.object(m.kittymux_agents, "load_panes", return_value={}), \
             patch.object(m.kittymux_git, "info", return_value=types.SimpleNamespace(branch="second-branch")) as git:
            card = m.collect(2, 8)
        self.assertEqual(card["cwd"], "/work/second")
        git.assert_called_once_with("/work/second")
        self.assertEqual(card["branch"], "second-branch")

    def test_zoomed_layout_does_not_renumber_hidden_panes(self):
        m, p = self.peek()
        p.card["panes"] = [{"id": wid, "agent": "", "glyph": "", "state": "", "title": "pane"} for wid in (7, 8, 9)]
        p.card["rects"] = [[9, 0, 0, 40, 30]]
        p.card["focus_id"] = 9
        with patch.object(m.deck, "numbered_layout") as diagram:
            p.draw_screen()
            diagram.assert_not_called()

    def test_terminal_spacing_survives_sanitizing(self):
        m, p = self.peek()
        rendered = p._line([(" │      │  ", 1, False)], 12, 0)
        self.assertTrue(rendered.startswith(" │      │  "))
        self.assertNotIn("\x1b", p._line([("safe\x1b[31m  line", 1, False)], 30, 0))

    def test_digit_previews_without_focus_then_enter_jumps_to_selected_pane(self):
        m, p = self.peek()
        p.card["panes"] = [{"id": 7}, {"id": 8}]
        event = lambda key: types.SimpleNamespace(type="press", key=key)
        p._refresh, p.quit_loop = Mock(), Mock()
        with patch.object(m, "_rc") as rc:
            p.on_key_event(event("2"))
            self.assertEqual(p._selected_id, 8)
            rc.assert_not_called()
            # Enter while the preview is still loading must use the requested pane.
            p.on_key_event(event("ENTER"))
            self.assertIn((("focus-window", "--match", "id:8"),), [tuple(x)[:1] for x in rc.call_args_list])


if __name__ == "__main__":
    unittest.main()
