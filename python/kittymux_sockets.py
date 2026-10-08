"""Owned kitty resolution shared by CLI workflows; invalid explicit targets fail closed."""
import glob
import os
import re
import socket
import stat


def socket_fd(target):
    """Only an open, owned, connected Unix socket can be an inherited handle."""
    if not isinstance(target, str) or not target.startswith('fd:') or not target[3:].isdecimal():
        return None
    fd = int(target[3:])
    if fd < 3:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            return None
        with socket.socket(fileno=os.dup(fd)) as endpoint:
            if endpoint.family != socket.AF_UNIX:
                return None
            endpoint.getpeername()
        return fd
    except OSError:
        return None


def own(directories, owned, env=None, ppid=None):
    env = os.environ if env is None else env
    ppid = os.getppid() if ppid is None else ppid
    for directory in directories:
        path = f'{directory}/mykitty-{ppid}'
        if owned(path):
            return 'unix:' + path
    hint = env.get('KITTY_LISTEN_ON', '')
    if socket_fd(hint) is not None:
        return hint
    if hint.startswith('unix:') and owned(hint[5:]):
        return hint
    pid = env.get('KITTY_PID', '')
    if pid.isdecimal():
        for directory in directories:
            path = f'{directory}/mykitty-{pid}'
            if owned(path):
                return 'unix:' + path
    return None


def target_how(own_socket, directories, owned, env=None):
    """(socket, how): `how` is "explicit" (KITTYMUX_TARGET), "own" (the kitty we were started in), "newest" (a guess: the newest socket we own) or "none"."""
    env = os.environ if env is None else env
    explicit = env.get('KITTYMUX_TARGET', '')
    if explicit:
        ok = (explicit.startswith('unix:') and owned(explicit[5:])) or socket_fd(explicit) is not None
        return (explicit, 'explicit') if ok else (None, 'none')
    current = own_socket()
    if current:
        return current, 'own'
    candidates = []
    for directory in directories:
        for path in glob.glob(os.path.join(directory, 'mykitty-*')):
            if owned(path):
                try:
                    candidates.append((os.stat(path).st_mtime_ns, path))
                except OSError:
                    pass
    return ('unix:' + max(candidates)[1], 'newest') if candidates else (None, 'none')


def target(own_socket, directories, owned, env=None):
    return target_how(own_socket, directories, owned, env)[0]


# ── the old place ─────────────────────────────────────────────────────────────
# kitty names its control socket <listen_on>-<pid>. kittymux recommends putting it in $XDG_RUNTIME_DIR (a private 0700 directory), but a lot of
# scripts written for `listen_on unix:/tmp/mykitty` look for /tmp/mykitty-<pid> and nowhere else: when the socket moved, every one of them
# silently stopped finding its kitty. A link at the old path keeps them working. The link grants nothing: the socket's permissions and its
# private directory are what protect it, and the link is only ever created by the kitty's own user, never over anything that exists.
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.]*-\d+$")


def is_owned_socket(path):
    """A real socket (a link to one counts) owned by the current user."""
    try:
        info = os.stat(path)
    except OSError:
        return False
    return stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid()


def legacy_link(listening_on, legacy_dir="/tmp"):
    """Make /tmp/<name>-<pid> point at kitty's real socket when that lives elsewhere. Returns what happened as short text; never raises."""
    try:
        if not isinstance(listening_on, str) or not listening_on.startswith("unix:"):
            return "not a unix socket path"
        path = listening_on[5:]
        if not path.startswith("/"):
            return "not a unix socket path"                      # relative paths and abstract sockets (@name) have no file to link to
        path = os.path.normpath(path)
        name = os.path.basename(path)
        if not _NAME.match(name):
            return "name is not kitty's <name>-<pid>: not ours to link"
        if os.path.realpath(os.path.dirname(path)) == os.path.realpath(legacy_dir):
            return "not needed"
        if not is_owned_socket(path):
            return "not a socket we own"
        link = os.path.join(legacy_dir, name)
        if os.path.lexists(link):
            if os.path.islink(link) and os.readlink(link) == path:
                return "already linked"
            return "left alone: something else is already at " + link
        os.symlink(path, link)
        return "linked"
    except OSError as e:
        return f"could not link: {e.strerror or e}"
    except Exception as e:                                       # a helper that runs inside kitty must never raise into it
        return f"could not link: {type(e).__name__}"


def _pid_alive(name):
    try:
        return os.path.exists("/proc/" + name.rsplit("-", 1)[1])
    except Exception:
        return True


def prune_links(legacy_dir="/tmp", runtime_dir=None):
    """Remove the links of kitties that have exited. Only a link of ours is touched: a symlink, owned by us, named <name>-<pid> and pointing at a
    file of that SAME name (what legacy_link makes), whose target is gone and whose pid is no longer running. Anything else is left alone."""
    removed = []
    try:
        for name in sorted(os.listdir(legacy_dir)):
            if not _NAME.match(name):
                continue
            path = os.path.join(legacy_dir, name)
            info = os.lstat(path)
            if not stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid() or os.path.exists(path):
                continue
            if os.path.basename(os.readlink(path)) != name or _pid_alive(name):
                continue
            os.unlink(path)
            removed.append(name)
    except OSError:
        pass
    return removed


def dedupe(paths):
    """One entry per real socket, first spelling kept, order kept (a socket and its compatibility link are the same kitty)."""
    seen, out = set(), []
    for p in paths:
        key = os.path.realpath(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out
