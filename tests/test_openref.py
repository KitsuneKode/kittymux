import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_layout as L  # noqa: E402
import kittymux_openref as R  # noqa: E402


class ParseTests(unittest.TestCase):
    def test_plain_references(self):
        self.assertEqual(R.parse_ref("src/app.py:42"), ("src/app.py", 42, None))
        self.assertEqual(R.parse_ref("./a/b.test.ts:7:13"), ("./a/b.test.ts", 7, 13))
        self.assertEqual(R.parse_ref("~/x/y.rs:1"), ("~/x/y.rs", 1, None))

    def test_rejects_what_is_not_a_reference(self):
        for text in ("", "app.py", "app.py:", "app.py:0", "app.py:x", "a b.py:3", "app.py:3 ; rm -rf ~", "$(x).py:3",
                     "`id`.py:1", "a.py:1\\n", "-e.py:3", "--eval.py:9", "a.py:12345678", "http://x.com:80"):
            self.assertIsNone(R.parse_ref(text), text)

    def test_open_actions_pattern_agrees_with_the_parser(self):
        import re
        rx = re.compile(R.OPEN_ACTIONS_URL)
        for text in ("src/app.py:42", "a.b.c:1:2", "~/x.rs:3"):
            self.assertTrue(rx.match(text) and R.parse_ref(text), text)
        for text in ("app.py", "a b.py:3", "x.py:1;ls"):
            self.assertFalse(rx.match(text), text)

    def test_detect_regex_is_the_same_in_the_layout_module(self):
        self.assertEqual(L.DETECT_URL_REGEX, R.DETECT_REGEX)


class ResolveTests(unittest.TestCase):
    def test_cwd_then_repo_root_and_only_regular_files(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "root", "src"))
            os.makedirs(os.path.join(d, "root", "sub"))
            open(os.path.join(d, "root", "src", "a.py"), "w").close()
            cwd = os.path.join(d, "root", "sub")
            self.assertEqual(R.resolve("src/a.py", cwd, os.path.join(d, "root")), os.path.join(d, "root", "src", "a.py"))
            self.assertIsNone(R.resolve("src/a.py", cwd, None))
            self.assertIsNone(R.resolve("src", os.path.join(d, "root"), None))          # a directory is not a file
            self.assertIsNone(R.resolve("../../../etc/nope.conf", cwd, None))

    def test_absolute_path(self):
        with tempfile.NamedTemporaryFile(suffix=".py") as f:
            self.assertEqual(R.resolve(f.name, "/", None), f.name)


class EditorTests(unittest.TestCase):
    def test_line_syntax_per_editor(self):
        self.assertEqual(R.editor_argv(["nvim"], "/a.py", 3, 5), ["nvim", "+3", "/a.py"])
        self.assertEqual(R.editor_argv(["hx"], "/a.py", 3, 5), ["hx", "/a.py:3:5"])
        self.assertEqual(R.editor_argv(["/usr/bin/code", "-r"], "/a.py", 3), ["/usr/bin/code", "-r", "--goto", "/a.py:3"])
        self.assertEqual(R.editor_argv(["kak"], "/a.py", 3, 2), ["kak", "/a.py", "+3:2"])
        self.assertEqual(R.editor_argv(["someeditor"], "/a.py", 3), ["someeditor", "/a.py"])
        self.assertEqual(R.editor_argv([], "/a.py", 3), [])

    def test_editor_choice_and_gui(self):
        self.assertEqual(R.default_editor({"VISUAL": "nvim -u NONE", "EDITOR": "nano"}), ["nvim", "-u", "NONE"])
        self.assertEqual(R.default_editor({"EDITOR": "nano"}), ["nano"])
        self.assertEqual(R.default_editor({"EDITOR": "bad 'quote"}, which=lambda n: "/x/" + n if n == "vi" else None), ["vi"])
        self.assertEqual(R.default_editor({}, which=lambda n: None), [])
        self.assertTrue(R.is_gui(["code"]) and R.is_gui(["/usr/bin/zed"]) and not R.is_gui(["nvim"]))


class GatedConfTests(unittest.TestCase):
    def test_nothing_for_a_kitty_that_does_not_know_the_options(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, L.DIM_FLAG), "w").close()
            self.assertEqual(L.gated_conf((0, 49, 1), d), "")
            self.assertEqual(L.gated_conf((0, 0, 0), d), "")          # version unknown: stay silent

    def test_detect_url_regex_on_0_49_2(self):
        with tempfile.TemporaryDirectory() as d:
            out = L.gated_conf((0, 49, 2), d)
            self.assertEqual(out, f"detect_url_regex {L.DETECT_URL_REGEX}\n")

    def test_dim_is_opt_in_and_gated(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertNotIn("custom_shaders", L.gated_conf((0, 49, 2), d, True))
            open(os.path.join(d, L.DIM_FLAG), "w").close()
            self.assertIn("custom_shaders dim-inactive-windows", L.gated_conf((0, 50, 0), d, True))
            self.assertNotIn("custom_shaders", L.gated_conf((0, 49, 1), d, True))      # that kitty would dim the tab bar too
            self.assertNotIn("custom_shaders", L.gated_conf((0, 49, 2), d, False))     # no slangc: the shader cannot build

    def test_slangc_detection(self):
        self.assertFalse(L.have_slangc({"SLANGC": "/nonexistent/slangc"}))
        self.assertFalse(L.have_slangc({"SLANGC": "'unterminated"}))
        self.assertTrue(L.have_slangc({"SLANGC": "sh -c x"}))

    def test_forced_version_env(self):
        old = os.environ.get("KITTYMUX_KITTY_VERSION")
        try:
            os.environ["KITTYMUX_KITTY_VERSION"] = "0.49.2"
            self.assertEqual(L.kitty_version(), (0, 49, 2))
            os.environ["KITTYMUX_KITTY_VERSION"] = "junk"
            self.assertEqual(L.kitty_version(), (0, 0, 0))
        finally:
            os.environ.pop("KITTYMUX_KITTY_VERSION", None) if old is None else os.environ.__setitem__("KITTYMUX_KITTY_VERSION", old)


if __name__ == "__main__":
    unittest.main()
