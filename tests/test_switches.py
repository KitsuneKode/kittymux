"""The catalog of switches (python/kittymux_switches.py).

The big test here is the equivalence table: before the catalog, every scanner/CLI call site tested its own environment variable and flag file inline. Those inline
expressions are kept below as `OLD`, as the SPECIFICATION, and the catalog must give the same answer for every combination of environment value and flag file.
Behaviour for anyone who already has a flag file or a variable set is identical by construction; the few deliberate differences are tested by name afterwards."""
import itertools
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_features as F  # noqa: E402
import kittymux_switches as S  # noqa: E402


def exists(sdir, name):
    return os.path.exists(os.path.join(sdir, name))


# the inline expressions, as they were (kittymux_scan, kittymux_layout, bin/kittymux), keyed by the catalog id
OLD = {
    "notify": lambda e, d: not (e.get("KITTYMUX_NOTIFY") == "0" or exists(d, "notify-off")),
    "notify-done": lambda e, d: e.get("KITTYMUX_NOTIFY_DONE") != "0" and not exists(d, "notify-done-off"),
    "bell": lambda e, d: not (e.get("KITTYMUX_BELL") == "0" or exists(d, "bell-off")),
    "autosave": lambda e, d: e.get("KITTYMUX_AUTOSAVE") != "0" and not exists(d, "autosave-off"),
    "changes": lambda e, d: e.get("KITTYMUX_CHANGES") != "0" and not exists(d, "changes-off"),
    "journal": lambda e, d: e.get("KITTYMUX_JOURNAL") != "0" and not exists(d, "journal-off"),
    "attention": lambda e, d: e.get("KITTYMUX_ATTENTION") == "1" or exists(d, "attention-on"),
    "resume-auto": lambda e, d: e.get("KITTYMUX_RESUME", "").lower() == "auto" or exists(d, "resume-auto"),
    "notify-private": lambda e, d: e.get("KITTYMUX_NOTIFY_PRIVATE") == "1" or exists(d, "notify-private"),
}
OLD_FILES = {"notify": ("notify-off",), "notify-done": ("notify-done-off",), "bell": ("bell-off",), "autosave": ("autosave-off",), "changes": ("changes-off",),
             "journal": ("journal-off",), "attention": ("attention-on",), "resume-auto": ("resume-auto",), "notify-private": ("notify-private",)}
VALUES = [None, "", "0", "1", "auto", "AUTO", "yes", "off", "false", "banana"]
ENV_VAR = {"notify": "KITTYMUX_NOTIFY", "notify-done": "KITTYMUX_NOTIFY_DONE", "bell": "KITTYMUX_BELL", "autosave": "KITTYMUX_AUTOSAVE", "changes": "KITTYMUX_CHANGES",
           "journal": "KITTYMUX_JOURNAL", "attention": "KITTYMUX_ATTENTION", "resume-auto": "KITTYMUX_RESUME", "notify-private": "KITTYMUX_NOTIFY_PRIVATE"}


class EquivalenceTests(unittest.TestCase):
    def test_every_legacy_switch_answers_as_its_inline_expression_did(self):
        checked = 0
        for name, old in OLD.items():
            files = OLD_FILES[name]
            for value in VALUES:
                for present in itertools.product((False, True), repeat=len(files)):
                    with tempfile.TemporaryDirectory() as d:
                        for f, here in zip(files, present):
                            if here:
                                open(os.path.join(d, f), "w").close()
                        env = {} if value is None else {ENV_VAR[name]: value}
                        self.assertEqual(S.enabled(name, d, env), old(env, d), f"{name} env={value!r} files={dict(zip(files, present))}")
                        checked += 1
        self.assertGreater(checked, 100)

    def test_the_old_twelve_features_answer_as_before(self):
        def old(name, d, env):                                  # the previous kittymux_features.source
            raw = env.get(f"KITTYMUX_{name.upper()}", "").strip().lower()
            if raw in {"0", "off", "false", "no"}:
                return False
            if raw in {"1", "on", "true", "yes"}:
                return True
            if exists(d, f"{name}-off"):
                return False
            if exists(d, f"{name}-on"):
                return True
            return {"folder": True, "hue": True, "collide": True, "sheet": True, "hover": False, "panetitle": True, "motion": True, "titles": True,
                    "sudo": True, "loginprompt": True, "pkgprompt": True, "socketlink": True}[name]
        for name in F.FEATURES:
            for value in VALUES + [" on ", "ON"]:
                for off, on in itertools.product((False, True), repeat=2):
                    with tempfile.TemporaryDirectory() as d:
                        for flag, here in ((f"{name}-off", off), (f"{name}-on", on)):
                            if here:
                                open(os.path.join(d, flag), "w").close()
                        env = {} if value is None else {f"KITTYMUX_{name.upper()}": value}
                        self.assertEqual(S.enabled(name, d, env), old(name, d, env), f"{name} env={value!r} off={off} on={on}")

    def test_defaults_are_the_old_defaults(self):
        old_defaults = {"notify": True, "notify-done": True, "bell": True, "autosave": True, "changes": True, "journal": True, "attention": False, "resume-auto": False,
                        "notify-private": False, "usage-live": False}
        for name, default in old_defaults.items():
            self.assertEqual(S.get(name).default, default, name)


class DeliberateDifferenceTests(unittest.TestCase):
    """Where the catalog is not byte-for-byte the old expression, and why."""

    def test_usage_live_is_on_only_for_an_explicit_yes(self):
        # Before: any value except '', '0' and 'no' enabled it, so KITTYMUX_USAGE_LIVE=off or =false turned a NETWORK feature ON. A switch that talks to providers with
        # your login must not be switched on by the word "off".
        for value, expect in (("1", True), ("on", True), ("true", True), ("yes", True), ("YES", True), ("0", False), ("no", False), ("off", False), ("false", False), ("", False), ("banana", False)):
            with tempfile.TemporaryDirectory() as d:
                self.assertEqual(S.enabled("usage-live", d, {"KITTYMUX_USAGE_LIVE": value}), expect, value)

    def test_the_old_alternative_spelling_of_usage_live_is_honoured_by_the_collector_not_here(self):
        self.assertEqual(S.get("usage-live").env, ("KITTYMUX_USAGE_LIVE",))

    def test_surrounding_whitespace_in_a_variable_no_longer_hides_it(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(S.enabled("notify", d, {"KITTYMUX_NOTIFY": " 0 "}))

    def test_the_new_flag_file_for_usage_live(self):
        with tempfile.TemporaryDirectory() as d:
            S.set_switch(d, "usage-live", True)
            self.assertEqual(os.listdir(d), ["usage-live-on"])
            self.assertTrue(S.enabled("usage-live", d, {}))


class CatalogTests(unittest.TestCase):
    def test_ids_are_unique_and_every_group_is_known(self):
        self.assertEqual(len(set(S.IDS)), len(S.IDS))
        for sw in S.CATALOG:
            self.assertIn(sw.group, S.GROUPS)

    def test_every_help_is_one_short_plain_sentence(self):
        for sw in S.CATALOG:
            self.assertLessEqual(len(sw.help), 90, f"{sw.id}: {len(sw.help)} characters")
            self.assertTrue(sw.help.endswith("."), sw.id)
            self.assertNotRegex(sw.help.lower(), r"\bplease\b", sw.id)
            self.assertLessEqual(len(sw.label), 30, sw.id)
            self.assertNotIn("\n", sw.help + sw.label)

    def test_every_risky_switch_says_what_it_does_and_no_other_does(self):
        for sw in S.CATALOG:
            self.assertEqual(bool(sw.consequence), sw.risk != S.NONE, sw.id)
            if sw.consequence:
                self.assertLessEqual(len(sw.consequence), 160, sw.id)
        self.assertEqual({s.id for s in S.CATALOG if s.risk != S.NONE}, {"attention", "resume-auto", "usage-live"})

    def test_a_risky_switch_is_off_by_default(self):
        for sw in S.CATALOG:
            if sw.risk != S.NONE:
                self.assertFalse(sw.default, sw.id)

    def test_every_old_feature_and_every_inline_switch_is_in_the_catalog(self):
        for name in list(F.FEATURES) + list(OLD):
            self.assertIn(name, S.BY_ID)
        self.assertIn("usage-live", S.BY_ID)

    def test_planned_switches_are_the_two_the_cli_always_called_planned(self):
        self.assertEqual({s.id for s in S.CATALOG if s.status == S.PLANNED}, {"sheet", "hover"})
        self.assertEqual(F.PLANNED, frozenset({"sheet", "hover"}))

    def test_flag_file_names_do_not_collide(self):
        seen = {}
        for sw in S.CATALOG:
            for fname in (sw.off_file(), sw.on_file()):
                self.assertNotIn(fname, seen, f"{fname} used by {seen.get(fname)} and {sw.id}")
                seen[fname] = sw.id

    def test_no_environment_variable_is_shared(self):
        seen = {}
        for sw in S.CATALOG:
            for var in sw.env_names():
                self.assertNotIn(var, seen, f"{var} used by {seen.get(var)} and {sw.id}")
                seen[var] = sw.id

    def test_unknown_names_are_refused_with_the_known_ones(self):
        with self.assertRaisesRegex(ValueError, "unknown setting 'nope'.*folder"):
            S.get("nope")


class SetTests(unittest.TestCase):
    def test_set_leaves_at_most_one_file_and_none_at_the_default(self):
        with tempfile.TemporaryDirectory() as d:
            for name in S.IDS:
                sw = S.get(name)
                S.set_switch(d, name, not sw.default)
                self.assertEqual(len(os.listdir(d)), 1, name)
                self.assertEqual(S.enabled(name, d, {}), not sw.default, name)
                S.set_switch(d, name, sw.default)
                self.assertEqual(os.listdir(d), [], name)

    def test_set_uses_the_old_file_names(self):
        with tempfile.TemporaryDirectory() as d:
            S.set_switch(d, "notify", False)
            S.set_switch(d, "attention", True)
            S.set_switch(d, "resume-auto", True)
            self.assertEqual(sorted(os.listdir(d)), ["attention-on", "notify-off", "resume-auto"])

    def test_set_removes_the_opposite_file(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "hue-on"), "w").close()
            S.set_switch(d, "hue", False)
            self.assertEqual(os.listdir(d), ["hue-off"])

    def test_a_directory_in_the_way_is_an_oserror_and_changes_nothing_else(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "hue-off"))
            with self.assertRaises(OSError):
                S.set_switch(d, "hue", False)

    def test_reset_removes_flag_files_but_not_the_environment(self):
        with tempfile.TemporaryDirectory() as d:
            S.set_switch(d, "hue", False)
            S.set_switch(d, "attention", True)
            self.assertEqual(sorted(S.reset(d, ["hue", "attention", "bell"])), ["attention", "hue"])
            self.assertEqual(os.listdir(d), [])

    def test_the_environment_wins_and_says_which_variable(self):
        with tempfile.TemporaryDirectory() as d:
            S.set_switch(d, "bell", False)
            self.assertEqual(S.resolve("bell", d, {"KITTYMUX_BELL": "0"}), (False, "env", "KITTYMUX_BELL"))
            self.assertEqual(S.resolve("bell", d, {}), (False, "flag", "bell-off"))
            self.assertEqual(S.resolve("folder", d, {}), (True, "default", ""))


if __name__ == "__main__":
    unittest.main()
