from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile
from inspect_eval_config import inspect_archive


class ArchiveTests(unittest.TestCase):
    def inspect(self, entries):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'agent.zip'
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                with zipfile.ZipFile(path,'w') as z:
                    for name, text in entries: z.writestr(name,text)
            before = path.read_bytes()
            result = inspect_archive(path)
            self.assertEqual(path.read_bytes(), before)
            return result

    def test_missing_is_unknown_not_default(self):
        r=self.inspect([('agent.yaml','name: test')])
        self.assertFalse(r['root_eval_config_present'])
        self.assertFalse(r['effective_limits_verified'])
        self.assertIsNone(r['config_text'])

    def test_root_and_nested_are_distinct(self):
        text='max_time_minutes: 5\n'
        r=self.inspect([('nested/eval_config.yaml',text),('eval_config.yaml',text)])
        self.assertEqual(r['config_text'],text)
        self.assertEqual(r['nested_config_paths'],['nested/eval_config.yaml'])
        self.assertFalse(r['effective_limits_verified'])

    def test_nested_only_does_not_count_as_root(self):
        self.assertFalse(self.inspect([('nested/eval_config.yaml','x')])['root_eval_config_present'])

    def test_oversized_config_refused_before_decompression(self):
        from inspect_eval_config import MAX_CONFIG_BYTES
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'large.zip'
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('eval_config.yaml', b'x'*(MAX_CONFIG_BYTES+1))
            with patch.object(zipfile.ZipFile, 'open', side_effect=AssertionError('must not decompress')):
                with self.assertRaisesRegex(ValueError, 'inspection limit'):
                    inspect_archive(path)

    def test_config_at_limit_and_utf8_validation(self):
        from inspect_eval_config import MAX_CONFIG_BYTES
        self.assertEqual(len(self.inspect([('eval_config.yaml', 'x'*MAX_CONFIG_BYTES)])['config_text']),
                         MAX_CONFIG_BYTES)
        with self.assertRaises(UnicodeDecodeError):
            self.inspect([('eval_config.yaml', b'\xff')])

    def test_ambiguous_or_duplicate_configs_refused(self):
        for names in (('eval_config.yaml','eval_config.yml'),('eval_config.yaml','eval_config.yaml')):
            with self.subTest(names=names), self.assertRaises(ValueError):
                self.inspect([(n,'x') for n in names])


if __name__ == '__main__': unittest.main()
