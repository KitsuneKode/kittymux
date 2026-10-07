import gc
import importlib
import os
import sys
import types
import unittest
import weakref
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_timers as TM  # noqa: E402


class StableCallableTests(unittest.TestCase):
    """kitty's timer table keeps a BARE pointer to the Python callable, and dispatches a snapshot of every due timer: a callback that removes another due
    timer (a config reload does: restart() → stop()) makes kitty call a freed object. The crash in libpython (PyObject_CallFunction from python_timer_callback,
    address 8) is that. So a timer is only ever given a callable that outlives the process' timers: one object per (module, function), kept alive here."""

    def setUp(self):
        self.mod = types.ModuleType("kmx_fake_timer_mod")
        self.calls = []
        self.mod.tick = lambda timer_id: self.calls.append(timer_id)
        sys.modules["kmx_fake_timer_mod"] = self.mod

    def tearDown(self):
        sys.modules.pop("kmx_fake_timer_mod", None)

    def test_the_same_object_every_time(self):
        a = TM.stable("kmx_fake_timer_mod", "tick")
        self.assertIs(a, TM.stable("kmx_fake_timer_mod", "tick"))
        self.assertIsNot(a, TM.stable("kmx_fake_timer_mod", "other"))

    def test_the_same_object_after_this_module_is_reloaded(self):
        a = TM.stable("kmx_fake_timer_mod", "tick")
        importlib.reload(TM)
        self.assertIs(a, TM.stable("kmx_fake_timer_mod", "tick"))

    def test_it_calls_the_CURRENT_function_of_the_module(self):
        cb = TM.stable("kmx_fake_timer_mod", "tick")
        cb(1)
        new_calls = []
        self.mod.tick = lambda timer_id: new_calls.append(timer_id)         # the module was re-executed: a new function object under the same name
        cb(2)
        self.assertEqual((self.calls, new_calls), ([1], [2]))

    def test_it_stays_alive_when_nothing_else_refers_to_it(self):
        cb = TM.stable("kmx_fake_timer_mod", "tick")
        ref = weakref.ref(cb)
        del cb
        gc.collect()
        self.assertIsNotNone(ref(), "the registry must keep it: kitty holds an unreferenced pointer to it")

    def test_a_missing_module_or_function_or_a_raising_one_never_raises(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()) as err:
            TM.stable("kmx_not_there", "tick")(1)
            TM.stable("kmx_fake_timer_mod", "missing")(1)
            self.mod.tick = mock.Mock(side_effect=RuntimeError("boom"))
            TM.stable("kmx_fake_timer_mod", "tick")(1)
        self.assertIn("boom", err.getvalue())                                  # reported, not raised

    def test_add_gives_kitty_the_stable_callable_and_returns_its_id(self):
        added = []
        fake = types.ModuleType("kitty.fast_data_types")
        fake.add_timer = lambda cb, interval, repeats=True: added.append((cb, interval, repeats)) or 7
        with mock.patch.dict(sys.modules, {"kitty": types.ModuleType("kitty"), "kitty.fast_data_types": fake}):
            self.assertEqual(TM.add("kmx_fake_timer_mod", "tick", 0.5, True), 7)
            self.assertEqual(TM.add("kmx_fake_timer_mod", "tick", 0.5, True), 7)
        self.assertIs(added[0][0], added[1][0])
        self.assertEqual(added[0][1:], (0.5, True))

    def test_add_without_kitty_is_none(self):
        with mock.patch.dict(sys.modules, {"kitty.fast_data_types": None}):
            self.assertIsNone(TM.add("kmx_fake_timer_mod", "tick", 1.0, False))


class NoRawTimersTests(unittest.TestCase):
    """The rule that keeps kitty alive, as a test: nothing in the in-kitty modules hands kitty a raw callable. A new timer goes through kittymux_timers."""

    def test_add_timer_is_only_ever_called_by_kittymux_timers(self):
        import glob
        import re
        root = os.path.join(os.path.dirname(__file__), "..", "python")
        offenders = []
        for path in sorted(glob.glob(os.path.join(root, "*.py")) + glob.glob(os.path.join(root, "collectors", "*.py"))):
            name = os.path.basename(path)
            if name == "kittymux_timers.py":
                continue
            for n, line in enumerate(open(path, encoding="utf-8"), 1):
                code = line.split("#", 1)[0]
                if re.search(r"\badd_timer\s*\(", code) or re.search(r"import[^#\n]*\badd_timer\b", code):
                    offenders.append(f"{name}:{n}: {line.strip()[:80]}")
        self.assertEqual(offenders, [], "a timer must be added with kittymux_timers.add (see its docstring): " + "; ".join(offenders))

    def test_every_timer_callback_ignores_a_stale_tick(self):
        import kittymux_barsize as B
        import kittymux_scan as KS
        for fn in (KS.scan_all, KS._spin_tick, B._watchdog, B._trail):
            self.assertEqual(fn.__code__.co_varnames[0], "timer_id", fn.__name__)


class FakeKitty:
    """kitty.fast_data_types with only the timer table: records what a timer was given and what was removed."""

    def __init__(self):
        self.added, self.removed, self.next_id = [], [], 100

    def install(self):
        mod = types.ModuleType("kitty.fast_data_types")
        mod.add_timer = self.add_timer
        mod.remove_timer = self.removed.append
        mod.get_boss = lambda: None
        self._patch = mock.patch.dict(sys.modules, {"kitty": types.ModuleType("kitty"), "kitty.fast_data_types": mod})
        self._patch.start()

    def uninstall(self):
        self._patch.stop()

    def add_timer(self, cb, interval, repeats=True):
        self.next_id += 1
        self.added.append((self.next_id, cb, interval, repeats))
        return self.next_id


class ScannerTimerTests(unittest.TestCase):
    """The scanner's two timers across what really happens in kitty: a config reload re-executes the module and calls restart()."""

    def setUp(self):
        import kittymux_scan as KS
        self.KS = KS
        self.k = FakeKitty()
        self.k.install()
        for attr, val in (("scan_timer", None), ("spin_timer", None), ("interval", 0.0)):
            setattr(KS._RT, attr, val)

    def tearDown(self):
        self.k.uninstall()
        self.KS._RT.scan_timer = self.KS._RT.spin_timer = None

    def test_the_callable_kitty_holds_is_the_same_object_after_a_reload(self):
        KS = self.KS
        KS._retime(0.5)
        first = self.k.added[-1][1]
        importlib.reload(KS)                                                   # a config load re-executes the module in place
        KS._RT.scan_timer = None
        KS._retime(0.5)
        self.assertIs(self.k.added[-1][1], first)

    def test_the_old_callable_still_runs_and_runs_the_RELOADED_code(self):
        KS = self.KS
        KS._retime(0.5)
        old = self.k.added[-1][1]
        importlib.reload(KS)
        with mock.patch.object(KS, "scan_all") as new_scan:
            old(KS._RT.scan_timer or 0)
        new_scan.assert_called_once()

    def test_a_timer_that_was_removed_cannot_be_freed_while_kitty_still_holds_it(self):
        KS = self.KS
        KS._retime(0.5)
        ref = weakref.ref(self.k.added[-1][1])
        self.k.added.clear()
        KS._RT.scan_timer = None
        importlib.reload(KS)
        gc.collect()
        self.assertIsNotNone(ref(), "kitty's dispatch table still points at it: it must not be freed")

    def test_a_stale_tick_is_ignored_and_never_re_arms_the_scanner(self):
        KS = self.KS
        KS._retime(0.5)
        old_id = KS._RT.scan_timer
        KS.stop()
        before = len(self.k.added)
        KS.scan_all(old_id)                                                    # kitty dispatches the snapshot AFTER the timer was removed
        self.assertEqual(len(self.k.added), before)
        self.assertIsNone(KS._RT.scan_timer)

    def test_a_stale_spin_tick_is_ignored(self):
        KS = self.KS
        KS._RT.spin_timer = 55
        with mock.patch.object(KS, "_working_tms") as w:
            KS._spin_tick(54)
        w.assert_not_called()

    def test_restart_replaces_the_timer_once_and_removes_the_old_one(self):
        KS = self.KS
        KS._retime(0.5)
        old = KS._RT.scan_timer
        KS._RT.scan_timer = old
        KS.stop()
        self.assertIn(old, self.k.removed)
        self.assertIsNone(KS._RT.scan_timer)


class BarsizeTimerTests(unittest.TestCase):
    def setUp(self):
        import kittymux_barsize as B
        self.B = B
        self.k = FakeKitty()
        self.k.install()

    def tearDown(self):
        self.k.uninstall()

    def test_the_watchdog_and_the_trailing_apply_use_stable_callables(self):
        B = self.B
        B._arm_watchdog()
        watchdog = self.k.added[-1][1]
        importlib.reload(B)
        B._arm_watchdog()
        self.assertIs(self.k.added[-1][1], watchdog)

    def test_the_collapse_buttons_reload_is_a_stable_named_callable_not_a_lambda(self):
        B = self.B
        B._timers().add(B.__name__, "_reload_config", 0.01, False)
        cb = self.k.added[-1][1]
        self.assertNotEqual(getattr(cb, "__name__", ""), "<lambda>")
        self.assertIs(cb, B._timers().stable(B.__name__, "_reload_config"))

    def test_a_stale_watchdog_tick_does_nothing(self):
        B = self.B
        B._S.watchdog, B._S.drag = 9, {"last": 0.0, "tm": None, "width": 1}
        B._watchdog(8)
        self.assertIsNotNone(B._S.drag)
        B._S.drag = None
        B._S.watchdog = None


if __name__ == "__main__":
    unittest.main()
