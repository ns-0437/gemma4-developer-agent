# Runtime planning before another submission

V4's saved API response reports a runtime-limit failure, not a numerical score. See [the frozen-package audit](../reference/v4_runtime_audit/README.md). Do not derive execution duration from queue time or account-level GPU usage.

## Offline commands

Inspect an archive without extracting it or inferring absent defaults:

```powershell
python -B scripts/inspect_eval_config.py releases/v4_thinking_on_submission.zip
```

Calculate an explicit hypothetical serial budget:

```powershell
python -B scripts/runtime_budget.py --tasks 120 --per-task-minutes 5 --setup-seconds 30 --startup-minutes 10 --reserve-minutes 40 --total-minutes 720
```

The CLI returns 0 when the scenario fits, 1 when it exceeds the budget, and 2 for invalid arguments. It prints JSON and writes no files. Counts and costs must be supplied as assumptions or separately measured inputs. A fitting scenario is not evidence that the grader enforces the proposed limits or that the hidden workload fits.

## Evidence required for a candidate

1. Establish the supported configuration route and inspect the compiled effective limits. A missing archive config alone proves neither a default nor a defect.
2. Measure startup, setup and agent execution separately; document how grading time is treated by the competition budget.
3. Keep solves, graded failures, ungraded outcomes and runtime distinct. Use realistic reserve and record uncertainty in task count and tail latency.
4. Confirm termination behavior, including slow tool calls, before relying on a per-task cap. Arithmetic cannot verify enforcement.
5. Compare a frozen candidate with the incumbent before deciding on submission; runtime changes can reduce solve quality.

The offline CI runner exercises input validation, CLI exit behavior and archive ambiguity checks. It does not contact Kaggle, launch models or certify score improvement.
