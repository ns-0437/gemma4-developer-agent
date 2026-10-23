"""Audit saved CPU replay evidence offline; not a new control execution."""
import json
from pathlib import Path, PurePosixPath
from verify_artifact_manifest import verify as verify_inventory
from verify_final_validation_packet import strict_json, require
from verify_v5_dependencies import verify as verify_dependencies

ROOT=Path(__file__).resolve().parent.parent
EVIDENCE=ROOT/'reference/v5_control_replay_v2_2026-10-22T16-01-44Z'
TASKS=['rich_3278','rich_3535','rich_3675','rich_3942']


def audit(arms, preconditions, identities, pins):
    expected={(t,a) for t in TASKS for a in ('baseline','reference')}
    require(len(arms)==8 and {(a['task'],a['arm']) for a in arms}==expected,
            'expected eight distinct control identities')
    require(len(preconditions)==4 and {p['task'] for p in preconditions}==set(TASKS),
            'expected four distinct preconditions')
    for name,record in identities.items():
        require(record['matches'] is True and record['version']==pins[name]['version']
                and record['python_files']==pins[name]['python_files'], 'runtime identity mismatch: '+name)
    for p in preconditions:
        require(p['ok'] is True and p['cleanup_ok'] is True,'precondition not passed')
        workspace=PurePosixPath(p['ws'])
        require(workspace.is_absolute(),'workspace must be absolute')
        for side in ('agent_file','grading_file'):
            path=PurePosixPath(p[side])
            require('..' not in path.parts and path.is_relative_to(workspace), 'import outside checkout')
    for a in arms:
        require(a['agrees_with_saved'] is True and a['cleanup_ok'] is True,'control acceptance or cleanup failed')
        require(a['workspace_probe_rc']==0 and a['test_patch_rc']==0 and a['junit_read_rc']==0,
                'control probe or test-patch failure')
        require(a['pytest_exit']==a['saved_exit']==(1 if a['arm']=='baseline' else 0),'control exit mismatch')
        require(a['patch_rc']==(None if a['arm']=='baseline' else 0),'reference patch failure')
        require(not a['duplicate_nodes'] and not a['junit_parse_error'] and bool(a['nodes']),'invalid JUnit nodes')
        c=a['node_comparison']
        require(not any(c[k] for k in ('missing','extra','changed','skipped','targets_wrong','reason')),
                'node comparison refused')
        require(c['n_observed']==c['n_expected']==len(a['nodes']) and a['n_targets']>0,'node or target count mismatch')
        canon=a['canonicalization']
        require(not canon.get('saved_root_error') and not canon.get('observed_root_error')
                and not canon.get('refused') and not canon.get('observed_collisions'), 'canonicalization refused')
    return {'controls_accepted':8,'preconditions_passed':4,'saved_evidence_only':True}


def verify(evidence=EVIDENCE):
    evidence=Path(evidence);raw=evidence/'raw'
    inventory=verify_inventory(raw,evidence/'review/raw_sha256.json')
    verify_dependencies()
    load=lambda p:strict_json(p.read_bytes())
    identities={k:load(raw/'pilot'/(k+'_identity.json')) for k in ('compiler','swegemma')}
    pins={k:load(ROOT/'experiments/v5_budget_v2'/(stem+'_hashes.json')) for k,stem in
          [('compiler','compiler_0_2_13'),('swegemma','swegemma_0_2_11')]}
    arms=load(raw/'pilot/control_recheck.json')
    result=audit(arms,load(raw/'pilot/preconditions.json'),identities,pins)
    for a in arms:
        stem=a['task']+'__'+a['arm']
        stored=load(raw/'pilot/control_evidence'/(stem+'.json'))
        require(stored=={k:v for k,v in a.items() if k!='junit_xml'},'aggregate and per-arm records differ')
        require((raw/'pilot/control_evidence'/(stem+'.junit.xml')).read_text(encoding='utf-8')==a['junit_xml'],
                'raw JUnit differs from aggregate evidence')
    result['inventory']=inventory
    result['remote_completeness']='not established by local hashes; see saved inventory limitations'
    return result


if __name__=='__main__':
    try: print(json.dumps(verify(),indent=2))
    except (ValueError,KeyError,OSError) as exc: raise SystemExit('CHECK FAILED: '+str(exc))
