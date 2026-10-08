"""The two ways kittymux keeps a long-lived thing from growing without limit: a table with a size cap and a log with a size cap. Pure; no kitty imports.

The scanner and the tab bar live as long as kitty does. Anything keyed by something that keeps arriving (a window id, an error text, a path) must be capped,
or a month-long session grows by one entry per distinct key it ever saw. `tests/test_bounded_state.py` lists every module-level container and asks why it is
safe; when the answer is "it is capped", use these instead of writing a third copy."""
from __future__ import annotations

import os


def cap_newest(table: dict, cap: int) -> int:
    """Drop the oldest-inserted entries until `len(table) <= cap`. Returns how many went. (A dict remembers insertion order; re-insert a key to make it newest.)"""
    drop = len(table) - max(0, cap)
    if drop <= 0:
        return 0
    for key in list(table)[:drop]:
        del table[key]
    return drop


def seen_within(table: dict, key, now: float, window: float, cap: int = 256) -> bool:
    """Has `key` been seen less than `window` seconds ago? True means "skip it". Otherwise it is recorded as seen now (and made the newest entry) and False is
    returned. The table never holds more than `cap` keys."""
    last = table.get(key)
    if last is not None and window > 0 and now - last < window:
        return True
    table.pop(key, None)
    table[key] = now
    cap_newest(table, cap)
    return False


def append_capped(path, text: str, cap: int = 64 * 1024) -> bool:
    """Append `text` to a log that never passes about `cap` bytes: past it, the file is rewritten with its newest half, cut at a line start. Never raises."""
    try:
        path = os.fspath(path)
        if os.path.exists(path) and os.path.getsize(path) > cap:
            with open(path, "rb") as f:
                f.seek(-(cap // 2), os.SEEK_END)
                tail = f.read()
            nl = tail.find(b"\n")
            tail = tail[nl + 1:] if nl >= 0 else b""
            fd = os.open(path, os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(tail)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception:
        return False
