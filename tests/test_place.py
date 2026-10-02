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


if __name__ == "__main__":
    unittest.main()
