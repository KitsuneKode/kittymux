import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_prompts as P  # noqa: E402

ALL = frozenset(P.FEATURES)


def hit(text, argv=("zsh",), enabled=ALL):
    r = P.classify(list(argv), text, enabled)
    return r.id if r else ""


class PasswordTests(unittest.TestCase):
    def test_a_sudo_prompt_is_recognised_whatever_runs_in_front(self):
        # sudo's own wording is distinctive enough to need no process check: `bash update.sh` and `paru` both lead the pty group
        for argv in (("sudo", "pacman", "-Syu"), ("paru", "-Syu"), ("bash", "./update.sh"), ("zsh",)):
            self.assertEqual(hit("resolving dependencies...\n[sudo] password for kit: ", argv), "sudo")

    def test_the_other_privilege_tools(self):
        self.assertEqual(hit("doas (kit@box) password: ", ("doas", "ls")), "sudo")
        self.assertEqual(hit("Password: ", ("su", "-")), "sudo")
        self.assertEqual(hit("Password: ", ("/usr/bin/pkexec", "x")), "sudo")
        self.assertEqual(hit("[sudo] password: ", ("sudo", "-v")), "sudo")

    def test_a_bare_password_line_needs_a_privilege_tool_in_front(self):
        self.assertEqual(hit("Password: ", ("zsh",)), "")
        self.assertEqual(hit("Password: ", ("python3", "app.py")), "")

    def test_it_must_be_the_last_line_not_scrollback(self):
        self.assertEqual(hit("[sudo] password for kit: \nsorry, try again.\n$ ", ("zsh",)), "")
        self.assertEqual(hit("[sudo] password for kit:\n\n\n"), "sudo")      # trailing blank rows do not hide it

    def test_prose_and_code_that_mention_it_are_not_prompts(self):
        for line in ("The [sudo] password for kit: is requested by sudo itself",
                     "echo '[sudo] password for kit:' | tee log",
                     "# then you will see [sudo] password for kit: and type it"):
            self.assertEqual(hit(line, ("sudo",)), "", line)

    def test_the_switch_turns_it_off(self):
        self.assertEqual(hit("[sudo] password for kit: ", enabled=ALL - {"sudo"}), "")


class LoginTests(unittest.TestCase):
    def test_ssh_and_git_logins(self):
        self.assertEqual(hit("Enter passphrase for key '/home/kit/.ssh/id_ed25519': ", ("ssh", "box")), "login")
        self.assertEqual(hit("kit@box's password: ", ("ssh", "kit@box")), "login")
        self.assertEqual(hit("Are you sure you want to continue connecting (yes/no/[fingerprint])? ", ("ssh", "box")), "login")
        self.assertEqual(hit("Password for 'https://kit@example.org': ", ("git", "push")), "login")

    def test_they_need_the_tool_in_front(self):
        self.assertEqual(hit("kit@box's password: ", ("zsh",)), "")

    def test_the_switch_turns_it_off(self):
        self.assertEqual(hit("kit@box's password: ", ("ssh", "x"), ALL - {"loginprompt"}), "")


class PackageTests(unittest.TestCase):
    def test_pacman_family_confirmations(self):
        self.assertEqual(hit(":: Proceed with installation? [Y/n] ", ("pacman", "-Syu")), "pkg")
        self.assertEqual(hit(":: Proceed with installation? [Y/n] ", ("paru", "-Syu")), "pkg")
        self.assertEqual(hit("==> Proceed with install? [Y/n] ", ("yay",)), "pkg")
        self.assertEqual(hit("Do you want to continue? [Y/n] ", ("apt", "upgrade")), "pkg")
        self.assertEqual(hit(":: Import PGP key ABCDEF, \"Someone\", created: 2024-01-01? [Y/n] ", ("makepkg",)), "pkg")

    def test_a_question_in_some_other_program_is_not_ours(self):
        self.assertEqual(hit("Delete everything? [y/N] ", ("rm-wrapper",)), "")
        self.assertEqual(hit("Proceed? [Y/n] ", ("zsh",)), "")

    def test_the_switch_turns_it_off(self):
        self.assertEqual(hit(":: Proceed with installation? [Y/n] ", ("pacman",), ALL - {"pkgprompt"}), "")


class ShapeTests(unittest.TestCase):
    def test_the_answer_is_fixed_text_never_screen_text(self):
        r = P.classify(["sudo"], "[sudo] password for someone-private: ", ALL)
        self.assertNotIn("someone-private", repr(r))
        self.assertTrue(r.say and r.kind in ("permission", "question"))

    def test_hostile_and_empty_input_never_raise(self):
        for text in ("", None, "\x00" * 5000, "x" * 100000, "\n\n\n", "\x1b[31m[sudo] password for kit:\x1b[0m"):
            P.classify(["sudo"], text, ALL)
        self.assertEqual(P.classify([], "[sudo] password for kit: ", ALL).id, "sudo")
        self.assertIsNone(P.classify(None, "", ALL))

    def test_colour_codes_around_a_prompt_do_not_hide_it(self):
        self.assertEqual(hit("\x1b[1m[sudo] password for kit:\x1b[0m "), "sudo")

    def test_every_rule_names_a_known_switch(self):
        for r in P.RULES:
            self.assertIn(r.feature, P.FEATURES)

    def test_features_and_defaults_are_in_the_switchboard(self):
        import kittymux_features as F
        for name in P.FEATURES:
            self.assertIn(name, F.FEATURES)
            self.assertTrue(F.DEFAULTS[name])
            self.assertIn(name, F.live())


if __name__ == "__main__":
    unittest.main()
