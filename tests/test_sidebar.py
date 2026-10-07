import importlib.util
import os
import queue
import time
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

PYTHON = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(PYTHON))


def load_sidebar(cfg=None, argv0=None):
    modules = {}
    attrs = {
        "kittens.tui.handler": dict(Handler=type("Handler", (), {"atomic_update": staticmethod(lambda f: f)}),
                                   kitten_ui=lambda **kw: lambda f: f,
                                   result_handler=lambda **kw: lambda f: f),
        "kittens.tui.loop": dict(EventType=types.SimpleNamespace(MOVE="move", PRESS="press", RELEASE="release"),
                                Loop=Mock(), MouseButton=types.SimpleNamespace(LEFT=1)),
        "kittens.tui.operations": dict(MouseTracking=types.SimpleNamespace(full=1),
                                      set_cursor_position=Mock(), styled=Mock()),
        "kitty.fast_data_types": dict(wcswidth=len),
        "kitty.key_encoding": dict(EventType=types.SimpleNamespace(RELEASE="release")),
        "kitty.rgb": dict(Color=Mock()), "kitty.typing_compat": dict(BossType=object),
    }
    for name, values in attrs.items():
        modules[name] = types.ModuleType(name)
        modules[name].__dict__.update(values)
    spec = importlib.util.spec_from_file_location("sidebar_under_test", PYTHON / "sidebar-kit.py")
    mod = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), \
         patch.dict(os.environ, KITTY_CONFIG_DIRECTORY=str(cfg or PYTHON)), \
         patch.object(sys, "argv", [argv0 or str(PYTHON / "sidebar-kit.py")]):
        spec.loader.exec_module(mod)
    assert Path(mod.deck.__file__).resolve().parent == PYTHON
    return mod


class QueuedLoop:
    def __init__(self):
        self.callbacks = queue.Queue()

    def call_soon_threadsafe(self, fn, *args):
        self.callbacks.put((fn, args))

    def call_later(self, delay, fn, *args):
        handle = types.SimpleNamespace(cancelled=False)
        handle.cancel = lambda: setattr(handle, "cancelled", True)
        self.callbacks.put((lambda: None if handle.cancelled else fn(*args), ()))
        return handle

    def apply_one(self):
        fn, args = self.callbacks.get(timeout=1)
        fn(*args)


class SidebarTests(unittest.TestCase):
    def test_hover_waits_briefly_and_old_result_is_rejected_immediately(self):
        s = self.sidebar()
        with patch.object(s._preview_worker, "submit") as submit, patch.object(s._preview_worker, "invalidate") as invalidate:
            s.sel = 1
            s._request_preview(delay=True)
            submit.assert_not_called()
            invalidate.assert_called_once()
            s.asyncio_loop.apply_one()
            submit.assert_called_once()
            s.finalize()

    def test_usage_switch_and_refresh_do_not_dismiss_persistent_panel(self):
        s = self.sidebar()
        s.quit_loop = Mock()
        event = lambda k: types.SimpleNamespace(type="press", key=k, mods=0)
        with patch.object(s, "_request_usage") as fetch, patch.object(self.m, "_PANEL", True):
            s.on_key_event(event("U"))
            self.assertEqual(s._view, "usage")
            s.on_key_event(event("R"))
            fetch.assert_called_with(force=True)
            s.on_key_event(event("ESCAPE"))
            self.assertEqual(s._view, "agents")
            s.quit_loop.assert_not_called()
        s.finalize()

    def test_narrow_usage_navigation_click_has_the_same_hit_boundary_as_drawing(self):
        s = self.sidebar()
        s.screen_size.cols = 16
        s._view = "usage"
        labels = s._navigation_labels(16)
        self.assertLessEqual(sum(len(t) for t in labels), 16)
        with patch.object(s, "_set_view") as select:
            s.on_click(types.SimpleNamespace(cell_y=1, cell_x=len(labels[0])))
            select.assert_called_once_with("usage")
        s.finalize()

    def test_periodic_snapshot_keeps_hovered_pane_by_identity(self):
        s = self.sidebar()
        r = self.m.deck.RowData(1, 11, pane_rows=(self.m.deck.PaneData(11), self.m.deck.PaneData(12)))
        s.snap = self.m.Snapshot([r], "")
        s.sel, s._hover_pane, s.preview_for, s._first = 0, (0, 1), 12, False
        with patch.object(s, "_request_preview"), patch.object(s, "_schedule_spin"):
            s._apply(self.m.Snapshot([self.m.deck.RowData(2, 22), r], ""))
        self.assertEqual(s._hover_pane, (1, 1))
        s.finalize()

    def setUp(self):
        self.m = load_sidebar()

    def sidebar(self):
        s = self.m.Sidebar()
        s.screen_size = types.SimpleNamespace(rows=30, cols=32, cell_width=10)
        s.asyncio_loop = QueuedLoop()
        s.draw_screen = Mock()
        with patch.object(self.m, "_rc", return_value=""), \
             patch.object(s, "_request_refresh"), patch.object(s, "_schedule"):
            s.initialize()
        s.snap = self.m.Snapshot([self.m.deck.RowData(1, 11), self.m.deck.RowData(2, 22)], "")
        return s

    def test_absorb_keeps_the_shape_by_handing_over_to_the_join_kitten(self):
        """`a` pulls the selected tab into the tab you are in. One `detach-window` for all its windows splits the same pane again and again
        (slivers); the join kitten places each pane next to its old neighbour (tests/smoke_join.sh measures the result)."""
        s = self.sidebar()
        s.snap = self.m.Snapshot([self.m.deck.RowData(tab_id=1, win_id=10, win_ids=(10,), current=True),
                                  self.m.deck.RowData(tab_id=2, win_id=20, win_ids=(20, 21))], "")
        s.sel = 1
        calls = []
        with patch.object(self.m, "_rc", side_effect=lambda *a: calls.append(a) or ""), \
             patch.object(s, "quit_loop", create=True), patch.object(s, "_request_refresh"):
            s._absorb()
        self.assertFalse(any(a[0] == "detach-window" for a in calls), calls)
        kit = [a for a in calls if a[0] == "kitten"]
        self.assertEqual(len(kit), 1, calls)
        self.assertEqual(kit[0][1:3], ("--match", "id:20"))
        self.assertTrue(kit[0][3].endswith("join-kit.py"))
        self.assertEqual(kit[0][4:], ("--to", "1", "--side", "auto"))
        self.assertIn(("focus-window", "--match", "id:20"), calls)

    def test_runner_prefers_its_source_over_an_older_installed_helper(self):
        with tempfile.TemporaryDirectory() as cfg:
            Path(cfg, "kittymux_deck.py").write_text("raise RuntimeError('old installed helper selected')\n")
            with patch.dict(sys.modules):
                sys.modules.pop("kittymux_deck", None)
                m = load_sidebar(cfg=cfg, argv0="-c")
                self.assertEqual(Path(m.deck.__file__).resolve().parent, PYTHON)

    def test_the_join_kitten_is_found_next_to_the_modules_not_in_the_config_dir(self):
        """Inside a running kitten sys.argv[0] is not the script, and the config dir holds only links to the modules: join-kit.py must be found
        beside the REAL path of an imported module (the regression: smoke_sidebar.sh 'absorb' did nothing because the path fell back to <config dir>/join-kit.py)."""
        import tempfile
        with tempfile.TemporaryDirectory() as cfg:
            for name in os.listdir(PYTHON):
                if name.startswith("kittymux_") and name.endswith(".py"):
                    os.symlink(PYTHON / name, os.path.join(cfg, name))
            m = load_sidebar(cfg=cfg, argv0="kitten")
        self.assertEqual(Path(m._JOIN_KIT).resolve(), (PYTHON / "join-kit.py").resolve())
        self.assertTrue(os.path.exists(m._JOIN_KIT))

    def test_absorb_with_nothing_to_pull_does_nothing(self):
        s = self.sidebar()
        s.sel = 0                                                   # the tab you are in
        calls = []
        with patch.object(self.m, "_rc", side_effect=lambda *a: calls.append(a) or ""), patch.object(s, "quit_loop", create=True):
            s._absorb()
        self.assertEqual(calls, [])

    def test_preview_single_flight_and_aba_rejects_old_completion(self):
        s = self.sidebar()
        entered, release = threading.Event(), threading.Event()
        calls = []

        def rc(*args):
            calls.append(args[-1])
            if len(calls) == 1:
                entered.set()
                release.wait(2)
                return "old-A"
            return "new-A"

        with patch.object(self.m, "_rc", side_effect=rc):
            try:
                s._request_preview()
                self.assertTrue(entered.wait(1))
                s.sel = 1
                s._request_preview()
                s.sel = 0
                s._request_preview()
                self.assertEqual(calls, ["id:11"])
                release.set()
                s.asyncio_loop.apply_one()
                self.assertEqual(s.preview, [])
                s.asyncio_loop.apply_one()
                self.assertEqual(s.preview, ["new-A"])
                self.assertEqual(calls, ["id:11", "id:11"])
            finally:
                s.finalize()
                release.set()

    def test_periodic_same_pane_refresh_does_not_starve_a_slow_preview(self):
        s = self.sidebar()
        entered, release = threading.Event(), threading.Event()
        calls = []

        def rc(*args):
            calls.append(args[-1])
            entered.set()
            release.wait(2)
            return "completed slow preview"

        with patch.object(self.m, "_rc", side_effect=rc):
            try:
                s._request_preview()
                self.assertTrue(entered.wait(1))
                for _ in range(5):
                    s._apply(s.snap)
                release.set()
                s.asyncio_loop.apply_one()
                self.assertEqual(s.preview, ["completed slow preview"])
                self.assertEqual(calls, ["id:11"])
            finally:
                s.finalize()
                release.set()

    def test_reordered_event_loop_completions_cannot_replace_newer_preview(self):
        s = self.sidebar()
        with patch.object(self.m, "_rc", side_effect=["old-A", "new-A"]):
            try:
                s._request_preview()
                old_fn, old_args = s.asyncio_loop.callbacks.get(timeout=1)
                s._request_preview(force=True)
                new_fn, new_args = s.asyncio_loop.callbacks.get(timeout=1)
                new_fn(*new_args)
                old_fn(*old_args)
                self.assertEqual(s.preview, ["new-A"])
            finally:
                s.finalize()

    def test_finalize_drops_pending_preview_and_late_error(self):
        s = self.sidebar()
        entered, release = threading.Event(), threading.Event()
        calls = []

        def rc(*args):
            calls.append(args)
            entered.set()
            release.wait(2)
            raise RuntimeError("disconnected")

        with patch.object(self.m, "_rc", side_effect=rc):
            try:
                s._request_preview()
                self.assertTrue(entered.wait(1))
                s.sel = 1
                s._request_preview()
                s.finalize()
                s._request_preview(force=True)
                release.set()
                s.asyncio_loop.apply_one()
                self.assertEqual(s.preview, [])
                self.assertEqual(len(calls), 1)
            finally:
                release.set()
                s.finalize()

    def test_mouse_release_never_waits_and_final_resize_drains_on_finalize(self):
        s = self.sidebar()
        entered, release, final = threading.Event(), threading.Event(), threading.Event()
        calls = []

        def run(args, **kwargs):
            calls.append(args[-1])
            if len(calls) == 1:
                entered.set()
                release.wait(2)
            if args[-1] == "columns=56":
                final.set()
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        def mouse(kind, x):
            return types.SimpleNamespace(type=kind, pixel_x=x, buttons=1)

        with tempfile.TemporaryDirectory() as state, patch.object(self.m, "_PANEL", True), \
             patch.object(self.m, "_PANEL_SOCK", "/private/panel.sock"), \
             patch.object(self.m, "_STATE_DIR", Path(state)), \
             patch.object(self.m.subprocess, "run", side_effect=run):
            timer = threading.Timer(0.3, release.set)
            try:
                s.on_mouse_event(mouse("press", 310))
                s.on_mouse_event(mouse("move", 350))
                self.assertTrue(entered.wait(1))
                timer.start()  # rescue the old blocking implementation, without hanging this test
                start = time.monotonic()
                s.on_mouse_event(mouse("release", 550))
                elapsed = time.monotonic() - start
                s.finalize()
                release.set()
                self.assertTrue(final.wait(1))
                self.assertLess(elapsed, 0.1)
                saved = Path(state) / "panel-columns"
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    if saved.exists() and saved.read_text() == "56":
                        break
                    threading.Event().wait(0.005)
                self.assertEqual(saved.read_text(), "56")
                self.assertEqual(calls, ["columns=36", "columns=56"])
                self.assertFalse(s._drag)
            finally:
                release.set()
                timer.cancel()
                timer.join()
                s.finalize()

    def test_empty_snapshot_invalidates_a_queued_preview(self):
        s = self.sidebar()
        with patch.object(self.m, "_rc", return_value="old pane"):
            s._request_preview()
            fn, args = s.asyncio_loop.callbacks.get(timeout=1)
            s.snap = self.m.Snapshot([], "")
            s._request_preview()
            fn(*args)
            self.assertEqual(s.preview, [])
            self.assertEqual(s.preview_for, 0)
            s.finalize()

    def test_missing_or_invalid_target_pid_never_falls_back_to_panel_parent(self):
        for pid in ("", "0", "bad", "-1"):
            with patch.object(self.m, "_TARGET", "unix:/tmp/custom.sock"), \
                 patch.dict(os.environ, KITTYMUX_TARGET_PID=pid), \
                 patch.object(self.m.kittymux_agents, "load_panes") as load:
                self.assertEqual(self.m._panes_state([]), {})
                load.assert_not_called()

    def test_loop_error_finalizes_workers(self):
        handler = Mock()
        loop = Mock()
        loop.loop.side_effect = RuntimeError("UI failed")
        with patch.object(self.m, "Sidebar", return_value=handler), \
             patch.object(self.m, "Loop", return_value=loop), patch.object(self.m, "_log_error"):
            with self.assertRaisesRegex(RuntimeError, "UI failed"):
                self.m.main([])
            handler.finalize.assert_called_once()

    def test_panel_uses_verified_target_owner_not_its_parent(self):
        with patch.object(self.m, "_TARGET", "unix:/tmp/custom.sock"), \
             patch.dict(os.environ, KITTYMUX_TARGET_PID="123"), \
             patch.object(self.m.deck, "target_pid", return_value=123, create=True), \
             patch.object(self.m.kittymux_agents, "load_panes", return_value={"1": "target"}) as load:
            self.assertEqual(self.m._panes_state([]), {"1": "target"})
            self.assertEqual(Path(load.call_args.args[0]).name, "panes-123.json")

    def test_unverified_panel_never_loads_other_instance_state(self):
        with patch.object(self.m, "_TARGET", "unix:/tmp/custom.sock"), \
             patch.dict(os.environ, KITTYMUX_TARGET_PID="123"), \
             patch.object(self.m.deck, "target_pid", return_value=456, create=True), \
             patch.object(self.m.kittymux_agents, "load_panes") as load:
            self.assertEqual(self.m._panes_state([]), {})
            load.assert_not_called()

    def test_overlay_defaults_to_parent(self):
        with patch.object(self.m, "_TARGET", ""), patch.object(self.m.os, "getppid", return_value=789), \
             patch.object(self.m.kittymux_agents, "load_panes", return_value={}) as load:
            self.m._panes_state([])
            self.assertEqual(Path(load.call_args.args[0]).name, "panes-789.json")


if __name__ == "__main__":
    unittest.main()
