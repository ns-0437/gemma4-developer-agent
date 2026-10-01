"""Offline official compilation and ADK-to-client request capture. Never calls HTTP."""
import asyncio
import hashlib
import importlib.metadata as md
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
import official_check as O
from google.adk.models.lite_llm import LiteLLMClient, LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.genai import types


class Captured(Exception):
    pass


class CaptureClient(LiteLLMClient):
    async def acompletion(self, **kwargs):
        CAPTURES.append(kwargs)
        raise Captured()


CAPTURES = []


async def inspect_agent(agent):
    agent.model.llm_client = CaptureClient()
    request = LlmRequest(model=agent.model.model,
                         contents=[types.Content(role='user', parts=[types.Part(text='Offline probe')])],
                         config=agent.generate_content_config)
    try:
        async for _ in agent.model.generate_content_async(request, stream=False):
            raise AssertionError('fake client should stop before any response')
    except Captured:
        pass
    else:
        raise AssertionError('transport capture not reached')
    sent = CAPTURES[-1]
    return {'compiled': agent.generate_content_config.model_dump(exclude_none=True),
            'client_parameters': {k: v for k, v in sent.items()
                                  if k not in ('messages', 'tools', 'api_key')},
            'instruction_sha256': hashlib.sha256(agent.instruction.encode()).hexdigest()}


def main():
    report = {'versions': {k: md.version(k) for k in ('google-adk', 'litellm', 'adk-submission')},
              'candidates': {}, 'boundary': 'ADK kwargs at LiteLLM client; no HTTP or server execution'}
    for key, folder, temp in [('S', 'experiments/concise_workflow_v1/candidate_S', .2),
                              ('S_temp', 'experiments/temperature_v1/candidate_S_temp', .7)]:
        source = ROOT / folder
        O.validate_directory(source, O.LIMITS)
        registry = O.ModelRegistry()
        registry.register('gemma-4-31b-it-qat-w4a16-ct',
                          LiteLlm(model='openai/gemma-4-31b-it-qat-w4a16-ct',
                                  api_base='http://127.0.0.1:9/v1', api_key='EMPTY'))
        agent = O.compile_submission(submission_dir=source, tool_registry=O.TOOLS,
                                     model_registry=registry, limits=O.LIMITS,
                                     generation_constraints=O.GEN)
        agents = [agent] + [t.agent for t in agent.tools if getattr(t, 'agent', None) is not None]
        assert len(agents) == 2
        report['candidates'][key] = {}
        for item in agents:
            result = asyncio.run(inspect_agent(item))
            assert result['compiled']['temperature'] == temp
            assert result['client_parameters']['temperature'] == temp
            assert result['compiled']['seed'] == 42
            assert 'seed' not in result['client_parameters']
            report['candidates'][key][item.name] = result
        print('OFFICIAL COMPILE + TRANSPORT CAPTURE OK:', key)
    for name, old in report['candidates']['S'].items():
        new = report['candidates']['S_temp'][name]
        assert old['instruction_sha256'] == new['instruction_sha256']
        for field in ('compiled', 'client_parameters'):
            a, b = dict(old[field]), dict(new[field])
            a.pop('temperature'); b.pop('temperature')
            assert a == b, (name, field)
    report['finding'] = 'Only temperature differs for both coder and analyzer; configured seed is not forwarded at this boundary.'
    (ROOT / 'experiments/temperature_v1/TRANSPORT.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['finding'])


if __name__ == '__main__':
    main()
