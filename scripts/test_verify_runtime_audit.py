import json
from pathlib import Path
import shutil
import tempfile
import unittest
from verify_runtime_audit import verify, ROOT


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.audit = Path(self.tmp.name)/'audit'
        shutil.copytree(ROOT/'reference/v4_runtime_audit', self.audit)

    def mutate(self, filename, change):
        p = self.audit/filename
        data = json.loads(p.read_text())
        change(data)
        p.write_text(json.dumps(data))

    def test_saved_evidence_verifies_without_writes(self):
        before = {p.name:p.read_bytes() for p in self.audit.iterdir()}
        self.assertEqual(verify(self.audit)['scenarios'], 3)
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.audit.iterdir()})

    def test_duplicate_keys_refused_in_both_evidence_files(self):
        for name in ('archive_config.json', 'scenarios.json'):
            p = self.audit/name
            original = p.read_bytes()
            for text in ('{"a":1,"a":2}', '{"nested":{"a":1,"a":1}}'):
                with self.subTest(name=name, text=text):
                    p.write_text(text)
                    with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
                        verify(self.audit)
            p.write_bytes(original)

    def test_nonfinite_json_constants_refused(self):
        p = self.audit/'scenarios.json'
        for token in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(token=token):
                p.write_text('{"value":' + token + '}')
                with self.assertRaisesRegex(ValueError, 'non-finite JSON'):
                    verify(self.audit)

    def test_archive_hash_drift_refused(self):
        self.mutate('archive_config.json', lambda d:d['v4'].update(archive_sha256='0'*64))
        with self.assertRaisesRegex(ValueError, 'archive evidence'): verify(self.audit)

    def test_changed_inputs_without_recomputed_result_refused(self):
        self.mutate('scenarios.json', lambda d:d['scenarios'][0]['inputs'].update(task_count=61))
        with self.assertRaisesRegex(ValueError, 'recomputed'): verify(self.audit)

    def test_false_guarantee_claim_refused(self):
        self.mutate('scenarios.json', lambda d:d['scenarios'][0]['result'].update(runtime_guarantee=True))
        with self.assertRaisesRegex(ValueError, 'recomputed'): verify(self.audit)

    def test_all_assumptions_required(self):
        p = self.audit/'scenarios.json'
        original = p.read_bytes()
        for key in json.loads(original)['scenarios'][0]['inputs']:
            p.write_bytes(original)
            self.mutate('scenarios.json', lambda d:d['scenarios'][0]['inputs'].pop(key))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'all six'):
                verify(self.audit)

    def test_malformed_documents_fail_cleanly(self):
        import subprocess, sys
        p = self.audit/'scenarios.json'
        for value in ([], None, {'hypothetical_inputs_not_hidden_dataset_estimates':True, 'scenarios':[None]}):
            p.write_text(json.dumps(value))
            r = subprocess.run([sys.executable, str(ROOT/'scripts/verify_runtime_audit.py'), str(self.audit)],
                               capture_output=True, text=True, timeout=20)
            self.assertEqual(r.returncode, 1)
            self.assertNotIn('Traceback', r.stderr)
            self.assertEqual(r.stdout, '')

    def test_empty_scenarios_refused(self):
        self.mutate('scenarios.json', lambda d:d.update(scenarios=[]))
        with self.assertRaisesRegex(ValueError, 'no scenarios'): verify(self.audit)

    def test_missing_hypothetical_declaration_refused(self):
        self.mutate('scenarios.json', lambda d:d.pop('hypothetical_inputs_not_hidden_dataset_estimates'))
        with self.assertRaisesRegex(ValueError, 'declaration'): verify(self.audit)


if __name__ == '__main__': unittest.main()
