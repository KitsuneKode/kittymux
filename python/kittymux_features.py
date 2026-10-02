# kittymux features — which optional pieces are switched on.
#
# Pure Python, no kitty imports. Precedence: environment variable > flag file in the
# state directory > default. A default-ON feature is turned off by the file `<name>-off`,
# a default-OFF one is turned on by `<name>-on` (the same convention as `notify-off`).
# If both files exist the `-off` one wins.

import os

FEATURES = ("folder", "hue", "collide", "sheet", "hover", "panetitle")
DEFAULTS = {"folder": True, "hue": True, "collide": True, "sheet": True, "hover": False, "panetitle": False}
PRESETS = {
    "minimal": frozenset({"folder"}),
    "default": frozenset(name for name, on in DEFAULTS.items() if on),
    "full": frozenset(FEATURES),
}
_OFF = {"0", "off", "false", "no"}
_ON = {"1", "on", "true", "yes"}


def state_dir(env=None) -> str:
    env = os.environ if env is None else env
    return env.get("KITTYMUX_STATE") or os.path.join(
        env.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "kittymux")


def _check(name: str) -> None:
    if name not in DEFAULTS:
        raise ValueError(f"unknown feature {name!r} (known: {', '.join(FEATURES)})")


def _flag(sdir: str, name: str, on: bool) -> str:
    return os.path.join(sdir, f"{name}-{'on' if on else 'off'}")


def source(name: str, sdir: str | None = None, env=None) -> tuple[bool, str]:
    """(on, where) — where is 'env', 'flag' or 'default'."""
    _check(name)
    env = os.environ if env is None else env
    raw = env.get(f"KITTYMUX_{name.upper()}", "").strip().lower()
    if raw in _OFF:
        return False, "env"
    if raw in _ON:
        return True, "env"
    sdir = sdir or state_dir(env)
    if os.path.exists(_flag(sdir, name, False)):
        return False, "flag"
    if os.path.exists(_flag(sdir, name, True)):
        return True, "flag"
    return DEFAULTS[name], "default"


def enabled(name: str, sdir: str | None = None, env=None) -> bool:
    return source(name, sdir, env)[0]


def resolve_all(sdir: str | None = None, env=None) -> dict[str, bool]:
    return {name: enabled(name, sdir, env) for name in FEATURES}


def set_feature(sdir: str, name: str, on: bool) -> None:
    """Persist the choice as at most one flag file — none when it equals the default."""
    _check(name)
    os.makedirs(sdir, mode=0o700, exist_ok=True)
    for state in (True, False):
        try:
            os.unlink(_flag(sdir, name, state))
        except FileNotFoundError:
            pass
    if on != DEFAULTS[name]:
        open(_flag(sdir, name, on), "a").close()


def apply_preset(sdir: str, preset: str) -> None:
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r} (known: {', '.join(PRESETS)})")
    for name in FEATURES:
        set_feature(sdir, name, name in PRESETS[preset])
