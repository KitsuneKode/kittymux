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


def style(active=True, state="idle", brand=0xD97757):
    pal = types.SimpleNamespace(text=0xDDDDDD, muted=0x999999, faint=0x777777, alert=0xFF4444,
                                waiting=0xE6C384, working=0x7FB4CA, done=0x98BB6C, bg=0x2A2B3C)
    return PT.derive_colours_full(0xC0CAF5, pal.bg, pal, brand, active, state)


def render(f, columns, *, active=True, name="kittymux", folder=None, icon="G", state="", progress=None, brand=0xD97757):
    folder = folder if folder is not None else PT.folder_caption(f)
    mark = "" if not state or state == "idle" else {"working": "◐", "waiting": "!", "limited": "⊘", "error": "✕", "done": "✓"}.get(state, "")
    return PT.render(f, "", columns, style(active, state, brand), active=active, icon=icon, name=name, folder=folder,
                     state_mark=mark, progress=progress)


class LayoutTests(unittest.TestCase):
    def test_icon_name_folder_then_right_aligned_state(self):
        f = P.facts("/work/kittymux/src/ui", REPO, HOME)
        out = plain(render(f, 60, name="Claude", folder="/kittymux/src/ui", state="waiting"))
        self.assertTrue(out.startswith("G Claude /kittymux/src/ui"), out)
        self.assertTrue(out.endswith("!"), out)
        self.assertGreater(out.index("!"), out.index("ui"))

    def test_state_mark_survives_narrow_widths(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        for columns in range(20, 121):
            for state in STATES:
                if state == "idle":
                    continue
                out = plain(render(f, columns, state=state))
                self.assertLessEqual(len(out), max(columns, 4) if columns >= 4 else 4, (columns, state, out))
                mark = {"working": "◐", "waiting": "!", "limited": "⊘", "error": "✕", "done": "✓"}[state]
                self.assertTrue(out.rstrip().endswith(mark), (columns, state, out))

    def test_folder_truncates_before_the_name(self):
        f = P.facts("/work/kittymux/a/very/long/path/segment", REPO, HOME)
        long_folder = PT.folder_caption(f)
        out = plain(render(f, 28, name="short", folder=long_folder, state="working"))
        self.assertIn("…", out)
        self.assertTrue(out.startswith("G short"), out)
        self.assertTrue(out.endswith("◐"), out)

    def test_long_title_truncates_after_folder(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        out = plain(render(f, 24, name="a very long agent task title here", folder="/kittymux", state="done"))
        self.assertTrue(out.endswith("✓"), out)
        self.assertIn("…", out)

    def test_path_with_esc_is_cleaned_in_folder(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        out = plain(render(f, 80, folder="\x1b[41mRED\x07pwned"))
        self.assertNotIn("\x1b[41m", out)
        self.assertNotIn("\x07", plain(out))

    def test_progress_and_state_on_the_right(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        out = plain(render(f, 50, state="working", progress=("set", 62)))
        self.assertIn("62%", out)
        self.assertTrue(out.endswith("◐"), out)

    def test_active_name_is_bold_inactive_is_not(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        self.assertIn("\x1b[1m", render(f, 80, active=True))
        self.assertNotIn("\x1b[1m", render(f, 80, active=False))

    def test_error_uses_alert_on_the_name(self):
        f = P.facts("/work/kittymux", REPO, HOME)
        st = style(True, "error", 0xD97757)
        out = PT.render(f, "", 40, st, active=True, icon="G", name="failed task", folder="/kittymux", state_mark="✕")
        self.assertIn(_sgr(st["name"][0]), out)
        self.assertIn(_sgr(st["state"][0]), out)

    def test_plain_shell_uses_terminal_glyph(self):
        glyph, brand = PT.pane_icon(None, "/bin/zsh")
        self.assertEqual(glyph, PT._ICON_SHELL)
        self.assertIsNone(brand)


def _sgr(rgb: int) -> str:
    return f"\x1b[38;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"


class HelperTests(unittest.TestCase):
    def test_folder_caption_for_repo_worktree_and_home(self):
        self.assertEqual(PT.folder_caption(P.facts("/work/kittymux/src", REPO, HOME)), "/kittymux/src")
        self.assertEqual(PT.folder_caption(P.facts("/work/kittymux/.worktrees/ui", WT, HOME)), "kittymux:ui")
        self.assertEqual(PT.folder_caption(P.facts(HOME + "/Documents/notes", None, HOME)), "~/Documents")


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


if __name__ == "__main__":
    unittest.main()
