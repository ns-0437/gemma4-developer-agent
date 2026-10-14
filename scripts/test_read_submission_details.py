import json
import unittest
from read_submission_details import read_details


class DetailsTests(unittest.TestCase):
    def read(self, **fields):
        row = dict(ref=7, status='COMPLETE', publicScore=None, errorDescription=None)
        row.update(fields)
        return read_details(json.dumps([row]), 7)

    def test_timeout_complete_is_error(self):
        r = self.read(errorDescription='Your submission notebook exceeded the allowed runtime.')
        self.assertEqual(r['outcome'], 'error')
        self.assertIsNone(r['public_score'])
        self.assertIn('runtime', r['error_description'])

    def test_zero_score_and_blank_are_distinct(self):
        self.assertEqual(self.read(publicScore=0)['outcome'], 'scored')
        self.assertEqual(self.read()['outcome'], 'complete_without_score')
        self.assertEqual(self.read(status='PENDING')['outcome'], 'pending_or_running')

    def test_error_takes_precedence_over_score(self):
        self.assertEqual(self.read(publicScore='0.06', errorDescription='failed')['outcome'], 'error')

    def test_summary_without_error_field_refused(self):
        with self.assertRaisesRegex(ValueError, 'full API record'):
            read_details('[{"ref":7,"status":"COMPLETE","publicScore":null}]', 7)

    def test_ambiguous_or_invalid_records(self):
        for raw in ('{}', '[]', '[{"ref":7},{"ref":7}]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): read_details(raw,7)
        for score in (True, 'NaN', 'oops'):
            with self.subTest(score=score), self.assertRaises(ValueError): self.read(publicScore=score)


if __name__ == '__main__': unittest.main()
