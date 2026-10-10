"""Verify fail-fast orchestration without running the nested suites."""
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from run_offline_checks import run_checks


class RunnerTests(unittest.TestCase):
    def test_success_uses_same_python_and_repository_root(self):
        runner = Mock(return_value=SimpleNamespace(returncode=0))
        root = Path('fixture-root')
        self.assertEqual(run_checks((('first.py',), ('second.py', 'arg')), root=root, runner=runner), 0)
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(runner.call_args.args[0], [sys.executable, '-B', 'second.py', 'arg'])
        self.assertEqual(runner.call_args.kwargs, dict(cwd=root, timeout=180, check=False))

    def test_nonzero_stops_before_next_check(self):
        runner = Mock(return_value=SimpleNamespace(returncode=7))
        self.assertEqual(run_checks((('bad.py',), ('not-run.py',)), runner=runner), 1)
        self.assertEqual(runner.call_count, 1)

    def test_spawn_error_and_timeout_stop(self):
        for error in (OSError('unavailable'), subprocess.TimeoutExpired('check', 180)):
            with self.subTest(error=error):
                runner = Mock(side_effect=error)
                self.assertEqual(run_checks((('bad.py',), ('not-run.py',)), runner=runner), 1)
                self.assertEqual(runner.call_count, 1)


if __name__ == '__main__':
    unittest.main()
