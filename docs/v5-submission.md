# V5: bounded-runtime resubmission

Prepared 2026-10-19 after a fresh full-API status read confirmed V4 reference 57064155 exceeded runtime and received no score. Evidence: reference/submission_status_2026-10-19.

V5 preserves all five V4 agent files byte-for-byte. The sole added file is eval_config.yaml, using the official sample's evaluation section and four supported fields: max_time_minutes 5, max_turns 60, max_tool_calls 100, timeout_seconds 60.

Validation: local package validator and official compiler passed; saved swegemma EvalConfig instantiated with inert paths and an empty model map confirmed all four budget mappings. This does not execute the private scorer or prove its current implementation. The packaging notebook embeds the exact validated ZIP, uses CPU only and runs no agent.

Confirmed failure: global runtime exhaustion. Correctable risk: V4 supplied no explicit per-task budget despite known long/repetitive development trajectories. The private failed-task traces are unavailable, so this is mitigation rather than a proven reconstruction of the entire failure.

Tradeoff: five minutes may cut off the previously observed roughly ten-minute Rich solve. This release is intended to obtain a completed evaluation within bounded per-task work, not a claim of improved task quality. A hypothetical 120-task workload gives 600 agent minutes, leaving 120 minutes within a 720-minute scenario for overhead; actual hidden count, setup costs and cap enforcement are not verified by that arithmetic.

No prompts, sampling, thinking budget, protected tasks or frozen previous releases changed. The user explicitly requested correction and resubmission. The receipt and exact package hash are in releases/v5_submission_record.json.
