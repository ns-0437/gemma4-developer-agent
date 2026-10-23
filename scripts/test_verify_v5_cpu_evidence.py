import copy
import unittest
from verify_v5_cpu_evidence import EVIDENCE, ROOT, strict_json, audit, verify


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        load=lambda p:strict_json(p.read_bytes())
        raw=EVIDENCE/'raw/pilot'
        self.arms=load(raw/'control_recheck.json');self.pre=load(raw/'preconditions.json')
        self.identities={n:load(raw/(n+'_identity.json')) for n in ('compiler','swegemma')}
        self.pins={n:load(ROOT/'experiments/v5_budget_v2'/(stem+'_hashes.json')) for n,stem in
                   [('compiler','compiler_0_2_13'),('swegemma','swegemma_0_2_11')]}

    def test_preserved_evidence(self): self.assertEqual(verify()['controls_accepted'],8)

    def test_acceptance_flag_does_not_mask_independent_failures(self):
        for key,value,reason in [('cleanup_ok',False,'cleanup'),('test_patch_rc',1,'test-patch'),
                                 ('pytest_exit',0,'exit'),('patch_rc',0,'reference patch'),
                                 ('duplicate_nodes',['duplicate'],'JUnit')]:
            with self.subTest(key=key):
                arms=copy.deepcopy(self.arms);arms[0][key]=value
                with self.assertRaisesRegex(ValueError,reason):audit(arms,self.pre,self.identities,self.pins)

    def test_missing_or_duplicate_arm_refused(self):
        for arms in (self.arms[:-1],self.arms[:-1]+[self.arms[0]]):
            with self.assertRaisesRegex(ValueError,'distinct control'):
                audit(arms,self.pre,self.identities,self.pins)

    def test_provenance_and_identity_refused(self):
        pre=copy.deepcopy(self.pre);pre[0]['grading_file']='/usr/lib/rich/__init__.py'
        with self.assertRaisesRegex(ValueError,'outside checkout'):
            audit(self.arms,pre,self.identities,self.pins)
        identities=copy.deepcopy(self.identities);identities['compiler']['version']='0.2.12'
        with self.assertRaisesRegex(ValueError,'identity mismatch'):
            audit(self.arms,self.pre,identities,self.pins)

    def test_changed_nodes_refused_even_when_acceptance_true(self):
        arms=copy.deepcopy(self.arms);arms[0]['node_comparison']['changed']=['node']
        with self.assertRaisesRegex(ValueError,'node comparison'):
            audit(arms,self.pre,self.identities,self.pins)


if __name__=='__main__':unittest.main()
