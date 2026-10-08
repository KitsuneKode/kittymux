"""A module-level dict, list or set that something keeps adding to is a leak waiting for a long enough session. This lists every one that exists and why it is
safe. A new one fails this test: bound it (python/kittymux_bounded.py) or add a line here saying what bounds it."""
import ast
import glob
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")

SAFE = {
    ("kittymux_agents.py", "TOOLS"): "filled once at import from a constant table",
    ("kittymux_barsize.py", "_DEFAULTS"): "a fixed set of named fields; copied into sys.modules['_kittymux_barsize_rt'], never grown",
    ("kittymux_git.py", "_cache"): "capped at _CACHE_MAX, oldest dropped",
    ("kittymux_keymap.py", "_MOD_NAME"): "a copy of a constant table",
    ("pane-state.py", "_state"): "one entry per live window; popped in on_close",
    ("tab_bar.py", "_MEMO"): "emptied at the start of every pass (_per_pass)",
    ("tab_bar.py", "_TITLE_KEY_CACHE"): "rebuilt each pass from the tabs that exist",
    ("tab_bar.py", "_dump_rows"): "test hook (KITTYMUX_BAR_DUMP), one row per tab id, off by default",
    ("tab_bar.py", "_AWI_CACHE"): "pruned past 64 entries by age",
    ("tab_bar.py", "_RISK"): "one key, 'table'",
    ("tab_bar.py", "_MASCOT_OK"): "one key, 'ok'",
    ("tab_bar.py", "_ERR_SEEN"): "capped by kittymux_bounded.seen_within",
}
CONTAINERS = {"dict", "list", "set", "deque", "OrderedDict", "defaultdict"}


def empty_containers():
    found = []
    for path in sorted(glob.glob(os.path.join(ROOT, "python", "*.py")) + glob.glob(os.path.join(ROOT, "python", "collectors", "*.py"))):
        src = open(path, encoding="utf-8").read()
        for node in ast.parse(src).body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
                continue
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            name = getattr(target, "id", None)
            v = node.value
            empty_literal = isinstance(v, (ast.Dict, ast.List, ast.Set)) and not (getattr(v, "keys", None) or getattr(v, "elts", None))
            constructor = isinstance(v, ast.Call) and getattr(v.func, "id", getattr(v.func, "attr", None)) in CONTAINERS
            if name and (empty_literal or constructor):
                found.append((os.path.basename(path), name))
    return found


class BoundedStateTests(unittest.TestCase):
    def test_every_module_level_container_has_a_reason(self):
        unlisted = [c for c in empty_containers() if c not in SAFE]
        self.assertEqual(unlisted, [], "a new module-level container: bound it with kittymux_bounded, then add (file, name): reason to SAFE in tests/test_bounded_state.py")

    def test_the_list_has_no_entries_for_things_that_are_gone(self):
        present = set(empty_containers())
        gone = [k for k in SAFE if k not in present]
        self.assertEqual(gone, [], "remove these from SAFE, they no longer exist")


if __name__ == "__main__":
    unittest.main()
