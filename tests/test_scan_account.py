"""The scanner reads which account an agent runs under from the agent process's own environment (/proc/<pid>/environ)."""
import os
import subprocess
import sys
import time
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import kittymux_scan as S  # noqa: E402


class AccountFromProcessTests(unittest.TestCase):
    def run_with(self, env_extra):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CONFIG_DIR", "CODEX_HOME")}
        env.update(env_extra)
        p = subprocess.Popen(["sleep", "30"], env=env)
        self.addCleanup(lambda: (p.kill(), p.wait()))
        want = [k.encode() + b"=" for k in env_extra]
        for _ in range(40):                       # the child's environment as /proc shows it (a CI runner can hide it)
            try:
                with open(f"/proc/{p.pid}/environ", "rb") as f:
                    items = f.read().split(b"\0")
            except OSError:
                items = []
            if all(any(i.startswith(w) for i in items) for w in want):
                break
            time.sleep(0.05)
        else:
            self.skipTest("this machine's /proc does not show a child's environment")
        return types.SimpleNamespace(foreground_processes=[{"pid": p.pid, "cmdline": ["sleep", "30"]}])

    def test_a_pane_started_with_another_config_dir_names_its_account(self):
        child = self.run_with({"CLAUDE_CONFIG_DIR": "/srv/agents/.claude_alt"})
        self.assertEqual(S._account(child, "claude"), "alt")

    def test_the_default_or_no_variable_is_no_account(self):
        self.assertEqual(S._account(self.run_with({}), "claude"), "")
        child = self.run_with({"CLAUDE_CONFIG_DIR": os.path.expanduser("~/.claude")})
        self.assertEqual(S._account(child, "claude"), "")

    def test_another_agents_variable_or_a_gone_process_is_no_account(self):
        self.assertEqual(S._account(self.run_with({"CLAUDE_CONFIG_DIR": "/srv/.claude_alt"}), "codex"), "")
        gone = types.SimpleNamespace(foreground_processes=[{"pid": 2 ** 22 + 7}])
        self.assertEqual(S._account(gone, "claude"), "")
        self.assertEqual(S._account(None, "claude"), "")


if __name__ == "__main__":
    unittest.main()
