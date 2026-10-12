import unittest
from read_submission_snapshot import read_submission


class SnapshotTests(unittest.TestCase):
    def test_pending_is_not_zero(self):
        r = read_submission('ref,status,publicScore\n7,SubmissionStatus.PENDING,\n', 7)
        self.assertEqual(r['status'], 'PENDING')
        self.assertIsNone(r['public_score'])
        self.assertFalse(r['score_available'])

    def test_zero_is_a_real_score(self):
        r = read_submission('ref,status,publicScore\n7,COMPLETE,0.0\n', 7)
        self.assertEqual(r['public_score'], '0.0')
        self.assertTrue(r['score_available'])

    def test_quoted_descriptions_and_bom(self):
        text = '\ufeffref,status,publicScore,description\n7,COMPLETE,0.06,"a,b"\n'
        self.assertEqual(read_submission(text, 7)['public_score'], '0.06')

    def test_missing_duplicate_and_malformed_refused(self):
        cases = ('ref,status\n7,PENDING\n', 'ref,status,publicScore,ref\n7,PENDING,,7\n',
                 'ref,status,publicScore\n8,PENDING,\n',
                 'ref,status,publicScore\n7,PENDING,\n7,PENDING,\n',
                 'ref,status,publicScore\n7,PENDING\n',
                 'ref,status,publicScore\n7,PENDING,,extra\n')
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ValueError):
                read_submission(text, 7)

    def test_unclosed_quote_and_empty_status(self):
        for text in ('ref,status,publicScore\n7,"PENDING,\n',
                     'ref,status,publicScore\n7, ,\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                read_submission(text, 7)

    def test_reference_requires_positive_integer(self):
        for ref in (True, 0, -1, '7'):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, 'positive integer'):
                read_submission('ref,status,publicScore\n7,PENDING,\n', ref)

    def test_invalid_or_nonfinite_score(self):
        for score in ('NaN', 'Infinity', 'unknown'):
            with self.subTest(score=score), self.assertRaises(ValueError):
                read_submission('ref,status,publicScore\n7,COMPLETE,' + score + '\n', 7)


if __name__ == '__main__':
    unittest.main()
