# kittymux switches — every on/off setting in one catalog.
#
# Pure Python, no kitty imports. A switch is DATA: what a person calls it, one sentence about it, its default, how much it can change, and how it was spelled
# before this module existed (an environment variable and a flag file whose names are older than the catalog). `resolve` answers "on or off, and why"; `set_switch`
# writes at most one flag file. The settings view, `kittymux features` and `kittymux settings` all read this, so none of them owns a file name.
#
# Precedence, unchanged: environment variable > flag file in the state directory > default. If both flag files exist the `-off` one wins.
# `tests/test_switches.py` keeps the OLD inline expressions as the specification and checks the catalog against them for every combination.

from __future__ import annotations

import os
from dataclasses import dataclass

NONE, NETWORK, FOCUS, RESUME = "none", "network", "focus", "resume"
LIVE, PLANNED = "live", "planned"

GROUPS = ("Bar", "Notifications", "Safety and recovery", "Opt-in")

_GENERIC_OFF = frozenset({"0", "off", "false", "no"})
_GENERIC_ON = frozenset({"1", "on", "true", "yes"})


@dataclass(frozen=True)
class Switch:
    id: str
    group: str
    label: str                     # what a person calls it
    help: str                      # one sentence, at most 90 characters
    default: bool
    status: str = LIVE             # LIVE | PLANNED (saved, nothing reads it yet)
    risk: str = NONE               # what turning it ON changes beyond the screen: NETWORK | FOCUS | RESUME
    consequence: str = ""          # shown before a risky switch is turned on
    # how it was spelled before the catalog (unset = the generic spelling)
    env: tuple[str, ...] = ()      # environment variables, first one set (to a value that means something) wins
    env_off: frozenset = _GENERIC_OFF
    env_on: frozenset = _GENERIC_ON
    flag_off: str = ""             # file in the state directory that switches it off
    flag_on: str = ""              # file that switches it on

    def env_names(self) -> tuple[str, ...]:
        return self.env or ("KITTYMUX_" + self.id.upper().replace("-", "_"),)

    def off_file(self) -> str:
        return self.flag_off or f"{self.id}-off"

    def on_file(self) -> str:
        return self.flag_on or f"{self.id}-on"


def _legacy_off(var: str, flag: str) -> dict:
    """A default-on switch as it was always spelled: only the value `0` turns it off, only the file `<x>-off`."""
    return dict(env=(var,), env_off=frozenset({"0"}), env_on=frozenset(), flag_off=flag)


def _legacy_on(var: str, values: tuple[str, ...], flag: str) -> dict:
    """A default-off switch as it was always spelled: only the listed values turn it on, only the file `flag`."""
    return dict(env=(var,), env_on=frozenset(values), env_off=frozenset(), flag_on=flag)


CATALOG: tuple[Switch, ...] = (
    # ── Bar ────────────────────────────────────────────────────────────────────────────────────────────────────────────
    Switch("folder", "Bar", "Folder line", "The project and branch under each tab's title.", True),
    Switch("hue", "Bar", "Colour per project", "A calm, stable tint for each project's name and icon.", True),
    Switch("collide", "Bar", "Mark tabs with the same title", "Emphasise the project of tabs whose titles are the same.", True),
    Switch("panetitle", "Bar", "Folder line in pane title bars", "The same line in each pane's title bar (needs kitty 0.49.2).", True),
    Switch("motion", "Bar", "Spinner motion", "The working spinner turns. Off: one still frame, nothing redraws to animate.", True),
    Switch("titles", "Bar", "Tidy tab names", "A tab is called by its task or project, never by an agent's reply.", True),
    Switch("sheet", "Bar", "Side sheet", "A sheet with a tab's details.", True, status=PLANNED),
    Switch("hover", "Bar", "Sheet on hover", "Open the side sheet when the pointer rests on a tab.", False, status=PLANNED),
    # ── Notifications ──────────────────────────────────────────────────────────────────────────────────────────────────
    Switch("notify", "Notifications", "Needs-you popups", "A desktop notification when an agent you are not looking at needs you.", True,
           **_legacy_off("KITTYMUX_NOTIFY", "notify-off")),
    Switch("notify-done", "Notifications", "Completion popups", "A notification when a run of 15 seconds or more finishes.", True,
           **_legacy_off("KITTYMUX_NOTIFY_DONE", "notify-done-off")),
    Switch("bell", "Notifications", "Bell", "A window-manager flash when an agent needs you (skipped where it would steal focus).", True,
           **_legacy_off("KITTYMUX_BELL", "bell-off")),
    Switch("notify-private", "Notifications", "Private notifications", "Popups and the inbox say that something happened, never what was on screen.", False,
           **_legacy_on("KITTYMUX_NOTIFY_PRIVATE", ("1",), "notify-private")),
    Switch("sudo", "Notifications", "Password prompts", "A notification when sudo, doas, su or pkexec waits in a pane you are not in.", True),
    Switch("loginprompt", "Notifications", "Login prompts", "The same for ssh and git asking for a passphrase, a password or to trust a host.", True),
    Switch("pkgprompt", "Notifications", "Package prompts", "The same for pacman, paru, yay, apt and dnf waiting for a yes or a no.", True),
    # ── Safety and recovery ────────────────────────────────────────────────────────────────────────────────────────────
    Switch("autosave", "Safety and recovery", "Autosave sessions", "Save the layout and its agents now and then, so a crash can be restored.", True,
           **_legacy_off("KITTYMUX_AUTOSAVE", "autosave-off")),
    Switch("journal", "Safety and recovery", "Session journal", "Remember every agent session: what it ran, how long, in which folder.", True,
           **_legacy_off("KITTYMUX_JOURNAL", "journal-off")),
    Switch("changes", "Safety and recovery", "Track what an agent changed", "Take a snapshot at a run's start and end (never written into your repo).", True,
           **_legacy_off("KITTYMUX_CHANGES", "changes-off")),
    Switch("socketlink", "Safety and recovery", "Legacy socket link", "A link at /tmp/mykitty-<pid> so scripts written for listen_on in /tmp still work.", True),
    # ── Opt-in ─────────────────────────────────────────────────────────────────────────────────────────────────────────
    Switch("attention", "Opt-in", "Let a bell move focus", "A bell may switch you to the window that rang it.", False, risk=FOCUS,
           consequence="A bell from any window can pull you to that window, and on some compositors to another workspace.",
           **_legacy_on("KITTYMUX_ATTENTION", ("1",), "attention-on")),
    Switch("resume-auto", "Opt-in", "Resume agents without asking", "A restored agent resumes its conversation straight away.", False, risk=RESUME,
           consequence="Restoring a session will start every saved agent again with its saved flags, without asking first.",
           **_legacy_on("KITTYMUX_RESUME", ("auto",), "resume-auto")),
    Switch("usage-live", "Opt-in", "Live usage requests", "Ask each provider for your quota, with your own login.", False, risk=NETWORK,
           consequence="kittymux will contact each provider's API with your own login to read your quotas, about every 5 minutes.",
           **_legacy_on("KITTYMUX_USAGE_LIVE", ("1", "on", "true", "yes"), "usage-live-on")),
)

BY_ID = {s.id: s for s in CATALOG}
IDS = tuple(s.id for s in CATALOG)


def state_dir(env=None) -> str:
    env = os.environ if env is None else env
    return env.get("KITTYMUX_STATE") or os.path.join(env.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "kittymux")


def get(name: str) -> Switch:
    try:
        return BY_ID[name]
    except KeyError:
        raise ValueError(f"unknown setting {name!r} (known: {', '.join(IDS)})") from None


def resolve(name: str, sdir: str | None = None, env=None) -> tuple[bool, str, str]:
    """(on, where, what): `where` is 'env', 'flag' or 'default'; `what` names the variable or the file that decided it ('' for the default)."""
    sw = get(name)
    env = os.environ if env is None else env
    for var in sw.env_names():
        raw = env.get(var, "").strip().lower()
        if raw in sw.env_off:
            return False, "env", var
        if raw in sw.env_on:
            return True, "env", var
    sdir = sdir or state_dir(env)
    if os.path.exists(os.path.join(sdir, sw.off_file())):
        return False, "flag", sw.off_file()
    if os.path.exists(os.path.join(sdir, sw.on_file())):
        return True, "flag", sw.on_file()
    return sw.default, "default", ""


def enabled(name: str, sdir: str | None = None, env=None) -> bool:
    return resolve(name, sdir, env)[0]


def source(name: str, sdir: str | None = None, env=None) -> tuple[bool, str]:
    on, where, _ = resolve(name, sdir, env)
    return on, where


def set_switch(sdir: str, name: str, on: bool) -> None:
    """Persist the choice as at most one flag file: none when it equals the default. Raises OSError when the state directory cannot be written."""
    sw = get(name)
    os.makedirs(sdir, mode=0o700, exist_ok=True)
    for fname in (sw.off_file(), sw.on_file()):
        try:
            os.unlink(os.path.join(sdir, fname))
        except FileNotFoundError:
            pass
    if on != sw.default:
        open(os.path.join(sdir, sw.on_file() if on else sw.off_file()), "a").close()


def reset(sdir: str, names) -> list[str]:
    """Back to the default for each of `names` (the flag files go; an environment variable is not ours to touch). Returns the ids whose file was removed."""
    changed = []
    for name in names:
        sw = get(name)
        for fname in (sw.off_file(), sw.on_file()):
            try:
                os.unlink(os.path.join(sdir, fname))
                changed.append(name)
            except FileNotFoundError:
                pass
    return changed


def by_group() -> list[tuple[str, list[Switch]]]:
    return [(g, [s for s in CATALOG if s.group == g]) for g in GROUPS]
