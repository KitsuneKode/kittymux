"""Clickable `path/to/file.py:42` references (pure — no kitty imports; unit-tested).

kitty ≥ 0.49.2 can treat arbitrary text as a link (`detect_url_regex`). kittymux uses that so a
file reference in an agent's output or a compiler error opens in your editor at that line.
The text under the mouse comes from program output, so it is untrusted: it must be a plain
`path:line[:col]` (no spaces, quotes or shell characters), must not start with `-`, and must
name a regular file that exists — it is never handed to a shell.
"""

from __future__ import annotations

import os
import re
import shlex

# POSIX-ERE form for kitty's `detect_url_regex` (no \d / \w there) and the Python form for
# open-actions.conf's `url` criterion; both describe the same text.
DETECT_REGEX = r"[[:alnum:]_./~-]+\.[[:alnum:]]+:[0-9]+(:[0-9]+)?"
OPEN_ACTIONS_URL = r"^[\w./~-]+\.\w+:\d+(:\d+)?$"

_REF = re.compile(r"^(?P<path>[\w./~-]+\.\w+):(?P<line>\d{1,7})(?::(?P<col>\d{1,5}))?$")

# editors by how they take a position
_PLUS_LINE = {"nvim", "vim", "vi", "nano", "emacs", "emacsclient", "pico", "joe", "ne"}   # +LINE FILE
_COLON_SUFFIX = {"hx", "helix", "micro", "zed", "zeditor", "subl", "sublime_text", "lite-xl"}   # FILE:LINE[:COL]
_GOTO = {"code", "codium", "code-oss", "cursor", "windsurf", "vscodium"}                        # --goto FILE:LINE[:COL]
GUI_EDITORS = {"zed", "zeditor", "subl", "sublime_text", "lite-xl"} | _GOTO                       # no terminal needed
FALLBACK_EDITORS = ("nvim", "vim", "vi", "nano")


def parse_ref(text: str) -> tuple[str, int, int | None] | None:
    """('path', line, col) for a well-formed reference, else None."""
    m = _REF.match(text.strip())
    if not m:
        return None
    path = m.group("path")
    if path.startswith("-"):                    # never let output smuggle a flag to the editor
        return None
    line = int(m.group("line"))
    if line < 1:
        return None
    col = m.group("col")
    return path, line, int(col) if col else None


def resolve(path: str, cwd: str, root: str | None = None) -> str | None:
    """Absolute path of an existing regular file: as given, under `cwd`, then under `root`
    (the repository root). None when nothing matches."""
    path = os.path.expanduser(path)
    candidates = [path] if os.path.isabs(path) else [os.path.join(cwd, path)] + ([os.path.join(root, path)] if root else [])
    for c in candidates:
        c = os.path.normpath(c)
        if os.path.isfile(c):
            return c
    return None


def default_editor(env: dict, which=None) -> list[str]:
    """argv of the user's editor: $VISUAL, $EDITOR, else the first of nvim/vim/vi/nano on PATH."""
    import shutil
    which = which or shutil.which
    for key in ("VISUAL", "EDITOR"):
        value = (env.get(key) or "").strip()
        if value:
            try:
                argv = shlex.split(value)
            except ValueError:
                continue
            if argv:
                return argv
    for name in FALLBACK_EDITORS:
        if which(name):
            return [name]
    return []


def editor_name(argv: list[str]) -> str:
    return os.path.basename(argv[0]) if argv else ""


def is_gui(argv: list[str]) -> bool:
    return editor_name(argv) in GUI_EDITORS


def editor_argv(editor: list[str], file: str, line: int, col: int | None = None) -> list[str]:
    """The editor's command line that opens `file` at `line` (and `col` where the editor takes one).
    An editor kittymux does not know just gets the file."""
    if not editor:
        return []
    name = editor_name(editor)
    pos = f"{line}:{col}" if col else str(line)
    if name in _PLUS_LINE:
        return [*editor, f"+{line}", file]
    if name in _COLON_SUFFIX:
        return [*editor, f"{file}:{pos}"]
    if name in _GOTO:
        return [*editor, "--goto", f"{file}:{pos}"]
    if name == "kak":
        return [*editor, file, f"+{pos}"]
    return [*editor, file]
