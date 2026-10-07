"""Publish complete autosaves atomically, in capture order rather than worker order."""
import fcntl
import os
import re
import tempfile
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
HEADER = '# kittymux captured_ns: '


def publish(directory, pid, captured_ns, text):
    if (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or
            not isinstance(captured_ns, int) or isinstance(captured_ns, bool) or captured_ns <= 0 or
            not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BYTES):
        raise ValueError('invalid session capture')
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f'autosave-{pid}.kitty-session'
    lock = os.open(directory / f'.autosave-{pid}.lock', os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with path.open(encoding='utf-8') as old:
                match = re.fullmatch(r'# kittymux captured_ns: (\d+)\n', old.readline(128))
            if match and int(match[1]) >= captured_ns:
                return False
        except OSError:
            pass
        fd, tmp = tempfile.mkstemp(prefix='.autosave-', dir=directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(HEADER + str(captured_ns) + '\n' + text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return True
    finally:
        os.close(lock)
