import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "python"))
import kittymux_scan as KS  # noqa: E402


def load_helper():
    loader = importlib.machinery.SourceFileLoader("mux_notify", os.path.join(ROOT, "bin", "mux-notify"))
    spec = importlib.util.spec_from_loader("mux_notify", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class SafeIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_helper()

    def test_only_assets_pngs_and_plain_theme_names_pass(self):
        icon = os.path.join(ROOT, "assets", "notify", "claude.png")
        self.assertEqual(self.m.safe_icon(icon), os.path.realpath(icon))
        self.assertEqual(self.m.safe_icon("kitty"), "kitty")
        self.assertEqual(self.m.safe_icon("utilities-terminal"), "utilities-terminal")

    def test_everything_else_becomes_the_kitty_icon(self):
        for bad in ("", "/etc/passwd", "../../etc/passwd", os.path.join(ROOT, "assets", "..", "bin", "mux-notify"),
                    "http://evil/x.png", "a b", "x" * 80, "$(id)", "icon;rm -rf"):
            self.assertEqual(self.m.safe_icon(bad), "kitty", bad)

    def test_a_symlink_out_of_assets_does_not_escape(self):
        d = tempfile.mkdtemp()
        target = os.path.join(d, "secret.png")
        open(target, "w").write("x")
        link = os.path.join(self.m.ASSETS, "notify", "zz-escape-test.png")
        os.symlink(target, link)
        try:
            self.assertEqual(self.m.safe_icon(link), "kitty")
        finally:
            os.unlink(link)


class ArgumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_helper()

    def run_main(self, **over):
        args = dict(sock="unix:/tmp/mykitty-1", wid="7", pid="1", urgency="normal", cat="kittymux.attention",
                    icon="kitty", title="t", body="b")
        args.update(over)
        argv = ["mux-notify", args["sock"], args["wid"], args["pid"], args["urgency"], args["cat"], args["icon"],
                args["title"], args["body"]]
        with mock.patch.object(self.m.shutil, "which", return_value="x"), \
                mock.patch.object(self.m, "notify", return_value="") as notify:
            return self.m.main(argv), notify

    def test_valid_arguments_are_accepted(self):
        rc, notify = self.run_main()
        self.assertEqual(rc, 0)
        notify.assert_called_once()

    def test_bad_arguments_are_refused_before_anything_runs(self):
        for over in ({"wid": "7; id"}, {"pid": "x"}, {"urgency": "urgent"}, {"cat": "a b"}, {"cat": "$(x)"},
                     {"sock": "tcp:evil:1"}, {"sock": "/tmp/s"}):
            rc, notify = self.run_main(**over)
            self.assertEqual(rc, 2, over)
            notify.assert_not_called()

    def test_wrong_argument_count(self):
        with mock.patch.object(self.m.shutil, "which", return_value="x"):
            self.assertEqual(self.m.main(["mux-notify", "a"]), 2)


class ScannerSideTests(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"KITTYMUX_STATE": self.state}, clear=False)
        self.env.start()
        vars(KS._RT)["notify_log"] = []
        KS._RT.notified.clear()

    def tearDown(self):
        self.env.stop()

    def test_each_agent_gets_its_own_mark_and_unknowns_fall_back(self):
        self.assertTrue(KS._icon("claude").endswith("assets/notify/claude.png"))
        self.assertTrue(KS._icon("droid").endswith("assets/notify/droid.png"))
        self.assertIn(KS._icon("nonesuch"), ("kitty",) + (KS._icon("kittymux"),))
        self.assertEqual(KS._icon("../../etc/passwd"), KS._icon(""))              # never a path from outside

    def test_unknown_agents_wear_the_mascot(self):
        self.assertTrue(KS._icon("nonesuch").endswith("assets/notify/kittymux.png"))
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "assets", "brand", "mascot-64.png")))     # the CLI banner

    def test_every_logo_agent_has_an_icon_file(self):
        import kittymux_agents as A
        missing = [n for n, a in A.AGENTS.items() if ord(a.glyph[0]) >= 0xE000
                   and not os.path.isfile(os.path.join(ROOT, "assets", "notify", n + ".png"))]
        self.assertEqual(missing, [], "run tools/build-notify-icons.py")

    def test_a_global_budget_stops_a_flood(self):
        results = [KS._within_budget(100.0 + i * 0.1) for i in range(8)]
        self.assertEqual(results, [True] * KS.NOTIFY_BURST + [False] * (8 - KS.NOTIFY_BURST))
        self.assertTrue(KS._within_budget(100.0 + KS.NOTIFY_WINDOW + 5))            # it refills

    def test_private_mode_hides_screen_text(self):
        w = mock.Mock(id=3, is_focused=False, title="client-secret-project: rm -rf /prod")
        with mock.patch.dict(os.environ, {"KITTYMUX_NOTIFY": "1", "KITTYMUX_NOTIFY_PRIVATE": "1"}), \
                mock.patch.object(KS.shutil, "which", return_value="x"), \
                mock.patch.object(KS.subprocess, "Popen") as popen:
            KS._notify(w, "waiting", "Approve: rm -rf /prod?", "claude")
        argv = popen.call_args[0][0]
        self.assertNotIn("secret", " ".join(argv))
        self.assertNotIn("rm -rf", " ".join(argv))
        self.assertIn("claude needs you", argv[7])

    def test_normal_mode_carries_the_message_and_the_agents_icon(self):
        w = mock.Mock(id=3, is_focused=False, title="api")
        with mock.patch.dict(os.environ, {"KITTYMUX_NOTIFY": "1"}), \
                mock.patch.object(KS.shutil, "which", return_value="x"), \
                mock.patch.object(KS.subprocess, "Popen") as popen:
            KS._notify(w, "waiting", "Approve: rm -rf node_modules?", "codex")
        argv = popen.call_args[0][0]
        self.assertTrue(argv[6].endswith("assets/notify/codex.png"))
        self.assertEqual(argv[7], "api needs you")
        self.assertIn("Approve", argv[8])


if __name__ == "__main__":
    unittest.main()
