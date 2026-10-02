"""Real local ADK argument handling and official compiler; no model/server/network."""
import asyncio
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
if '--host-compiler' in sys.argv:
    sys.path.insert(0, str(ROOT / 'experiments/shellread_v1/compiler_0_2_12/src'))
import official_check as O
from google.adk.tools.function_tool import FunctionTool
from google.adk.models.lite_llm import LiteLlm
import importlib.metadata as md

async def reproduce():
    def read_file(filepath: str, start_line: int | None = None, end_line: int | None = None):
        return {'filepath': filepath, 'start_line': start_line, 'end_line': end_line}
    tool = FunctionTool(read_file)
    assert set(inspect.signature(read_file).parameters) == set(inspect.signature(O.read_file).parameters)
    base = ROOT / 'reference/temperature_run_2026-10-01/pilot/S_temp__rich_3278/traces/trace_rich_3278.json'
    trace = json.loads(base.read_text())
    step = next(s for s in trace['steps'] if s['step_id'] == 6)
    args = step['tool_calls'][0]['arguments']
    bad = await tool.run_async(args=args, tool_context=None)
    good = await tool.run_async(args={'filepath': args['filepath'], 'start_line': 1100, 'end_line': 1357}, tool_context=None)
    assert bad['start_line'] is None and bad['end_line'] is None, bad
    assert good['start_line'] == 1100 and good['end_line'] == 1357
    return {'recorded_step': 6, 'malformed_result': bad, 'correct_result': good}

def compile_one(folder):
    O.validate_directory(folder, O.LIMITS)
    registry = O.ModelRegistry()
    registry.register('gemma-4-31b-it-qat-w4a16-ct', LiteLlm(model='openai/gemma-4-31b-it-qat-w4a16-ct', api_base='http://127.0.0.1:9/v1', api_key='EMPTY'))
    return O.compile_submission(submission_dir=folder, tool_registry=O.TOOLS,
        model_registry=registry, limits=O.LIMITS, generation_constraints=O.GEN)

def main():
    exp = ROOT / 'experiments/shellread_v1'
    source = ROOT / 'experiments/concise_workflow_v1/candidate_S'
    target = exp / 'candidate_S_shellread'
    a, b = compile_one(source), compile_one(target)
    from check_temperature_transport import inspect_agent
    # That helper adds the legacy dependency directory. Restore compiler metadata
    # precedence; the already loaded compiler module remains the host wheel.
    if '--host-compiler' in sys.argv:
        sys.path.insert(0, str(ROOT / 'experiments/shellread_v1/compiler_0_2_12/src'))
        import adk_submission
        assert Path(adk_submission.__file__).resolve().is_relative_to(
            (ROOT / 'experiments/shellread_v1/compiler_0_2_12/src').resolve())
    transport_a = asyncio.run(inspect_agent(a))
    transport_b = asyncio.run(inspect_agent(b))
    assert transport_a['client_parameters'] == transport_b['client_parameters']
    assert transport_a['client_parameters']['extra_body']['chat_template_kwargs']['enable_thinking'] is False
    assert a.generate_content_config == b.generate_content_config
    def names(agent):
        return {getattr(t, 'name', None) or getattr(t, '__name__', None) for t in agent.tools}
    assert names(a) - names(b) == {'read_file'}
    assert names(b) - names(a) == set()
    assert 'read_file' not in b.instruction
    assert 'sed -n' in b.instruction
    files = {p.relative_to(source) for p in source.rglob('*') if p.is_file()}
    assert files == {p.relative_to(target) for p in target.rglob('*') if p.is_file()}
    for rel in files - {Path('agent.yaml'), Path('prompts/system.md')}:
        assert (source / rel).read_bytes() == (target / rel).read_bytes()
    report = {'versions': {k: md.version(k) for k in ['google-adk', 'adk-submission']},
              'reproduction': asyncio.run(reproduce()), 'official_compile': 'passed',
              'generation_config_unchanged': True, 'model_run': False,
              'transport': transport_a['client_parameters'],
              'limitation': 'Local compilation only; no server inference or remote sandbox execution.'}
    if '--host-compiler' in sys.argv:
        assert md.version('adk-submission') == '0.2.12'
        assert transport_a['client_parameters']['seed'] == 42
    (exp / ('HOST_COMPILER_CHECKS.json' if '--host-compiler' in sys.argv else 'LOCAL_CHECKS.json')).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
