"""Build an offline-only staged workflow; never arm, launch, or submit."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / 'experiments/staged_workflow_v1'


def main():
    out = EXP / 'prototype'
    files = {
        'agent.yaml': '''agent_class: SequentialAgent
name: staged_workflow
description: Offline feasibility prototype, not a promoted submission.
sub_agents:
  - config_path: stages/planner.yaml
  - config_path: stages/coder.yaml
  - config_path: stages/reviewer.yaml
''',
        'prompts/planner.md': '''ROLE: planner
Inspect the issue and relevant source with read_file. Return a concise plan identifying
the requested behavior, assumptions, relevant paths and checks. Do not edit or submit.
Your final text hands the task to the coder. No claim of a per-stage turn limit is made.
''',
        'prompts/coder.md': '''ROLE: coder
Use the issue and preceding plan to make a source fix. Read source, edit with a unique
anchor, run targeted checks with uncaught assertion failures, then run git diff to
expose the actual patch in the tool history. Return a concise handoff with patch paths,
checks and unresolved assumptions. Do not submit: a separate reviewer follows you.
''',
        'prompts/reviewer.md': '''ROLE: reviewer
Review the actual diff in the preceding tool history, not just the coder's claims.
Read affected files independently with read_file. Check consistency with the issue,
preserved behavior and reported verification. If the actual diff is missing, do not
claim to have reviewed it. You have no editing or command-execution tools.
If acceptable call submit_patch then report your verdict. Otherwise return REJECT
with the specific reasons and do not submit. This instruction is not a grading gate.
''',
    }
    for role, names in {
        'planner': ['read_file'],
        'coder': ['read_file', 'edit_file', 'run_command'],
        'reviewer': ['read_file', 'get_status', 'submit_patch'],
    }.items():
        files[f'stages/{role}.yaml'] = (
            f'name: {role}\nmodel: gemma-4-31b-it-qat-w4a16-ct\n'
            f'instruction: !include ../prompts/{role}.md\n'
            'include_contents: default\n'
            f'output_key: {role}_report\n'
            'disallow_transfer_to_parent: true\ndisallow_transfer_to_peers: true\n'
            'tools:\n' + ''.join(f'  - {name}\n' for name in names) +
            'generate_content_config: !include ../configs/sampling.yaml\n'
        )
    for name, content in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
    sampling = out / 'configs/sampling.yaml'
    sampling.parent.mkdir(parents=True, exist_ok=True)
    sampling.write_bytes((ROOT / 'experiments/shellread_v1/candidate_S_shellread/configs/sampling.yaml').read_bytes())
    manifest = {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(out.rglob('*')) if p.is_file()}
    (EXP / 'PROTOTYPE_SHA256.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Prepared offline prototype:', out)


if __name__ == '__main__':
    main()
