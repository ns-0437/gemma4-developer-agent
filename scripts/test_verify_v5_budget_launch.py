import copy
import unittest
from verify_v5_budget_launch import ROOT, verify, verify_artifacts, strict_json


class LaunchTests(unittest.TestCase):
    def setUp(self):
        nb=ROOT/'notebooks/v5_budget_v2'; exp=ROOT/'experiments/v5_budget_v2/gpu_baseline'
        self.raw=(nb/'v5_budget_v2.ipynb').read_bytes()
        self.disabled=(exp/'v5_budget_v2_disabled.ipynb').read_bytes()
        self.meta=(nb/'kernel-metadata.json').read_bytes()
        self.prepared=strict_json((exp/'NOTEBOOK_PREPARED.json').read_bytes())
        self.launch=strict_json((exp/'LAUNCH_RECORD.json').read_bytes())

    def test_recorded_launch(self): self.assertTrue(verify()['armed'])

    def test_changes_beyond_dispatch_refused(self):
        for part in ('raw','disabled','meta'):
            with self.subTest(part=part):
                args=[self.raw,self.disabled,self.meta,self.prepared,self.launch]
                args[('raw','disabled','meta').index(part)]+=b' '
                with self.assertRaises(ValueError): verify_artifacts(*args)

    def test_receipt_cannot_relabel_launch(self):
        for key,value in [('kernel_version',2),('kernel_version',True),('push_attempts',2),
                          ('order',list(reversed(self.launch['order']))),('budgets',{}),('candidate',{})]:
            with self.subTest(key=key,value=value):
                changed=copy.deepcopy(self.launch);changed[key]=value
                with self.assertRaises(ValueError):
                    verify_artifacts(self.raw,self.disabled,self.meta,self.prepared,changed)


if __name__=='__main__':unittest.main()
