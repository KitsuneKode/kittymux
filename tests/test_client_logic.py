"""The kittymux client's rules (client/lib/logic.js), run under node exactly as the file ships to QML (tests/client_logic.mjs)."""
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ClientLogicTests(unittest.TestCase):
    def test_the_client_logic(self):
        r = subprocess.run(["node", os.path.join(HERE, "client_logic.mjs")], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"^ok \d+")


if __name__ == "__main__":
    unittest.main()
