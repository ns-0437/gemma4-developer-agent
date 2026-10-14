import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from capture_submission_status import capture


class CaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / 'new'
        self.raw = b'ref,status,publicScore\n7,PENDING,\n'
        self.runner = Mock(return_value=SimpleNamespace(stdout=self.raw))

    def test_one_request_preserves_bytes_and_verifies(self):
        result = capture(self.folder, 7, runner=self.runner)
        self.assertTrue(result['verified'])
        self.assertEqual((self.folder / 'submissions.csv').read_bytes(), self.raw)
        self.runner.assert_called_once()
        self.assertEqual(self.runner.call_args.args[0][1:],
                         ['-m','kaggle','competitions','submissions','gemma-4-developer-agent','--csv'])
        self.assertEqual(self.runner.call_args.kwargs, dict(capture_output=True, timeout=90, check=True))

    def test_existing_directory_refuses_before_network(self):
        self.folder.mkdir(); (self.folder / 'keep').write_text('original')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            capture(self.folder, 7, runner=self.runner)
        self.runner.assert_not_called()
        self.assertEqual((self.folder / 'keep').read_text(), 'original')

    def test_failure_or_invalid_response_creates_no_snapshot(self):
        for runner in (Mock(side_effect=subprocess.TimeoutExpired('kaggle',90)),
                       Mock(side_effect=subprocess.CalledProcessError(1,'kaggle')),
                       Mock(return_value=SimpleNamespace(stdout=b'not csv'))):
            with self.subTest(runner=runner), self.assertRaises((ValueError, subprocess.SubprocessError)):
                capture(self.folder, 7, runner=runner)
            self.assertFalse(self.folder.exists())
            runner.assert_called_once()

    def test_directory_race_preserves_existing_data(self):
        def respond(*args, **kwargs):
            self.folder.mkdir(); (self.folder / 'keep').write_text('other process')
            return SimpleNamespace(stdout=self.raw)
        with self.assertRaises(FileExistsError):
            capture(self.folder, 7, runner=respond)
        self.assertEqual(list(p.name for p in self.folder.iterdir()), ['keep'])


if __name__ == '__main__': unittest.main()
