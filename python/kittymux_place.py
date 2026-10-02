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


def place_room(avail: int, later: list[int], sep: int = 2, floor: int = 6) -> int:
    """Cells the folder line may take when pieces drawn AFTER it (the layout picture, pane chips, "N panes") need
    `later` cells each: they keep theirs (and their separator) — unless that would squeeze the folder line under
    `floor` cells, then the folder line wins and they are dropped, as the branch alone always did."""
    want = avail - sum(width + sep for width in later)
    return want if want >= floor else avail


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


def worktree_named(title: str, f: Facts) -> bool:
    """True when the title says the linked worktree too ("kittymux:ui"): then nothing of project or worktree needs repeating."""
    t = " ".join(title.lower().split())
    return bool(t and f.worktree) and t == f"{f.project}:{f.worktree}".lower()


def layout(f: Facts, width: int, *, icon: str = "", branch_icon: str = "", hide_project: bool = False,
           hide_worktree: bool = False, cells: Callable[[str], int] = len) -> list[tuple[str, str]]:
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
            if wt_on and worktree and not hide_worktree:
                parts.append((worktree, "worktree"))
        elif wt_on and f.worktree and not hide_worktree:
            parts.append((f.worktree, "worktree"))       # the project is already said by the title; the worktree is not
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
