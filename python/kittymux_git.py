# kittymux git — branch / project / worktree of a directory WITHOUT spawning git.
#
# The tab bar asks "what branch is this tab on?" for every tab on every redraw (and a
# redraw can be 10×/second while a spinner runs). Forking `git rev-parse` for that costs
# a process per tab per second; reading the two tiny files git itself reads costs
# microseconds. Results are cached per repo and invalidated by HEAD's mtime, so a
# `git switch` shows up immediately.
#
# Pure Python, no kitty imports.

import os
from typing import NamedTuple

_MAX_UP = 40            # never walk further than this many parents
_CACHE_MAX = 256        # bound the cache (a long-lived kitty visits many directories)


class GitInfo(NamedTuple):
    top: str            # working tree root
    branch: str         # branch name, or "detached"
    project: str        # main repository's directory name (same for all its worktrees)
    worktree: str       # linked worktree's directory name, else ""


_cache: dict[str, tuple[float, GitInfo]] = {}     # top -> (HEAD mtime, info)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def _find_dotgit(cwd: str) -> tuple[str, str] | None:
    """(top, dotgit path) for the nearest enclosing repo, else None."""
    path = os.path.abspath(cwd)
    for _ in range(_MAX_UP):
        dotgit = os.path.join(path, ".git")
        if os.path.exists(dotgit):
            return path, dotgit
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent
    return None


def _resolve_gitdir(top: str, dotgit: str) -> str | None:
    """A normal repo's .git directory; for worktrees/submodules the `gitdir:` target."""
    if os.path.isdir(dotgit):
        return dotgit
    text = _read(dotgit)                                   # "gitdir: /path/to/.git/worktrees/x"
    if text.startswith("gitdir:"):
        target = text[len("gitdir:"):].strip()
        return target if os.path.isabs(target) else os.path.normpath(os.path.join(top, target))
    return None


def _common_dir(gitdir: str) -> str:
    """Where the main repository's data lives (differs from gitdir for linked worktrees)."""
    rel = _read(os.path.join(gitdir, "commondir"))
    if not rel:
        return gitdir
    return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(gitdir, rel))


def _branch(gitdir: str) -> str:
    head = _read(os.path.join(gitdir, "HEAD"))
    if head.startswith("ref:"):
        ref = head[4:].strip()
        return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    return "detached" if head else ""


def info(cwd: str) -> GitInfo | None:
    """Git facts for `cwd`, or None outside a repository."""
    if not cwd:
        return None
    found = _find_dotgit(cwd)
    if found is None:
        return None
    top, dotgit = found
    gitdir = _resolve_gitdir(top, dotgit)
    if gitdir is None:
        return None
    head_path = os.path.join(gitdir, "HEAD")
    try:
        mtime = os.stat(head_path).st_mtime
    except OSError:
        return None
    hit = _cache.get(top)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    common = _common_dir(gitdir)
    is_linked_worktree = os.path.realpath(common) != os.path.realpath(gitdir) \
        and os.path.basename(os.path.dirname(gitdir)) == "worktrees"
    main_top = os.path.dirname(common) if os.path.basename(common) == ".git" else top
    result = GitInfo(
        top=top,
        branch=_branch(gitdir),
        project=os.path.basename(main_top) or os.path.basename(top),
        worktree=(os.path.basename(top) or "worktree") if is_linked_worktree else "",
    )
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))                      # drop the oldest entry
    _cache[top] = (mtime, result)
    return result


def label(cwd: str, home: str | None = None, limit: int = 34) -> tuple[str, str]:
    """(label, branch) like the tab bar's right-hand anchor: project[:worktree]/inner-path
    inside a repo, else the abbreviated ~ path."""
    gi = info(cwd)
    if gi is None:
        return short_path(cwd, home, limit), ""
    text = gi.project + (":" + gi.worktree if gi.worktree else "")
    if os.path.abspath(cwd) != gi.top:
        rel = os.path.relpath(os.path.abspath(cwd), gi.top)
        if rel != ".":
            text += "/" + rel
    return text, gi.branch


def short_path(path: str, home: str | None = None, limit: int = 34) -> str:
    home = home or os.path.expanduser("~")
    if path == home:
        shown = "~"
    elif path.startswith(home + "/"):
        shown = "~/" + path[len(home) + 1:]
    else:
        shown = path
    if len(shown) <= limit:
        return shown
    parts = [p for p in shown.split("/") if p]
    if len(parts) >= 2:
        shown = ("~/" if shown.startswith("~/") else "") + f"…/{parts[-2]}/{parts[-1]}"
    return shown if len(shown) <= limit else shown[: limit - 1] + "…"
