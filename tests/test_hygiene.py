import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("hygiene", Path(__file__).resolve().parents[1] / "scripts/check_public_tree.py")
hygiene = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hygiene)


class HygieneTests(unittest.TestCase):
    def test_sensitive_paths(self):
        for path in (".env", "a/.env.local", "a/private.key", "a/cache.sqlite3", "a/test.session",
                     ".aws/config", "personal-data/messages.json", "../outside", "/outside"):
            self.assertTrue(hygiene.unsafe_path(path), path)
        for path in ("README.md", "src/assistant_hub/core/store.py", ".github/workflows/ci.yml"):
            self.assertFalse(hygiene.unsafe_path(path), path)

    def test_secret_signatures(self):
        self.assertTrue(hygiene.sensitive_content(b"-----BEGIN " + b"PRIVATE KEY-----"))
        self.assertTrue(hygiene.sensitive_content(b"access_" + b"token = abcdefghijk"))
        self.assertFalse(hygiene.sensitive_content(b"Synthetic content only."))

    def test_public_working_tree(self):
        self.assertEqual(hygiene.scan(include_untracked=True), [])
