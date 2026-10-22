import copy
import json
import unittest
from verify_v5_control_packet import ROOT, inspect_notebook, verify


class PacketTests(unittest.TestCase):
    def test_pinned_packet(self):
        self.assertFalse(verify()['dispatch'])

    def test_executable_drift_is_rejected(self):
        original=json.loads((ROOT/'notebooks/v5_control_replay/v5_control_replay.ipynb').read_text())
        cases=[('DISPATCH_CONFIRM = False','DISPATCH_CONFIRM = True','dispatch'),
               ('max_time_minutes=5.0','max_time_minutes=10.0','budget'),
               ('verify_runtime_swegemma()','# omitted gate','missing or duplicate gate'),
               ('rich_3278','rich_wrong','task list')]
        for before,after,reason in cases:
            with self.subTest(reason=reason):
                nb=copy.deepcopy(original); changed=False
                for cell in nb['cells']:
                    if cell['cell_type']!='code': continue
                    source=''.join(cell['source'])
                    if before in source and not changed:
                        cell['source']=source.replace(before,after,1); changed=True
                self.assertTrue(changed)
                with self.assertRaisesRegex(ValueError,reason): inspect_notebook(nb)

    def test_forbidden_dispatch_survives_neither_hash_nor_semantic_check(self):
        nb=json.loads((ROOT/'notebooks/v5_control_replay/v5_control_replay.ipynb').read_text())
        nb['cells'].append({'cell_type':'code','source':'Evaluator()'})
        with self.assertRaisesRegex(ValueError,'unexpected executable'):
            inspect_notebook(nb)


if __name__=='__main__': unittest.main()
