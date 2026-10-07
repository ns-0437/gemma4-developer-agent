"""Execute official-compiled ADK stages with scripted model responses, offline.

Real: compiler, Runner, session history, function dispatch, global LLM limit,
temporary Git repository, file edit, git diff. Simulated: model responses and
harness tool implementations (same signatures). No Gemma, HTTP, or GPU.
"""
from __future__ import annotations
import asyncio
import hashlib
import importlib.metadata as metadata
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / 'experiments/staged_workflow_v1'
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
sys.path.insert(0, str(ROOT / 'experiments/shellread_v1/compiler_0_2_12/src'))
os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
import official_check as O
import adk_submission
from google.adk.models.lite_llm import LiteLlm, LiteLLMClient
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.run_config import RunConfig
from google.genai import types
from litellm import ModelResponse

EXPECTED = {'planner': ['read_file'],
            'coder': ['edit_file', 'read_file', 'run_command'],
            'reviewer': ['get_status', 'read_file', 'submit_patch']}
BEFORE = 'def twice(n):\n    return n + 1\n'
AFTER = 'def twice(n):\n    return n * 2\n'


class Fixture:
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.submitted = None
        (root / 'toy.py').write_text(BEFORE)
        self.git('init', '-q')
        self.git('add', 'toy.py')
        self.git('-c', 'user.name=Offline Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '-qm', 'Synthetic baseline')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout

    def path(self, filepath):
        p = (self.root / filepath).resolve()
        if not p.is_relative_to(self.root.resolve()):
            raise ValueError('fixture path outside repository')
        return p

    def tools(self):
        def read_file(filepath: str, start_line: int | None = None, end_line: int | None = None) -> str:
            """Read a repository file."""
            self.calls.append(('read_file', filepath))
            lines = self.path(filepath).read_text().splitlines(keepends=True)
            return json.dumps({'status': 'ok', 'content': ''.join(lines[(start_line or 1)-1:end_line])})

        def edit_file(filepath: str, old_string: str, new_string: str, allow_multiple: bool = False) -> str:
            """Replace an exact source anchor."""
            self.calls.append(('edit_file', filepath))
            p = self.path(filepath)
            s = p.read_text()
            assert allow_multiple or s.count(old_string) == 1
            p.write_text(s.replace(old_string, new_string))
            return json.dumps({'status': 'ok', 'filepath': filepath, 'diff': self.git('diff', '--', filepath)})

        def run_command(command: str) -> str:
            """Offline fixture supports a diff or an empty search only."""
            self.calls.append(('run_command', command))
            if command == 'git diff -- toy.py':
                stdout = self.git('diff', '--', 'toy.py')
            elif command == 'git log --grep=missing --oneline':
                stdout = self.git('log', '--grep=missing', '--oneline')
            else:
                raise ValueError('Unsupported offline fixture command')
            return json.dumps({'status': 'ok', 'stdout': stdout, 'stderr': '', 'exit_code': 0})

        def get_status() -> str:
            """Report submission metadata, not a diff."""
            self.calls.append(('get_status', ''))
            return json.dumps({'status': 'ok', 'patch_submitted': self.submitted is not None})

        def submit_patch() -> str:
            """Capture the real temporary repository diff."""
            self.calls.append(('submit_patch', ''))
            self.submitted = self.git('diff', '--', 'toy.py')
            return json.dumps({'status': 'ok', 'patch_size': len(self.submitted)})

        registry = {f.__name__: f for f in (read_file, edit_file, run_command, get_status, submit_patch)}
        for name, func in registry.items():
            assert inspect.signature(func) == inspect.signature(O.TOOLS[name]), name
        return registry


class ScriptClient(LiteLLMClient):
    def __init__(self, scenario):
        super().__init__()
        self._scenario = scenario
        self._requests = []
        self._counts = {}

    async def acompletion(self, **kwargs):
        system = '\n'.join(str(m.get('content', '')) for m in kwargs['messages'] if m['role'] == 'system')
        stage = next(x for x in EXPECTED if f'ROLE: {x}' in system)
        tools = sorted(t['function']['name'] for t in kwargs.get('tools') or [])
        assert tools == EXPECTED[stage], (stage, tools)
        count = self._counts.get(stage, 0)
        self._counts[stage] = count + 1
        self._requests.append({'stage': stage, 'tools': tools, 'messages': kwargs['messages']})
        call, args, text = None, {}, 'Stage complete.'
        scenario = self._scenario
        if scenario == 'planner_forbidden' and stage == 'planner':
            call, args = 'run_command', {'command': 'git diff -- toy.py'}
        elif scenario == 'reviewer_forbidden' and stage == 'reviewer':
            call, args = 'edit_file', {'filepath':'toy.py','old_string':'n * 2','new_string':'999'}
        elif scenario == 'coder_forbidden' and stage == 'coder':
            call = 'submit_patch'
        elif scenario == 'planner_loops' and stage == 'planner':
            call, args = 'read_file', {'filepath':'toy.py'}
        elif scenario in ('coder_loops', 'coder_loops_60', 'loop_wrapper') and stage == 'coder':
            call, args = 'run_command', {'command':'git log --grep=missing --oneline'}
        elif stage == 'planner':
            if count == 0: call, args = 'read_file', {'filepath':'toy.py'}
            else: text = 'Plan: twice should return twice its input; inspect and test toy.py.'
        elif stage == 'coder':
            if scenario == 'no_patch': text = 'No patch available.'
            elif count == 0: call, args = 'edit_file', {'filepath':'toy.py','old_string':'n + 1','new_string':'n * 2'}
            elif count == 1: call, args = 'run_command', {'command':'git diff -- toy.py'}
            else: text = 'Review the actual tool diff. Verification remains an offline fixture.'
        elif stage == 'reviewer':
            if count == 0: call, args = 'read_file', {'filepath':'toy.py'}
            elif scenario in ('review_rejects', 'no_patch', 'reviewer_no_history'):
                text = 'REJECT: missing verification or actual patch evidence.'
            elif count == 1: call = 'submit_patch'
            else: text = 'ACCEPT: synthetic patch reviewed.'
        message = {'role':'assistant','content':text}
        if call:
            message = {'role':'assistant','content':None,'tool_calls':[{
                'id':f'{stage}_{count}','type':'function',
                'function':{'name':call,'arguments':json.dumps(args)}}]}
        return ModelResponse(model=kwargs['model'], choices=[{'index':0,'message':message,
            'finish_reason':'tool_calls' if call else 'stop'}],
            usage={'prompt_tokens':100,'completion_tokens':10,'total_tokens':110})

    def completion(self, **kwargs):
        raise AssertionError('Unexpected sync transport')


def compile_workflow(folder, fixture, client):
    O.validate_directory(folder, O.LIMITS)
    registry = O.ModelRegistry()
    model = LiteLlm(model='openai/gemma-4-31b-it-qat-w4a16-ct', api_base='http://127.0.0.1:9/v1', api_key='EMPTY')
    model.llm_client = client
    registry.register('gemma-4-31b-it-qat-w4a16-ct', model)
    agent = O.compile_submission(submission_dir=folder, tool_registry=fixture.tools(),
                                 model_registry=registry, limits=O.LIMITS, generation_constraints=O.GEN)
    # The compiler clones registered models. Capture each compiled stage's
    # transport in the same offline client; do not replace its flow or tools.
    for child in agent.sub_agents:
        child.model.llm_client = client
    return agent


async def run_case(scenario, out):
    with tempfile.TemporaryDirectory(prefix='staged_offline_') as tmp:
        base = Path(tmp)
        repo = base / 'repo'; repo.mkdir()
        fixture = Fixture(repo)
        folder = base / 'prototype'
        shutil.copytree(EXP / 'prototype', folder)
        if scenario == 'loop_wrapper':
            p = folder/'agent.yaml'
            p.write_text(p.read_text().replace('SequentialAgent','LoopAgent')+'max_iterations: 1\n')
        if scenario == 'reviewer_no_history':
            p = folder/'stages/reviewer.yaml'
            p.write_text(p.read_text().replace('include_contents: default','include_contents: none'))
        client = ScriptClient(scenario)
        agent = compile_workflow(folder, fixture, client)
        budget = 60 if scenario == 'coder_loops_60' else 8
        sessions = InMemorySessionService()
        session = await sessions.create_session(app_name='staged_offline', user_id='fixture')
        runner = Runner(agent=agent, app_name='staged_offline', session_service=sessions)
        error = None
        events = []
        try:
            async for event in runner.run_async(user_id='fixture', session_id=session.id,
                    new_message=types.Content(role='user',parts=[types.Part(text='Synthetic task: twice(n) must equal n * 2.')]),
                    run_config=RunConfig(max_llm_calls=budget)):
                events.append({'author':event.author,'content':event.content.model_dump(mode='json') if event.content else None})
        except Exception as exc:
            error = {'type':type(exc).__name__,'message':str(exc)}
        finally:
            await runner.close()
        requests = client._requests
        stages = list(dict.fromkeys(r['stage'] for r in requests))
        review_requests = [r for r in requests if r['stage']=='reviewer']
        review_has_patch = bool(review_requests and 'diff --git a/toy.py b/toy.py' in json.dumps(review_requests[0]['messages']))
        diff = fixture.git('diff','--','toy.py')
        result = {'scenario':scenario,'stage_order':stages,'request_counts':dict(client._counts),
                  'reviewer_saw_actual_diff':review_has_patch,'tool_calls':fixture.calls,
                  'submitted':fixture.submitted is not None,'patch':diff,'error':error,'global_llm_budget':budget}
        if scenario == 'happy':
            assert error is None and stages == ['planner','coder','reviewer'], result
            assert fixture.path('toy.py').read_text()==AFTER and review_has_patch and fixture.submitted==diff and diff
            first_review = json.dumps(review_requests[0]['messages'])
            assert 'Synthetic task: twice(n)' in first_review and 'Plan: twice' in first_review
            assert len([x for x in fixture.calls if x[0]=='read_file'])==2
        elif scenario in ('planner_loops','coder_loops','coder_loops_60','loop_wrapper'):
            assert error and 'LlmCallsLimitExceeded' in error['type'], result
            assert len(requests)==budget and not review_requests and fixture.submitted is None, result
        elif scenario.endswith('_forbidden'):
            forbidden = {'planner_forbidden':'run_command','coder_forbidden':'submit_patch','reviewer_forbidden':'edit_file'}[scenario]
            assert error and 'not found' in error['message'], result
            expected_count = 1 if scenario=='reviewer_forbidden' else 0
            assert sum(name==forbidden for name,arg in fixture.calls)==expected_count, result
            assert fixture.submitted is None
            if scenario=='reviewer_forbidden': assert fixture.path('toy.py').read_text()==AFTER
        elif scenario == 'review_rejects':
            assert error is None and review_has_patch and fixture.submitted is None and diff, result
        elif scenario == 'no_patch':
            assert error is None and review_requests and not review_has_patch and not diff and fixture.submitted is None, result
        elif scenario == 'reviewer_no_history':
            assert error is None and review_requests and not review_has_patch and diff and fixture.submitted is None, result
        (out/f'{scenario}.json').write_text(json.dumps({'result':result,'requests':requests,'events':events},indent=2),encoding='utf-8')
        return result


def reject_unsupported_caps():
    results = []
    for field in ['max_llm_calls: 3', 'max_turns: 3', 'run_config: {max_llm_calls: 3}']:
        with tempfile.TemporaryDirectory(prefix='staged_schema_') as tmp:
            base = Path(tmp); repo=base/'repo'; repo.mkdir()
            fixture=Fixture(repo); folder=base/'prototype'
            shutil.copytree(EXP/'prototype',folder)
            path=folder/'stages/coder.yaml'
            path.write_text(path.read_text()+'\n'+field+'\n')
            try:
                compile_workflow(folder,fixture,ScriptClient('happy'))
            except Exception as exc:
                assert 'extra' in str(exc).lower() and field.split(':')[0] in str(exc), str(exc)
                results.append({'field':field,'error':type(exc).__name__,'message':str(exc)})
            else:
                raise AssertionError('Unrecognized cap accepted; inspect semantics: '+field)
    return results


async def main():
    assert metadata.version('adk-submission')=='0.2.12'
    assert Path(adk_submission.__file__).is_relative_to(ROOT/'experiments/shellread_v1/compiler_0_2_12/src')
    out = EXP/'offline_evidence'; out.mkdir(exist_ok=True)
    results=[]
    scenarios=['happy','planner_forbidden','coder_forbidden','reviewer_forbidden',
               'planner_loops','coder_loops','coder_loops_60','loop_wrapper','review_rejects','no_patch','reviewer_no_history']
    # A stray provider HTTP call must fail rather than silently reaching a service.
    with patch('socket.socket.connect', side_effect=AssertionError('Network disabled in offline proof')):
        schema_checks = reject_unsupported_caps()
        for scenario in scenarios:
            result = await run_case(scenario,out)
            results.append(result)
            print('PASS', scenario, result['stage_order'], result['error']['type'] if result['error'] else '')
    report={'versions':{k:metadata.version(k) for k in ('adk-submission','google-adk','litellm')},
            'real_model_used':False,'network_used':False,'scenarios_passed':len(results),'results':results,
            'unsupported_per_stage_caps_rejected':schema_checks,
            'verdict':'Normal handoff supported; forced progress under repeated tool calls NOT established. Global-budget starvation reproduced.'}
    (EXP/'CHECKS.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(report['verdict'])


if __name__=='__main__':
    asyncio.run(main())
