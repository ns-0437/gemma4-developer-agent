# Measurement plan toward a public score of 0.15

Target, not guarantee. Baseline observations are v1/v2/v3 = 0.06; identical rounded scores do not establish identical solves. Private score is unknown.

## Immediate gate
1. CPU-only control preflight: reproduce the original patch writer with command output; validate all four baseline/reference pairs with the repaired transport. Preserve frozen v1 and original evidence.
2. If any control fails, diagnose it on CPU. Do not remove failed tasks after seeing candidate outcomes or lower the acceptance rule to obtain a pass.
3. Following CPU success and GPU authorization, run the frozen A/B experiment once. No candidate or budget changes mixed into the repair. Capture the pre-run quota if visible, actual devices, package versions, candidate hashes and command evidence.

## Decision from the comparison
- No inference from missing grades. Gradeable outcomes require clean control, provenance and cleanup evidence.
- Compare paired solved tasks, newly solved versus regressed cases, source edits, repeated tool calls, context failures, and agent-loop time. Four Rich tasks are diagnostic only.
- If both candidates solve the same tasks, keep the incumbent while using traces to choose the next single intervention; do not declare an improvement from prompt length alone.
- If B improves observed outcomes without unexplained grading failures, treat it as a candidate for broader development testing, not a proven leaderboard winner.

## Subsequent experiments, prioritized by observed bottleneck
1. Repeated exploration or test-environment detours: measure tool calls to first successful source edit and repair-cycle cost. Change one workflow rule only if the trace supports it.
2. Context failures: measure prompt/output counts at the failing call and tool-output growth. Test output budget or compaction separately, identically across comparison arms. Notebook compaction is evaluation support, not automatically part of the submitted config.
3. Reasoning failures with clean environment: test thinking with an explicitly compatible context/output budget; previous thinking pilot overflow is not evidence thinking is intrinsically worse.
4. Architecture overhead: compare optional analyzer against a simple coder or bounded second opinion only after identifying delegation cost in traces.
5. LoRA: verify current support and test nonzero adapter effect before any training budget. Do not rely on an old broken-adapter report or claim training is needed without evidence.

## Coverage and publication
Recover or screen additional development tasks from FastAPI and Requests using predeclared selection and real controls; preserve all 12 protected held-out tasks. Never craft prompts from reference solutions. Use the held-out set only after selecting the next candidate. Keep attribution/licenses for any borrowed public material.

Release gate: official compiler, deterministic archive, frozen hash, notebook output downloaded and matched, allowed tools/model/rules rechecked, daily slot verified. No score or rank guarantee and no automatic submission from a validation script.

## Public-source update, 2026-09-29
Downloaded host notebook and Black Cat Pack Instinct for inspection only. Host notebook now uses token_threshold 14336; this does not establish the private grader setting. Pack Instinct contains a challenger with a tool-free optional second opinion, 4096 coder output tokens, and a five-minute budget; no improvement in our environment is established. Existing A/B candidates remain unchanged.
