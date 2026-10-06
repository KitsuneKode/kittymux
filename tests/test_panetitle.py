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


def plain(s: str) -> str:
    return SGR.sub("", s)


def style(active=True):
    pal = types.SimpleNamespace(text=0xDDDDDD, muted=0x999999, faint=0x777777)
    return P.style(pal, active, 0x88CCAA, False)


def render(f, title, columns, active=True, **kw):
    return PT.render(f, title, columns, style(active), 0x999999, 0x555555, active=active, icon="F", branch_icon="B", **kw)


class RenderTests(unittest.TestCase):
    def test_agent_state_is_reserved_before_the_folder_at_narrow_widths(self):
        f = P.facts("/work/kittymux/long/path", REPO, HOME)
        for columns in (4, 8, 16, 40):
            out = plain(render(f, "long title", columns, state_mark="!", state_rgb=0x999999))
            self.assertTrue(out.startswith("! "), out)
            self.assertLessEqual(len(out), columns)

    def test_the_folder_line_then_the_panes_own_title(self):
        f = P.facts("/work/kittymux/src/ui", REPO, HOME)
        self.assertEqual(plain(render(f, "nvim README.md", 80)), "F kittymux/src/ui  B main  ·  nvim README.md")

    def test_the_project_is_bold_only_on_the_active_pane(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        self.assertIn("\x1b[1m", render(f, "", 80, active=True))
        self.assertNotIn("\x1b[1m", render(f, "", 80, active=False))

    def test_colours_are_24_bit_sgr_and_the_string_ends_reset(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        out = render(f, "", 80)
        self.assertIn("\x1b[38;2;136;204;170m", out)             # the project hue 0x88CCAA
        self.assertTrue(out.endswith("\x1b[0m"))

    def test_a_title_that_says_nothing_new_is_left_out(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        for title in ("", "zsh", "bash", "kitty", "KITTYMUX", "kittymux", "~/work/kittymux", "/work/kittymux", "sh"):
            self.assertEqual(plain(render(f, title, 80)), "F kittymux  B main", title)

    def test_it_never_exceeds_the_pane_width(self):
        for f in (P.facts("/work/kittymux/a/b/c/d", REPO, HOME), P.facts("/work/kittymux/.worktrees/ui/src", WT, HOME),
                  P.facts(HOME + "/Documents/notes", None, HOME), P.Facts("日本語のプロジェクト", "", "", "", "")):
            for title in ("", "nvim", "a very long title that goes on and on and on for ages " * 2):
                for columns in range(0, 130):
                    out = render(f, title, columns)
                    self.assertLessEqual(len(plain(out)), max(columns, 0) if columns >= 4 else 4, (columns, title[:10], plain(out)))

    def test_a_hostile_title_cannot_inject_terminal_sequences(self):
        """kitty's own sanitiser misses ESC; the line is parsed for SGR, so a title could recolour or break the bar."""
        f = P.facts("/work/kittymux", REPO, HOME)
        out = render(f, "\x1b[41mRED\x1b[0m\x07\x1b]0;pwned\x07 title", 80)
        body = plain(out)
        self.assertFalse(any(ord(c) < 32 or 127 <= ord(c) < 160 for c in body), repr(body))
        self.assertNotIn("\x1b[41m", out)

    def test_the_folder_line_wins_the_room_and_the_title_gets_what_is_left(self):
        f = P.facts("/work/kittymux/src", REPO, HOME)
        out = plain(render(f, "a long title here", 40))
        self.assertTrue(out.startswith("F kittymux/src  B main"), out)
        self.assertLessEqual(len(out), 40)
        narrow = plain(render(f, "a long title here", 22))
        self.assertNotIn("·", narrow)                               # no room for both: only the folder line

    def test_a_worktree_is_shown(self):
        f = P.facts("/work/kittymux/.worktrees/ui", WT, HOME)
        self.assertEqual(plain(render(f, "", 80)), "F kittymux:ui  B feat/ui")

    def test_outside_a_repo_it_says_where_the_folder_lives(self):
        f = P.facts(HOME + "/Documents/notes", None, HOME)
        self.assertEqual(plain(render(f, "", 80)), "F notes  ~/Documents")


class DeriveColoursTests(unittest.TestCase):
    BARS = {                                       # (title bar foreground, background): a dark bar, a light bar, a solid accent block
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
        """The same project gets the same hue in the tab bar and in its pane title bars (when the backgrounds read alike)."""
        fg, bg = self.BARS["dark"]
        style, _t, _d = PT.derive_colours(fg, bg, 0xBB9AF7, self.STATUS, "kittymux", True)
        self.assertEqual(style["icon"][0], T.project_hue("kittymux", 0xBB9AF7, bg, avoid=self.STATUS))


class DrawTests(unittest.TestCase):
    """The kitty-facing part, with the kitty modules faked."""

    def fake_kitty(self, cwd="/work/kittymux", columns=80, enabled=True):
        window = types.SimpleNamespace(child=types.SimpleNamespace(current_cwd=cwd, cwd=cwd), screen=types.SimpleNamespace(columns=columns))
        boss = types.SimpleNamespace(window_id_map={7: window})
        opts = types.SimpleNamespace(
            foreground=0xC0CAF5, background=0x1A1B26, active_border_color=0xBB9AF7, inactive_border_color=0x414868,
            window_title_bar_active_foreground=None, window_title_bar_active_background=None,
            window_title_bar_inactive_foreground=None, window_title_bar_inactive_background=None,
            active_tab_foreground=0xC0CAF5, active_tab_background=0x2A2B3C, inactive_tab_foreground=0x888888, inactive_tab_background=0x1A1B26,
            color_table=[0x808080] * 16)
        return types.SimpleNamespace(boss=boss, opts=opts, enabled=enabled)

    def run_draw(self, fk, data):
        with mock.patch.object(PT, "_kitty", return_value=(lambda: fk.boss, lambda: fk.opts, lambda c: int(c), len)), \
                mock.patch.object(PT, "_enabled", return_value=fk.enabled), \
                mock.patch.object(PT.kittymux_git, "info", return_value=REPO):
            return PT.draw(data)

    def data(self, **kw):
        base = dict(title="nvim", is_active=True, window_id=7, tab_id=1)
        base.update(kw)
        return types.SimpleNamespace(**base)

    def test_draws_the_folder_line_for_a_pane(self):
        out = self.run_draw(self.fake_kitty(), self.data())
        self.assertIn("kittymux", plain(out))
        self.assertIn("main", plain(out))
        self.assertTrue(plain(out).endswith("nvim"))

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


if __name__ == "__main__":
    unittest.main()
