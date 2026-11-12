import importlib
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_reload as R  # noqa: E402


class OrderTests(unittest.TestCase):
    """A running kitty keeps every module it ever imported. After an upgrade the tab bar must refresh ALL of them, dependencies first: a helper that is only
    imported lazily (the inbox, the prompts, the socket link…) used to stay at the version loaded hours earlier, so new code called old code."""

    def test_dependencies_come_first(self):
        deps = {"kittymux_scan": {"kittymux_state", "kittymux_inbox"}, "kittymux_inbox": set(), "kittymux_state": {"kittymux_theme"}, "kittymux_theme": set()}
        order = R.order(deps)
        for mod, needs in deps.items():
            for dep in needs:
                self.assertLess(order.index(dep), order.index(mod), f"{dep} must be reloaded before {mod}")
        self.assertEqual(sorted(order), sorted(deps))


    def test_a_checkout_stays_in_front_of_the_installed_config(self):
        # runpy has already put the checkout on the path. Putting the installed config in front of it
        # is how a trial kitty kept running the scanner from ~/.config/kitty, which never publishes the bar.
        path = ["/checkout/python", "/usr/lib/kitty"]
        out = R.prefer_own("/checkout/python/tab_bar.py", path, cfg="/home/installed/.config/kitty")
        self.assertEqual(out[0], "/checkout/python")
        self.assertEqual(out[1], "/home/installed/.config/kitty")
        self.assertEqual(out[2], "/usr/lib/kitty")

    def test_the_order_is_deterministic(self):
        deps = {"kittymux_b": {"kittymux_a"}, "kittymux_c": set(), "kittymux_a": set()}
        self.assertEqual(R.order(deps), R.order(dict(reversed(list(deps.items())))))

    def test_a_cycle_does_not_hang_or_drop_a_module(self):
        deps = {"kittymux_a": {"kittymux_b"}, "kittymux_b": {"kittymux_a"}, "kittymux_c": {"kittymux_c"}}
        self.assertEqual(sorted(R.order(deps)), ["kittymux_a", "kittymux_b", "kittymux_c"])

    def test_imports_are_read_from_the_source_and_only_kittymux_ones_that_are_loaded(self):
        src = "import os\nimport kittymux_inbox\nfrom kittymux_state import x\n    import kittymux_lazy  # noqa\n# import kittymux_comment\nimport kittymux_missing\n"
        self.assertEqual(R.imports_of(src, {"kittymux_inbox", "kittymux_state", "kittymux_lazy"}), {"kittymux_inbox", "kittymux_state", "kittymux_lazy"})


class ReloadAllTests(unittest.TestCase):
    def make(self, name, body):
        d = tempfile.mkdtemp()
        path = os.path.join(d, name + ".py")
        open(path, "w").write(body)
        sys.path.insert(0, d)
        self.addCleanup(lambda: (sys.path.remove(d), sys.modules.pop(name, None)))
        return importlib.import_module(name)

    def test_every_loaded_kittymux_module_is_reloaded_with_its_new_code(self):
        a = self.make("kittymux_rl_a", "VALUE = 1\n")
        b = self.make("kittymux_rl_b", "import kittymux_rl_a\nSEEN = kittymux_rl_a.VALUE\n")
        open(a.__file__, "w").write("VALUE = 2  # new\n")
        importlib.invalidate_caches()
        report = R.reload_all(sys.modules, only_prefix="kittymux_rl_")
        self.assertEqual(a.VALUE, 2)
        self.assertEqual(b.SEEN, 2, "the dependent must see the NEW dependency: it is reloaded after it")
        self.assertEqual(report["failed"], {})

    def test_one_module_that_fails_to_reload_does_not_stop_the_others(self):
        a = self.make("kittymux_rl_c", "VALUE = 1\n")
        b = self.make("kittymux_rl_d", "VALUE = 1\n")
        open(a.__file__, "w").write("raise RuntimeError('broken upgrade')\n")
        open(b.__file__, "w").write("VALUE = 5  # a different size, so a cached .pyc of the same second is not reused\n")
        importlib.invalidate_caches()
        report = R.reload_all(sys.modules, only_prefix="kittymux_rl_")
        self.assertIn("kittymux_rl_c", report["failed"])
        self.assertEqual(b.VALUE, 5)

    def test_a_module_without_a_file_is_skipped(self):
        sys.modules["kittymux_rl_fake"] = types.ModuleType("kittymux_rl_fake")
        self.addCleanup(lambda: sys.modules.pop("kittymux_rl_fake", None))
        report = R.reload_all(sys.modules, only_prefix="kittymux_rl_")
        self.assertNotIn("kittymux_rl_fake", report["reloaded"])


class WiringTests(unittest.TestCase):
    def test_the_tab_bar_uses_it_and_no_longer_keeps_its_own_short_list(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "python", "tab_bar.py"), encoding="utf-8").read()
        self.assertIn("kittymux_reload", src)
        self.assertNotIn("for _mod in (kittymux_theme", src)


class BootstrapTests(unittest.TestCase):
    def test_a_module_linked_alone_into_a_config_dir_still_finds_kittymux_reload(self):
        # A kitty config dir that links only some modules (the smoke rigs; a partial install): the module must find
        # kittymux_reload next to its REAL file before it can call prefer_own (CI's smoke_state: the bar failed to load).
        import subprocess
        import tempfile
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python", "kittymux_barsize.py")
        with tempfile.TemporaryDirectory() as cfg:
            os.symlink(os.path.realpath(src), os.path.join(cfg, "kittymux_barsize.py"))
            run = subprocess.run([sys.executable, "-I", "-c", "import runpy, sys; runpy.run_path(sys.argv[1])", os.path.join(cfg, "kittymux_barsize.py")],
                                 cwd="/", env={"KITTY_CONFIG_DIRECTORY": cfg, "PATH": os.environ.get("PATH", "")}, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr[-600:])

    def test_a_kitty_holding_an_older_kittymux_reload_still_loads_the_new_bar(self):
        # A kitty started before prefer_own existed keeps that kittymux_reload in sys.modules: `import` hands back the old
        # copy, and calling prefer_own on it raised before the bar reached its reload, so kitty drew its plain fallback bar
        # (2026-11-12, a kitty started on e415a52 hot-reloaded to 7601482). The bar must refresh kittymux_reload first.
        import importlib.util
        from unittest.mock import patch
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python", "kittymux_reload.py")
        spec = importlib.util.spec_from_file_location("kittymux_reload", here)
        stale = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stale)
        del stale.prefer_own
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from test_tab_bar_header import load_tab_bar
        with patch.dict(sys.modules, {"kittymux_reload": stale}):
            tb, _boss = load_tab_bar()
        self.assertTrue(callable(getattr(tb, "draw_tab", None)))


if __name__ == "__main__":
    unittest.main()
