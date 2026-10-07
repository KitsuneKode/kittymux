"""Timers for code that runs inside kitty — safe against kitty's own timer dispatch.

kitty keeps a BARE pointer to the Python callable of every timer, and its dispatcher (glfw/backend_utils.c `dispatchTimers`) first copies (function, data)
of every timer that is due into a table, then runs them one by one "so that the callbacks can modify timers". A callback that removes another timer which
is due in the same batch (a config reload does: `restart()` → `stop()` removes the scan and spin timers) makes kitty drop its reference to that timer's
callable; when nothing else holds the function (a module that was re-executed replaced it), it is FREED, and the table still holds the pointer: kitty calls
a dead object from `python_timer_callback` and the whole process dies (libpython SIGSEGV, address 8, 2026-10-07 22:57).

So a timer is never given a function of a module that can be re-executed. It gets a *stable* callable: ONE object per (module, function) for the life of the
process, kept alive here, that looks the real function up by name each time it fires (so it still runs the reloaded code). Removing such a timer can never
free what kitty is about to call. A stale tick (its timer was removed in the same batch) is the callback's to ignore: compare the id you were given.
"""
import sys
import types

# the registry lives in sys.modules: re-executing this file must not forget it (and must hand back the SAME callables)
_REG = sys.modules.setdefault("_kittymux_timers_rt", types.SimpleNamespace(stable={}))


def stable(module_name: str, func_name: str):
    """The one callable for `module_name.func_name`: same object every call, in every version of this file."""
    key = (module_name, func_name)
    cb = _REG.stable.get(key)
    if cb is None:
        def cb(timer_id, _module=module_name, _func=func_name):
            try:
                fn = getattr(sys.modules.get(_module), _func, None)
                if callable(fn):
                    fn(timer_id)
            except Exception:                      # a timer callback must never raise into kitty's event loop
                try:
                    import traceback
                    sys.stderr.write(f"kittymux timer {_module}.{_func}: {traceback.format_exc()}")
                except Exception:
                    pass
        _REG.stable[key] = cb
    return cb


def add(module_name: str, func_name: str, interval: float, repeats: bool = True):
    """kitty's add_timer with a stable callable; the timer id, or None when kitty is not there (tests, a plain python)."""
    try:
        from kitty.fast_data_types import add_timer
        return add_timer(stable(module_name, func_name), interval, repeats)
    except Exception:
        return None
