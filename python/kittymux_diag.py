"""What kittymux says when it cannot reach a kitty, in one place. Pure; no kitty imports.

A command bound to a key has no terminal: its stderr goes nowhere, so a failure used to look like "the key did nothing". `log_failure` leaves one line where
`kittymux doctor` shows it. Only fixed wording, directory names and the first line of kitty's own error are stored: never screen text, titles or agent output."""
from __future__ import annotations

import os
import subprocess
import time

SETUP_HINT = "set allow_remote_control socket-only and listen_on unix:${XDG_RUNTIME_DIR}/mykitty in kitty.conf, then restart kitty"
LOG = "cli-errors.log"
_CTRL = {c: " " for c in list(range(0, 32)) + [127] + list(range(0x80, 0xA0))}


def _clean(text, limit: int) -> str:
    return " ".join(str(text).translate(_CTRL).split())[:limit]


def no_socket_message(cmd: str, dirs: list[str]) -> str:
    where = ", ".join(_clean(d, 80) for d in dirs) or "nowhere (no socket directory exists)"
    return f"kittymux {_clean(cmd, 24)}: no kitty remote-control socket found (looked in {where}). {SETUP_HINT}; `kittymux doctor` checks it."


def describe_failure(rc: int, err: str, exc: BaseException | None) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return "timed out"
    if isinstance(exc, FileNotFoundError):
        return "kitty is not on PATH"
    first = _clean((err or "").strip().splitlines()[0] if (err or "").strip() else "", 160)
    return f"kitty @ exited {rc}" + (f": {first}" if first else "")


def log_failure(state_dir: str, cmd: str, text: str, now: float | None = None) -> None:
    try:
        import kittymux_bounded
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() if now is None else now))
        kittymux_bounded.append_capped(os.path.join(state_dir, LOG), f"{stamp} {_clean(cmd, 24)}: {_clean(text, 240)}\n", cap=32 * 1024)
    except Exception:
        pass


def recent_failures(state_dir: str, limit: int = 5) -> list[str]:
    try:
        with open(os.path.join(state_dir, LOG), encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n") for line in f.readlines()[-limit:]]
    except OSError:
        return []
