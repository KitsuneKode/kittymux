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


def load_sidebar():
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
         patch.dict(os.environ, KITTY_CONFIG_DIRECTORY=str(PYTHON)), \
         patch.object(sys, "argv", [str(PYTHON / "sidebar-kit.py")]):
        spec.loader.exec_module(mod)
    assert Path(mod.deck.__file__).resolve().parent == PYTHON
    return mod


class QueuedLoop:
    def __init__(self):
        self.callbacks = queue.Queue()

    def call_soon_threadsafe(self, fn, *args):
        self.callbacks.put((fn, args))

    def apply_one(self):
        fn, args = self.callbacks.get(timeout=1)
        fn(*args)


class SidebarTests(unittest.TestCase):
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
