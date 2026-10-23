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

    def test_unknown_status_is_not_reported_as_active(self):
        self.assertEqual(self.read(status='NEW_STATE')['outcome'], 'unknown_status')
        for status in ('ERROR', 'FAILED', 'CANCELLED'):
            with self.subTest(status=status):
                self.assertEqual(self.read(status=status)['outcome'], 'error')

    def test_status_whitespace_and_empty_enum(self):
        self.assertEqual(self.read(status=' SubmissionStatus.COMPLETE ', publicScore='0.06')['outcome'], 'scored')
        with self.assertRaisesRegex(ValueError, 'empty normalized status'):
            self.read(status='SubmissionStatus.')

    def test_error_takes_precedence_over_score(self):
        self.assertEqual(self.read(publicScore='0.06', errorDescription='failed')['outcome'], 'error')

    def test_omitted_error_is_unknown_not_explicit_success(self):
        for score, expected in ((None,'complete_without_score_error_unknown'),
                                ('0.13','score_observed_error_unknown'),
                                (0,'score_observed_error_unknown')):
            with self.subTest(score=score):
                result=read_details(json.dumps([dict(ref=7,status='COMPLETE',publicScore=score)]),7)
                self.assertEqual(result['outcome'],expected)
                self.assertIs(result['error_description_observed'],False)
                self.assertEqual(result['score_available'],score is not None)
        result=read_details('[{"ref":7,"status":"ERROR","publicScore":"0.13"}]',7)
        self.assertEqual(result['outcome'],'error')

    def test_ambiguous_or_invalid_records(self):
        for raw in ('{}', '[]', '[{"ref":7},{"ref":7}]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): read_details(raw,7)
        for score in (True, 'NaN', 'oops'):
            with self.subTest(score=score), self.assertRaises(ValueError): self.read(publicScore=score)


if __name__ == '__main__': unittest.main()
