"""Owned kitty resolution shared by CLI workflows; invalid explicit targets fail closed."""
import glob
import os
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


def target(own_socket, directories, owned, env=None):
    env = os.environ if env is None else env
    explicit = env.get('KITTYMUX_TARGET', '')
    if explicit:
        return explicit if (explicit.startswith('unix:') and owned(explicit[5:])) or socket_fd(explicit) is not None else None
    current = own_socket()
    if current:
        return current
    candidates = []
    for directory in directories:
        for path in glob.glob(os.path.join(directory, 'mykitty-*')):
            if owned(path):
                try:
                    candidates.append((os.stat(path).st_mtime_ns, path))
                except OSError:
                    pass
    return 'unix:' + max(candidates)[1] if candidates else None
