"""Reading option values off a command line, in one place. Pure."""
from __future__ import annotations


class UsageError(Exception):
    """The command was used wrongly: print this, exit 2, do nothing else."""


def take(it, flag: str, *, allow=None) -> str:
    """The value that follows `flag`. A missing one, another `--option`, or (when `allow` is given) anything not in it is a usage error. A lone `-` is a value."""
    value = next(it, None)
    if value is None or value.startswith("--"):
        raise UsageError(f"{flag} needs a value")
    if allow is not None and value not in allow:
        raise UsageError(f"{flag} needs one of: {', '.join(allow)}")
    return value
