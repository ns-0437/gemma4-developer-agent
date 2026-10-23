"""Prepare the repaired V5 GPU baseline with a raised vLLM startup timeout; never arm or push.

Evidence for the change: two prior successful GPU sessions observed vLLM server startup taking
6.0 min (thinking_v3, 2026-10-07) and 12.1 min (thinking_v2 v2, 2026-10-06) against the shipped
1200s (20 min) ceiling; the 2026-10-22 v5-budget-v2 launch then exhausted that ceiling entirely
(ServerStartupError after 1200s, model weights still loading) before any candidate code ran. This
is upstream of candidate dispatch and identical across adk-submission 0.2.11/0.2.12/0.2.13
(server.py is byte-identical across the extracted 0.2.12 and 0.2.13 sources), so it is not a
consequence of the V5 agent, its budgets, or the compiler/swegemma repair.

Change: raise startup_timeout from 1200s to 1800s (30 min), 2.5x the longest observed successful
startup. No candidate, task, order or budget change. Matched to the launched v5-budget-v2 packet
in every other respect.
"""
import sys
import make_v5_budget_notebook as V5


def main():
    if len(sys.argv) != 1:
        raise SystemExit('Preparation only; no launch options supported')
    V5.OUT_NAME = 'v5_budget_v3'
    V5.NB_FILENAME = 'v5_budget_v3.ipynb'
    V5.OUT_EXP = V5.ROOT / 'experiments/v5_budget_v3/gpu_baseline'
    V5.KERNEL_ID = 'navin03/gemma4-v5-budget-v3'
    V5.STARTUP_TIMEOUT_S = 60 * 30  # 1800s; was 60*20=1200s
    V5.main()


if __name__ == '__main__':
    main()
