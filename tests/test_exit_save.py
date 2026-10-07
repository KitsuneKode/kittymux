import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
import kittymux_sessionfile as S

class SessionFileTests(unittest.TestCase):
    def test_old_writer_cannot_replace_new_exit_capture(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(S.publish(d, 123, 200, 'new_tab latest\nlaunch sh\n'))
            self.assertFalse(S.publish(d, 123, 100, 'new_tab stale\nlaunch sh\n'))
            p = Path(d, 'autosave-123.kitty-session')
            self.assertIn('latest', p.read_text())
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(d).glob('*.kitty-session')), [p])
    def test_rejects_invalid_identity_and_oversize_text(self):
        with tempfile.TemporaryDirectory() as d:
            for pid, stamp, text in ((True, 1, 'launch sh'), (1, -1, 'launch sh'), (1, 1, 'x' * (S.MAX_BYTES + 1))):
                with self.assertRaises(ValueError): S.publish(d, pid, stamp, text)
