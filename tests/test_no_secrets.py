"""No credential — real or merely credential-SHAPED — belongs in this repository. A real token once reached a commit through a test fixture copied from a process listing;
this fails the unit run (and so CI) on anything shaped like one, in any tracked file. Build sample values at run time from filler instead: "sbp_" + "x" * 24."""
import os
import re
import subprocess
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")

SHAPES = {
    "provider key (sk-/pk-/rk-)": r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{20,}",
    "supabase token": r"\bsbp_[A-Za-z0-9]{16,}",
    "github token": r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}",
    "aws key id": r"\bAKIA[0-9A-Z]{12,}",
    "google api key": r"\bAIza[0-9A-Za-z_-]{20,}",
    "slack token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    "jwt": r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "secret-named assignment": r"""(?i)\b(?:api[_-]?key|secret|token|passwd|password)\b["']?\s*[:=]\s*["'][A-Za-z0-9+/_-]{24,}["']""",
}


def tracked_text_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
    for rel in filter(None, out):
        path = os.path.join(ROOT, rel.decode())
        if not os.path.isfile(path) or os.path.getsize(path) > 2_000_000:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                yield rel.decode(), f.read()
        except (UnicodeDecodeError, OSError):
            continue                                              # binary: fonts, images


class NoSecretsTests(unittest.TestCase):
    def test_no_tracked_file_contains_a_credential_shaped_value(self):
        found = []
        for rel, text in tracked_text_files():
            for label, rx in SHAPES.items():
                for m in re.finditer(rx, text):
                    found.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: {label}")
        self.assertEqual(found, [], "credential-shaped literal(s) — build sample values at run time from filler, never paste one from a real listing")

    def test_the_guard_itself_recognises_the_shapes(self):
        samples = ["sbp_" + "x" * 24, "sk-" + "y" * 30, "ghp_" + "z" * 30, "AKIA" + "A" * 16, "eyJ" + "a" * 20 + "." + "b" * 12 + "." + "c" * 8,
                   "-----BEGIN " + "RSA PRIVATE KEY-----", 'api_key = "' + "q" * 30 + '"']
        for s in samples:
            self.assertTrue(any(re.search(rx, s) for rx in SHAPES.values()), s)
        for ok in ["--api-key", "abc123", "0a1b2c3d-0000-4000-8000-000000000001", "sk-learn"]:
            self.assertFalse(any(re.search(rx, ok) for rx in SHAPES.values()), ok)


if __name__ == "__main__":
    unittest.main()
