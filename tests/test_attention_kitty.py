import os
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


@unittest.skipUnless(shutil.which("kitty"), "kitty not installed")
class AttentionInRealKittyTests(unittest.TestCase):
    """The geninclude runs inside kitty's own interpreter at config load: with a compositor that would focus a window that asks for attention,
    kitty's bell→attention request (window_alert_on_bell) must come out switched off; otherwise left alone."""

    def load(self, focus_on_activate, signature=True, attention_on=False):
        d = tempfile.mkdtemp()
        bindir = os.path.join(d, "bin")
        os.makedirs(bindir)
        fake = os.path.join(bindir, "hyprctl")
        with open(fake, "w") as f:
            f.write('#!/bin/sh\nprintf \'{"option":"misc:focus_on_activate","int":%s}\' %s\n' % (1 if focus_on_activate else 0, "''"))
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
        state = os.path.join(d, "state")
        os.makedirs(state)
        if attention_on:
            open(os.path.join(state, "attention-on"), "w").close()
        conf = os.path.join(d, "kitty.conf")
        with open(conf, "w") as f:
            f.write("window_alert_on_bell yes\ngeninclude %s/python/kittymux_layout.py\n" % os.path.realpath(ROOT))
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"], KITTYMUX_STATE=state)
        env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        if signature:
            env["HYPRLAND_INSTANCE_SIGNATURE"] = "test"
        out = subprocess.run(["kitty", "+runpy", "from kitty.config import load_config\nbad=[]\no=load_config('%s', accumulate_bad_lines=bad)\n"
                              "print('BAD', len(bad), 'ALERT', o.window_alert_on_bell)" % conf], capture_output=True, text=True, env=env, timeout=30)
        shutil.rmtree(d, ignore_errors=True)
        return out.stdout.strip().splitlines()[-1]

    def test_switched_off_when_the_compositor_focuses_on_activate(self):
        self.assertEqual(self.load(True), "BAD 0 ALERT False")

    def test_left_alone_when_it_does_not_or_when_it_is_not_hyprland(self):
        self.assertEqual(self.load(False), "BAD 0 ALERT True")
        self.assertEqual(self.load(True, signature=False), "BAD 0 ALERT True")

    def test_the_user_can_insist(self):
        self.assertEqual(self.load(True, attention_on=True), "BAD 0 ALERT True")


if __name__ == "__main__":
    unittest.main()
