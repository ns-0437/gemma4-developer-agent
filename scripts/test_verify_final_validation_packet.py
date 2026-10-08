"""Identity regressions using an in-memory copy of the real prepared packet."""
import ast
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from verify_final_validation_packet import verify_directory, verify_packet

ROOT = Path(__file__).resolve().parent.parent
RAW = (ROOT / 'notebooks/final_validation_v2/final_validation_v2.ipynb').read_bytes()
PREPARED = json.loads((ROOT / 'experiments/final_validation_v2/NOTEBOOK_PREPARED.json').read_text())


def mutated_bundles(mutate):
    notebook = json.loads(RAW)
    for cell in notebook['cells']:
        if cell['cell_type'] != 'code':
            continue
        source = ''.join(cell['source'])
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == 'BUNDLES' for t in node.targets):
                bundles = ast.literal_eval(node.value)
                mutate(bundles)
                lines = source.splitlines(keepends=True)
                lines[node.lineno - 1:node.end_lineno] = ['BUNDLES = ' + repr(bundles) + '\n']
                cell['source'] = lines
    raw = (json.dumps(notebook) + '\n').encode()
    prepared = copy.deepcopy(PREPARED)
    # Simulate a newly generated packet so the semantic guard, not outer hash,
    # must identify the candidate binding error.
    prepared['notebook_sha256'] = hashlib.sha256(raw).hexdigest()
    return raw, prepared


class PacketIdentityTests(unittest.TestCase):
    def test_original_packet(self):
        self.assertEqual(verify_packet(RAW, PREPARED)['runs'], 6)

    def test_swapped_candidate_bindings_refused(self):
        def swap(bundles):
            bundles['V3'], bundles['ON'] = bundles['ON'], bundles['V3']
        with self.assertRaisesRegex(ValueError, 'declared package hash mismatch'):
            verify_packet(*mutated_bundles(swap))

    def test_wrong_payload_under_correct_declared_hash_refused(self):
        def swap_payload(bundles):
            bundles['V3']['b64'] = bundles['ON']['b64']
        with self.assertRaisesRegex(ValueError, 'decoded package hash mismatch for V3'):
            verify_packet(*mutated_bundles(swap_payload))

    def test_extra_candidate_refused(self):
        with self.assertRaisesRegex(ValueError, 'candidate labels differ'):
            verify_packet(*mutated_bundles(lambda b: b.update(EXTRA=b['ON'])))

    def test_arming_is_exact_and_in_memory(self):
        armed = RAW.replace(b'DISPATCH_CONFIRM = False', b'DISPATCH_CONFIRM = True', 1)
        self.assertTrue(verify_packet(armed, PREPARED, armed=True, baseline=RAW)['armed'])
        with self.assertRaisesRegex(ValueError, 'unexpected change beyond'):
            verify_packet(armed + b'\n', PREPARED, armed=True, baseline=RAW)

    def test_arming_requires_baseline(self):
        with self.assertRaisesRegex(ValueError, 'requires a preserved'):
            verify_packet(RAW, PREPARED, armed=True)


class PacketDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        paths = [
            'notebooks/final_validation_v2/final_validation_v2.ipynb',
            'notebooks/final_validation_v2/kernel-metadata.json',
            'experiments/final_validation_v2/NOTEBOOK_PREPARED.json',
            'experiments/final_validation_v2/VALIDATION_MANIFEST.json',
            'experiments/ab_v3_vs_short/task_freeze.json',
            'releases/v3_submission.zip', 'experiments/thinking_v2/ON.zip',
        ]
        for name in paths:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())

    def test_complete_packet_is_read_only(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(verify_directory(self.root)['source_packages_verified'], 2)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_manifest_reordered_refused(self):
        path = self.root / 'experiments/final_validation_v2/VALIDATION_MANIFEST.json'
        manifest = json.loads(path.read_text())
        manifest['order'].reverse()
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'manifest run order mismatch'):
            verify_directory(self.root)

    def test_changed_source_package_refused(self):
        (self.root / 'releases/v3_submission.zip').write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'source package hash mismatch for V3'):
            verify_directory(self.root)

    def test_cli_refuses_drift_with_nonzero_exit(self):
        (self.root / 'experiments/ab_v3_vs_short/task_freeze.json').write_text('{}')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/verify_final_validation_packet.py'),
                                 '--root', str(self.root)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertIn('holdout freeze hash mismatch', result.stderr)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
