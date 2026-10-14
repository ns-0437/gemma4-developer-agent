import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from read_submission_snapshot import read_submission
from verify_submission_observation import verify


class ObservationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        raw = b'ref,status,publicScore\n7,PENDING,\n'
        (self.root / 'submissions.csv').write_bytes(raw)
        self.record = {'stdout_sha256': hashlib.sha256(raw).hexdigest(),
                       'checked_at_utc': '2026-10-12T00:00:00+00:00',
                       'observation': read_submission(raw.decode(), 7)}
        self.save()

    def save(self):
        (self.root / 'observation.json').write_text(json.dumps(self.record))

    def test_valid_is_read_only(self):
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        self.assertTrue(verify(self.root)['verified'])
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_invalid_record_shapes_and_boolean_aliases(self):
        import copy
        baseline = copy.deepcopy(self.record)
        cases = [[], dict(baseline, checked_at_utc=None),
                 dict(baseline, stdout_sha256=123), dict(baseline, observation=[])]
        for flag, value in (('score_available', 0), ('live_status_checked', 0),
                            ('live_status_checked', True)):
            item = copy.deepcopy(baseline); item['observation'][flag] = value; cases.append(item)
        for item in cases:
            with self.subTest(item=item):
                self.record = item; self.save()
                with self.assertRaises(ValueError): verify(self.root)

    def test_csv_drift(self):
        (self.root / 'submissions.csv').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'): verify(self.root)

    def test_fabricated_score_or_status(self):
        for key,value in (('public_score','0.20'), ('status','COMPLETE')):
            with self.subTest(key=key):
                original = dict(self.record['observation'])
                self.record['observation'][key] = value; self.save()
                with self.assertRaisesRegex(ValueError, 'differs'): verify(self.root)
                self.record['observation'] = original

    def test_timezone_required(self):
        for value in ('2026-10-12T00:00:00', '2026-10-12T00:00:00+05:30', 'invalid'):
            with self.subTest(value=value):
                self.record['checked_at_utc'] = value; self.save()
                with self.assertRaises(ValueError): verify(self.root)


if __name__ == '__main__': unittest.main()
