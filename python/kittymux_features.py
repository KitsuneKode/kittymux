# kittymux features — which optional pieces are switched on.
#
# Pure Python, no kitty imports. Precedence: environment variable > flag file in the
# state directory > default. A default-ON feature is turned off by the file `<name>-off`,
# a default-OFF one is turned on by `<name>-on` (the same convention as `notify-off`).
# If both files exist the `-off` one wins.

import os

import kittymux_switches as SW

# The twelve switches `kittymux features` has always listed, in their old order: presets and the CLI list are about these. The full catalog (notifications, safety
# and recovery, opt-in) lives in kittymux_switches and is reachable through the same functions below.
FEATURES = ("folder", "hue", "collide", "sheet", "hover", "panetitle", "motion", "titles", "sudo", "loginprompt", "pkgprompt", "socketlink")
DEFAULTS = {name: SW.get(name).default for name in FEATURES}      # panetitle only shows when pane title bars are on; motion off = a still glyph where a spinner turned
PRESETS = {
    "minimal": frozenset({"folder", "motion", "titles", "sudo", "loginprompt", "pkgprompt", "socketlink"}),
    "default": frozenset(name for name, on in DEFAULTS.items() if on),
    "full": frozenset(FEATURES),
}
PLANNED = frozenset(s.id for s in SW.CATALOG if s.status == SW.PLANNED)     # settings that are saved but nothing reads yet: the CLI says so


def state_dir(env=None) -> str:
    return SW.state_dir(env)


def live() -> frozenset:
    """The switches something actually reads today."""
    return frozenset(FEATURES) - PLANNED


def source(name: str, sdir: str | None = None, env=None) -> tuple[bool, str]:
    """(on, where) — where is 'env', 'flag' or 'default'. Any switch in the catalog, not only the twelve."""
    return SW.source(name, sdir, env)


def enabled(name: str, sdir: str | None = None, env=None) -> bool:
    return SW.enabled(name, sdir, env)


def resolve_all(sdir: str | None = None, env=None) -> dict[str, bool]:
    return {name: enabled(name, sdir, env) for name in FEATURES}


def set_feature(sdir: str, name: str, on: bool) -> None:
    """Persist the choice as at most one flag file — none when it equals the default."""
    SW.set_switch(sdir, name, on)


def apply_preset(sdir: str, preset: str) -> None:
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r} (known: {', '.join(PRESETS)})")
    for name in FEATURES:
        set_feature(sdir, name, name in PRESETS[preset])
