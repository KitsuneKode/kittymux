"""bin/mux-ask accepts only an answer naming the request it is waiting on."""
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MuxAskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.asks = t / "state/kittymux/asks"
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(t), "XDG_STATE_HOME": str(t / "state"),
                    "KITTY_WINDOW_ID": "7", "KITTY_PID": "4242", "MUX_ASK_WAIT": "4"}

    def tearDown(self):
        self.tmp.cleanup()

    def ask(self, answer_with):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls -la"}})
        p = subprocess.Popen([str(ROOT / "bin/mux-ask"), "claude"], env=self.env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

        def reply():
            req = self.asks / "w4242.7.json"
            for _ in range(100):
                if req.exists():
                    break
                time.sleep(0.05)
            data = json.loads(req.read_text())
            (self.asks / "w4242.7.answer").write_text(answer_with(data))

        th = threading.Thread(target=reply)
        th.start()
        out, _ = p.communicate(payload, timeout=15)
        th.join()
        return out

    def test_an_answer_with_this_requests_id_decides(self):
        out = self.ask(lambda d: "allow " + d["id"])
        self.assertIn('"behavior":"allow"', out)
        out = self.ask(lambda d: "deny " + d["id"])
        self.assertIn('"behavior":"deny"', out)

    def test_a_bare_or_stale_answer_is_ignored(self):
        self.assertEqual(self.ask(lambda d: "allow"), "")
        self.assertEqual(self.ask(lambda d: "allow 0123456789abcdef"), "")

    def test_the_request_names_the_command_and_a_random_id(self):
        seen = {}

        def grab(d):
            seen.update(d)
            return "deny " + d["id"]
        self.ask(grab)
        self.assertEqual(seen["what"], "Run: ls -la")
        self.assertRegex(seen["id"], r"^[0-9a-f]{16}$")


if __name__ == "__main__":
    unittest.main()
