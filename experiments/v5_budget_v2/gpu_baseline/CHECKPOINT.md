# Repaired V5 GPU baseline: prepared, not launched

CPU replay passed both runtime identities and all eight fresh control arms.
Evidence: `reference/v5_control_replay_v2_2026-10-22T16-01-44Z/review/REPORT.md`.
Raw outputs were hashed before analysis and rechecked afterwards: 27 unchanged files.
Remote basename inventory matched 26 entries plus the log; remote byte completeness
is unverified because the listing's sizes do not match the downloaded files.

New packet: `notebooks/v5_budget_v2/v5_budget_v2.ipynb`.
SHA-256: `70f9d5d98baa44ae77396013cc036bbec6a6a3599f43a9cd55a54dee1bc10989`.
Metadata SHA-256: `454a39b7a8716140a38ff54181b435e8d9521dd78ca6e83c22f3797a79dad9d1`.
Kernel id: `navin03/gemma4-v5-budget-v2`. DISPATCH_CONFIRM remains False.

Exactly the candidate-validation cell differs from the preserved original disabled
baseline. Candidate, tasks, order, budget and other runtime cells remain unchanged.
Four tasks: rich_3278, rich_3535, rich_3675, rich_3942; V5 only.
Limits: five minutes, 60 turns, 100 tools, 60-second command timeout.

Focused simulated lifecycle checks pass: disabled produces zero servers/evaluations;
enabled produces four evaluations in the declared order, one server started and
stopped, and all eight controls accepted with cleanup. No real model was invoked.
The runtime compiler and swegemma gates use the identities proven by the CPU replay.
A passing CPU replay does not establish GPU/vLLM operation or private-grader parity.

Next decision: one separately authorized GPU launch. No GPU launch or submission
was performed while checking this CPU replay. Original launch receipts, raw evidence,
frozen candidate, task freeze, and failed notebook remain unchanged.
