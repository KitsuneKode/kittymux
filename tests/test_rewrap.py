"""kitty's methods that kittymux_barsize wraps are rebuilt by every load of the module, around kitty's OWN method.

Seen live 2026-11-12: a kitty started on e415a52 (before the pixel tab bar) and hot-reloaded for two days still ran the
TabBar.tab_id_at wrapper built by that first load: `install()` skipped anything already marked `_kittymux_wrapped`, and its
`_S.installed` flag survives reloads. The old wrapper's code had no pixel-bar lookup, so a click on a row activated the tab
whose old text cell sat there, not the row drawn in the picture.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

PYTHON = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(PYTHON))


def _old_load_wrapper(original, stale):
    """A hook as an older release built it: kitty's method held in its closure as `original`, no generation tag."""
    def wrapper(*args, **kwargs):
        stale.append(args)
        return original(*args, **kwargs)
    wrapper._kittymux_wrapped = True
    return wrapper


class RewrapTests(unittest.TestCase):
    def setUp(self):
        self.stale = []

        def tab_id_at(self, x, y):
            return 1

        class TabBar:
            is_vertical = True
            laid_out_once = True

            def tab_insertion_target_at(self, *a):         # kitty >= 0.49.2: the native drag path
                return None

            def _drop_spans(self, *a):
                return []

            def update_vertical(self, data, *a, **k):
                return None

        TabBar.tab_id_at = tab_id_at

        class TabManager:
            def handle_tab_bar_mouse(self, x, y, button, modifiers, action):
                return "kitty"

            def on_tab_drop_move(self, *a):
                return None

            def layout_tab_bar(self, *a, **k):
                return None

        class Boss:
            def drag_resize_start(self, *a):
                return "kitty"

            def drag_resize_update(self, x, y):
                return None

            def drag_resize_end(self):
                return None

        borders = types.ModuleType("kitty.borders")
        borders.set_borders_rects = lambda os_window_id, tab_id, rects: None
        self.kitty_own = {
            (TabBar, "tab_id_at"): TabBar.tab_id_at, (TabBar, "_drop_spans"): TabBar._drop_spans,
            (TabBar, "update_vertical"): TabBar.update_vertical,
            (TabManager, "handle_tab_bar_mouse"): TabManager.handle_tab_bar_mouse,
            (TabManager, "layout_tab_bar"): TabManager.layout_tab_bar,
            (Boss, "drag_resize_start"): Boss.drag_resize_start, (Boss, "drag_resize_update"): Boss.drag_resize_update,
            (Boss, "drag_resize_end"): Boss.drag_resize_end, (borders, "set_borders_rects"): borders.set_borders_rects,
        }
        for (owner, attr), fn in self.kitty_own.items():          # what a kitty that has run since an older release holds
            setattr(owner, attr, _old_load_wrapper(fn, self.stale))
        self.TabBar, self.TabManager, self.Boss, self.borders = TabBar, TabManager, Boss, borders
        mods = {
            "kitty": types.ModuleType("kitty"),
            "kitty.tab_bar": types.SimpleNamespace(TabBar=TabBar),
            "kitty.tabs": types.SimpleNamespace(TabManager=TabManager),
            "kitty.boss": types.SimpleNamespace(Boss=Boss),
            "kitty.borders": borders,
            "kitty.fast_data_types": types.SimpleNamespace(get_tab_being_dragged=lambda: (0, False, 0, 0)),
            "_kittymux_barsize_rt": types.SimpleNamespace(installed=True, edge_installed=True),   # an older load said "done"
        }
        p = patch.dict(sys.modules, mods)
        p.start()
        self.addCleanup(p.stop)

    def load(self):
        spec = importlib.util.spec_from_file_location("barsize_under_test", PYTHON / "kittymux_barsize.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def assert_rebuilt_by(self, m):
        for (owner, attr), own in self.kitty_own.items():
            fn = getattr(owner, attr)
            self.assertIs(fn.__globals__, m.__dict__, f"{attr}: still the hook an older load built")
            self.assertIs(getattr(fn, "_kittymux_original", None), own, f"{attr}: must wrap kitty's own method, not a wrapper")

    def test_hooks_an_older_release_built_are_rebuilt_around_kittys_own_methods(self):
        m = self.load()
        m.install()
        self.assert_rebuilt_by(m)

    def test_a_click_on_the_pixel_bar_asks_the_picture_after_an_upgrade(self):
        m = self.load()
        m.install()
        m.pxbar_tab_at = lambda tab_bar, x, y: 7                   # the picture says the row under the pointer is tab 7
        self.assertEqual(self.TabBar.tab_id_at(self.TabBar(), 120, 87), 7)
        self.assertEqual(self.stale, [], "the old hook still ran")

    def test_installing_again_in_the_same_load_changes_nothing(self):
        m = self.load()
        m.install()
        before = {k: getattr(*k) for k in self.kitty_own}
        m.install()
        for k, fn in before.items():
            self.assertIs(getattr(*k), fn)

    def test_every_reload_rebuilds_without_stacking_wrappers(self):
        self.load().install()
        m2 = self.load()                                          # the next config reload executes the module again
        m2.install()
        self.assert_rebuilt_by(m2)

    def test_a_wrapper_whose_original_cannot_be_found_is_left_alone(self):
        def opaque(*a):                                           # ours by its mark, but nothing says what it wraps
            return 3
        opaque._kittymux_wrapped = True
        self.TabBar.tab_id_at = opaque
        self.load().install()
        self.assertIs(self.TabBar.tab_id_at, opaque)              # never wrap a wrapper: two layers would run twice


if __name__ == "__main__":
    unittest.main()
