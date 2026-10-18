import unittest
from runtime_budget import budget


class BudgetTests(unittest.TestCase):
    def test_boundary_and_overrun(self):
        self.assertTrue(budget(120, 6)['fits_scenario'])
        self.assertFalse(budget(120, 6.01)['fits_scenario'])

    def test_overhead_and_reserve_are_counted_once(self):
        r = budget(100, 5, setup_seconds=30, startup_minutes=10, reserve_minutes=40)
        self.assertEqual(r['scenario_minutes'], 600)
        self.assertEqual(r['affordable_task_minutes'], 6.2)
        self.assertFalse(r['runtime_guarantee'])

    def test_no_budget_remaining_for_tasks(self):
        r = budget(2, 0, startup_minutes=721)
        self.assertTrue(r['overhead_exceeds_budget'])
        self.assertFalse(r['fits_scenario'])
        self.assertEqual(r['affordable_task_minutes'], 0)

    def test_cli_budget_exit_codes(self):
        import subprocess, sys, json
        from pathlib import Path
        command = [sys.executable, str(Path(__file__).with_name('runtime_budget.py')),
                   '--tasks', '120', '--total-minutes', '720', '--per-task-minutes']
        for minutes, code in (('5', 0), ('10', 1), ('-1', 2)):
            with self.subTest(minutes=minutes):
                result = subprocess.run(command + [minutes], capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, code, result.stderr)
                if code != 2:
                    self.assertEqual(json.loads(result.stdout)['fits_scenario'], code == 0)
                else:
                    self.assertNotIn('Traceback', result.stderr)

    def test_overflow_is_a_validation_error(self):
        for args, kwargs in [((2, 1e308), {}), ((10**400, 1), {}),
                             ((1, 10**400), {}), ((2, 0), {'setup_seconds':1e308})]:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                budget(*args, **kwargs)

    def test_cli_overflow_has_no_traceback_or_nonfinite_json(self):
        import subprocess, sys
        from pathlib import Path
        r = subprocess.run([sys.executable, str(Path(__file__).with_name('runtime_budget.py')),
                            '--tasks', '2', '--per-task-minutes', '1e308', '--total-minutes', '720'],
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, '')
        self.assertNotIn('Traceback', r.stderr)

    def test_invalid_inputs(self):
        for args in ((0, 1), (True, 1), (1.5, 1), (1, -1), (1, float('nan')), (1, True)):
            with self.subTest(args=args), self.assertRaises(ValueError): budget(*args)
        for kwargs in ({'setup_seconds':-1}, {'total_minutes':0}, {'reserve_minutes':float('inf')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): budget(1,1,**kwargs)


if __name__ == '__main__': unittest.main()
