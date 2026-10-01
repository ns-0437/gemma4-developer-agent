"""Real Git regression: a complete unified diff must end with a newline.

No harness mocks, model, network, or competition inputs. Uses a temporary checkout.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

PATCH = 'diff --git a/value.py b/value.py\n--- a/value.py\n+++ b/value.py\n@@ -1 +1 @@\n-value = 1\n+value = 2'


class PatchTransportTests(unittest.TestCase):
    def test_original_transport_corrupt_normalized_transport_applies(self):
        with tempfile.TemporaryDirectory(prefix='gemma_patch_test_') as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'core.autocrlf', 'false'], cwd=root,
                           check=True, capture_output=True)
            source = root / 'value.py'
            source.write_bytes(b'value = 1\n')
            patch = root / 'change.patch'
            patch.write_bytes(PATCH.encode('utf-8'))
            broken = subprocess.run(['git', 'apply', str(patch)], cwd=root,
                                    capture_output=True, text=True)
            self.assertNotEqual(broken.returncode, 0)
            self.assertIn('corrupt patch', broken.stderr.lower())
            self.assertEqual(source.read_bytes(), b'value = 1\n')
            patch.write_bytes((PATCH + '\n').encode('utf-8'))
            fixed = subprocess.run(['git', 'apply', str(patch)], cwd=root,
                                   capture_output=True, text=True)
            self.assertEqual(fixed.returncode, 0, fixed.stderr)
            self.assertEqual(source.read_bytes(), b'value = 2\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
