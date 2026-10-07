"""Refresh every kittymux module a running kitty has imported, dependencies first.

kitty re-runs tab_bar.py on every config load, but Python keeps each module it ever imported for the life of the process. After an upgrade a long-running
kitty would therefore keep serving the OLD helper to the NEW code — including helpers that are only imported lazily, on first use (the inbox, the prompts, the
socket link…): a list of "the modules to reload" kept by hand in tab_bar.py missed them, and went stale every time a module was added. This reloads whatever is
actually loaded, in dependency order, and never lets one broken module stop the rest.
"""
import importlib
import re
import sys

_IMPORT = re.compile(r"^\s*(?:import|from)\s+(kittymux_[a-z0-9_]+)", re.M)


def imports_of(source: str, loaded) -> set:
    """The loaded kittymux modules a source file imports (at any indentation: most are imported inside functions)."""
    return {name for name in _IMPORT.findall(source or "") if name in loaded}


def order(deps: dict) -> list:
    """Every module once, each after the modules it imports. Deterministic; a cycle is broken, never followed."""
    done, out = set(), []

    def visit(name, stack):
        if name in done or name in stack:
            return
        for dep in sorted(deps.get(name, ())):
            if dep in deps:
                visit(dep, stack + (name,))
        done.add(name)
        out.append(name)

    for name in sorted(deps):
        visit(name, ())
    return out


def reload_all(modules=None, only_prefix: str = "kittymux_") -> dict:
    """Reload every loaded module whose name starts with `only_prefix` (and that has a source file), dependencies first.
    Returns {"reloaded": [names], "failed": {name: error text}}."""
    modules = sys.modules if modules is None else modules
    loaded = {name: mod for name, mod in list(modules.items()) if name.startswith(only_prefix) and getattr(mod, "__file__", None)}
    deps = {}
    for name, mod in loaded.items():
        try:
            with open(mod.__file__, encoding="utf-8") as f:
                deps[name] = imports_of(f.read(), loaded) - {name}
        except OSError:
            deps[name] = set()
    report = {"reloaded": [], "failed": {}}
    for name in order(deps):
        try:
            importlib.reload(loaded[name])
            report["reloaded"].append(name)
        except Exception as e:                        # a module that fails to reload keeps its old self; the rest still refresh
            report["failed"][name] = f"{type(e).__name__}: {e}"
    return report
