"""kittymux fanout — one task, several agents, each in its own git worktree (no kitty imports; unit-tested against real git repositories).

`create` makes `<repo>/.worktrees/<name>-<agent>` on a new branch `<name>-<agent>` from one base commit for every agent, all-or-nothing (a failure removes what it made). The fan-out is
recorded in the state dir so `compare` can later say what each agent did relative to that base (committed or not: it diffs the base tree against each worktree's current tree through
kittymux_changes, never writing into the repositories), and `clean` can remove exactly what `create` made.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time

import kittymux_changes as C

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$")
KEEP = 50


def _git(args: list[str], cwd: str, timeout: float = 60.0) -> tuple[int, str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C"})
    try:
        r = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args], cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)
    return r.returncode, r.stdout.decode("utf-8", "replace").strip(), r.stderr.decode("utf-8", "replace").strip()


def main_repo(cwd: str) -> str | None:
    """The MAIN checkout of the repository around `cwd` (a linked worktree's toplevel is the worktree itself), else None."""
    if not cwd or not os.path.isdir(cwd):
        return None
    rc, out, _ = _git(["rev-parse", "--show-toplevel", "--path-format=absolute", "--git-common-dir"], cwd)
    lines = out.split("\n")
    if rc != 0 or len(lines) < 2:
        return None
    top, common = lines[0], lines[1]
    return os.path.dirname(common) if os.path.basename(common) == ".git" and os.path.isdir(os.path.dirname(common)) else top


def resolve_base(repo: str, ref: str | None) -> str | None:
    ref = (ref or "HEAD").strip()
    if not ref or ref.startswith("-") or any(c in ref for c in "\0\n"):
        return None
    rc, out, _ = _git(["rev-parse", "--verify", "-q", f"{ref}^{{commit}}"], repo)
    return out if rc == 0 and re.fullmatch(r"[0-9a-f]{40}", out) else None


def valid_branch(name: str, repo: str) -> bool:
    return _git(["check-ref-format", "--branch", name], repo)[0] == 0 and not name.startswith("-")


def plan(repo: str, name: str, agents: list[str]) -> list[dict]:
    return [{"agent": a, "branch": f"{name}-{a}", "path": os.path.join(repo, ".worktrees", f"{name}-{a}")} for a in agents]


def _exclude_worktrees(repo: str) -> None:
    """Keep `.worktrees/` out of `git status` through the repository's local exclude file (not a tracked .gitignore) — the same convention as `mux-agent-new`."""
    rc, common, _ = _git(["rev-parse", "--path-format=absolute", "--git-common-dir"], repo)
    if rc != 0:
        return
    path = os.path.join(common, "info", "exclude")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        existing = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                existing = f.read()
        if ".worktrees/" not in existing.split():
            with open(path, "a", encoding="utf-8") as f:
                f.write(("" if existing.endswith("\n") or not existing else "\n") + ".worktrees/\n")
    except OSError:
        pass


def create(repo: str, name: str, base: str, agents: list[str]) -> tuple[list[dict], str | None]:
    """Make the worktrees. All or nothing: returns (made, None) or ([], why) after removing whatever it had made. Refuses an existing path or branch (never reuses someone's work)."""
    items = plan(repo, name, agents)
    for it in items:
        if os.path.exists(it["path"]):
            return [], f"{it['path']} already exists (pick another --name)"
        if _git(["rev-parse", "--verify", "-q", f"refs/heads/{it['branch']}"], repo)[0] == 0:
            return [], f"branch {it['branch']} already exists (pick another --name)"
        if not valid_branch(it["branch"], repo):
            return [], f"'{it['branch']}' is not a valid branch name"
    _exclude_worktrees(repo)
    made: list[dict] = []
    for it in items:
        rc, _out, err = _git(["worktree", "add", "-q", "-b", it["branch"], it["path"], base], repo)
        if rc != 0:
            remove(repo, made, force=True)
            return [], f"git could not create the worktree for {it['agent']}: {err.splitlines()[-1] if err else 'unknown error'}"
        made.append(it)
    return made, None


def remove(repo: str, items: list[dict], force: bool = False) -> list[str]:
    """Remove worktrees and their branches that `create` made. Without `force`, a worktree with uncommitted changes is kept (git refuses) and said so. Returns messages."""
    notes = []
    for it in items:
        if os.path.exists(it["path"]):
            rc, _o, err = _git(["worktree", "remove", *(["--force"] if force else []), it["path"]], repo)
            if rc != 0:
                notes.append(f"kept {it['agent']}: {err.splitlines()[-1] if err else 'could not remove'} (use --force to discard its changes)")
                continue
        if _git(["rev-parse", "--verify", "-q", f"refs/heads/{it['branch']}"], repo)[0] == 0:
            _git(["branch", "-D", it["branch"]], repo)
        notes.append(f"removed {it['agent']} ({it['branch']})")
    return notes


# ── the record ────────────────────────────────────────────────────────────────
def _path(state_dir: str) -> str:
    return os.path.join(state_dir, "fanouts.json")


def load(state_dir: str) -> dict:
    try:
        with open(_path(state_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if NAME_RE.match(str(k)) and isinstance(v, dict) and isinstance(v.get("agents"), list)} if isinstance(data, dict) else {}


def save(state_dir: str, name: str, repo: str, base: str, prompt: str, items: list[dict], now: float | None = None) -> None:
    data = load(state_dir)
    data[name] = {"repo": repo, "base": base, "created": now if now is not None else time.time(), "prompt": prompt[:200], "agents": items}
    for k in sorted(data, key=lambda k: data[k].get("created", 0), reverse=True)[KEEP:]:
        del data[k]
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    tmp = f"{_path(state_dir)}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, _path(state_dir))


def forget(state_dir: str, name: str) -> None:
    data = load(state_dir)
    if data.pop(name, None) is not None:
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        tmp = f"{_path(state_dir)}.{os.getpid()}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, _path(state_dir))


def compare(state_dir: str, rec: dict) -> list[dict]:
    """For each agent of a fan-out: what its worktree holds now relative to the base commit — `summary` (files / +add / −del, committed or not, untracked files included) or None when the
    worktree is gone or unreadable."""
    out = []
    for it in rec.get("agents", []):
        row = {"agent": it.get("agent"), "branch": it.get("branch"), "path": it.get("path"), "summary": None, "exists": os.path.isdir(it.get("path", ""))}
        if row["exists"]:
            snap = C.snapshot(it["path"], state_dir)
            base_tree = C._tree_of(it["path"], rec.get("base", ""), state_dir) if snap else None
            if snap and base_tree:
                row["summary"] = C.summarize(C.numstat(base_tree, snap["tree"], it["path"], state_dir))
        out.append(row)
    return out
