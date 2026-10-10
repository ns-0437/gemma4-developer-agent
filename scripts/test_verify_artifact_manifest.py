"""Failure-path checks for the read-only evidence inventory verifier."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from verify_artifact_manifest import verify


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'raw'
        self.root.mkdir()
        (self.root / 'result.json').write_bytes(b'{"status":"saved"}\n')
        self.manifest = Path(self.temp.name) / 'manifest.json'
        self.expected = {'result.json': hashlib.sha256((self.root / 'result.json').read_bytes()).hexdigest()}
        self.save_manifest()

    def save_manifest(self):
        self.manifest.write_text(json.dumps({'files': self.expected}), encoding='utf-8')

    def test_valid_tree_stays_byte_identical(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        manifest_before = self.manifest.read_bytes()
        self.assertEqual(verify(self.root, self.manifest)['files'], 1)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.assertEqual(manifest_before, self.manifest.read_bytes())

    def test_modified_file_refused(self):
        (self.root / 'result.json').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch: result.json'):
            verify(self.root, self.manifest)

    def test_missing_file_refused(self):
        (self.root / 'result.json').unlink()
        with self.assertRaisesRegex(ValueError, 'inventory mismatch: missing='):
            verify(self.root, self.manifest)

    def test_extra_file_refused(self):
        (self.root / 'unlisted.log').write_text('partial second download')
        with self.assertRaisesRegex(ValueError, 'extra=.*unlisted.log'):
            verify(self.root, self.manifest)

    def test_unsafe_paths_refused(self):
        for name in ('../outside', '/absolute', 'C:/outside', 'a\\b', './result.json'):
            with self.subTest(name=name):
                self.expected = {name: '0' * 64}
                self.save_manifest()
                with self.assertRaisesRegex(ValueError, 'unsafe or noncanonical'):
                    verify(self.root, self.manifest)

    def test_windows_alias_and_stream_paths_refused(self):
        for name in ('result.json:stream', 'nested/NUL.txt', 'con', 'LPT1.log',
                     'folder./result.json', 'result.json ', 'COM9'):
            with self.subTest(name=name):
                self.expected = {name: '0' * 64}
                self.save_manifest()
                with self.assertRaisesRegex(ValueError, 'unsafe or noncanonical'):
                    verify(self.root, self.manifest)

    def test_invalid_digest_refused(self):
        self.expected['result.json'] = 'not-a-hash'
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'invalid SHA-256'):
            verify(self.root, self.manifest)

    def test_duplicate_manifest_paths_refused(self):
        self.manifest.write_text('{"files":{"result.json":"x","result.json":"y"}}')
        with self.assertRaisesRegex(ValueError, 'duplicate manifest key'):
            verify(self.root, self.manifest)


if __name__ == '__main__':
    unittest.main()
