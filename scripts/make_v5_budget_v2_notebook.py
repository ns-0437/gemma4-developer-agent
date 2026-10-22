"""Prepare the repaired V5 GPU baseline in fresh directories; never arm or push."""
import sys
import make_v5_budget_notebook as V5


def main():
    if len(sys.argv) != 1:
        raise SystemExit('Preparation only; no launch options supported')
    V5.OUT_NAME = 'v5_budget_v2'
    V5.NB_FILENAME = 'v5_budget_v2.ipynb'
    V5.OUT_EXP = V5.ROOT / 'experiments/v5_budget_v2/gpu_baseline'
    V5.KERNEL_ID = 'navin03/gemma4-v5-budget-v2'
    V5.main()


if __name__ == '__main__': main()
