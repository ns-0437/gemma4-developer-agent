# Staged workflow: offline feasibility result

Tested 2026-10-03. **Normal stage advancement works; guaranteed advancement when a stage loops does not. Do not launch this prototype as a proven loop fix.**

## What was built

An official-compiler-compatible YAML `SequentialAgent` with three stages:

| Stage | Exposed tools | Purpose |
|---|---|---|
| planner | read_file | Inspect source and hand over a plan |
| coder | read_file, edit_file, run_command | Make a patch and expose its actual Git diff |
| reviewer | read_file, get_status, submit_patch | Independently read source and review the patch; cannot edit or run commands |

Sampling is copied byte-for-byte from S_shellread. This is a synthetic feasibility prototype, not a measured candidate or a proposed competition submission. No task-specific solution or held-out task was used.

## Execution boundary

Tests execute the **real compiler 0.2.12, ADK 1.36.1 Runner, SequentialAgent/LoopAgent, session history, function routing, tool schema construction and max_llm_calls enforcement**. They intercept each compiled model's LiteLLM client, returning scripted responses. Those responses are not Gemma output and prove no model competence or instruction following.

Tool implementations are explicit offline fixtures with the official signatures, operating on a temporary synthetic repository. They perform a real file edit and actual Git diff. They are not the production sandbox implementations. The fixture command tool accepts only two fixed commands. TCP connections are blocked during the execution tests; no server, GPU, Kaggle request or competition submission is used. Local LiteLLM is 1.102.1; the earlier run recorded 1.82.4, so no wire/server equivalence is claimed.

Initial test-code defects were corrected before recording the passing results: LiteLLMClient is not a Pydantic model, and the compiler clones registered model instances. Capture is now attached to each compiled model's transport; no agent flow, callback, tool list or stage transition is patched by the test.

## Results

**11 executed scenarios passed their assertions; three additional schema rejection checks passed.** Passing a test that demonstrates starvation is evidence of a limitation, not successful recovery.

| Scenario | Observed result |
|---|---|
| Normal handoff | planner -> coder -> reviewer, eight model-client calls total |
| Reviewer evidence | First reviewer request includes original issue, plan and real Git diff; reviewer independently reads changed file |
| Planner requests run_command | Tool absent from planner schema; real dispatcher raises ValueError; implementation never executes |
| Coder requests submit_patch | Tool absent; rejected without a submission |
| Reviewer requests edit_file | Tool absent; rejected without executing a second edit; coder's earlier edit remains |
| Planner repeats read_file | Global eight-call cap stops the invocation; coder and reviewer never run |
| Coder repeats empty search | Global eight-call cap stops the invocation; reviewer never runs |
| Coder repeats at actual budget | Planner uses two calls, coder uses 58, shared 60-call cap stops invocation; reviewer never runs |
| LoopAgent(max_iterations=1) wrapper | Still starves inside coder; outer iteration limit does not cap its internal calls |
| Reviewer rejects | Returns REJECT and does not submit; the real working-tree diff remains |
| No patch | Reviewer receives no actual diff and scripted response rejects; no submission |
| Reviewer include_contents=none | Reviewer loses previous diff/history; test detects missing patch evidence |

The three proposed coder fields `max_llm_calls`, `max_turns` and `run_config: {max_llm_calls: 3}` are rejected as extra fields by the official schema. They are not supported ways to reserve a reviewer budget.

The happy-path reviewer acceptance and negative-path rejection are **scripted fixtures**. We have proved that the inputs can be delivered, not that Gemma will judge them correctly or refuse inadequate evidence.

## Rejection is advisory, not a grading gate

The executed rejection fixture leaves an unsubmitted diff. Separately, inspected `reference/harness_src/src_swegemma/swegemma/harness/agent_runner.py` captures a non-empty working-tree diff when no patch was explicitly submitted (fallback near lines 758-779). That source evidence means a text-only reviewer rejection cannot be represented as suppressing grading. No full harness/grader was executed in this proof.

The read-only reviewer cannot repair or revert a rejected patch. Giving it edit or command tools would change that design and reintroduce looping/mutation risks. Merely appending more stages does not solve starvation in an earlier stage.

## Decision and remaining requirement

**Feasibility is partial:** allowed tool subsets and ordinary handoff are real; a forced transition and hard reviewer gate are not established. No GPU experiment or promotion is justified as a fix for the observed 50-call loops on this evidence.

Before further compute, any replacement design must demonstrate within the accepted artifact/compiler/harness path that:

1. Repeated allowed calls in an earlier stage cannot consume the reviewer's reserved budget.
2. The reviewer receives the actual current patch, not just a summary.
3. A rejection has an explicitly defined effect on the final diff and fallback behavior.

The current supported fields tested here do not supply item 1. This report does not claim exhaustive impossibility of every allowed architecture. A notebook-only custom callback would alter the evaluation setup, and must not be described as a deployable submission fix.

## Reproduce and evidence

Run with the Windows Python interpreter used for the existing compiler checks:

```powershell
python scripts/prepare_staged_workflow.py
python scripts/test_staged_workflow.py
```

- `prototype/`: YAML, instructions and sampling configuration.
- `PROTOTYPE_SHA256.json`: exact prototype identity.
- `CHECKS.json`: versions, all scenario results and schema rejection details.
- `offline_evidence/*.json`: captured client requests, real ADK events and fixture tool calls for each case.
- `EVIDENCE_SHA256.json`: report/test/source evidence identities.

Existing candidates, launched notebooks, protected holdout and downloaded raw experiment artifacts are unchanged.
