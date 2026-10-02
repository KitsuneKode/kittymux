import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_git as G  # noqa: E402
import kittymux_place as P  # noqa: E402

HOME = "/home/someone"
REPO = G.GitInfo(top="/work/kittymux", branch="main", project="kittymux", worktree="")
WT = G.GitInfo(top="/work/kittymux/.worktrees/ui", branch="feat/ui", project="kittymux", worktree="ui")


def text(parts):
    return "".join(t for t, _r in parts)


class FactsTests(unittest.TestCase):
    def test_repo_root(self):
        self.assertEqual(P.facts("/work/kittymux", REPO, HOME), P.Facts("kittymux", "", "", "", "main"))

    def test_inside_a_repo(self):
        self.assertEqual(P.facts("/work/kittymux/src/ui", REPO, HOME).inner, "src/ui")

    def test_linked_worktree_keeps_the_main_project_name(self):
        f = P.facts("/work/kittymux/.worktrees/ui", WT, HOME)
        self.assertEqual((f.project, f.worktree, f.inner, f.branch), ("kittymux", "ui", "", "feat/ui"))

    def test_outside_a_repo_shows_the_folder_then_where_it_lives(self):
        self.assertEqual(P.facts(HOME + "/Documents/notes", None, HOME), P.Facts("notes", "", "", "~/Documents", ""))
        self.assertEqual(P.facts("/etc", None, HOME), P.Facts("etc", "", "", "/", ""))
        self.assertEqual(P.facts(HOME, None, HOME).project, "~")
        self.assertEqual(P.facts("/", None, HOME).project, "/")

    def test_empty_cwd_never_raises(self):
        self.assertEqual(P.facts("", None, HOME).project, "~")


class LayoutTests(unittest.TestCase):
    ICONS = dict(icon="F", branch_icon="B")

    def lay(self, f, width, **kw):
        return P.layout(f, width, cells=len, **self.ICONS, **kw)

    def test_everything_fits(self):
        f = P.facts("/work/kittymux/src/ui", REPO, HOME)
        self.assertEqual(self.lay(f, 40), [("F ", "icon"), ("kittymux", "project"), ("/src/ui", "inner"), ("  B main", "branch")])

    def test_branch_goes_first_then_the_path_then_the_icon(self):
        f = P.facts("/work/kittymux/src/ui", REPO, HOME)
        self.assertEqual(text(self.lay(f, 19)), "F kittymux/src/ui")      # no room for the branch
        self.assertEqual(text(self.lay(f, 15)), "F kittymux/…/ui")        # a shorter path variant
        self.assertEqual(text(self.lay(f, 10)), "F kittymux")             # no path at all
        self.assertEqual(text(self.lay(f, 8)), "kittymux")                # no icon
        self.assertEqual(text(self.lay(f, 6)), "kit…ux")                  # the name itself is cut in the middle

    def test_the_worktree_outranks_the_path(self):
        f = P.facts("/work/kittymux/.worktrees/ui/src", WT, HOME)
        out = self.lay(f, 13)
        self.assertIn(("kittymux", "project"), out)
        self.assertIn((":ui", "worktree"), out)
        self.assertNotIn("inner", [r for _t, r in out])

    def test_the_project_is_only_ever_middle_truncated(self):
        f = P.Facts("kittymux-landing-page", "", "", "", "")
        out = self.lay(f, 11)
        self.assertEqual(len(text(out)), 11)
        self.assertEqual(P.mid_ellipsis("kittymux-landing", 10), "kitty…ding")

    def test_every_width_fits_and_never_raises(self):
        for f in (P.facts("/work/kittymux/a/b/c/d", REPO, HOME), P.facts("/work/kittymux/.worktrees/ui/a/b", WT, HOME),
                  P.facts(HOME + "/Documents/notes", None, HOME), P.Facts("~", "", "", "", "")):
            for width in range(0, 60):
                parts = self.lay(f, width)
                self.assertLessEqual(len(text(parts)), max(width, 0), (f, width, parts))
                if width < 2:
                    self.assertEqual(parts, [])
                for _t, role in parts:
                    self.assertIn(role, P.ROLES)

    def test_non_repo_shows_where_when_there_is_room(self):
        f = P.facts(HOME + "/Documents/notes", None, HOME)
        self.assertEqual(self.lay(f, 30), [("F ", "icon"), ("notes", "project"), ("  ~/Documents", "where")])

    def test_hidden_project_shows_the_rest_without_a_dangling_separator(self):
        f = P.facts("/work/kittymux/src/ui", REPO, HOME)
        self.assertEqual(text(self.lay(f, 40, hide_project=True)), "src/ui  B main")
        root = P.facts("/work/kittymux", REPO, HOME)
        self.assertEqual(text(self.lay(root, 40, hide_project=True)), "B main")

    def test_wide_characters_are_measured_by_the_callers_width_function(self):
        f = P.Facts("日本語のプロジェクト", "", "", "", "")
        wide = lambda s: sum(2 if ord(c) > 0x2E80 else 1 for c in s)      # noqa: E731
        out = P.layout(f, 12, cells=wide)
        self.assertLessEqual(wide("".join(t for t, _r in out)), 12)


class ControlCharactersTests(unittest.TestCase):
    """A directory can be NAMED with an escape sequence (`mkdir $'\\e[31mx'`), and kitty's own title sanitiser leaves ESC (0x1b) and 0x1a-0x1f
    through: neither may reach a screen we draw on."""
    EVIL = "ev\x1b[31mil\x07\x9bdir\n\x7f"

    def test_no_control_character_survives_in_any_field(self):
        info = G.GitInfo(top="/work/" + self.EVIL, branch="main", project=self.EVIL, worktree=self.EVIL)
        for f in (P.facts("/work/" + self.EVIL + "/in\x1bner", info, HOME), P.facts("/x/" + self.EVIL + "/leaf" + self.EVIL, None, HOME)):
            for field in f:
                self.assertFalse(any(ord(c) < 32 or 127 <= ord(c) < 160 for c in field), repr(field))
        self.assertEqual(P.facts("/x/a\x1bb", None, HOME).project, "ab")

    def test_clean_keeps_ordinary_text_and_collapses_whitespace(self):
        self.assertEqual(P.clean("  héllo \t wörld  "), "héllo wörld")
        self.assertEqual(P.clean("日本語"), "日本語")
        self.assertEqual(P.clean("a\x1b[31mb"), "a[31mb")


class HiddenProjectKeepsTheWorktreeTests(unittest.TestCase):
    """A tab titled "kittymux" sitting in worktree `ui`: the project is already said, the WORKTREE is not — parallel
    agents on one repo must stay distinguishable."""

    def lay(self, f, width, **kw):
        return P.layout(f, width, icon="F", branch_icon="B", cells=len, **kw)

    def test_the_worktree_stays_when_only_the_project_is_hidden(self):
        f = P.facts("/work/kittymux/.worktrees/ui/src", WT, HOME)
        self.assertEqual(text(self.lay(f, 40, hide_project=True)), "ui/src  B feat/ui")
        root = P.facts("/work/kittymux/.worktrees/ui", WT, HOME)
        self.assertEqual(text(self.lay(root, 40, hide_project=True)), "ui  B feat/ui")

    def test_a_title_that_names_the_worktree_hides_it_too(self):
        f = P.facts("/work/kittymux/.worktrees/ui/src", WT, HOME)
        self.assertEqual(text(self.lay(f, 40, hide_project=True, hide_worktree=True)), "src  B feat/ui")

    def test_which_titles_name_the_worktree(self):
        f = P.Facts("kittymux", "ui", "", "", "x")
        self.assertTrue(P.worktree_named("kittymux:ui", f))
        self.assertFalse(P.worktree_named("kittymux", f))
        self.assertFalse(P.worktree_named("", f))
        self.assertFalse(P.worktree_named("kittymux:ui", P.Facts("kittymux", "", "", "", "x")))     # no worktree to name

    def test_it_fits_every_width_and_never_raises(self):
        f = P.facts("/work/kittymux/.worktrees/ui/a/b/c", WT, HOME)
        for hide_wt in (False, True):
            for width in range(0, 40):
                parts = self.lay(f, width, hide_project=True, hide_worktree=hide_wt)
                self.assertLessEqual(len(text(parts)), max(width, 0), (width, hide_wt, parts))


class RedundantAndCollidingTests(unittest.TestCase):
    def test_redundant(self):
        f = P.Facts("kittymux", "ui", "", "", "x")
        self.assertTrue(P.redundant("Kittymux", f))
        self.assertTrue(P.redundant("kittymux:ui", f))
        self.assertFalse(P.redundant("Claude: refactor", f))
        self.assertFalse(P.redundant("", f))

    def test_colliding(self):
        self.assertEqual(P.colliding({1: "Claude", 2: "claude ", 3: "zsh", 4: ""}), frozenset({1, 2}))
        self.assertEqual(P.colliding({}), frozenset())
        self.assertEqual(P.colliding({1: "a", 2: "b"}), frozenset())


class StyleTests(unittest.TestCase):
    PAL = types.SimpleNamespace(text=1, muted=2, faint=3)

    def test_only_the_project_is_bright_and_only_when_it_matters(self):
        quiet = P.style(self.PAL, active=False, hue=9, emphasised=False)
        self.assertEqual(quiet["project"], (2, False))
        self.assertEqual(quiet["icon"], (9, False))
        active = P.style(self.PAL, active=True, hue=9, emphasised=False)
        self.assertEqual(active["project"], (9, True))
        twin = P.style(self.PAL, active=False, hue=9, emphasised=True)
        self.assertEqual(twin["project"], (9, True))
        for role in ("worktree", "inner", "where", "branch"):
            self.assertFalse(active[role][1])

    def test_hue_off_uses_the_text_colour_and_never_the_hue(self):
        s = P.style(self.PAL, active=True, hue=None, emphasised=False)
        self.assertEqual(s["project"], (1, True))
        self.assertEqual(s["icon"], (2, False))


class PlaceRoomTests(unittest.TestCase):
    """The folder line must not eat the room of the pieces drawn after it (the layout picture, pane chips, "N panes")."""

    def test_nothing_after_it_means_all_the_room(self):
        self.assertEqual(P.place_room(21, []), 21)

    def test_what_follows_keeps_its_cells_and_its_separator(self):
        self.assertEqual(P.place_room(21, [8]), 11)             # 8-cell map + the 2-cell separator before it
        self.assertEqual(P.place_room(30, [8, 6]), 30 - 10 - 8)

    def test_the_folder_line_wins_when_keeping_them_would_squeeze_it_to_nothing(self):
        self.assertEqual(P.place_room(12, [8]), 12)             # 12 - 10 = 2 < the floor: the map is dropped, as before
        self.assertEqual(P.place_room(16, [8]), 6)              # exactly the floor still leaves room for the map
        self.assertEqual(P.place_room(15, [8]), 15)             # one cell under it: the folder line wins

    def test_a_default_bar_split_tab_keeps_both(self):
        f = P.Facts("kittymux", "", "", "", "main")
        room = P.place_room(21, [8])
        parts = P.layout(f, room, icon="F", branch_icon="B", cells=len)
        self.assertEqual("".join(t for t, _r in parts), "F kittymux")      # the branch gives way, the project stays
        self.assertLessEqual(len("".join(t for t, _r in parts)), room)


if __name__ == "__main__":
    unittest.main()
