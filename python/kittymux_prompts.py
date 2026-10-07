# kittymux prompts — recognise a plain terminal waiting on YOU for a password or a yes/no
# (sudo, ssh, git, pacman/paru), so it can be announced like an agent that needs you.
#
# Pure Python, no kitty imports. A prompt needs POSITIVE evidence, as everywhere in kittymux:
# the line must be the LAST thing on the screen (a prompt waits at the bottom; the same words in
# scrollback or in prose are not one), and it must either be wording only that tool prints
# (`[sudo] password for kit:`) or be printed while that tool leads the pty's foreground group.
# What is returned is a Rule with FIXED text: the matched line carries a user name or a host, and
# is never stored, logged or shown. Nothing the user types is ever read.

import os
import re
from typing import NamedTuple

FEATURES = ("sudo", "loginprompt", "pkgprompt")     # the switches of kittymux_features, one per kind of prompt

_TAIL = 2000                                        # only the end of a screen is looked at
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|[\x00-\x08\x0b-\x1f\x7f]")


class Rule(NamedTuple):
    id: str
    feature: str
    kind: str            # an inbox kind
    progs: frozenset     # programs whose leading the pty makes the WEAK patterns count
    strong: tuple        # patterns that need no program
    weak: tuple          # patterns that need one
    say: str             # fixed text for the notification and the inbox


def _rx(*patterns):
    return tuple(re.compile(p) for p in patterns)


RULES = (
    Rule("sudo", "sudo", "permission", frozenset({"sudo", "sudo-rs", "su", "doas", "pkexec", "run0"}),
         _rx(r"\[sudo\] password( for [^\s:]+)?:", r"doas \([^)]*\) password:"),
         _rx(r"(?i)password:"),
         "is asking for your password"),
    Rule("login", "loginprompt", "permission", frozenset({"ssh", "scp", "sftp", "rsync", "ssh-add", "sshfs", "mosh", "git", "git-remote-https", "git-remote-http"}),
         (),
         _rx(r"Enter passphrase for .*:", r"\S+'s password:", r"Are you sure you want to continue connecting.*\?",
             r"(?:Username|Password) for '[^']*':", r"Enter passphrase.*:"),
         "is asking you to log in"),
    Rule("pkg", "pkgprompt", "question", frozenset({"pacman", "paru", "yay", "pikaur", "makepkg", "apt", "apt-get", "aptitude", "dnf", "yum", "zypper", "pamac", "flatpak"}),
         (),
         _rx(r".*\[(?:Y/n|y/N|y/n|Y/N)\]\s*:?"),
         "is waiting for a yes or a no"),
)


def _program(argv) -> str:
    try:
        return os.path.basename(str(argv[0])) if argv else ""
    except Exception:
        return ""


def last_line(text) -> str:
    """The last non-empty line of the screen text, control sequences removed, trailing blanks trimmed."""
    if not text:
        return ""
    for raw in reversed(str(text)[-_TAIL:].splitlines()):
        line = _ANSI.sub("", raw).rstrip()
        if line.strip():
            return line.strip()
    return ""


def classify(argv, text, enabled) -> Rule | None:
    """The rule whose prompt ends the screen, or None. `enabled` is the set of switched-on FEATURES names."""
    try:
        line = last_line(text)
        if not line or len(line) > 400:
            return None
        prog = _program(argv)
        for rule in RULES:
            if rule.feature not in enabled:
                continue
            if any(rx.fullmatch(line) for rx in rule.strong):
                return rule
            if prog in rule.progs and any(rx.fullmatch(line) for rx in rule.weak):
                return rule
    except Exception:
        return None
    return None


def who(rule: Rule, argv) -> str:
    """The name to show for the program: only ever one of OUR known names, never text taken from a command line."""
    prog = _program(argv)
    return prog if prog in rule.progs else rule.id
