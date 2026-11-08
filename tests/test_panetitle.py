import os
import re
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_git as G  # noqa: E402
import kittymux_panetitle as PT  # noqa: E402
import kittymux_place as P  # noqa: E402
import kittymux_theme as T  # noqa: E402

HOME = "/home/someone"
REPO = G.GitInfo(top="/work/kittymux", branch="main", project="kittymux", worktree="")
WT = G.GitInfo(top="/work/kittymux/.worktrees/ui", branch="feat/ui", project="kittymux", worktree="ui")
SGR = re.compile(r"\x1b\[[0-9;:]*m")
STATES = ("idle", "working", "waiting", "done", "limited", "error")


def plain(s: str) -> str:
    return SGR.sub("", s)


ACCENT = 0xBB9AF7
STATUS = (0xE6C384, 0xFF4444, 0x7FB4CA, 0x98BB6C)
MARKS = {"working": "◐", "waiting": "!", "limited": "⊘", "error": "✕", "done": "✓"}


def palette(accent=None):
    return types.SimpleNamespace(text=0xDDDDDD, muted=0x999999, faint=0x777777, alert=0xFF4444,
                                 waiting=0xE6C384, working=0x7FB4CA, done=0x98BB6C, bg=0x2A2B3C, accent=accent)


def style(active=True, state="idle", brand=0xD97757, project="", accent=None):
    pal = palette(accent)
    hue = None
    if accent is not None and project:
        hue = T.project_hue(project, accent, pal.bg, avoid=STATUS)
    return PT.derive_colours_full(0xC0CAF5, pal.bg, pal, brand, active, state, project=project, hue=hue)


def render(f, columns, *, active=True, name="kittymux", icon="G", state="", progress=None, brand=0xD97757, accent=ACCENT):
    mark = "" if not state or state == "idle" else MARKS.get(state, "")
    st = style(active, state, brand, project=f.project, accent=accent)
    return PT.render(f, columns, st, active=active, icon=icon, name=name, state=state, state_mark=mark, progress=progress)


def mentions(text: str, word: str) -> int:
    """How many times `word` stands alone (a following / or : still counts: `kittymux/src`, `kittymux:ui`)."""
    return len(re.findall(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", text))


class LayoutTests(unittest.TestCase):
    def test_task_then_place_with_branch_and_no_leading_slash(self):
        f = P.facts("/work/kittymux/src/ui", REPO, HOME)
        out = plain(render(f, 80, name="nvim src/main.rs", state="waiting"))
        self.assertTrue(out.startswith("G nvim src/main.rs  kittymux/src/ui"), out)
        self.assertNotIn("/kittymux", out)
        self.assertIn("main", out)
        self.assertIn(PT._ICON_BRANCH, out)
        self.assertTrue(out.endswith("!"), out)
        self.assertLess(out.index("nvim"), out.index("kittymux"))
        self.assertEqual(mentions(out, "kittymux"), 1, out)

    def test_a_shell_named_by_the_project_does_not_repeat_it(self):
        root = P.facts("/work/kittymux", REPO, HOME)
        out = plain(render(root, 80, name="kittymux"))
        self.assertEqual(mentions(out, "kittymux"), 1, out)
        self.assertIn("main", out)
        self.assertNotIn("kittymux kittymux", out)
        self.assertNotIn("kittymux  kittymux", out)
        inner = P.facts("/work/kittymux/src/ui", REPO, HOME)
        shown = plain(render(inner, 80, name="kittymux"))
        self.assertEqual(mentions(shown, "kittymux"), 1, shown)
        self.assertIn("src/ui", shown)
        self.assertNotIn("/src", shown)
        self.assertIn("main", shown)

    def test_a_worktree_shell_keeps_the_worktree_and_the_branch(self):
        f = P.facts("/work/kittymux/.worktrees/ui", WT, HOME)
        out = plain(render(f, 80, name="kittymux"))
        self.assertRegex(out, r"(?<![\w/:-])ui(?![\w/:-])")
        self.assertIn("feat/ui", out)
        self.assertNotIn("kittymux:ui", out)          # the project is the name; the worktree stands on its own
        self.assertEqual(mentions(out, "kittymux"), 1, out)
        task = plain(render(f, 80, name="nvim src/main.rs"))
        self.assertIn("kittymux:ui", task, task)
        self.assertIn("feat/ui", task)

    def test_home_folder_is_not_rewritten_as_an_absolute_project_path(self):
        f = P.facts(HOME + "/Documents/notes", None, HOME)
        out = plain(render(f, 80, name="notes"))
        self.assertEqual(mentions(out, "notes"), 1, out)
        self.assertIn("~/Documents", out)
        self.assertFalse(out.strip().startswith("/"), out)

    def test_the_active_project_uses_its_hue_and_an_unfocused_pane_recedes(self):
        f = P.facts("/work/kittymux/src/ui", REPO, HOME)
        hue = T.project_hue("kittymux", ACCENT, 0x2A2B3C, avoid=STATUS)
        active = render(f, 80, name="nvim src/main.rs", active=True)
        idle = render(f, 80, name="nvim src/main.rs", active=False)
        quiet = style(False, project="kittymux", accent=ACCENT)["project"][0]
        self.assertIn(_sgr(hue), active)
        self.assertNotIn(_sgr(hue), idle)
        self.assertIn(_sgr(quiet), idle)                       # the same hue, pulled back, so an unfocused pane still matches its tab
        self.assertNotEqual(quiet, hue)
        self.assertGreaterEqual(T.contrast(quiet, 0x2A2B3C), 3.0)
        self.assertIn("\x1b[1m", active)
        self.assertNotIn("\x1b[1m", idle)
        self.assertIn(_sgr(hue) + "\x1b[1mkittymux", active)   # the project word, not the task name, carries the hue
        self.assertIn(_sgr(style(True, project="kittymux", accent=ACCENT)["name"][0]) + "\x1b[1mnvim", active)
        shell = render(P.facts("/work/kittymux", REPO, HOME), 80, name="kittymux", active=True)
        self.assertIn(_sgr(hue) + "\x1b[1mkittymux", shell)
        shell_idle = render(P.facts("/work/kittymux", REPO, HOME), 80, name="kittymux", active=False)
        self.assertIn(_sgr(quiet) + "kittymux", shell_idle)
        self.assertNotIn("\x1b[1m", shell_idle)

    def test_hue_off_leaves_the_project_in_the_text_colour(self):
        f = P.facts("/work/kittymux/src/ui", REPO, HOME)
        hue = T.project_hue("kittymux", ACCENT, 0x2A2B3C, avoid=STATUS)
        st = style(True, "idle", project="kittymux", accent=None)
        out = PT.render(f, 80, st, active=True, icon="G", name="nvim src/main.rs")
        self.assertNotIn(_sgr(hue), out)
        self.assertIn("kittymux/src/ui", plain(out))

    def test_state_mark_survives_every_state_from_20_to_120(self):
        f = P.facts("/work/kittymux/src/ui", REPO, HOME)
        for columns in range(20, 121):
            for state in STATES:
                out = plain(render(f, columns, name="nvim src/main.rs", state=state))
                self.assertLessEqual(len(out), columns, (columns, state, out))
                if state == "idle":
                    self.assertFalse(any(out.rstrip().endswith(m) for m in MARKS.values()), (columns, state, out))
                else:
                    self.assertTrue(out.rstrip().endswith(MARKS[state]), (columns, state, out))

    def test_truncation_gives_up_the_path_then_the_branch_then_the_name(self):
        f = P.facts("/work/kittymux/a/very/long/path/segment", REPO, HOME)
        path_cut = branch_dropped = name_cut = False
        for columns in range(20, 121):
            out = plain(render(f, columns, name="short", state="working"))
            self.assertTrue(out.endswith("◐"), (columns, out))
            self.assertLessEqual(len(out), columns, (columns, out))
            branch_here = "main" in out
            if branch_here and "…" in out and "short" in out and "segment" in out and out.find("a/") < out.find("…"):
                path_cut = True                            # both ends of the path stay; the name and the branch are still whole
            if "short" in out and not branch_here:
                branch_dropped = True
            if "short" not in out:
                self.assertNotIn("main", out, out)        # the name is cut only after the branch is gone
                self.assertIn("…", out, out)
                name_cut = True
        self.assertTrue(path_cut)
        self.assertTrue(branch_dropped)
        long_name = "a very long agent task title here"
        for columns in range(20, 40):
            out = plain(render(f, columns, name=long_name, state="working"))
            self.assertTrue(out.endswith("◐"), (columns, out))
            if long_name not in out:
                self.assertNotIn("main", out, out)
                self.assertIn("…", out, out)
                self.assertTrue(out.startswith("G "), out)
                name_cut = True
        self.assertTrue(name_cut)

    def test_a_long_name_is_cut_in_the_middle_after_the_place_yields(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        out = plain(render(f, 24, name="a very long agent task title here", state="done"))
        self.assertTrue(out.endswith("✓"), out)
        self.assertIn("…", out)
        self.assertNotIn("main", out)
        self.assertIn("kittymux", out)

    def test_a_name_with_esc_is_cleaned(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        out = render(f, 80, name="\x1b[41mRED\x07pwned")
        self.assertNotIn("\x1b[41m", out)
        self.assertNotIn("\x07", plain(out))

    def test_progress_and_state_on_the_right(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        out = plain(render(f, 50, state="working", progress=("set", 62)))
        self.assertIn("62%", out)
        self.assertTrue(out.endswith("◐"), out)
        self.assertLess(out.index("main"), out.index("62%"))

    def test_a_state_pill_names_the_state_and_yields_to_the_mark_when_tight(self):
        f = P.facts("/work/kittymux/a/very/long/path/segment", REPO, HOME)
        words = {"working": "Working", "waiting": "Needs you", "done": "Finished", "error": "Error", "limited": "Limited"}
        for state, word in words.items():
            mark = MARKS[state]
            st = style(True, state, project=f.project, accent=ACCENT)
            fill, ink = PT.pill_colours(st["state"][0], 0x2A2B3C)
            self.assertGreaterEqual(T.contrast(ink, fill), 4.5)
            wide = PT.render(f, 100, st, active=True, icon="G", name="short", state=state, state_mark=mark,
                             progress=("set", 62), state_word=word, pill=(fill, ink))
            self.assertTrue(plain(wide).endswith("\ue0b6" + word + "\ue0b4"), plain(wide))
            self.assertIn(PT._sgr_bg(fill), wide)
            self.assertIn("62%", plain(wide))
            shrank = False
            for columns in range(14, 101):
                out = PT.render(f, columns, st, active=True, icon="G", name="short", state=state, state_mark=mark,
                                progress=("set", 62), state_word=word, pill=(fill, ink))
                text = plain(out)
                self.assertLessEqual(len(text), columns, (columns, text))
                self.assertTrue(text.endswith(mark) or text.endswith(word + "\ue0b4"), (columns, text))
                if text.endswith(mark):
                    shrank = True
                    self.assertNotIn("62%", text)           # the percent goes before the pill does
                    self.assertNotIn("\x1b[48;", out)
            self.assertTrue(shrank, state)

    def test_idle_has_no_pill(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        st = style(True, "idle", project=f.project, accent=ACCENT)
        out = PT.render(f, 80, st, active=True, icon="G", name="short", state="idle", state_mark="",
                        state_word="Idle", pill=(0x333333, 0xFFFFFF))
        self.assertNotIn("\ue0b6", out)

    def test_the_percent_yields_before_the_name_and_the_mark_stays(self):
        f = P.facts("/work/kittymux/a/very/long/path/segment", REPO, HOME)
        wide = plain(render(f, 80, name="short", state="working", progress=("set", 62)))
        self.assertIn("62%", wide)
        tight = None
        for columns in range(20, 40):
            out = plain(render(f, columns, name="short", state="working", progress=("set", 62)))
            self.assertTrue(out.endswith("◐"), (columns, out))
            if "62%" not in out and "short" in out:
                tight = out
                break
        self.assertIsNotNone(tight, "the percent should be dropped before the name is")

    def test_error_uses_alert_on_the_name(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        st = style(True, "error", 0xD97757, project="kittymux", accent=ACCENT)
        out = PT.render(f, 40, st, active=True, icon="G", name="failed task", state="error", state_mark="✕")
        self.assertIn(_sgr(st["name"][0]), out)
        self.assertIn(_sgr(st["state"][0]), out)
        self.assertNotIn(_sgr(st["project"][0]) + "failed", out)

    def test_plain_shell_uses_terminal_glyph(self):
        glyph, brand = PT.pane_icon(None, "/bin/zsh")
        self.assertEqual(glyph, PT._ICON_SHELL)
        self.assertIsNone(brand)

    def test_names(self):
        f = P.facts("/work/kittymux/src/ui", REPO, HOME)
        self.assertEqual(PT.pane_name("nvim src/main.rs", None, "", f), "nvim src/main.rs")
        self.assertEqual(PT.pane_name("sh", None, "", f), "kittymux")
        self.assertEqual(PT.pane_name("kittymux", None, "", f), "kittymux")
        self.assertEqual(PT.pane_name("ui", None, "", f), "kittymux")
        self.assertEqual(PT.pane_name("Claude Code", "claude", "", f), "Claude Code")
        self.assertEqual(PT.pane_name("Fix the header", "claude", "", f), "Fix the header")
        wt = P.facts("/work/kittymux/.worktrees/ui", WT, HOME)
        self.assertEqual(PT.pane_name("ui", None, "", wt), "kittymux")
        self.assertEqual(PT.pane_name("kittymux:ui", None, "", wt), "kittymux")


def _sgr(rgb: int) -> str:
    return f"\x1b[38;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"


class DeriveColoursTests(unittest.TestCase):
    BARS = {
        "dark": (0xC0CAF5, 0x2A2B3C),
        "light": (0x4C4F69, 0xD9DCE5),
        "accent-block": (0x1A1B26, 0x7AA2F7),
    }
    STATUS = (0xE0AF68, 0xF7768E, 0x7AA2F7, 0x9ECE6A)

    def test_every_colour_reads_on_the_real_title_bar_background(self):
        for name, (fg, bg) in self.BARS.items():
            for active in (True, False):
                style, title, dot = PT.derive_colours(fg, bg, 0xBB9AF7, self.STATUS, "kittymux", active)
                for role, (rgb, _bold) in style.items():
                    floor = 4.5 if role in ("project", "icon") and active else 3.0
                    self.assertGreaterEqual(T.contrast(rgb, bg), floor, (name, active, role, hex(rgb)))
                self.assertGreaterEqual(T.contrast(title, bg), 3.0, (name, active, "title"))
                self.assertGreaterEqual(T.contrast(dot, bg), 1.5, (name, active, "dot"))

    def test_the_project_keeps_its_colour_from_the_bar(self):
        fg, bg = self.BARS["dark"]
        style, _t, _d = PT.derive_colours(fg, bg, 0xBB9AF7, self.STATUS, "kittymux", True)
        self.assertEqual(style["icon"][0], T.project_hue("kittymux", 0xBB9AF7, bg, avoid=self.STATUS))


class DrawTests(unittest.TestCase):
    def fake_kitty(self, cwd="/work/kittymux", columns=80, enabled=True):
        window = types.SimpleNamespace(child=types.SimpleNamespace(current_cwd=cwd, cwd=cwd),
                                      screen=types.SimpleNamespace(columns=columns), progress=types.SimpleNamespace(state=types.SimpleNamespace(name="unset")))
        boss = types.SimpleNamespace(window_id_map={7: window})
        opts = types.SimpleNamespace(
            foreground=0xC0CAF5, background=0x1A1B26, active_border_color=0xBB9AF7, inactive_border_color=0x414868,
            window_title_bar_active_foreground=None, window_title_bar_active_background=None,
            window_title_bar_inactive_foreground=None, window_title_bar_inactive_background=None,
            active_tab_foreground=0xC0CAF5, active_tab_background=0x2A2B3C, inactive_tab_foreground=0x888888, inactive_tab_background=0x1A1B26,
            color_table=[0x808080] * 16)
        return types.SimpleNamespace(boss=boss, opts=opts, enabled=enabled, window=window)

    def run_draw(self, fk, data):
        with mock.patch.object(PT, "_kitty", return_value=(lambda: fk.boss, lambda: fk.opts, lambda c: int(c), len)), \
                mock.patch.object(PT, "_enabled", return_value=fk.enabled), \
                mock.patch.object(PT.kittymux_git, "info", return_value=REPO):
            return PT.draw(data)

    def data(self, **kw):
        base = dict(title="nvim", is_active=True, window_id=7, tab_id=1)
        base.update(kw)
        return types.SimpleNamespace(**base)

    def test_draws_name_and_folder_for_a_pane(self):
        out = self.run_draw(self.fake_kitty(), self.data())
        body = plain(out)
        self.assertIn("kittymux", body)
        self.assertIn("nvim", body)

    def test_off_switch_returns_nothing_so_kitty_shows_its_own_title(self):
        self.assertEqual(self.run_draw(self.fake_kitty(enabled=False), self.data()), "")

    def test_a_window_that_is_gone_or_has_no_directory_returns_nothing(self):
        self.assertEqual(self.run_draw(self.fake_kitty(), self.data(window_id=99)), "")
        self.assertEqual(self.run_draw(self.fake_kitty(cwd=""), self.data()), "")

    def test_it_never_raises(self):
        def boom():
            raise RuntimeError("kitty changed")
        with mock.patch.object(PT, "_kitty", side_effect=boom):
            self.assertEqual(PT.draw(self.data()), "")



class CloseQuestionTests(unittest.TestCase):
    """Closing a busy agent asks on the pane's own title bar, in the waiting colour, on one line (kittymux_closeguard)."""

    def setUp(self):
        import kittymux_closeguard as G
        self.G = G
        G.clear()
        self.addCleanup(G.clear)
        self.pal = T.from_colors({"background": 0x101014, "foreground": 0xE6E6EA})

    def test_only_the_asking_window_shows_the_question_and_it_fits(self):
        G = self.G
        self.assertEqual(PT.close_question(7, 80, self.pal, self.pal.bar), "")
        G.decide("window", 7, [7])
        G.set_text(G.question("Claude Code", "working", "ctrl+shift+w"), G.short("ctrl+shift+w"))
        line = PT.close_question(7, 80, self.pal, self.pal.bar)
        self.assertIn("Close Claude Code? It is working", line)
        self.assertEqual(PT.close_question(8, 80, self.pal, self.pal.bar), "")
        narrow = re.sub(r"\x1b\[[0-9;]*m", "", PT.close_question(7, 30, self.pal, self.pal.bar))
        self.assertEqual(narrow.strip(), "Close? Press again")                    # what to do survives a narrow pane
        tiny = re.sub(r"\x1b\[[0-9;]*m", "", PT.close_question(7, 12, self.pal, self.pal.bar))
        self.assertLessEqual(len(tiny), 12)
        self.assertTrue(tiny.rstrip().endswith("…"))
        self.assertNotIn("\n", line)


class ProgramPositionTests(unittest.TestCase):
    def test_an_argument_never_names_the_program(self):
        self.assertEqual(PT._title_from_cmdline(["git", "commit", "-m", "vim"]), "git")
        self.assertEqual(PT._title_from_cmdline(["git", "diff", "--", "src/nvim"]), "git")

    def test_wrappers_launchers_and_runtimes_are_seen_through(self):
        self.assertEqual(PT._title_from_cmdline(["sudo", "nvim", "x"]), PT._title_from_cmdline(["nvim", "x"]))
        self.assertEqual(PT._title_from_cmdline(["env", "-i", "hx"]), PT._title_from_cmdline(["hx"]))
        self.assertEqual(PT._title_from_cmdline(["mux-pty", "--", "codex"]), "Codex")
        self.assertEqual(PT._title_from_cmdline(["node", "/opt/x/claude"]), "Claude")
        self.assertEqual(PT._title_from_cmdline([]), "")


if __name__ == "__main__":
    unittest.main()
