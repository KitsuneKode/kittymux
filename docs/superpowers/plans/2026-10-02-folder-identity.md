# Folder identity (P0 probes + P1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every vertical tab says *where* it is — `project[:worktree]/inner  branch`, the project name highlighted, a stable per-project hue, look-alike tabs emphasised — with each piece switchable on its own, and three probes that decide the later side-sheet phases.

**Architecture:** Three new pure modules (`kittymux_features`, `kittymux_place`, and `project_hue` inside `kittymux_theme`) hold all logic and are unit-tested under system Python. `tab_bar.py` stays the only integrator: per-pass memoised lookups feed one `_Place` subtitle piece that is laid out at draw time (when the room left by the state word is known). `kittymux features` is the CLI; flag files + env vars are the switches (same convention as `notify-off`).

**Tech Stack:** Python 3 (kitty's bundled interpreter in the bar, system Python in tests), bash smoke rigs on Xvfb, kitty 0.49.2.

**Spec:** `docs/superpowers/specs/2026-10-02-folder-identity-and-side-sheet-design.md`. This plan implements P0 (probes a and c; b and d are a manual script) and P1/P1b/P1c plus the pluggability layer (3c). **P2 (side sheet), P3 (hover), P4 (pane title bars) and P5 (community polish beyond what is below) get their own plans once the probes report** — they depend on the probe answers, and P1 ships and is useful without them.

**Execution order: 1, 2, 3, 4, 6, 5, 7, 8, 9, 10** — Task 5's rig drives the `kittymux features` command that Task 6 creates, so do Task 6 first.

**Dry run.** Before this plan was handed over, its code was applied to a scratch copy and run: the 36 new unit tests pass, `bin/kittymux features` prints the six rows, `tab_bar.py` compiles, `tests/smoke_place.sh` **passes in a real Xvfb kitty** (twins emphasised, hidden duplicates, every switch on its own, all-off is the old line, no other kitty touched), and the draw cost measured +0.011 ms per tab draw with 23 tabs. Two things the dry run taught the rig, now baked in: a real window size (`xdotool windowsize`) and a saved per-instance layout are needed or the bar is only 16 columns wide and the path and branch never fit. **Probe answers from the same dry run (Xvfb, kitty 0.49.2, real pointer events — re-run in Task 9 to record them):** (a) idle mouse motion over the tab bar does **not** reach Python (0 of 8 moves; only press/release arrive) → hover cannot open anything from the bar itself, so P3 is limited to hover inside the sheet/docked panel; (c) `draw_window_title` receives `WindowTitleData(has_activity_since_last_focus, is_active, needs_attention, tab_id, title, window_id)` → P4 is feasible through `window_id`. (b) panel placement is compositor-only and still needs the person to run `tests/probe_panel.sh` on Hyprland. Not dry-run: the six `smoke_*.sh` module-list edits and Task 8's demo/README.

## Global Constraints

- No hardcoded palettes: every colour derives from the live kitty theme (`kittymux_theme`); never put a palette in `tab_bar.py`.
- Draw path: no per-tab `os.stat`, file read or subprocess — new lookups are `@_per_pass` helpers (`tab_bar._per_pass`, reset when tab 1 is drawn). Budget: draw_tab p50 within **+0.05 ms per tab** of today at 23 tabs.
- No module-level timer state; helper modules reload on every config load (`tab_bar.py` reload tuple).
- Never run git on kitty's main thread: only `kittymux_git.info` (reads `.git/HEAD`) is used on the draw path.
- Never log or store screen text; the bar dump hook (`KITTYMUX_BAR_DUMP=1`) records only our own subtitle pieces and exists for tests.
- A test must never touch another kitty: rigs use their own socket and end with the `others()` tripwire (copy from `tests/smoke_spawn.sh`).
- Never restart live kitties; work only in `.worktrees/folder-sheet`; apply to live by `kittymux upgrade` after merging. Record `kitty @ ls` window counts before/after.
- No credential-shaped values anywhere (tests build fixtures from filler; paths in tests are synthetic).
- A new key chord is not introduced in this plan. Anything that changes a key updates `kittymux-keys.conf.tpl` AND the README key table in one commit.
- Contrast: every text role ≥ 4.5:1 (hue) on the tab's row background; hue is a second cue, never the only one.
- Python files run under kitty's bundled interpreter — `kitty.*` is not importable under system Python, so the three new modules import nothing from kitty.

## Review Focus

1. **A repo path with a wide-character or very long project name at a very narrow bar** — expect a middle-ellipsis name that never exceeds the room and never raises (`test_every_width_fits_and_never_raises`, `test_wide_characters…`).
2. **A tab whose cwd is empty/unreadable (a window that just closed, a process with no `/proc` cwd)** — expect a `~` project, no crash, no blank row (`test_empty_cwd_never_raises`; smoke tab 4 covers a non-repo folder).
3. **A linked worktree of a repo** — expect `project:worktree` so parallel agents on one repo stay distinguishable (`test_the_worktree_outranks_the_path`).
4. **Two tabs titled the same in different projects, then a tab closed or renamed** — expect emphasis to appear and disappear on the next redraw without a restart (`smoke_place.sh` steps 2 and 3).
5. **A user who turns everything off, or sets an env var to garbage** — expect today's subtitle exactly, and garbage ignored (`test_garbage_env_is_ignored`; smoke step 5 compares the legacy rows).

---

## File structure

| File | Change | Responsibility |
|---|---|---|
| `python/kittymux_features.py` | create | which optional pieces are on (env > flag file > default), presets |
| `python/kittymux_place.py` | create | pure: facts about a cwd, laid-out pieces, collisions, role styles |
| `python/kittymux_theme.py` | modify | `hue_slot`, `project_hue` |
| `python/tab_bar.py` | modify | imports/reload, per-pass helpers, `_Place` piece, subtitle + rail wiring, dump hook |
| `bin/kittymux` | modify | `features` command, doctor section, demo twins |
| `tests/test_features.py`, `tests/test_place.py`, `tests/test_hue.py` | create | unit tests |
| `tests/test_kittymux_cli.py` | modify | CLI tests for `features` |
| `tests/smoke_place.sh` | create | real-kitty rig: the folder line, twins, switches |
| `tests/profile_bar.sh` | create | draw-cost rig (N tabs + a spinner), compare two trees |
| `tests/smoke_{click,drag,resize,native,sidebar,state}.sh` | modify | add the two new modules to their symlink lists |
| `tests/probe_motion.py`, `tests/probe_motion.sh`, `tests/probe_titledata.sh`, `tests/probe_panel.sh` | create | P0 probes |
| `docs/compatibility.md`, `docs/testing.md`, `README.md`, `CHANGELOG.md` | modify | honest results, switches, docs |
| `docs/superpowers/specs/…-design.md` | modify | three small corrections found while planning |

Run everything from `/home/kitsunekode/Projects/kittymux/.worktrees/folder-sheet`.

---

### Task 1: `kittymux_features` — the switchboard

**Files:**
- Create: `python/kittymux_features.py`
- Test: `tests/test_features.py`

**Interfaces:**
- Produces: `FEATURES: tuple[str, ...]`, `DEFAULTS: dict[str, bool]`, `PRESETS: dict[str, frozenset[str]]`, `state_dir(env=None) -> str`, `source(name, sdir=None, env=None) -> (bool, "env"|"flag"|"default")`, `enabled(name, sdir=None, env=None) -> bool`, `resolve_all(sdir=None, env=None) -> dict[str, bool]`, `set_feature(sdir, name, on) -> None`, `apply_preset(sdir, preset) -> None`. Unknown names/presets raise `ValueError`.

- [ ] **Step 1: Write the failing test** — create `tests/test_features.py`:

```python
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_features as F  # noqa: E402


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.sdir = tempfile.mkdtemp()

    def test_defaults(self):
        self.assertEqual(F.resolve_all(self.sdir, {}), F.DEFAULTS)
        self.assertTrue(F.enabled("hue", self.sdir, {}))
        self.assertFalse(F.enabled("hover", self.sdir, {}))

    def test_flag_files_flip_the_default(self):
        open(os.path.join(self.sdir, "hue-off"), "w").close()
        open(os.path.join(self.sdir, "hover-on"), "w").close()
        self.assertEqual(F.source("hue", self.sdir, {}), (False, "flag"))
        self.assertEqual(F.source("hover", self.sdir, {}), (True, "flag"))

    def test_env_beats_flag(self):
        open(os.path.join(self.sdir, "hue-off"), "w").close()
        self.assertEqual(F.source("hue", self.sdir, {"KITTYMUX_HUE": "on"}), (True, "env"))
        self.assertEqual(F.source("folder", self.sdir, {"KITTYMUX_FOLDER": "0"}), (False, "env"))

    def test_garbage_env_is_ignored(self):
        self.assertEqual(F.source("hue", self.sdir, {"KITTYMUX_HUE": "banana"}), (True, "default"))

    def test_off_flag_wins_over_on_flag(self):
        for n in ("sheet-off", "sheet-on"):
            open(os.path.join(self.sdir, n), "w").close()
        self.assertFalse(F.enabled("sheet", self.sdir, {}))

    def test_unknown_feature_is_rejected(self):
        for call in (lambda: F.enabled("nope", self.sdir, {}), lambda: F.set_feature(self.sdir, "nope", True)):
            with self.assertRaises(ValueError):
                call()

    def test_set_feature_round_trip_leaves_no_file_at_the_default(self):
        F.set_feature(self.sdir, "hue", False)
        self.assertEqual(os.listdir(self.sdir), ["hue-off"])
        F.set_feature(self.sdir, "hue", True)
        self.assertEqual(os.listdir(self.sdir), [])
        F.set_feature(self.sdir, "hover", True)
        self.assertEqual(os.listdir(self.sdir), ["hover-on"])
        F.set_feature(self.sdir, "hover", False)
        self.assertEqual(os.listdir(self.sdir), [])

    def test_presets(self):
        F.apply_preset(self.sdir, "minimal")
        self.assertEqual(F.resolve_all(self.sdir, {}),
                         {"folder": True, "hue": False, "collide": False, "sheet": False, "hover": False, "panetitle": False})
        F.apply_preset(self.sdir, "full")
        self.assertTrue(all(F.resolve_all(self.sdir, {}).values()))
        F.apply_preset(self.sdir, "default")
        self.assertEqual(F.resolve_all(self.sdir, {}), F.DEFAULTS)
        self.assertEqual(os.listdir(self.sdir), [])
        with self.assertRaises(ValueError):
            F.apply_preset(self.sdir, "loud")

    def test_state_dir_precedence(self):
        self.assertEqual(F.state_dir({"KITTYMUX_STATE": "/a"}), "/a")
        self.assertEqual(F.state_dir({"XDG_STATE_HOME": "/x"}), "/x/kittymux")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_features -v`
Expected: `ModuleNotFoundError: No module named 'kittymux_features'`.

- [ ] **Step 3: Write the implementation** — create `python/kittymux_features.py`:

```python
# kittymux features — which optional pieces are switched on.
#
# Pure Python, no kitty imports. Precedence: environment variable > flag file in the
# state directory > default. A default-ON feature is turned off by the file `<name>-off`,
# a default-OFF one is turned on by `<name>-on` (the same convention as `notify-off`).
# If both files exist the `-off` one wins.

import os

FEATURES = ("folder", "hue", "collide", "sheet", "hover", "panetitle")
DEFAULTS = {"folder": True, "hue": True, "collide": True, "sheet": True, "hover": False, "panetitle": False}
PRESETS = {
    "minimal": frozenset({"folder"}),
    "default": frozenset(name for name, on in DEFAULTS.items() if on),
    "full": frozenset(FEATURES),
}
_OFF = {"0", "off", "false", "no"}
_ON = {"1", "on", "true", "yes"}


def state_dir(env=None) -> str:
    env = os.environ if env is None else env
    return env.get("KITTYMUX_STATE") or os.path.join(
        env.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "kittymux")


def _check(name: str) -> None:
    if name not in DEFAULTS:
        raise ValueError(f"unknown feature {name!r} (known: {', '.join(FEATURES)})")


def _flag(sdir: str, name: str, on: bool) -> str:
    return os.path.join(sdir, f"{name}-{'on' if on else 'off'}")


def source(name: str, sdir: str | None = None, env=None) -> tuple[bool, str]:
    """(on, where) — where is 'env', 'flag' or 'default'."""
    _check(name)
    env = os.environ if env is None else env
    raw = env.get(f"KITTYMUX_{name.upper()}", "").strip().lower()
    if raw in _OFF:
        return False, "env"
    if raw in _ON:
        return True, "env"
    sdir = sdir or state_dir(env)
    if os.path.exists(_flag(sdir, name, False)):
        return False, "flag"
    if os.path.exists(_flag(sdir, name, True)):
        return True, "flag"
    return DEFAULTS[name], "default"


def enabled(name: str, sdir: str | None = None, env=None) -> bool:
    return source(name, sdir, env)[0]


def resolve_all(sdir: str | None = None, env=None) -> dict[str, bool]:
    return {name: enabled(name, sdir, env) for name in FEATURES}


def set_feature(sdir: str, name: str, on: bool) -> None:
    """Persist the choice as at most one flag file — none when it equals the default."""
    _check(name)
    os.makedirs(sdir, mode=0o700, exist_ok=True)
    for state in (True, False):
        try:
            os.unlink(_flag(sdir, name, state))
        except FileNotFoundError:
            pass
    if on != DEFAULTS[name]:
        open(_flag(sdir, name, on), "a").close()


def apply_preset(sdir: str, preset: str) -> None:
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r} (known: {', '.join(PRESETS)})")
    for name in FEATURES:
        set_feature(sdir, name, name in PRESETS[preset])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_features -v`
Expected: `Ran 9 tests … OK`.

- [ ] **Step 5: Commit**

```bash
git add python/kittymux_features.py tests/test_features.py
git commit -m "features: one switchboard for the optional pieces (env > flag file > default, presets)"
```

---

### Task 2: `kittymux_place` — where a tab is, laid out

**Files:**
- Create: `python/kittymux_place.py`
- Test: `tests/test_place.py`

**Interfaces:**
- Consumes: `kittymux_git.GitInfo(top, branch, project, worktree)` (already in the repo; tests construct it).
- Produces:
  - `ROLES = ("icon","project","worktree","inner","where","branch")`
  - `Facts(project, worktree, inner, where, branch)` NamedTuple
  - `facts(cwd: str, info, home: str|None=None) -> Facts` (never raises)
  - `redundant(title: str, f: Facts) -> bool`
  - `colliding(titles: dict[int,str]) -> frozenset[int]`
  - `mid_ellipsis(text, width, cells=len) -> str`
  - `layout(f, width, *, icon="", branch_icon="", hide_project=False, cells=len) -> list[(text, role)]`
  - `style(pal, active: bool, hue: int|None, emphasised: bool) -> dict[role, (colour:int, bold:bool)]` — `pal` needs `.text .muted .faint`.

- [ ] **Step 1: Write the failing test** — create `tests/test_place.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_place -v`
Expected: `ModuleNotFoundError: No module named 'kittymux_place'`.

- [ ] **Step 3: Write the implementation** — create `python/kittymux_place.py`:

```python
# kittymux place — "where is this tab?" as a short, laid-out line.
#
#   project[:worktree]/inner  branch          (inside a git repository)
#   notes  ~/Documents                         (anywhere else: the folder, then where it lives)
#
# Pure Python, no kitty imports: the tab bar, the side sheet and the pane title bar all render the
# same pieces. `layout` returns [(text, role)]; the caller picks colours (`style`).

import os
from typing import Callable, NamedTuple

ROLES = ("icon", "project", "worktree", "inner", "where", "branch")
_SEP = "  "


class Facts(NamedTuple):
    project: str       # repo name (the main repository's, same for all its worktrees) or the folder's name
    worktree: str      # linked worktree's directory name, else ""
    inner: str         # path inside the repo ("" at its root)
    where: str         # outside a repo: the folder's parent, ~-abbreviated
    branch: str


def facts(cwd: str, info, home: str | None = None) -> Facts:
    """`info` is kittymux_git.info(cwd) (a GitInfo) or None. Never raises."""
    home = home or os.path.expanduser("~")
    if not cwd:
        return Facts("~", "", "", "", "")
    path = os.path.abspath(cwd)
    if info is not None:
        inner = "" if path == info.top else os.path.relpath(path, info.top)
        if inner == "." or inner.startswith(".."):
            inner = ""
        return Facts(info.project, info.worktree, inner, "", info.branch)
    if path == home:
        return Facts("~", "", "", "", "")
    trimmed = path.rstrip("/")
    leaf = os.path.basename(trimmed) or "/"
    parent = os.path.dirname(trimmed)
    where = ""
    if parent and leaf != "/":
        where = "~" + parent[len(home):] if parent == home or parent.startswith(home + "/") else parent
    return Facts(leaf, "", "", where, "")


def redundant(title: str, f: Facts) -> bool:
    """True when the tab's title already says the project (a shell tab titled by its folder)."""
    t = " ".join(title.lower().split())
    return bool(t) and t in {f.project.lower(), f"{f.project}:{f.worktree}".lower()}


def colliding(titles: dict[int, str]) -> frozenset[int]:
    """Tab ids whose title is shared with another tab (case and spacing ignored)."""
    seen: dict[str, list[int]] = {}
    for tab_id, title in titles.items():
        key = " ".join(title.lower().split())
        if key:
            seen.setdefault(key, []).append(tab_id)
    return frozenset(i for ids in seen.values() if len(ids) > 1 for i in ids)


def mid_ellipsis(text: str, width: int, cells: Callable[[str], int] = len) -> str:
    """Cut the middle so both ends of a name stay readable: `kittymux-landing` → `kitty…ding`."""
    if cells(text) <= width:
        return text
    if width <= 1:
        return "…"[:max(0, width)]
    for keep in range(min(len(text), width), -1, -1):
        head, tail = (keep + 1) // 2, keep // 2
        out = text[:head] + "…" + (text[len(text) - tail:] if tail else "")
        if cells(out) <= width:
            return out
    return "…"


def _inner_variants(inner: str) -> list[str]:
    parts = inner.split("/")
    out = ["/" + inner]
    if len(parts) > 2:
        out.append("/…/" + "/".join(parts[-2:]))
    if len(parts) > 1:
        out.append("/…/" + parts[-1])
    return out


def _where_variants(where: str) -> list[str]:
    parts = where.split("/")
    out = [_SEP + where]
    if len(parts) > 2:
        out.append(_SEP + "…/" + parts[-1])
    return out


def layout(f: Facts, width: int, *, icon: str = "", branch_icon: str = "", hide_project: bool = False,
           cells: Callable[[str], int] = len) -> list[tuple[str, str]]:
    """Pieces that fit in `width` cells, most useful first: the branch goes first when room runs out, then the
    path, then the icon; the worktree outranks the path (parallel agents on one repo must stay apart) and the
    project name is only ever middle-truncated. Returns [] when there is no room at all."""
    if width < 2:
        return []
    icon_text = icon + " " if icon else ""
    worktree = ":" + f.worktree if f.worktree else ""
    branch = (_SEP + (branch_icon + " " if branch_icon else "") + f.branch) if f.branch else ""
    if f.inner:
        context = ("inner", _inner_variants(f.inner))
    elif f.where:
        context = ("where", _where_variants(f.where))
    else:
        context = ("", [])

    def total(parts):
        return sum(cells(t) for t, _r in parts)

    def build(*, icon_on, wt_on, ctx, branch_on):
        parts = []
        if not hide_project:
            if icon_on and icon_text:
                parts.append((icon_text, "icon"))
            parts.append((f.project, "project"))
            if wt_on and worktree:
                parts.append((worktree, "worktree"))
        if ctx:
            parts.append((ctx, context[0]))
        if branch_on and branch:
            parts.append((branch, "branch"))
        if parts and hide_project:                      # nothing before the first piece: no separator, no leading slash
            text, role = parts[0]
            text = text.lstrip(" ")
            parts[0] = (text[1:] if role == "inner" and text.startswith("/") else text, role)
        return parts

    first_ctx = context[1][0] if context[1] else ""
    attempts = [dict(icon_on=True, wt_on=True, ctx=first_ctx, branch_on=True),
                dict(icon_on=True, wt_on=True, ctx=first_ctx, branch_on=False)]
    attempts += [dict(icon_on=True, wt_on=True, ctx=c, branch_on=False) for c in context[1][1:]]
    attempts += [dict(icon_on=True, wt_on=True, ctx="", branch_on=False),
                 dict(icon_on=False, wt_on=True, ctx="", branch_on=False)]
    seen = set()
    for kwargs in attempts:
        key = tuple(sorted(kwargs.items()))
        if key in seen:
            continue
        seen.add(key)
        parts = build(**kwargs)
        if parts and total(parts) <= width:
            return parts
    if hide_project:
        # only the path / branch was wanted and even that does not fit: show what the path ends with
        text = (context[1][-1] if context[1] else branch).lstrip(" /")
        return [(mid_ellipsis(text, width, cells), context[0] or "branch")] if text else []
    room = width - cells(worktree)
    if worktree and room >= 3:
        return [(mid_ellipsis(f.project, room, cells), "project"), (worktree, "worktree")]
    return [(mid_ellipsis(f.project, width, cells), "project")]


def style(pal, active: bool, hue: int | None, emphasised: bool) -> dict[str, tuple[int, bool]]:
    """role → (colour, bold). The project name is the ONE bright element of the row: it takes the project hue
    (or the text colour when hue is off) on the active tab and on a tab that looks like another one; elsewhere
    it stays muted. Everything else steps down."""
    muted = pal.muted if active else pal.faint
    loud = active or emphasised
    name = (hue if hue is not None else pal.text) if loud else pal.muted
    return {
        "icon": (hue if hue is not None else muted, False),
        "project": (name, loud),
        "worktree": (muted, False),
        "inner": (pal.faint, False),
        "where": (pal.faint, False),
        "branch": (muted, False),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_place -v`
Expected: `Ran 17 tests … OK`.

- [ ] **Step 5: Commit**

```bash
git add python/kittymux_place.py tests/test_place.py
git commit -m "place: where a tab is — project[:worktree]/inner  branch, laid out to the room it has"
```

---

### Task 3: `project_hue` — a stable colour per project, from the live theme

**Files:**
- Modify: `python/kittymux_theme.py` (imports at the top; new functions before `@dataclass(frozen=True)\nclass Palette:`)
- Test: `tests/test_hue.py`

**Interfaces:**
- Consumes: existing `kittymux_theme.ensure_contrast(fg, bg, minimum)`, `blend`, `contrast`.
- Produces: `HUE_SLOTS = 12`, `hue_slot(name: str) -> int`, `project_hue(name: str, accent: int, bg: int, minimum: float = 4.5) -> int` (cached, pure).

- [ ] **Step 1: Write the failing test** — create `tests/test_hue.py`:

```python
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import kittymux_theme as T  # noqa: E402

# (accent, background, row background) — a dark theme, a light theme and a theme whose accent is grey
THEMES = {
    "dark": (0x89B4FA, 0x1E1E2E, T.blend(0xCDD6F4, 0x1E1E2E, 0.15)),
    "light": (0x1E66F5, 0xEFF1F5, T.blend(0x4C4F69, 0xEFF1F5, 0.15)),
    "grey": (0x888888, 0x101010, T.blend(0xDDDDDD, 0x101010, 0.15)),
}


class HueTests(unittest.TestCase):
    def test_a_project_keeps_its_slot_across_processes(self):
        here = T.hue_slot("kittymux")
        code = "import sys; sys.path.insert(0, %r); import kittymux_theme as T; print(T.hue_slot('kittymux'))" % \
               os.path.join(os.path.dirname(__file__), "..", "python")
        for seed in ("1", "2"):
            out = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, PYTHONHASHSEED=seed),
                                 capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(int(out), here)

    def test_slots_are_in_range_and_spread(self):
        slots = {T.hue_slot(f"project-{i}") for i in range(200)}
        self.assertTrue(slots <= set(range(T.HUE_SLOTS)))
        self.assertGreaterEqual(len(slots), 10)

    def test_every_slot_is_readable_on_every_theme(self):
        for theme, (accent, _bg, row) in THEMES.items():
            seen = set()
            for i in range(200):
                rgb = T.project_hue(f"p{i}", accent, row)
                self.assertGreaterEqual(T.contrast(rgb, row), 4.5, (theme, i, hex(rgb)))
                seen.add(rgb)
            self.assertGreaterEqual(len(seen), 8, theme)          # the slots are visibly different colours

    def test_it_follows_the_theme(self):
        a = T.project_hue("kittymux", THEMES["dark"][0], THEMES["dark"][2])
        b = T.project_hue("kittymux", THEMES["light"][0], THEMES["light"][2])
        self.assertNotEqual(a, b)

    def test_same_project_same_colour(self):
        accent, _bg, row = THEMES["dark"]
        self.assertEqual(T.project_hue("kittymux", accent, row), T.project_hue("kittymux", accent, row))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_hue -v`
Expected: `AttributeError: module 'kittymux_theme' has no attribute 'hue_slot'`.

- [ ] **Step 3: Write the implementation** — in `python/kittymux_theme.py` change the import block to

```python
import colorsys
import functools
import hashlib
import os
import re
from dataclasses import dataclass
```

and insert directly above `@dataclass(frozen=True)\nclass Palette:`:

```python
HUE_SLOTS = 12


def hue_slot(name: str) -> int:
    """Which of HUE_SLOTS hues a project name gets. SHA-1, not hash(): Python salts str hashes per process,
    and a project must keep its colour across restarts and between the bar and the sheet."""
    return int.from_bytes(hashlib.sha1(name.encode("utf-8", "replace")).digest()[:4], "big") % HUE_SLOTS


@functools.lru_cache(maxsize=512)
def project_hue(name: str, accent: int, bg: int, minimum: float = 4.5) -> int:
    """A colour for a project: the theme's own accent with its hue turned by the project's slot, so every theme
    gets a matching family (never a fixed palette). Saturation and lightness follow the accent (a grey accent
    still gets colour), then it is nudged until it reads on `bg` at the given WCAG ratio — a hue is a second
    cue next to the project's name, never the only one. On a theme with no lightness room it degrades toward
    the text colour rather than failing."""
    r, g, b = (accent >> 16) & 0xFF, (accent >> 8) & 0xFF, accent & 0xFF
    h, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    h = (h + hue_slot(name) / HUE_SLOTS) % 1.0
    r2, g2, b2 = colorsys.hls_to_rgb(h, light, max(sat, 0.45))
    candidate = (round(r2 * 255) << 16) | (round(g2 * 255) << 8) | round(b2 * 255)
    return ensure_contrast(candidate, bg, minimum)


```

- [ ] **Step 4: Run the tests to verify they pass (new and existing theme tests)**

Run: `python3 -m unittest tests.test_hue tests.test_theme -v`
Expected: all `OK`.

- [ ] **Step 5: Commit**

```bash
git add python/kittymux_theme.py tests/test_hue.py
git commit -m "theme: project_hue — a stable per-project colour from the live accent, readable on every theme"
```

---

### Task 4: Wire it into the vertical bar

**Files:**
- Modify: `python/tab_bar.py` (imports ~L33-47, reload tuple ~L52, new helpers after `_kb_mode` ~L168, subtitle block ~L1002, subtitle loop ~L1110-1124, rail number ~L1075)
- Modify: `tests/smoke_click.sh:17`, `tests/smoke_drag.sh:17`, `tests/smoke_resize.sh:17`, `tests/smoke_native.sh:19`, `tests/smoke_sidebar.sh:31`, `tests/smoke_state.sh:43` (symlink lists — a rig that does not link the new modules would make `tab_bar.py` fail to import)

**Interfaces:**
- Consumes: Tasks 1–3 (`kittymux_features.resolve_all/state_dir/DEFAULTS`, `kittymux_place.facts/layout/style/redundant/colliding`, `kittymux_theme.project_hue/blend`), and from `tab_bar.py`: `_per_pass`, `_compact_title(tab, limit)`, `_palette`, `_rgb`, `_put`, `_cells`, `_ICON_FOLDER`, `_ICON_BRANCH`, `_git_anchor`, `_short_cwd`.
- Produces: `_features() -> dict`, `_facts(cwd) -> Facts`, `_tab_hue(cwd, pal) -> int|None`, `_title_keys(os_window_id) -> dict[int,str]`, `_twins(os_window_id) -> frozenset[int]`, class `_Place`, `_place_piece(...)`, `_dump_row(tab_id, **row)`. Test hook: with `KITTYMUX_BAR_DUMP=1` the bar writes `$STATE/bar-dump.json` = `{tab_id: {legacy: bool, pieces: [[text, role]…], emphasised, hue, hidden}}`.

- [ ] **Step 1: Add the imports and reload entries.** In `python/tab_bar.py` replace

```python
import kittymux_deck  # noqa: E402
import kittymux_git  # noqa: E402
import kittymux_launcher  # noqa: E402
import kittymux_layout  # noqa: E402
import kittymux_scan  # noqa: E402
```
with
```python
import kittymux_deck  # noqa: E402
import kittymux_features  # noqa: E402
import kittymux_git  # noqa: E402
import kittymux_launcher  # noqa: E402
import kittymux_layout  # noqa: E402
import kittymux_place  # noqa: E402
import kittymux_scan  # noqa: E402
```
and replace
```python
for _mod in (kittymux_theme, kittymux_agents, kittymux_git, kittymux_layout, kittymux_state, kittymux_scan,
             kittymux_barsize, kittymux_deck):
```
with
```python
for _mod in (kittymux_theme, kittymux_agents, kittymux_git, kittymux_features, kittymux_place, kittymux_layout,
             kittymux_state, kittymux_scan, kittymux_barsize, kittymux_deck):
```

- [ ] **Step 2: Add the per-pass helpers.** Insert directly after the `_kb_mode` function (the one ending `return ""` right before `def _mute`):

```python
@_per_pass
def _features() -> dict:
    """Which optional pieces are on (kittymux_features: env > flag file > default), resolved once per pass."""
    try:
        return kittymux_features.resolve_all()
    except Exception:
        return dict(kittymux_features.DEFAULTS)


@_per_pass
def _facts(cwd: str):
    """Project / worktree / inner path / branch of a directory — once per pass and per directory (reads .git/HEAD only)."""
    return kittymux_place.facts(cwd, kittymux_git.info(cwd))


def _tab_hue(cwd: str, pal):
    """The project's hue (cached per name by kittymux_theme), or None when hue is off or the tab has no directory."""
    if not cwd or not _features()["hue"]:
        return None
    return kittymux_theme.project_hue(_facts(cwd).project, pal.accent, pal.surface_hi)


@_per_pass
def _title_keys(os_window_id: int) -> dict:
    """tab id → the title that tab shows, for every tab of this OS window (once per pass)."""
    out: dict = {}
    try:
        tm = get_boss().os_window_map.get(os_window_id)
        for t in (tm.tabs if tm else []):
            out[t.id] = _compact_title(types.SimpleNamespace(title=t.title or "", tab_id=t.id), 40)
    except Exception:
        pass
    return out


@_per_pass
def _twins(os_window_id: int) -> frozenset:
    """Tabs that show the same title as another tab of this OS window — their project name is emphasised."""
    if not _features()["collide"]:
        return frozenset()
    return kittymux_place.colliding(_title_keys(os_window_id))


class _Place:
    """The folder line of a vertical tab. Laid out at DRAW time: the room left by the state word is only known there."""
    __slots__ = ("facts", "hide", "style", "emphasised", "hue")

    def __init__(self, facts, hide, style, emphasised, hue):
        self.facts, self.hide, self.style, self.emphasised, self.hue = facts, hide, style, emphasised, hue


def _place_piece(tab, cwd: str, pal, active: bool, os_window_id: int) -> "_Place":
    f = _facts(cwd)
    title = _title_keys(os_window_id).get(tab.tab_id, "")
    hue = _tab_hue(cwd, pal)
    emphasised = tab.tab_id in _twins(os_window_id)
    return _Place(f, kittymux_place.redundant(title, f), kittymux_place.style(pal, active, hue, emphasised), emphasised, hue)


_BAR_DUMP = os.environ.get("KITTYMUX_BAR_DUMP") == "1"      # test hook (tests/smoke_place.sh): what each tab's folder line drew
_dump_rows: dict = {}


def _dump_row(tab_id: int, **row) -> None:
    if not _BAR_DUMP:
        return
    try:
        _dump_rows[str(tab_id)] = row
        with open(os.path.join(kittymux_features.state_dir(), "bar-dump.json"), "w") as f:
            json.dump(_dump_rows, f)
    except Exception:
        pass


```

- [ ] **Step 3: Replace the subtitle's folder/branch piece.** In `_draw_vertical`, replace

```python
    branch = _git_anchor(cwd)[1] if cwd else ""
    subtitle: list[tuple[str, int]] = []
    if branch:
        subtitle.append((f"{_ICON_BRANCH} {branch}", pal.muted if active else pal.faint))
    elif cwd:
        subtitle.append((f"{_ICON_FOLDER} {_short_cwd(cwd, 24)}", pal.muted if active else pal.faint))
```
with
```python
    subtitle: list = []
    if cwd and _features()["folder"]:
        subtitle.append((_place_piece(tab, cwd, pal, active, draw_data.os_window_id), pal.faint))
    else:                                                    # folder off: the line this bar always drew
        branch = _git_anchor(cwd)[1] if cwd else ""
        if branch:
            subtitle.append((f"{_ICON_BRANCH} {branch}", pal.muted if active else pal.faint))
        elif cwd:
            subtitle.append((f"{_ICON_FOLDER} {_short_cwd(cwd, 24)}", pal.muted if active else pal.faint))
        if subtitle and not extra_data.for_layout:
            _dump_row(tab.tab_id, legacy=True, pieces=[[subtitle[0][0], "legacy"]])
```

- [ ] **Step 4: Draw the piece.** In the `for i, (text, color) in enumerate(lead):` loop, insert immediately before `if isinstance(text, list):                       # pane chips…`:

```python
            if isinstance(text, _Place):                     # the folder line: laid out to the room that is really left
                runs = kittymux_place.layout(text.facts, avail - _cells(sep), icon=_ICON_FOLDER, branch_icon=_ICON_BRANCH,
                                             hide_project=text.hide, cells=_cells)
                if runs:
                    x = _put(screen, x, sep, _rgb(color))
                    for run, role in runs:
                        fg, bold = text.style[role]
                        x = _put(screen, x, run, _rgb(fg), bold)
                    if not extra_data.for_layout:
                        _dump_row(tab.tab_id, legacy=False, pieces=[[r, k] for r, k in runs], emphasised=text.emphasised,
                                  hue=text.hue, hidden=text.hide)
                continue
```

The existing `tail = [p for p in subtitle if isinstance(p[0], str) and …]` and `lead = [p for p in subtitle if p not in tail]` lines already cope with non-string pieces; the message override `subtitle = [p for p in subtitle if isinstance(p[0], _MiniMap) and cols >= 26] + [(msg, state_fg)]` drops the folder line while a question is pending, exactly as it dropped the branch before.

- [ ] **Step 5: Tint the rail number.** Replace

```python
        _put(screen, 3, str(index), _rgb(pal.muted if active else pal.faint))
```
with
```python
        hue = _tab_hue(cwd, pal)
        number = pal.muted if active else pal.faint
        if hue is not None:                                  # the rail has no room for a name: the project's hue is its only cue
            number = hue if active else kittymux_theme.blend(hue, pal.bar, 0.6)
        _put(screen, 3, str(index), _rgb(number))
```

- [ ] **Step 6: Link the new modules in every rig that lists modules.** The six rigs name each helper explicitly; add the two new files. Run:

```bash
sed -i 's/kittymux_git\.py kittymux_layout\.py/kittymux_git.py kittymux_features.py kittymux_place.py kittymux_layout.py/' \
  tests/smoke_click.sh tests/smoke_drag.sh tests/smoke_resize.sh tests/smoke_native.sh tests/smoke_sidebar.sh tests/smoke_state.sh
grep -c "kittymux_place.py" tests/smoke_click.sh tests/smoke_drag.sh tests/smoke_resize.sh tests/smoke_native.sh tests/smoke_sidebar.sh tests/smoke_state.sh
```
Expected: six lines ending `:1`.

- [ ] **Step 7: Compile and run the unit suite**

Run: `python3 -m py_compile python/tab_bar.py python/kittymux_place.py python/kittymux_features.py python/kittymux_theme.py && bash -n tests/smoke_click.sh && python3 -m unittest discover -s tests 2>&1 | tail -4`
Expected: no compile output, `OK` from the suite.

- [ ] **Step 8: Run the existing real-kitty rigs that exercise the bar** (they prove nothing regressed and that the new modules import inside a real kitty)

Run: `bash tests/smoke_state.sh && bash tests/smoke_click.sh && bash tests/smoke_reload.sh`
Expected: each prints `PASS` (or `SKIP: …` if Xvfb/xdotool is missing — then say so, do not claim verification). `smoke_reload.sh` links modules by glob; if it fails on an import error, add the two new files to its list the same way.

- [ ] **Step 9: Commit**

```bash
git add python/tab_bar.py tests/smoke_click.sh tests/smoke_drag.sh tests/smoke_resize.sh tests/smoke_native.sh tests/smoke_sidebar.sh tests/smoke_state.sh
git commit -m "bar: every tab says where it is — project name highlighted, branch and path stepped down, hue on the rail"
```

---

### Task 5: `smoke_place.sh` — the folder line in a real kitty

**Files:**
- Create: `tests/smoke_place.sh`
- Modify: `bin/kittymux` is NOT touched here, but the rig drives `bin/kittymux features` (Task 6). **Do Task 6 first if running this task's step 3 for real; write the file now.**

**Interfaces:**
- Consumes: the dump hook from Task 4; `kittymux features on|off|preset` from Task 6; `tests/probe_bar.py` pattern.
- Produces: a rig that prints `PASS: …`.

- [ ] **Step 1: Write the rig** — create `tests/smoke_place.sh` (then `chmod +x tests/smoke_place.sh`):

```bash
#!/usr/bin/env bash
# The folder line of vertical tabs, in a real kitty. Four tabs: two in DIFFERENT repos whose shells show the SAME title ("app"),
# one at a repo root (the title already says the project) and one plain folder outside any repo. Reads what the bar drew from the
# KITTYMUX_BAR_DUMP hook, then flips the switches (`kittymux features`) and checks each piece goes away on its own and that with
# everything off the bar draws the line it always did. Needs Xvfb, xdotool, kitty, git, python3; else SKIP.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty git python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-place.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
fail() { echo "FAIL: $*"; [ -s "$STATE/tab_bar-error.log" ] && sed 's/^/  | /' "$STATE/tab_bar-error.log" | tail -12; [ -f "$STATE/bar-dump.json" ] && cat "$STATE/bar-dump.json"; exit 1; }
for n in $(seq 201 229); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in tab_bar.py kittymux_theme.py kittymux_deck.py kittymux_git.py kittymux_features.py kittymux_place.py kittymux_layout.py kittymux_barsize.py kittymux_agents.py kittymux_state.py kittymux_scan.py; do
  ln -s "$HOME_DIR/python/$f" "$CFG/$f"
done
printf 'window_padding_width 10\nconfirm_os_window_close 0\nallow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$HOME_DIR" "$HOME_DIR" "$HOME_DIR" > "$CFG/kitty.conf"
mkdir -p "$T/work/alpha/app" "$T/work/bravo/app" "$T/plain/notes"
for r in alpha bravo; do git -C "$T/work/$r" init -q -b main || fail "git init"; done
cat > "$T/session" <<S
new_tab
cd $T/work/alpha/app
launch sh
new_tab
cd $T/work/bravo/app
launch sh
new_tab
cd $T/work/alpha
launch sh
new_tab
cd $T/plain/notes
launch sh
focus_tab 0
S
others() { for s in /tmp/mykitty-* "${REAL_RUNTIME:-/nonexistent}"/mykitty-*; do [ -S "$s" ] && [ "$s" != "${SOCK#unix:}" ] && kitty @ --to "unix:$s" ls 2>/dev/null | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))'; done | tr '\n' ' '; }
OTHERS_BEFORE=$(others)
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_BAR_DUMP=1 \
  kitty -o linux_display_server=x11 --class kmx-place --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --class kmx-place | head -1)
X windowsize "$W" 1390 890; sleep 0.4; X windowsize "$W" 1400 900; sleep 1.2       # a real size (and a first redraw), as the other rigs do
# a known bar width (30 columns): without a saved layout kitty's own, narrower width applies (same trick as smoke_resize.sh)
python3 -c "import sys;sys.path.insert(0,'$HOME_DIR/python');import kittymux_layout as L;L.save('$STATE',$KPID,L.Layout('left','full',22))"
kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1; kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1.5
reload() { kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 2.5; }
# `kittymux features` reloads every kitty it can find: confine its discovery to NOTHING (and drop KITTY_LISTEN_ON, which points at the kitty this rig was started from),
# so only this rig's own `reload` below touches a kitty
FEAT() { env -u KITTY_LISTEN_ON KITTYMUX_SOCKET_DIRS="$T/no-sockets" KITTYMUX_STATE=$STATE "$HOME_DIR/bin/kittymux" features "$@" >/dev/null 2>&1; }
# check KIND — prints the rows as one line per tab:  text|roles|emphasised|hue|legacy|hidden
rows() { python3 - "$STATE/bar-dump.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for k in sorted(d, key=int):
    r = d[k]
    print("%s|%s|%s|%s|%s|%s" % ("".join(t for t, _ in r["pieces"]), ",".join(role for _, role in r["pieces"]),
          r.get("emphasised"), "none" if r.get("hue") is None else "hue", r["legacy"], r.get("hidden")))
PY
}
for _ in $(seq 80); do [ -s "$STATE/bar-dump.json" ] && [ "$(rows 2>/dev/null | wc -l)" -ge 4 ] && break; sleep 0.25; done
[ "$(rows | wc -l)" -ge 4 ] || fail "the bar drew fewer than 4 folder lines"

# 1. defaults: project highlighted, the twins ("app" in alpha and bravo) emphasised, hue on
R=$(rows)
echo "$R" | grep -q "^[^|]*alpha/app[^|]*|icon,project,inner,branch|True|hue|False|False$" || fail "alpha/app line wrong:
$R"
echo "$R" | grep -q "^[^|]*bravo/app[^|]*|icon,project,inner,branch|True|hue|False|False$" || fail "bravo/app line wrong:
$R"
echo "  ok   two tabs titled 'app' show their projects, both emphasised, with a hue"
# the repo-root tab and the plain folder: the title already says the project, so the line shows the rest
echo "$R" | grep -q "|branch|False|hue|False|True$" || fail "the repo-root tab should hide the project and show only the branch:
$R"
echo "$R" | grep -q "|where|False|hue|False|True$" || fail "the plain-folder tab should hide the project and show where it lives:
$R"
echo "  ok   a title that already says the project is not repeated (branch / location shown instead)"

# 2. collide off: the twins lose their emphasis, everything else stays
FEAT off collide; reload
R=$(rows)
echo "$R" | grep "alpha/app" | grep -q "|False|hue|False|False$" || fail "collide off should clear the emphasis:
$R"
echo "  ok   features off collide: no emphasis, the rest unchanged"
FEAT on collide

# 3. hue off: no hue anywhere
FEAT off hue; reload
R=$(rows)
echo "$R" | grep -q "|hue|" && fail "hue off left a hue in a row:
$R"
echo "  ok   features off hue: no hue"
FEAT on hue

# 4. minimal preset = folder only
FEAT preset minimal; reload
R=$(rows)
echo "$R" | grep "alpha/app" | grep -q "|False|none|False|False$" || fail "preset minimal should leave the folder line without hue or emphasis:
$R"
echo "  ok   preset minimal: the folder line alone"

# 5. everything off: the line this bar always drew (branch, or folder outside a repo) — no project, no roles
FEAT preset default; FEAT off folder; reload
R=$(rows)
[ "$(echo "$R" | grep -c '^[^|]*|legacy|None|none|True|None$')" -ge 4 ] || fail "folder off should draw the legacy line on every tab:
$R"
echo "$R" | grep -q "alpha" && fail "folder off still shows a project name:
$R"
echo "  ok   features off folder: the original branch / folder line, nothing new"

# 6. no other kitty on this machine was touched
[ "$(others)" = "$OTHERS_BEFORE" ] || fail "this rig changed the windows of ANOTHER kitty (before: $OTHERS_BEFORE after: $(others))"
echo "  ok   no other kitty on this machine was touched"
echo "PASS: tabs say where they are; every piece switches off on its own; all off is the old line"
```

- [ ] **Step 2: Syntax-check**

Run: `chmod +x tests/smoke_place.sh && bash -n tests/smoke_place.sh && echo ok`
Expected: `ok`.

- [ ] **Step 3: Run it (after Task 6 exists)**

Run: `bash tests/smoke_place.sh`
Expected: six `ok` lines then `PASS: …`, or `SKIP: …`. If a grep fails, the `fail` output prints the dump rows — fix the code, not the expectation, unless the expectation itself was wrong (e.g. kitty names a tab differently than the title key). Do not weaken a check to make it pass.

- [ ] **Step 4: Commit**

```bash
git add tests/smoke_place.sh
git commit -m "smoke: the folder line in a real kitty — twins, hidden duplicates, every switch on its own"
```

---

### Task 6: `kittymux features` + doctor

**Files:**
- Modify: `bin/kittymux` (import ~L52, new functions before `def snooze`, dispatch in `main` ~L2493, doctor section before `print("\nlauncher (kittymux pick)")`)
- Test: `tests/test_kittymux_cli.py` (append a new `FeaturesTests` class)

**Interfaces:**
- Consumes: Task 1 API; existing `OK`, `BAD`, `WARN`, `c(...)`, `_sockets()`, `_run(cmd, timeout)`, `Report.ok/warning`.
- Produces: `features_cmd(argv: list[str]) -> int`; `FEATURE_HELP: dict[str,str]`; `_nudge_bars() -> None` (reloads every kitty once so a switch shows now).

- [ ] **Step 1: Write the failing test** — append to `tests/test_kittymux_cli.py` (before any `if __name__` block):

```python
class FeaturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load()

    def run_cmd(self, *argv):
        import contextlib
        import io
        import tempfile
        sdir = tempfile.mkdtemp()
        env = {"KITTYMUX_STATE": sdir}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(self.m, "_nudge_bars"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            for k in [k for k in os.environ if k.startswith("KITTYMUX_") and k != "KITTYMUX_STATE"]:
                os.environ.pop(k)
            rc = self.m.features_cmd(list(argv))
        return rc, out.getvalue(), err.getvalue(), sdir

    def test_list_shows_every_feature_and_where_it_comes_from(self):
        rc, out, _err, _ = self.run_cmd()
        self.assertEqual(rc, 0)
        for name in ("folder", "hue", "collide", "sheet", "hover", "panetitle"):
            self.assertIn(name, out)
        self.assertIn("default", out)

    def test_off_and_on_round_trip(self):
        rc, out, _e, sdir = self.run_cmd("off", "hue")
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(os.path.join(sdir, "hue-off")))

    def test_preset_and_unknown_names(self):
        rc, _o, _e, sdir = self.run_cmd("preset", "minimal")
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(os.path.join(sdir, "hue-off")))
        rc, _o, err, _ = self.run_cmd("on", "nonsense")
        self.assertEqual(rc, 2)
        self.assertIn("unknown feature", err)
        rc, _o, err, _ = self.run_cmd("preset", "loud")
        self.assertEqual(rc, 2)

    def test_usage_on_garbage(self):
        rc, _o, err, _ = self.run_cmd("frobnicate")
        self.assertEqual(rc, 2)
        self.assertIn("usage: kittymux features", err)

    def test_an_env_override_is_called_out(self):
        import contextlib
        import io
        import tempfile
        sdir = tempfile.mkdtemp()
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"KITTYMUX_STATE": sdir, "KITTYMUX_HUE": "off"}), mock.patch.object(self.m, "_nudge_bars"), \
                contextlib.redirect_stdout(out):
            self.m.features_cmd(["on", "hue"])
        self.assertIn("KITTYMUX_HUE", out.getvalue())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_kittymux_cli.FeaturesTests -v`
Expected: `AttributeError: module 'kittymux_cli' has no attribute 'features_cmd'` (or `_nudge_bars`).

- [ ] **Step 3: Implement.** In `bin/kittymux`:

(a) add to the imports, alphabetically after `import kittymux_fanout  # noqa: E402`:
```python
import kittymux_features  # noqa: E402
```

(b) insert before `def snooze(argv: list[str]) -> int:`:

```python
FEATURE_HELP = {
    "folder": "project[:worktree]/inner and branch under each tab (off: just the branch, as before)",
    "hue": "a stable colour per project (folder icon, active name, rail number)",
    "collide": "emphasise the project of tabs that show the same title",
    "sheet": "the side sheet for a tab (right-click / key)",
    "hover": "open the sheet on hover (only where kitty delivers it)",
    "panetitle": "folder + branch in pane title bars",
}


def _nudge_bars() -> None:
    """Reload every running kitty once so a switch shows now (the bar reads the switches on each redraw)."""
    for sock in _sockets():
        _run(["kitty", "@", "--to", sock, "load-config"], 8)


def features_cmd(argv: list[str]) -> int:
    """`kittymux features [list] | on|off NAME | preset minimal|default|full` — pick which optional pieces are on."""
    KF = kittymux_features
    sdir = KF.state_dir()
    cmd = argv[0] if argv else "list"
    try:
        if cmd in ("on", "off") and len(argv) == 2:
            KF.set_feature(sdir, argv[1], cmd == "on")
            note = ""
            if os.environ.get(f"KITTYMUX_{argv[1].upper()}", "").strip():
                note = f"  {WARN} KITTYMUX_{argv[1].upper()} is set in your environment and wins over this"
            print(f"{OK} {argv[1]} {cmd}{note}")
            _nudge_bars()
            return 0
        if cmd == "preset" and len(argv) == 2:
            KF.apply_preset(sdir, argv[1])
            print(f"{OK} preset {argv[1]}: " + ", ".join(sorted(KF.PRESETS[argv[1]], key=KF.FEATURES.index)))
            _nudge_bars()
            return 0
        if cmd in ("list", "status") and len(argv) <= 1:
            for name in KF.FEATURES:
                on, where = KF.source(name, sdir)
                print(f"  {name:<10} {'on ' if on else 'off'}  {c('2', where):<18} {FEATURE_HELP[name]}")
            print(c("2", "\n  presets: minimal (folder only) · default · full     kittymux features off hue"))
            return 0
    except ValueError as e:
        print(f"{BAD} {e}", file=sys.stderr)
        return 2
    print("usage: kittymux features [list] | on NAME | off NAME | preset minimal|default|full", file=sys.stderr)
    return 2


```

(c) in `main`, after the `if cmd == "snooze":` pair add:
```python
    if cmd == "features":
        return features_cmd(argv[1:])
```

(d) in `doctor`, insert immediately before `print("\nlauncher (kittymux pick)")`:
```python
    print("\nfeatures (kittymux features)")
    try:
        r.ok("  ".join(f"{n} {'on' if on else 'off'}" for n in kittymux_features.FEATURES
                       for on, _where in [kittymux_features.source(n)]))
    except Exception as e:                                   # a status line must never break doctor
        r.warning(f"could not read the feature switches: {e}")

```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_kittymux_cli tests.test_features -v 2>&1 | tail -6 && python3 -m py_compile bin/kittymux && ./bin/kittymux features`
Expected: tests `OK`; `kittymux features` prints the six rows.

- [ ] **Step 5: Commit**

```bash
git add bin/kittymux tests/test_kittymux_cli.py
git commit -m "cli: kittymux features — pick the pieces you want (on/off/preset), doctor lists them"
```

---

### Task 7: Run the folder-line rig, then measure the draw cost

**Files:** none modified unless a check fails.

- [ ] **Step 1: Run the new rig for real**

Run: `bash tests/smoke_place.sh`
Expected: six `ok` lines and `PASS`. On `FAIL`, read the dump printed by the rig, fix the implementation (not the expectation) and re-run until green. If the rig `SKIP`s, say so in the report and do not claim real-kitty verification.

- [ ] **Step 2: Measure the draw path before and after.** Create `tests/profile_bar.sh` (`chmod +x`) — a private kitty with 23 tabs and one fake working agent (its spinner redraws the whole bar ~10×/s), run with `KITTYMUX_PROFILE=1`:

```bash
#!/usr/bin/env bash
# Draw cost of the vertical bar. A private kitty with N tabs (default 23, every one in the git checkout $1) and one fake working agent (its spinner
# redraws the whole bar ~10x/s) runs the tab_bar.py of that tree with KITTYMUX_PROFILE=1 for ~20 s; prints the profile lines and their mean.
# Compare two trees:   bash tests/profile_bar.sh /path/to/main    then    bash tests/profile_bar.sh .
# Needs Xvfb, xdotool, kitty; else SKIP. Touches only its own kitty.
set -u
TREE=$(cd "${1:-$(dirname "${BASH_SOURCE[0]}")/..}" && pwd); N=${N:-23}
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-prof.XXXXXX"); CFG=$T/cfg STATE=$T/state SOCK=unix:$T/sock
mkdir -p "$CFG" "$STATE" && chmod 700 "$STATE"
XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
for n in $(seq 290 319); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1400x900x24 >/dev/null 2>&1 & XPID=$!
sleep 1; kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
for f in "$TREE"/python/tab_bar.py "$TREE"/python/kittymux_*.py; do ln -s "$f" "$CFG/$(basename "$f")"; done
printf 'window_padding_width 10\nconfirm_os_window_close 0\nallow_remote_control socket-only\ninclude %s/kittymux.conf\nwatcher %s/python/pane-state.py\ntab_bar_edge left\ntab_bar_min_tabs 1\ngeninclude %s/python/kittymux_layout.py\n' \
  "$TREE" "$TREE" "$TREE" > "$CFG/kitty.conf"
{ echo "new_tab agent"; echo "cd $TREE"
  echo "launch bash -c 'printf \"· Pondering… (12s · ↓ 1.2k tokens)\\n\"; exec -a claude sleep 86400'"
  for i in $(seq 2 "$N"); do echo "new_tab t$i"; echo "cd $TREE"; echo "launch sh"; done
  echo "focus_tab 0"; } > "$T/session"
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP \
  KITTY_CONFIG_DIRECTORY=$CFG KITTYMUX_STATE=$STATE KITTYMUX_NOTIFY=0 KITTYMUX_PROFILE=1 \
  kitty -o linux_display_server=x11 --class kmx-prof --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --class kmx-prof | head -1)
X windowsize "$W" 1390 890; sleep 0.4; X windowsize "$W" 1400 900; sleep 1.2
python3 -c "import sys;sys.path.insert(0,'$TREE/python');import kittymux_layout as L;L.save('$STATE',$KPID,L.Layout('left','full',22))"
kitty @ --to "$SOCK" load-config >/dev/null 2>&1; sleep 1; kitty @ --to "$SOCK" load-config >/dev/null 2>&1
sleep 20
LOG=$STATE/tab_bar-profile.log
[ -s "$LOG" ] || { echo "no profile lines were written (tree: $TREE) — is the bar drawing?"; tail -5 "$STATE/tab_bar-error.log" 2>/dev/null; exit 1; }
echo "tree: $TREE   tabs: $N"
tail -6 "$LOG"
python3 - "$LOG" <<'PY'
import re, sys
rows = [l for l in open(sys.argv[1]) if "avg_ms=" in l][-6:]
avg = [float(re.search(r"avg_ms=([\d.]+)", l).group(1)) for l in rows]
mx = [float(re.search(r"max_ms=([\d.]+)", l).group(1)) for l in rows]
print("MEAN avg_ms=%.3f  worst max_ms=%.3f  (%d samples)" % (sum(avg) / len(avg), max(mx), len(avg)))
PY
```

Run it on `main` (the baseline) and on this branch, from this checkout:

```bash
bash tests/profile_bar.sh /home/kitsunekode/Projects/kittymux      # baseline: main's tab_bar.py
bash tests/profile_bar.sh .                                        # this branch
```
Compare the `MEAN avg_ms` lines (per `draw_tab` call = one tab). **Budget: no more than +0.05 ms per call.** The plan's own dry run on a scratch copy measured 0.044 → 0.055 ms (+0.011) with 23 tabs. If yours is over budget, stop and report — the likely cause is `_title_keys` (one `_compact_title` per tab per pass); the fix is to key collisions on the cleaned raw `t.title` only.

- [ ] **Step 3: Confirm nothing else regressed**

Run: `bash tests/smoke_sidebar.sh && bash tests/smoke_native.sh && bash tests/smoke_demo.sh`
Expected: `PASS` or `SKIP` each.

- [ ] **Step 4: Commit the rig and the measurements**

```bash
git add tests/profile_bar.sh
git commit -m "perf: folder line draw cost — <avg>/<max> ms per draw (23 tabs) vs <avg>/<max> before"
```

---

### Task 8: Demo twins, README, CHANGELOG, spec corrections

**Files:**
- Modify: `bin/kittymux` (`DEMO_SESSION` L457-494; `demo()` after the `project` setup ~L547-551; the "try:" print block ~L568)
- Modify: `tests/smoke_demo.sh:25` (expected tab list)
- Modify: `README.md` (off-switch table ~L221; new "Pick what you want" section right after that table's section)
- Modify: `CHANGELOG.md` (`## [Unreleased]` → `### Added`)
- Modify: `docs/superpowers/specs/2026-10-02-folder-identity-and-side-sheet-design.md`

- [ ] **Step 1: Demo — two tabs that look the same.** In `DEMO_SESSION`, insert before `new_tab notes`:

```
new_tab app
cd {twins}/web/app
launch
new_tab app
cd {twins}/api/app
launch
```
In `demo()`, after the block that writes the `project` files (the `for rel, n in (...)` loop), add:

```python
    twins = os.path.join(tmp, "twins")                         # two repos with an `app` folder each: same tab title, different projects
    for repo in ("web", "api"):
        os.makedirs(os.path.join(twins, repo, "app"))
        if shutil.which("git"):
            subprocess.run(["git", "init", "-q", "-b", "main", os.path.join(twins, repo)], capture_output=True)
```
and change the session write to `DEMO_SESSION.format(home=os.path.expanduser("~"), project=project, twins=twins)`. Add to the printed hints, after the `file-refs` line:

```python
    print(f"  in the two {c('1', 'app')} tabs: the same title, different projects — the bar says which (`kittymux features` turns pieces off)")
```

- [ ] **Step 2: Demo smoke** — in `tests/smoke_demo.sh` change the `for want in …` list to include `app`:

```bash
for want in claude codex antigravity droid review panes file-refs scrollback notes app; do
```

- [ ] **Step 3: README.** (a) In the "Turn it off" table of the "When you are elsewhere" section nothing changes. Add this section immediately before the `### When you are elsewhere` heading:

```markdown
### Where is this tab?

Under each tab the bar says **where it is**: `project[:worktree]/inner  branch`, the project name bright (in the project's own hue on the
active tab), the path and branch stepped down. Two tabs that show the same title get their project emphasised so you can tell them apart;
a tab whose title already says the project shows the branch or location instead of repeating it. The rail (slim bar) tints the tab number
with the project's hue.

### Pick what you want

Every optional piece is its own switch — use all of it, some of it, or none:

| Switch | What it does | Default |
|---|---|---|
| `folder` | the project/branch line under each tab (off: just the branch, as before) | on |
| `hue` | a stable colour per project, derived from your theme's accent | on |
| `collide` | emphasise the project of tabs that show the same title | on |
| `sheet` | the side sheet (planned) | on |
| `hover` | open the sheet on hover (planned; only where kitty delivers it) | off |
| `panetitle` | folder + branch in pane title bars (planned) | off |

```bash
kittymux features                 # what is on, and where each setting comes from
kittymux features off hue         # one piece off (flag file in ~/.local/state/kittymux)
kittymux features preset minimal  # folder line only   (presets: minimal · default · full)
KITTYMUX_HUE=off kitty            # or per process, by environment — the environment wins
```
```

(b) In `CHANGELOG.md`, under `## [Unreleased]` → `### Added`, first bullet:
```markdown
- **Every tab says where it is.** `project[:worktree]/inner  branch` under each vertical tab, the project name highlighted; a stable per-project hue from your theme's accent; tabs that look alike get their project emphasised. Each piece is its own switch — `kittymux features [on|off NAME | preset minimal|default|full]`.
```

- [ ] **Step 4: Spec corrections** (three things this plan found). In the spec: (1) in P1's "Rendering" bullet change "`branch` in `pal.done` hue as the horizontal bar does" to "`branch` in `pal.muted` (active) / `pal.faint`, as today's subtitle — one emphasis per row (3b) wins over matching the horizontal bar"; (2) in 3d item 1 replace "The hue is skipped (accent used as-is) when the theme leaves too little lightness range to reach 4.5:1." with "On a theme with no lightness room the hue degrades toward the text colour (`ensure_contrast`) rather than failing."; (3) in 3c replace "Changes apply on the next reload (no restart)." with "Changes apply on the bar's next redraw (the CLI also reloads every kitty once); no restart."

- [ ] **Step 5: Run everything**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3 && bash tests/test_mux_status.sh && bash tests/test_socket_lib.sh && bash tests/smoke_demo.sh && bash tests/test_install.sh`
Expected: `OK` and `PASS`/`SKIP` lines; `test_install.sh` proves the new modules are linked by `install.sh`'s glob (it must still pass — if it enumerates files, add the two new ones there).

- [ ] **Step 6: Commit**

```bash
git add bin/kittymux tests/smoke_demo.sh README.md CHANGELOG.md docs/superpowers/specs
git commit -m "docs+demo: where-is-this-tab, pick-what-you-want, two same-titled demo tabs"
```

---

### Task 9: P0 probes — what kitty really does (answers, not features)

**Files:**
- Create: `tests/probe_motion.py`, `tests/probe_motion.sh`, `tests/probe_titledata.sh`, `tests/probe_panel.sh`
- Modify: `docs/compatibility.md` (a new `## Side-sheet probes (kitty 0.49.2)` section), `docs/testing.md` (manual-only note)

Everything here is throwaway measurement; the deliverable is a written answer per probe.

- [ ] **Step 1: Motion probe (a)** — create `tests/probe_motion.py` (runs INSIDE kitty like `probe_bar.py`):

```python
# Test helper, run INSIDE a kitty: `kitty @ kitten tests/probe_motion.py LOG SECONDS` records every call kitty makes to
# TabManager.handle_tab_bar_mouse for SECONDS seconds, one JSON line [x, y, button, action] each, then restores the method.
# Answers one question: does kitty hand Python mouse motion over the tab bar when no button is held?
import json

from kittens.tui.handler import result_handler


def main(args):
    return ""


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    from kitty.fast_data_types import add_timer
    from kitty.tabs import TabManager
    log, seconds = args[1], float(args[2])
    original = TabManager.handle_tab_bar_mouse

    def spy(self, x, y, button, modifiers, action):
        with open(log, "a") as f:
            f.write(json.dumps([round(x), round(y), button, action]) + "\n")
        return original(self, x, y, button, modifiers, action)

    TabManager.handle_tab_bar_mouse = spy

    def restore(_timer_id):
        TabManager.handle_tab_bar_mouse = original

    add_timer(restore, seconds, False)
```

and `tests/probe_motion.sh` (`chmod +x`):

```bash
#!/usr/bin/env bash
# P0-a: does kitty deliver idle mouse motion over a vertical tab bar to Python? Prints the counts; no pass/fail — it is an answer.
set -u
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for dep in Xvfb xdotool kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-motion.XXXXXX"); SOCK=unix:$T/sock; XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
for n in $(seq 230 259); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1200x800x24 >/dev/null 2>&1 & XPID=$!; sleep 1
kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
mkdir -p "$T/cfg"; printf 'allow_remote_control socket-only\ntab_bar_edge left\ntab_bar_min_tabs 1\ntab_bar_style separator\nconfirm_os_window_close 0\n' > "$T/cfg/kitty.conf"
printf 'new_tab one\nlaunch sh\nnew_tab two\nlaunch sh\nnew_tab three\nlaunch sh\nfocus_tab 0\n' > "$T/session"
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP KITTY_CONFIG_DIRECTORY=$T/cfg \
  kitty -o linux_display_server=x11 --class kmx-motion --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
X() { DISPLAY=$DISP xdotool "$@"; }
W=$(X search --class kmx-motion | head -1); X windowsize "$W" 1190 790; sleep 0.3; X windowsize "$W" 1200 800; sleep 1.5
kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_bar.py" "$T/geom.json" >/dev/null 2>&1
BX=$(python3 -c "import json;g=json.load(open('$T/geom.json'));print(int((g['left']+g['right'])/2))")
BY=$(python3 -c "import json;g=json.load(open('$T/geom.json'));print(int(g['top']+40))")
: > "$T/motion.log"
kitty @ --to "$SOCK" kitten "$HOME_DIR/tests/probe_motion.py" "$T/motion.log" 12 >/dev/null 2>&1
sleep 0.5
for i in 1 2 3 4 5 6 7 8; do X mousemove $((BX + i)) $((BY + i * 6)); sleep 0.15; done          # no button held
idle=$(python3 -c "import json;print(sum(1 for l in open('$T/motion.log') if json.loads(l)[2] == -1))")
X mousemove $BX $BY mousedown 1; sleep 0.1; for i in 1 2 3 4 5; do X mousemove $((BX + 20 + i * 4)) $((BY + 30)); sleep 0.1; done; X mouseup 1; sleep 0.5
total=$(wc -l < "$T/motion.log")
echo "idle motion events (button -1, no button held): $idle"
echo "all calls to handle_tab_bar_mouse (incl. press/release/drag): $total"
echo "RESULT: $([ "$idle" -gt 0 ] && echo 'idle motion REACHES Python — hover on the bar is possible' || echo 'idle motion does NOT reach Python — hover must live in the sheet/panel, not the bar')"
```

- [ ] **Step 2: Run it**

Run: `chmod +x tests/probe_motion.sh && bash tests/probe_motion.sh`
Expected: the three count lines and a `RESULT:` line. Copy them verbatim into `docs/compatibility.md`.

- [ ] **Step 3: Title-bar data probe (c)** — create `tests/probe_titledata.sh` (`chmod +x`):

```bash
#!/usr/bin/env bash
# P0-c: what does kitty hand a custom window_title_bar.py's draw_window_title(data)? Dumps the keys; no pass/fail.
set -u
for dep in Xvfb kitty python3; do command -v "$dep" >/dev/null 2>&1 || { echo "SKIP: $dep not installed"; exit 0; }; done
T=$(mktemp -d "${TMPDIR:-/tmp}/kmx-title.XXXXXX"); SOCK=unix:$T/sock; XPID="" KPID=""
cleanup() { [ -n "$KPID" ] && kill "$KPID" 2>/dev/null; [ -n "$XPID" ] && kill "$XPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
for n in $(seq 260 289); do [ -e "/tmp/.X$n-lock" ] || { DISP=:$n; break; }; done
Xvfb "$DISP" -screen 0 1000x700x24 >/dev/null 2>&1 & XPID=$!; sleep 1
kill -0 "$XPID" 2>/dev/null || { echo "SKIP: Xvfb would not start"; XPID=""; exit 0; }
mkdir -p "$T/cfg"
cat > "$T/cfg/window_title_bar.py" <<PY
import json

def draw_window_title(data):
    try:
        fields = data._asdict() if hasattr(data, "_asdict") else (dict(data) if hasattr(data, "items") else vars(data))
        with open("$T/title-data.json", "w") as f:
            json.dump({k: repr(v)[:80] for k, v in fields.items()}, f)
    except Exception as e:
        with open("$T/title-data.json", "w") as f:
            f.write(repr(type(data)) + " " + repr(dir(data)) + " " + repr(e))
    return "probe"
PY
printf 'allow_remote_control socket-only\nwindow_title_bar_min_windows 1\nwindow_title_template "{custom}"\nconfirm_os_window_close 0\n' > "$T/cfg/kitty.conf"
printf 'new_tab one\nlaunch sh\nlaunch --location=vsplit sh\n' > "$T/session"
env -u WAYLAND_DISPLAY __GLX_VENDOR_LIBRARY_NAME=mesa LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=$DISP KITTY_CONFIG_DIRECTORY=$T/cfg \
  kitty -o linux_display_server=x11 --class kmx-title --listen-on "$SOCK" --session "$T/session" >"$T/k.log" 2>&1 & KPID=$!
for _ in $(seq 60); do [ -S "$T/sock" ] && break; sleep 0.25; done; sleep 3
if [ -s "$T/title-data.json" ]; then echo "draw_window_title(data) received:"; cat "$T/title-data.json"; echo
  python3 - "$T/title-data.json" <<'PY'
import json, sys
try:
    keys = set(json.load(open(sys.argv[1])))
    ident = sorted(keys & {"cwd", "wd", "active_wd", "window_id", "id"})
    print("RESULT: a directory or window id is available:", bool(ident), ident, "| all fields:", sorted(keys))
except ValueError:
    print("RESULT: data was not a mapping — see the dump above")
PY
else echo "RESULT: draw_window_title was never called (see $T/k.log: $(tail -3 "$T/k.log" 2>/dev/null))"; fi
```

Run: `chmod +x tests/probe_titledata.sh && bash tests/probe_titledata.sh`. Copy the `RESULT:` line into `docs/compatibility.md`. If the data has no directory and no window id, P4 shrinks to "unchanged" (spec §7 risk 3). (Dry run on kitty 0.49.2: `WindowTitleData(has_activity_since_last_focus, is_active, needs_attention, tab_id, title, window_id)` — a `window_id`, so the cwd is reachable as `get_boss().window_id_map[data.window_id].child.current_cwd`.)

- [ ] **Step 4: Manual probe (b)+(d) for Hyprland** — create `tests/probe_panel.sh` (`chmod +x`). It is **manual by design** (Xvfb has no layer-shell); it must be run by the person from a terminal inside the kitty whose bar they want to align with:

```bash
#!/usr/bin/env bash
# P0-b/d (MANUAL, Wayland + Hyprland): where does a layer-shell sheet land, and how fast does it start?
# Run from a shell INSIDE the kitty you want to measure. It opens a small os-panel beside that kitty's tab bar for 6 s.
# Look: is the panel's left edge flush with the bar's right edge, and does its top line up with the row you expect?
set -u
command -v hyprctl >/dev/null 2>&1 || { echo "needs Hyprland (hyprctl)"; exit 1; }
SOCK="${KITTY_LISTEN_ON:-}"; [ -n "$SOCK" ] || { echo "run this inside a kitty with listen_on set (allow_remote_control socket-only)"; exit 1; }
read -r AX AY AW AH < <(hyprctl activewindow -j | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["at"][0],d["at"][1],d["size"][0],d["size"][1])')
BAR_PX="${1:-260}"      # the bar's width in pixels (pass it if yours differs: `kitty @ kitten tests/probe_bar.py out.json` prints right-left)
ROW_PX="${2:-120}"      # distance from the window's top to the row you want the sheet beside
M=$(mktemp); START=$(date +%s%N)
echo "active window at ${AX},${AY} size ${AW}x${AH}; placing the panel at margin-left=$((AX + BAR_PX)) margin-top=$((AY + ROW_PX))"
kitty @ --to "$SOCK" launch --type os-panel --os-panel edge=left --os-panel layer=overlay --os-panel focus-policy=not-allowed \
  --os-panel columns=36 --os-panel lines=14 --os-panel margin-left=$((AX + BAR_PX)) --os-panel margin-top=$((AY + ROW_PX)) \
  sh -c "date +%s%N > $M; printf '\n   side-sheet placement probe\n   (closes in 6 s)\n'; sleep 6" >/dev/null
for _ in $(seq 40); do [ -s "$M" ] && break; sleep 0.05; done
[ -s "$M" ] && echo "panel process started $(( ($(cat "$M") - START) / 1000000 )) ms after the launch call (first paint is a little later; budget ≤ 150 ms)"
echo "Report: (1) flush with the bar's edge? (2) top aligned with the row? (3) did it steal focus? (4) the ms above."
```

Run it once and write the four answers into `docs/compatibility.md`. Add to `docs/testing.md` under the manual-only list: "os-panel placement and start time on Hyprland (`tests/probe_panel.sh`) — never claimed from an Xvfb run."

- [ ] **Step 5: Write the results.** Add to `docs/compatibility.md`:

```markdown
## Side-sheet probes (kitty 0.49.2)

| Question | How checked | Answer |
|---|---|---|
| Does idle mouse motion over the tab bar reach Python? | `tests/probe_motion.sh` (Xvfb, real pointer events) | <paste the RESULT line and both counts> |
| What does `draw_window_title(data)` receive? | `tests/probe_titledata.sh` (Xvfb) | <paste the RESULT line> |
| Does an os-panel land flush beside the bar, and how fast does it start? | `tests/probe_panel.sh` — **manual, Hyprland** | <the person's four answers; "not yet run" if skipped> |
```
Replace each `<…>` with the real output; a row nobody ran says **not yet run**. Never record an Xvfb result as compositor verification.

- [ ] **Step 6: Commit and report**

```bash
git add tests/probe_motion.py tests/probe_motion.sh tests/probe_titledata.sh tests/probe_panel.sh docs/compatibility.md docs/testing.md
git commit -m "probes: does kitty deliver bar hover, what do pane title bars receive, where does a panel land (answers recorded)"
```
Report the three answers. They decide the next plans: hover (P3) exists only if the first answer is yes; pane title bars (P4) only if the second shows a directory or window id; sheet placement (P2) uses `hyprctl` if the third looks right, else the screen-edge dock.

---

### Task 10: Merge and apply to live (reload only)

**Files:** none.

- [ ] **Step 1: Record the live state first** — `for s in /tmp/mykitty-* "$XDG_RUNTIME_DIR"/mykitty-*; do [ -S "$s" ] && echo "$s $(kitty @ --to unix:$s ls | python3 -c 'import sys,json;print(sum(len(t["windows"]) for o in json.load(sys.stdin) for t in o["tabs"]))')"; done > /tmp/kmx-live-before.txt; cat /tmp/kmx-live-before.txt` — this only reads.
- [ ] **Step 2: Full verification on the branch** — `python3 -m unittest discover -s tests && bash tests/test_mux_status.sh && bash tests/test_socket_lib.sh && for t in place state click reload demo sidebar native drag resize; do bash tests/smoke_$t.sh || break; done`. Every rig must print `PASS` or an honest `SKIP`.
- [ ] **Step 3: Merge** — from the main checkout: `git -C /home/kitsunekode/Projects/kittymux merge --no-ff folder-sheet` (ask the person first: `main` is what live kitties load; never leave it half-merged). Resolve conflicts only in files this plan touched.
- [ ] **Step 4: Apply by reload only** — `kittymux upgrade` (re-links, reloads each kitty twice, runs doctor). Doctor must show the new `features` line.
- [ ] **Step 5: Compare** — repeat Step 1's loop into `/tmp/kmx-live-after.txt` and `diff` the two files: window counts must be identical. Tell the person to look at the bar.

---

## Self-review (run against the spec)

**Spec coverage.** P1 folder line → Tasks 2, 4; roles/colours/one-emphasis → `style` (Task 2) + Task 4 step 4; project:worktree → Task 2; hue → Task 3 + Task 4 steps 2/5; collisions → Task 2 (`colliding`) + Task 4 step 2; rail tint → Task 4 step 5; pluggability/presets/doctor/CLI → Tasks 1, 6; all-off equals today → Task 4 step 3 (legacy branch) + Task 5 step 5; perf budget → Task 7; probes a/c/b/d → Task 9; demo twins/README/CHANGELOG → Task 8; manual-only honesty → Task 9 step 4. **Not in this plan by design:** P2 sheet, P3 hover, P4 pane title bars, the `hover`/`sheet`/`panetitle` switches' behaviour (they exist in the switchboard and README as "planned"), light/dark screenshot review at 4/12/23 tabs (do it during Task 7 step 3 with `kittymux screenshot` and attach to the PR; it needs a human eye), P5 beyond the README/CHANGELOG/demo above.

**Placeholder scan.** The only `<…>` markers are measurement values the executor must paste from real output (Task 7 step 4, Task 9 step 5) — they are results, not unfinished design.

**Type consistency.** `Facts` fields (`project, worktree, inner, where, branch`), `layout(...)` signature and `style(...)` roles match across Tasks 2 and 4; `_Place.__slots__` (`facts, hide, style, emphasised, hue`) matches `_place_piece` and the dump keys (`emphasised`, `hue`, `hidden`) read by `smoke_place.sh`; `features_cmd`, `_nudge_bars`, `FEATURE_HELP` names match Task 6's tests; `kittymux_features.source/state_dir/FEATURES` used in doctor match Task 1.
