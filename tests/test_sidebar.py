import importlib.util
import json
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
        "kitty.key_encoding": dict(EventType=types.SimpleNamespace(PRESS="press", RELEASE="release")),
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

    def test_narrow_tab_strip_click_has_the_same_hit_boundary_as_drawing(self):
        s = self.sidebar()
        for cols in (16, 20, 26):
            s.screen_size.cols = cols
            s._view = "usage"
            with patch.object(s, "_ansi", return_value=""):
                s._tabs_line(cols)                               # drawing records the regions a click is tested against
            self.assertEqual({name for _a, _b, name in s._tab_regions}, {"agents", "usage", "inbox", "settings"})
            for x0, x1, name in s._tab_regions:
                self.assertLessEqual(x1, cols)
                for x in (x0, x1 - 1):
                    with patch.object(s, "_set_view") as select:
                        s.on_click(types.SimpleNamespace(cell_y=1, cell_x=x))
                        if name == "usage":
                            select.assert_not_called()           # already there
                        else:
                            select.assert_called_once_with(name)
            last = max(b for _a, b, _n in s._tab_regions)
            if last < cols:
                with patch.object(s, "_set_view") as select:
                    s.on_click(types.SimpleNamespace(cell_y=1, cell_x=last))
                    select.assert_not_called()                   # past the pills is not a pill
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

    # ---- a split tab's panes are listed only when you open it ------------------------------------------------------------------------
    def split_rows(self, current=1):
        D = self.m.deck
        def row(tab, win, panes, cur=False, status=""):
            pr = tuple(D.PaneData(win * 10 + j, state="waiting" if status == "waiting" and j == 1 else "") for j in range(panes)) if panes >= 2 else ()
            return D.RowData(tab, win, title=f"tab {tab}", pane_rows=pr, panes=max(1, panes), current=cur, status=status, win_ids=tuple(win * 10 + j for j in range(panes)))
        return [row(1, 1, 3, cur=current == 1), row(2, 2, 1), row(3, 3, 2, cur=current == 3), row(4, 4, 2)]

    def applied(self, rows=None):
        s = self.sidebar()
        with patch.object(s, "_request_preview"), patch.object(s, "_schedule_spin"):
            s._apply(self.m.Snapshot(rows or self.split_rows(), ""))
        return s

    def kinds(self, s):
        return [(i.kind, i.row) for i in s.snap.items if i.kind in ("row", "pane")]

    def test_the_first_look_opens_only_the_tab_you_are_in(self):
        s = self.applied()
        self.assertEqual(s._open, {1})
        self.assertEqual([k for k in self.kinds(s) if k[0] == "pane"], [("pane", 0)] * 3)         # tab 1's three panes; tab 3 and 4 are one line each
        s.finalize()

    def test_hovering_never_opens_a_tab_and_a_refresh_does_not_either(self):
        s = self.applied()
        before = list(s.snap.items)
        with patch.object(s, "_request_preview"):
            for y in range(2, 14):
                s.on_mouse_move(types.SimpleNamespace(cell_x=5, cell_y=y))
        self.assertEqual(s._open, {1})
        # an agent in a collapsed split starts asking: its row says so, the list does not move under the pointer
        rows = self.split_rows()
        rows[3].status = "waiting"
        rows[3].pane_rows[1].state = "waiting"
        with patch.object(s, "_request_preview"), patch.object(s, "_schedule_spin"):
            s._apply(self.m.Snapshot(rows, ""))
        self.assertEqual(s._open, {1})
        self.assertEqual([i.kind for i in s.snap.items], [i.kind for i in before])
        s.finalize()

    def test_keys_open_and_close_the_picked_tab_and_do_nothing_for_a_single_pane(self):
        s = self.applied()
        with patch.object(s, "_request_preview"):
            s.sel = 2                                                                           # tab 3: two panes, closed
            s.on_key_event(self.key("RIGHT"))
            self.assertEqual(s._open, {1, 3})
            s.on_key_event(self.key("LEFT"))
            self.assertEqual(s._open, {1})
            s.on_key_event(self.key("O"))
            self.assertEqual(s._open, {1, 3})
            s.on_key_event(self.key("O"))
            self.assertEqual(s._open, {1})
            s.sel = 1                                                                           # tab 2: one pane
            for k in ("RIGHT", "O", "LEFT"):
                s.on_key_event(self.key(k))
            self.assertEqual(s._open, {1})
        s.finalize()

    def test_a_click_on_the_marker_toggles_and_does_not_jump_but_a_click_elsewhere_does(self):
        s = self.applied()
        y_of = {}
        for off, it in self.m.deck.visible(s.snap.items, s.scroll, s._avail()):
            if it.kind == "row":
                y_of[it.row] = off + 2
        with patch.object(s, "_jump") as jump, patch.object(s, "_request_preview"):
            s.on_click(self.click(2, y_of[2] + 1))                                              # the ▸ of tab 3's context line
            self.assertEqual(s._open, {1, 3})
            jump.assert_not_called()
            s.on_mouse_move(types.SimpleNamespace(cell_x=8, cell_y=y_of[0]))                    # a click jumps to the row you are on: hovering selects it
            s.on_click(self.click(8, y_of[0]))                                                  # the title of tab 1
            jump.assert_called()
        s.finalize()

    def test_what_you_opened_survives_a_refresh_and_a_closed_tab_is_forgotten(self):
        s = self.applied()
        with patch.object(s, "_request_preview"):
            s._toggle_open(3, True)
        self.assertEqual(s._open, {1, 4})
        with patch.object(s, "_request_preview"), patch.object(s, "_schedule_spin"):
            s._apply(self.m.Snapshot(self.split_rows(), ""))
            self.assertEqual(s._open, {1, 4})
            s._apply(self.m.Snapshot(self.split_rows()[1:], ""))                                # tab 1 is gone
        self.assertEqual(s._open, {4})
        s.finalize()

    def test_a_search_keeps_the_open_state(self):
        s = self.applied()
        s.query = "tab"
        with patch.object(s, "_request_preview"):
            s._refilter()
        self.assertEqual(s.snap.open_tabs, frozenset({1}))
        self.assertEqual(len([k for k in self.kinds(s) if k[0] == "pane"]), 3)
        s.finalize()

    # ---- what the collector puts in a row: the title, the raw title, the project, the age -------------------------------------------
    def ls_json(self, title, cwd="/tmp/x/myproj", agent=True, extra_win=False):
        def win(i):
            return {"id": i, "title": title, "cwd": cwd, "pid": 0, "is_focused": i == 21, "cmdline": ["sh"],
                    "foreground_processes": [{"cmdline": ["claude"] if agent else ["zsh"]}]}
        wins = [win(21)] + ([win(22)] if extra_win else [])
        return json.dumps([{"id": 1, "is_focused": True, "tabs": [{"id": 2, "is_active": True, "title": title, "windows": wins,
                                                                  "active_window_history": [21]}]}])

    def collect(self, title, panes=None, tidy=True, **kw):
        c = self.m.Collector()
        with patch.object(self.m, "_rc", return_value=self.ls_json(title, **kw)), patch.object(self.m, "_panes_state", return_value=panes or {}), \
             patch.object(self.m, "_proc_ppids", return_value={}), patch.object(self.m, "_listeners", return_value=[]), \
             patch.object(self.m.kittymux_features, "enabled", return_value=tidy):
            return c.collect().rows[0]

    def test_a_reply_used_as_a_title_is_shown_as_the_project_but_stays_searchable(self):
        r = self.collect("I can't do that. I don't have access to the files")
        self.assertEqual(r.title, "myproj")
        self.assertEqual(r.raw_title, "I can't do that. I don't have access to the files")
        self.assertTrue(self.m.deck.matches(r, ["access"]))                          # the `/` search still finds it by what the agent said

    def test_a_real_title_is_cleaned_and_the_product_name_alone_is_the_project(self):
        self.assertEqual(self.collect("**Fix** the login redirect.").title, "Fix the login redirect")
        self.assertEqual(self.collect("Claude Code").title, "myproj")
        self.assertEqual(self.collect("Port Hyprland configs to Lua").title, "Port Hyprland configs to Lua")

    def test_with_the_switch_off_the_title_is_the_old_one(self):
        r = self.collect("I can't do that. I don't have access", tidy=False)
        self.assertEqual(r.title, "I can't do that. I don't have access")

    def test_a_plain_shell_tab_is_not_called_anything_but_what_it_says(self):
        r = self.collect("zsh", agent=False)
        self.assertEqual(r.title, "zsh")                                              # no agent: a program's own title is not a reply

    def test_how_long_an_agent_has_waited_reaches_the_row(self):
        now = time.monotonic()
        panes = {"21": {"state": "waiting", "agent": "claude", "ts_scan": now, "ts_state": now - 300, "wid": "21"}}
        r = self.collect("Fix login", panes=panes)
        self.assertEqual(r.status, "waiting")
        self.assertEqual(r.age, "5m")
        fresh = {"21": {"state": "waiting", "agent": "claude", "ts_scan": now, "ts_state": now - 5, "wid": "21"}}
        self.assertEqual(self.collect("Fix login", panes=fresh).age, "")              # under a minute is not news

    # ---- the ? card -----------------------------------------------------------------------------------------------------------------
    def test_question_mark_opens_the_card_and_any_key_closes_it_and_a_view_switch_clears_it(self):
        s = self.quiet(self.applied())                                   # a real _request_usage would run the collector against the real state dir
        s.draw_screen = Mock()
        s.on_key_event(self.key("?"))
        self.assertTrue(s._help)
        s.on_key_event(self.key("j"))
        self.assertFalse(s._help)                                        # one keypress closes it and is not also acted on
        self.assertEqual(s.sel, 0)
        s.on_key_event(self.key("/", mods=1))                            # shift+/ is how a US keyboard types ?
        self.assertTrue(s._help)
        s._set_view("usage")
        self.assertFalse(s._help)
        s.finalize()

    def test_question_mark_is_text_while_searching(self):
        s = self.applied()
        s.draw_screen = Mock()
        s.searching = True
        s.on_key_event(types.SimpleNamespace(type="press", key="?", mods=1, text="?"))
        self.assertFalse(s._help)
        s.finalize()

    def test_the_footer_has_a_question_mark_keycap_at_the_right_edge_that_a_click_presses(self):
        s = self.applied()
        s.draw_screen = Mock()
        with patch.object(s, "_ansi", return_value=""):
            s._footer([], [("a", "join", "A")], 30)
        slot = [r for r in s._foot_regions if r[2] == "?"]
        self.assertEqual(len(slot), 1)
        x0, x1, _tok, idx = slot[0]
        self.assertEqual((x1, x1 - x0), (30, 3))
        self.assertEqual(idx, self.m._HELP_SLOT)
        s._foot_y = 5
        s.on_click(self.click(x0 + 1, 5))
        self.assertTrue(s._help)
        s.on_click(self.click(3, 9))                                     # a click anywhere closes the card
        self.assertFalse(s._help)
        s.finalize()

    def test_a_footer_too_narrow_for_the_keycap_does_not_draw_it(self):
        s = self.applied()
        with patch.object(s, "_ansi", return_value=""):
            s._footer([], [("a", "join", "A")], 14)
        self.assertEqual([r for r in s._foot_regions if r[2] == "?"], [])
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

    # ---- the Usage and Inbox views -------------------------------------------------------------------------------------------------
    def quiet(self, s):
        s._request_usage = Mock()                          # a real one would spawn the collector against the real state dir
        return s

    def key(self, k, mods=0):
        return types.SimpleNamespace(type="press", key=k, mods=mods)

    def click(self, x, y):
        return types.SimpleNamespace(cell_x=x, cell_y=y)

    def providers(self, n=4):
        return {"ts": time.time(), "providers": [{"name": f"p{i}", "rows": [{"label": "5h", "pct": 10.0 * i}]} for i in range(n)]}

    def inbox_events(self):
        import kittymux_inbox as I
        out = []
        for i, kind in enumerate(("permission", "done", "limit")):
            e = I.make_event(kind, "claude", 7, "screen", time.time() - 60 * (i + 1), pid=1, tab="web", title=f"{kind} title")
            e.pop("op")
            out.append(e)
        return out

    def test_i_opens_the_inbox_and_escape_or_a_closes_it_without_quitting_the_panel(self):
        s = self.quiet(self.sidebar())
        s.quit_loop = Mock()
        with patch.object(self.m, "_PANEL", True):
            s.on_key_event(self.key("I"))
            self.assertEqual(s._view, "inbox")
            s.on_key_event(self.key("ESCAPE"))
            self.assertEqual(s._view, "agents")
            s.on_key_event(self.key("I"))
            s.on_key_event(self.key("A"))
            self.assertEqual(s._view, "agents")
            s.on_key_event(self.key("U"))
            s.on_key_event(self.key("I"))
            self.assertEqual(s._view, "inbox")
            s.on_key_event(self.key("I"))
            self.assertEqual(s._view, "agents")
        s.quit_loop.assert_not_called()
        s.finalize()

    def test_usage_provider_keys_wrap_and_digits_pick(self):
        s = self.sidebar()
        s._view, s._usage_data = "usage", self.providers()
        s.on_key_event(self.key("RIGHT"))
        self.assertEqual(s._usage_sel, 1)
        s.on_key_event(self.key("LEFT"))
        s.on_key_event(self.key("LEFT"))
        self.assertEqual(s._usage_sel, 3)                                # wrapped
        s.on_key_event(self.key("L"))
        self.assertEqual(s._usage_sel, 0)
        s.on_key_event(self.key("3"))
        self.assertEqual(s._usage_sel, 2)
        s.on_key_event(self.key("9"))
        self.assertEqual(s._usage_sel, 3)                                # past the end: the last one
        s.finalize()

    def test_usage_pick_with_no_data_does_nothing(self):
        s = self.sidebar()
        s._view = "usage"
        for k in ("RIGHT", "LEFT", "1", "TAB"):
            s.on_key_event(self.key(k))
        self.assertEqual(s._usage_sel, 0)
        s.finalize()

    def test_inbox_navigation_filters_and_clamping(self):
        s = self.sidebar()
        s._view, s._inbox = "inbox", self.inbox_events()
        s.on_key_event(self.key("J"))
        s.on_key_event(self.key("J"))
        s.on_key_event(self.key("J"))
        self.assertEqual(s._inbox_sel, 2)                                # clamped to the last card
        s.on_key_event(self.key("K"))
        self.assertEqual(s._inbox_sel, 1)
        s.on_key_event(self.key("TAB"))
        self.assertEqual((s._inbox_filter, s._inbox_sel), ("needs", 0))
        s.on_key_event(self.key("TAB", mods=1))
        self.assertEqual(s._inbox_filter, "all")
        s.on_key_event(self.key("4"))
        self.assertEqual(s._inbox_filter, "limits")
        s.finalize()

    def test_g_and_shift_g_and_home_end_jump_to_the_ends_of_the_inbox(self):
        s = self.sidebar()
        s._view, s._inbox = "inbox", self.inbox_events()
        s.on_key_event(self.key("G", mods=1))
        self.assertEqual(s._inbox_sel, 2)
        s.on_key_event(self.key("G"))
        self.assertEqual(s._inbox_sel, 0)
        s.on_key_event(self.key("END"))
        self.assertEqual(s._inbox_sel, 2)
        s.on_key_event(self.key("HOME"))
        self.assertEqual(s._inbox_sel, 0)
        s.finalize()

    def test_enter_jumps_with_the_cli_and_never_touches_the_agent(self):
        s = self.sidebar()
        s._view, s._inbox = "inbox", self.inbox_events()
        first = s._inbox_items()[0]
        with patch.object(self.m.subprocess, "Popen") as popen, patch.object(self.m, "_PANEL", True):
            s.on_key_event(self.key("ENTER"))
        argv = popen.call_args.args[0]
        self.assertEqual(argv[1:], ["inbox", "jump", first["id"]])
        self.assertTrue(argv[0].endswith("bin/kittymux"))
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        s.finalize()

    def test_x_dismisses_the_picked_event_and_shift_x_every_visible_one(self):
        s = self.sidebar()
        s._view, s._inbox = "inbox", self.inbox_events()
        order = [e["id"] for e in s._inbox_items()]
        with tempfile.TemporaryDirectory() as d, patch.object(self.m, "_STATE_DIR", Path(d)):
            s._inbox = self.inbox_events()
            import kittymux_inbox as I
            for e in s._inbox:
                I._append(I.store_path(d), dict(e, op="add"))
            s._inbox = I.load(d)
            order = [e["id"] for e in s._inbox_items()]
            s.on_key_event(self.key("X"))
            self.assertNotIn(order[0], [e["id"] for e in s._inbox_items()])
            self.assertEqual(len(s._inbox_items()), 2)
            s.on_key_event(self.key("X", mods=1))
            self.assertEqual(s._inbox_items(), [])
            self.assertEqual(s._inbox_sel, 0)
        s.finalize()

    def test_a_dismiss_with_nothing_listed_is_a_no_op(self):
        s = self.sidebar()
        s._view = "inbox"
        with patch.object(self.m.kittymux_inbox, "ack") as ack:
            s.on_key_event(self.key("X"))
            s.on_key_event(self.key("ENTER"))
        ack.assert_not_called()
        s.finalize()

    def test_clicking_the_tab_strip_switches_views_in_every_view(self):
        s = self.quiet(self.sidebar())
        s._tab_regions = [(0, 5, "agents"), (5, 12, "usage"), (12, 20, "inbox")]
        for view in ("agents", "usage", "inbox"):
            s._view = view
            s.on_click(self.click(6, 1))
            self.assertEqual(s._view, "usage")
            s.on_click(self.click(13, 1))
            self.assertEqual(s._view, "inbox")
            s.on_click(self.click(1, 1))
            self.assertEqual(s._view, "agents")
        s._view = "usage"
        s.on_click(self.click(25, 1))                                    # empty part of the strip: nothing
        self.assertEqual(s._view, "usage")
        s.finalize()

    def test_clicking_a_provider_tile_picks_it(self):
        s = self.sidebar()
        s._view, s._usage_data = "usage", self.providers()
        s._usage_regions = [(1, 9, 3, 7, 0), (10, 18, 3, 7, 1)]
        s.on_click(self.click(12, 5))
        self.assertEqual(s._usage_sel, 1)
        s.on_click(self.click(12, 9))                                    # below the tiles: nothing
        self.assertEqual(s._usage_sel, 1)
        s.finalize()

    def test_clicking_inbox_buttons_chips_and_cards(self):
        s = self.sidebar()
        s._view, s._inbox = "inbox", self.inbox_events()
        s._inbox_regions = ([(1, 8, 2, "all"), (9, 20, 2, "needs")], [(4, 9, 0), (10, 15, 1)], [(2, 8, 7, 1, "jump"), (9, 18, 7, 1, "dismiss")])
        s.on_click(self.click(10, 2))
        self.assertEqual(s._inbox_filter, "needs")
        s.on_click(self.click(3, 12))
        self.assertEqual(s._inbox_sel, 1)
        with patch.object(s, "_inbox_act") as act:
            s.on_click(self.click(3, 7))
            act.assert_called_once_with("jump", 1)
        s.finalize()

    def test_a_changed_inbox_redraws_only_when_the_badge_moved_or_the_inbox_is_up(self):
        s = self.sidebar()
        events = self.inbox_events()
        s.draw_screen.reset_mock()
        s._apply_side(None, events, 5.0)
        s.draw_screen.assert_called_once()                                # the badge went 0 -> 3
        s.draw_screen.reset_mock()
        s._apply_side(None, list(events), 6.0)
        s.draw_screen.assert_not_called()                                 # same unread count in the deck: no redraw
        s._view = "inbox"
        s._apply_side(None, list(events), 7.0)
        s.draw_screen.assert_called_once()
        s.finalize()

    def draw_ready(self, s):
        s._seg = lambda text, fg=None, bg=None, bold=False, dim=False: text
        s.write, s.flush = Mock(), Mock()

    def drawn(self, s):
        return "".join(c.args[0] for c in s.write.call_args_list)

    def test_the_usage_view_draws_end_to_end_and_publishes_clickable_regions(self):
        s = self.sidebar()
        s.draw_screen = type(s).draw_screen.__get__(s)
        self.draw_ready(s)
        s._view, s._usage_data = "usage", self.providers()
        with patch.object(self.m, "set_cursor_position", lambda x, y: f"@{x},{y}:"):
            s.draw_screen()
        out = self.drawn(s)
        self.assertIn("4 providers", out)
        self.assertIn("P0", out.upper())
        self.assertEqual(len(s._usage_regions), 4)
        for x0, x1, y0, y1, _ in s._usage_regions:
            self.assertTrue(0 <= x0 < x1 <= s.screen_size.cols and 2 <= y0 < y1 <= s.screen_size.rows)
        self.assertTrue(s._tab_regions and s._tab_regions[1][2] == "usage")
        s.finalize()

    def test_the_inbox_view_draws_end_to_end_and_publishes_regions(self):
        s = self.sidebar()
        s.draw_screen = type(s).draw_screen.__get__(s)
        self.draw_ready(s)
        s._view, s._inbox = "inbox", self.inbox_events()
        with patch.object(self.m, "set_cursor_position", lambda x, y: f"@{x},{y}:"):
            s.draw_screen()
        out = self.drawn(s)
        self.assertIn("unread", out)
        self.assertIn("Jump", out)
        chips, cards, buttons = s._inbox_regions
        self.assertEqual((len(chips), len(cards), len(buttons)), (4, 3, 2))        # all four filters even in a 32 column panel
        s.finalize()

    def test_an_empty_inbox_and_empty_usage_draw_without_error(self):
        s = self.sidebar()
        s.draw_screen = type(s).draw_screen.__get__(s)
        self.draw_ready(s)
        with patch.object(self.m, "set_cursor_position", lambda x, y: f"@{x},{y}:"):
            for view in ("inbox", "usage"):
                s._view = view
                s.draw_screen()
        self.assertIn("All clear", self.drawn(s))
        self.assertIn("Collecting local usage", self.drawn(s))
        s.finalize()

    def test_the_docked_panel_keeps_its_last_column_for_the_resize_handle(self):
        s = self.sidebar()
        s.draw_screen = type(s).draw_screen.__get__(s)
        self.draw_ready(s)
        s._view, s._usage_data = "usage", self.providers()
        with patch.object(self.m, "set_cursor_position", lambda x, y: f"@{x},{y}:"), patch.object(s, "_can_drag", return_value=True):
            s.draw_screen()
        out = self.drawn(s)
        self.assertIn(f"@{s.screen_size.cols - 1},0:▕", out)
        for chunk in out.split("@")[1:]:
            coords, _, text = chunk.partition(":")
            if coords.endswith(",0") and coords.startswith("0,"):
                self.assertEqual(len(text), s.screen_size.cols - 1)
        s.finalize()

    def test_overlay_defaults_to_parent(self):
        with patch.object(self.m, "_TARGET", ""), patch.object(self.m.os, "getppid", return_value=789), \
             patch.object(self.m.kittymux_agents, "load_panes", return_value={}) as load:
            self.m._panes_state([])
            self.assertEqual(Path(load.call_args.args[0]).name, "panes-789.json")


if __name__ == "__main__":
    unittest.main()
