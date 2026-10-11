"""Regression checks for the preserved submission provenance chain."""
import json
import tempfile
import unittest
from pathlib import Path
from verify_v4_submission import ROOT, verify


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        names = ['releases/v4_submission_record.json', 'releases/v4_thinking_on_submission.zip',
                 'experiments/thinking_v2/ON.zip', 'reference/submission_v4_2026-10-11/submission.zip']
        for directory in ('releases/v4_thinking_on', 'notebooks/submit_v4_thinking_on'):
            names += [p.relative_to(ROOT).as_posix() for p in (ROOT / directory).rglob('*') if p.is_file()]
        for name in names:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())

    def test_intact_chain_is_read_only(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(verify(self.root)['submission_ref'], 57064155)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_duplicate_receipt_and_metadata_keys(self):
        for name, key, value in (
            ('releases/v4_submission_record.json', 'kernel_version', '99'),
            ('notebooks/submit_v4_thinking_on/kernel-metadata.json', 'enable_gpu', 'true')):
            with self.subTest(name=name):
                p = self.root / name
                original = p.read_bytes()
                p.write_text('{"' + key + '":' + value + ',' + original.decode().lstrip()[1:])
                try:
                    with self.assertRaisesRegex(ValueError, 'duplicate packet JSON key'):
                        verify(self.root)
                finally:
                    p.write_bytes(original)

    def test_download_drift(self):
        (self.root / 'reference/submission_v4_2026-10-11/submission.zip').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError, 'archive copy mismatch'):
            verify(self.root)

    def test_source_drift(self):
        (self.root / 'releases/v4_thinking_on/agent.yaml').write_text('wrong')
        with self.assertRaisesRegex(ValueError, 'release source mismatch'):
            verify(self.root)

    def test_extra_source_file(self):
        (self.root / 'releases/v4_thinking_on/extra.txt').write_text('untracked')
        with self.assertRaisesRegex(ValueError, 'file set mismatch'):
            verify(self.root)

    def test_metadata_accelerator_change(self):
        p = self.root / 'notebooks/submit_v4_thinking_on/kernel-metadata.json'
        data = json.loads(p.read_text()); data['enable_gpu'] = True; p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'execution settings mismatch'):
            verify(self.root)

    def test_metadata_entry_point_and_sources(self):
        p = self.root / 'notebooks/submit_v4_thinking_on/kernel-metadata.json'
        original = json.loads(p.read_text())
        for key, value, message in (
            ('code_file', 'other.ipynb', 'entry point'),
            ('competition_sources', [], 'input sources'),
            ('dataset_sources', ['unexpected/input'], 'input sources'),
            ('model_sources', ['unexpected/model'], 'input sources'),
            ('kernel_sources', ['unexpected/kernel'], 'input sources')):
            with self.subTest(key=key):
                data = dict(original); data[key] = value; p.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, message):
                    verify(self.root)

    def test_receipt_version_change(self):
        p = self.root / 'releases/v4_submission_record.json'
        data = json.loads(p.read_text()); data['kernel_version'] = 3; p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'submission identity mismatch'):
            verify(self.root)


if __name__ == '__main__':
    unittest.main()
