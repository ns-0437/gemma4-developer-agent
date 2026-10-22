import hashlib
import tempfile
import unittest
from pathlib import Path
from verify_v5_dependencies import verify, verify_sources


class DependencyTests(unittest.TestCase):
    def test_repository_pins(self):
        self.assertTrue(all(r['matches'] for r in verify().values()))

    def test_each_drift_is_reported(self):
        for fault in ('missing','extra','changed','version'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); source = root / 'pkg'; source.mkdir()
                module = source / '__init__.py'; module.write_bytes(b'# original')
                metadata = root / 'METADATA'; metadata.write_text('Version: 1.0\n')
                manifest = {'version':'1.0','python_files':{'__init__.py':hashlib.sha256(module.read_bytes()).hexdigest()}}
                if fault == 'missing': module.unlink()
                elif fault == 'extra': (source / 'extra.py').write_bytes(b'# extra')
                elif fault == 'changed': module.write_bytes(b'# changed')
                else: metadata.write_text('Version: 2.0\n')
                result = verify_sources(source, metadata, manifest)
                self.assertFalse(result['matches'])
                if fault == 'version': self.assertFalse(result['version_ok'])
                else: self.assertTrue(result[fault])
                for other in {'missing','extra','changed'} - {fault}:
                    self.assertEqual(result[other], [])

    def test_manifest_drift_refused_before_source_reads(self):
        from verify_v5_dependencies import PINS
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'experiments/v5_budget_v2'; base.mkdir(parents=True)
            stem = next(iter(PINS.values()))[0]
            (base / (stem + '_hashes.json')).write_text('{}')
            with self.assertRaisesRegex(ValueError, 'manifest drift'):
                verify(tmp)


if __name__ == '__main__': unittest.main()
