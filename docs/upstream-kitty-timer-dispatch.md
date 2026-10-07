# Draft: a timer callback that removes another due timer makes kitty call a freed Python object

Status: **a draft for the kitty issue tracker, not filed.** It records the evidence from a real crash (kitty 0.49.2, Python 3.14.7, Wayland) and a 30-line reproduction, so the report can be made without guessing. kittymux works around it (`python/kittymux_timers.py`); this is about the flaw underneath.

## Title

`glfw/backend_utils.c` `dispatchTimers`: removing a timer from another timer's callback can call a freed callback (SIGSEGV in `python_timer_callback`)

## What happened

kitty died with SIGSEGV (`segfault at 8`, null/dead object) with this stack:

```
#0  libpython3.14.so  (a field read off a dead object)
#1  libpython3.14.so
#2  PyObject_CallFunction
#3  fast_data_types.so  python_timer_callback
#4  glfw-wayland.so  (dispatchTimers, via glfwRunMainLoop)
#5  glfwRunMainLoop
```

Nothing else was wrong: no OOM, one coredump in a week.

## Why

`dispatchTimers` (glfw/backend_utils.c, 0.49.2) first copies `(func, id, data, repeats)` of every due timer into a static `dispatches[]` table, and then calls them one by one ("we dispatch separately so that the callbacks can modify timers"). The copy holds the raw `data` pointer, which for a Python timer is the callable `add_timer` was given, with one reference owned by the timer entry.

If callback A calls `remove_timer(B)` where B is in the same batch, `removeTimer` frees B's entry and releases B's callable. When that was the last reference (for example a function of a module that has since been reloaded), the object is freed, and the loop then calls `dispatches[i].func(id, data)` for B with a dangling `data`.

## Reproduction (kitty 0.49.2, X11 or Wayland)

A kitten whose `handle_result` runs in kitty:

```python
from kittens.tui.handler import result_handler

def main(args):
    pass

@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    from kitty.fast_data_types import add_timer, remove_timer
    ids = {}

    def a(tid):
        remove_timer(ids["b"])                  # B is due in the same batch

    def make_b():
        def b(tid):
            pass
        return b

    ids["a"] = add_timer(a, 0.3, False)
    ids["b"] = add_timer(make_b(), 0.3, False)  # the only reference to b is kitty's timer entry
```

`kitty @ kitten probe.py` kills kitty about 0.3 s later, with the same stack as above (frames #1 to #6 are identical to the real crash). `tests/smoke_timers.sh` in kittymux does exactly this in a private kitty, as its control.

## Suggested fix

Either of:

- hold a reference for the duration of the batch: `Py_INCREF` the callable when it is copied into `dispatches[]` and release it after the call (a `dispatches[i].free` hook next to `func`), or
- skip a dispatch whose timer id is no longer in `eld->timers` (look it up again just before calling).

## What kittymux does meanwhile

Every timer it creates gets a callable that is never freed and that looks up the real function by name when it fires (`python/kittymux_timers.py`), and a callback ignores a tick whose id is no longer the live one. `kittymux_timers.add` is the only way the code base adds a timer (a unit test enforces it).
