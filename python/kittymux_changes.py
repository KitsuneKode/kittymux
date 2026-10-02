"""kittymux changes — "what did the agent change?" (no kitty imports; unit-tested against real git repositories).

When an agent's run starts, a helper snapshots the working tree as a git TREE (tracked, modified and untracked-but-not-ignored files); when it ends, it snapshots again and diffs the
two trees. The summary — `7 files +142 −30` and the biggest files — is cached per window and shown in the picker, the peek card, the bar (on a finished tab) and `kittymux changes`.

It never writes into your repository. The snapshot uses a TEMPORARY index and a PRIVATE object directory under the state dir, with the repository's own objects as read-only alternates,
so `.git` is untouched (no new objects, no index change, no refs, no locks: GIT_OPTIONAL_LOCKS=0). Git runs without a terminal, without our environment's GIT_* variables, with the
file-system monitor and external diff / textconv programs off, a timeout, and low priority; a repository git itself distrusts (`safe.directory`) is skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time

TIMEOUT_S = 25.0
MAX_ROWS = 400                  # numstat rows read; the summary still counts the rest
KEEP_S = 7 * 86400
ODB_MAX_BYTES = 512 * 1024 * 1024
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _clean_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C"})
    env.update(extra or {})
    return env


def _git(args: list[str], cwd: str, env: dict | None = None, timeout: float = TIMEOUT_S) -> tuple[int, str]:
    cmd = ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", "-c", "core.quotePath=false", *args]
    try:
        r = subprocess.run(cmd, cwd=cwd, env=_clean_env(env), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return r.returncode, r.stdout.decode("utf-8", "replace")


def repo_info(cwd: str) -> dict | None:
    """{"top", "objects", "head"} for the repository containing `cwd`, else None (not a repository, or git distrusts it)."""
    if not cwd or not os.path.isdir(cwd):
        return None
    rc, out = _git(["rev-parse", "--show-toplevel", "--path-format=absolute", "--git-common-dir"], cwd)
    lines = out.split("\n")
    if rc != 0 or len(lines) < 2 or not os.path.isdir(lines[0]) or not os.path.isdir(lines[1]):
        return None
    rc, head = _git(["rev-parse", "--verify", "-q", "HEAD"], lines[0])
    return {"top": lines[0], "objects": os.path.join(lines[1], "objects"), "head": head.strip() if rc == 0 else None}


def odb_dir(state_dir: str, top: str) -> str:
    return os.path.join(state_dir, "changes-objects", hashlib.sha1(top.encode()).hexdigest()[:16])


def _odb_env(state_dir: str, info: dict, index: str | None = None) -> dict:
    d = odb_dir(state_dir, info["top"])
    os.makedirs(os.path.join(d, "pack"), mode=0o700, exist_ok=True)
    env = {"GIT_OBJECT_DIRECTORY": d, "GIT_ALTERNATE_OBJECT_DIRECTORIES": info["objects"]}
    if index:
        env["GIT_INDEX_FILE"] = index
    return env


def snapshot(cwd: str, state_dir: str) -> dict | None:
    """{"tree", "head", "top"}: the working tree of the repository around `cwd` as a git tree object living in OUR private object directory. None if it is not a repository or git failed."""
    info = repo_info(cwd)
    if info is None:
        return None
    fd, index = tempfile.mkstemp(prefix="idx-", dir=_private_tmp(state_dir))
    os.close(fd)
    os.unlink(index)                                           # git wants to create it itself
    env = _odb_env(state_dir, info, index)
    try:
        rc, _ = _git(["read-tree", info["head"]] if info["head"] else ["read-tree", "--empty"], info["top"], env)
        if rc == 0:
            rc, _ = _git(["add", "-A", "--", "."], info["top"], env)
        if rc != 0:
            return None
        rc, tree = _git(["write-tree"], info["top"], env)
        tree = tree.strip()
        return {"tree": tree, "head": info["head"], "top": info["top"]} if rc == 0 and len(tree) == 40 else None
    finally:
        try:
            os.unlink(index)
        except OSError:
            pass


def _private_tmp(state_dir: str) -> str:
    d = os.path.join(state_dir, "changes-tmp")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def numstat(base_tree: str, cur_tree: str, top: str, state_dir: str) -> list[tuple[int | None, int | None, str]] | None:
    """[(added, deleted, path)] between two trees (None, None for a binary file). None when git failed."""
    info = repo_info(top)
    if info is None:
        return None
    rc, out = _git(["diff", "--numstat", "-z", "--no-ext-diff", "--no-textconv", base_tree, cur_tree], info["top"], _odb_env(state_dir, info))
    if rc != 0:
        return None
    rows, parts, i = [], out.split("\0"), 0
    while i < len(parts) and parts[i]:
        a, d, rest = (parts[i].split("\t", 2) + ["", ""])[:3]
        path = rest
        if rest == "":                                          # a rename: "a\td\t\0old\0new\0"
            path = parts[i + 2] if i + 2 < len(parts) else ""
            i += 2
        rows.append((int(a) if a.isdigit() else None, int(d) if d.isdigit() else None, path))
        i += 1
    return rows


def summarize(rows: list[tuple[int | None, int | None, str]] | None, top_n: int = 5) -> dict | None:
    if rows is None:
        return None
    add = sum(a or 0 for a, _d, _p in rows)
    dele = sum(d or 0 for _a, d, _p in rows)
    biggest = sorted(rows, key=lambda r: -((r[0] or 0) + (r[1] or 0)))[:top_n]
    return {"files": len(rows), "add": add, "del": dele, "top": [{"path": p, "add": a, "del": d} for a, d, p in biggest]}


def format_summary(summary: dict | None) -> str:
    """`7 files +142 −30` / `1 file +3` / `no changes` ('' when unknown). Built from integers only: safe to put anywhere."""
    if not summary:
        return ""
    try:
        n, a, d = int(summary["files"]), int(summary["add"]), int(summary["del"])
    except (KeyError, TypeError, ValueError):
        return ""
    if n == 0:
        return "no changes"
    return f"{n} file{'s' if n != 1 else ''}" + (f" +{a}" if a else "") + (f" −{d}" if d else "")


# ── the cache: one small file per kitty ───────────────────────────────────────
def path_for(state_dir: str, kitty_pid: int) -> str:
    return os.path.join(state_dir, f"changes-{int(kitty_pid)}.json")


def load(state_dir: str, kitty_pid: int) -> dict:
    try:
        with open(path_for(state_dir, kitty_pid), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return {str(k): v for k, v in data.items() if str(k).isdigit() and isinstance(v, dict)} if isinstance(data, dict) else {}


def update(state_dir: str, kitty_pid: int, window_id, fields: dict, now: float | None = None) -> None:
    """Merge `fields` into one window's entry (atomic, 0600, flock'd). Entries older than a week and all but the 200 newest are dropped."""
    import fcntl
    now = time.time() if now is None else now
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    lock = os.open(os.path.join(state_dir, "changes.lock"), os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load(state_dir, kitty_pid)
        entry = data.setdefault(str(int(window_id)), {})
        entry.update(fields)
        entry["touched"] = now
        for k in [k for k, v in data.items() if now - v.get("touched", 0) > KEEP_S]:
            del data[k]
        for k in sorted(data, key=lambda k: data[k].get("touched", 0), reverse=True)[200:]:
            del data[k]
        path = path_for(state_dir, kitty_pid)
        tmp = f"{path}.{os.getpid()}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, path)
    finally:
        os.close(lock)


def prune_stores(state_dir: str, now: float | None = None, max_bytes: int = ODB_MAX_BYTES) -> None:
    """Keep the private object directories bounded: drop the ones untouched for a week, then the oldest until under `max_bytes`."""
    root = os.path.join(state_dir, "changes-objects")
    now = time.time() if now is None else now
    try:
        dirs = [(os.path.join(root, n), os.stat(os.path.join(root, n)).st_mtime) for n in os.listdir(root)]
    except OSError:
        return

    def size(p: str) -> int:
        return sum(os.path.getsize(os.path.join(a, f)) for a, _d, fs in os.walk(p) for f in fs if os.path.exists(os.path.join(a, f)))

    for p, t in [x for x in dirs if now - x[1] > KEEP_S]:
        shutil.rmtree(p, ignore_errors=True)
    live = sorted([x for x in dirs if now - x[1] <= KEEP_S], key=lambda x: x[1])
    total = sum(size(p) for p, _t in live)
    while live and total > max_bytes:
        p, _t = live.pop(0)
        total -= size(p)
        shutil.rmtree(p, ignore_errors=True)


# ── the two moments ───────────────────────────────────────────────────────────
def start(state_dir: str, kitty_pid: int, window_id, cwd: str, now: float | None = None) -> bool:
    """A run began: remember the working tree as it is now."""
    snap = snapshot(cwd, state_dir)
    if snap is None:
        return False
    update(state_dir, kitty_pid, window_id, {"base_tree": snap["tree"], "head": snap["head"], "top": snap["top"], "base_ts": now if now is not None else time.time(),
                                            "summary": None, "summary_ts": None, "vs": "run"}, now)
    return True


def finish(state_dir: str, kitty_pid: int, window_id, cwd: str, now: float | None = None) -> dict | None:
    """A run ended (or you asked): diff the working tree now against the baseline — or against HEAD when there is none (kittymux started watching mid-run). Caches and returns the summary."""
    cur = snapshot(cwd, state_dir)
    if cur is None:
        return None
    entry = load(state_dir, kitty_pid).get(str(int(window_id))) or {}
    if entry.get("base_tree") and entry.get("top") == cur["top"]:
        base, vs = entry["base_tree"], "run"
    else:
        base, vs = (cur["head"] and _tree_of(cur["top"], cur["head"], state_dir)) or EMPTY_TREE, "HEAD"
    rows = numstat(base, cur["tree"], cur["top"], state_dir)
    summary = summarize(rows)
    if summary is None:
        return None
    summary["files_list"] = [{"path": p, "add": a, "del": d} for a, d, p in (rows or [])[:MAX_ROWS]]
    update(state_dir, kitty_pid, window_id, {"summary": summary, "summary_ts": now if now is not None else time.time(), "vs": vs, "top": cur["top"]}, now)
    return summary


def _tree_of(top: str, commit: str, state_dir: str) -> str | None:
    info = repo_info(top)
    if info is None:
        return None
    rc, out = _git(["rev-parse", "--verify", "-q", f"{commit}^{{tree}}"], info["top"], _odb_env(state_dir, info))
    return out.strip() if rc == 0 else None
