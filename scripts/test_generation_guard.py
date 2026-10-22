import tempfile
import unittest
from pathlib import Path
from generation_guard import require_unlaunched


class GuardTests(unittest.TestCase):
    def test_fresh_destination_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'new'
            require_unlaunched(p)
            self.assertFalse(p.exists())

    def test_any_receipt_refuses_and_is_preserved(self):
        for raw in (b'{}', b'incomplete receipt', b''):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / 'LAUNCH_RECORD.json'
                p.write_bytes(raw)
                with self.assertRaisesRegex(RuntimeError, 'launched experiment'):
                    require_unlaunched(tmp)
                self.assertEqual(p.read_bytes(), raw)

    def test_generators_guard_before_writing(self):
        import ast
        for name in ('make_v5_budget_notebook.py', 'make_v5_control_replay_notebook.py'):
            source = (Path(__file__).parent / name).read_text()
            tree = ast.parse(source)
            main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
            calls = [n for n in ast.walk(main) if isinstance(n, ast.Call)]
            guard = next(n for n in calls if ast.unparse(n.func) == 'require_unlaunched')
            writer = next(n for n in calls if ast.unparse(n.func) == 'M.main')
            self.assertLess(guard.lineno, writer.lineno)


if __name__ == '__main__':
    unittest.main()
