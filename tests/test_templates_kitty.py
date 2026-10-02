import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


@unittest.skipUnless(shutil.which("kitty"), "kitty not installed")
class TemplatesParseInKittyTests(unittest.TestCase):
    """kitty's own session parser must accept every shipped template once rendered (it is the only judge of what a session file means)."""

    def test_every_template_parses(self):
        sys_path = os.path.join(ROOT, "python")
        d = tempfile.mkdtemp()
        script = (
            "import sys, os\n"
            "sys.path.insert(0, %r)\n"
            "import kittymux_resume as R\n"
            "from kitty.session import parse_session\n"
            "from kitty.config import load_config\n"
            "opts = load_config()\n"
            "for name in sorted(os.listdir(%r)):\n"
            "    if not name.endswith('.kitty-session'): continue\n"
            "    text = R.render_template(open(os.path.join(%r, name)).read(), {'NAME': 'demo', 'CWD': %r, 'AGENT': 'claude', 'AGENT2': 'codex', 'SHELL': '/bin/sh'})\n"
            "    s = list(parse_session(text, opts))\n"
            "    tabs = sum(len(o.tabs) for o in s)\n"
            "    assert tabs >= 1, name\n"
            "    print('OK', name, tabs)\n" % (sys_path, os.path.join(ROOT, "assets", "templates"), os.path.join(ROOT, "assets", "templates"), d))
        env = dict(os.environ, KITTY_CONFIG_DIRECTORY=d)
        out = subprocess.run(["kitty", "+runpy", script], capture_output=True, text=True, env=env, timeout=60)
        shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(out.returncode, 0, out.stderr[-600:])
        names = re.findall(r"^OK (\S+)", out.stdout, re.M)
        for want in ("plain.kitty-session", "agent.kitty-session", "duo.kitty-session", "review.kitty-session"):
            self.assertIn(want, names)


if __name__ == "__main__":
    unittest.main()
