"""Candidate S: candidate A (= releases/v3, the scored 0.06 agent) with a CONCISE coder prompt.

Derived from A, NOT from R. Only `prompts/system.md` changes. YAML, sampling, model, analyzer prompt,
sub-agent config and budgets are untouched.

This is a prompt-PACKAGE experiment. It does not assert that prompt length caused the repetition loop;
that remains an untested hypothesis. The Stage-1 run showed the anti-repetition instructions were
present and retained in context and still not followed, so S tests whether a shorter workflow is
followed more reliably. Generic instructions only: no rich_3278 details, no gold data, no task hints.

Preserved from A because they are environment facts the agent cannot discover cheaply:
  * scratch files go in /tmp and the write tools refuse /tmp, so a heredoc is required
  * test files are reset before grading, so only source changes count
  * pytest's exit code must be preserved rather than masked by a pipe
  * exit code 5 means nothing was collected, and a skipped test is not a pass
  * `rg` and `tree` are unavailable
"""
import filecmp, hashlib, io, shutil, sys, difflib
from pathlib import Path

ROOT = Path(r'C:\Documents2\KaggleMLChallenge\The Gemma 4')
SRC = ROOT / 'experiments' / 'ab_v3_vs_short' / 'candidate_A'
EXP = ROOT / 'experiments' / 'concise_workflow_v1'
DST = EXP / 'candidate_S'

SYSTEM_MD = """You are an autonomous senior Python engineer resolving one issue in the repository at /workspace. Work with your tools until the issue is fixed, then call `submit_patch`.

Hidden tests run against your changes in a fresh checkout. They pass only if the code behaves as the issue asks, including the exact names, parameters, messages, types and status codes it mentions. **Test files are reset before grading, so change source code only, never tests, `pytest.ini` or `conftest.py`.**

## Workflow
1. **Understand.** Say in one or two sentences what the issue expects and what happens instead. Some issues are pull-request descriptions: skip the template text.
2. **Localize.** `git grep -n -F -- "<identifier from the issue>" -- '*.py' | head -30`, then read the matching ranges with `read_file`.
3. **Reproduce once.** Write one assertion-based script and run it. One reproduction is enough: once it fails the way the issue describes, stop reproducing and start fixing.
4. **Edit the source.** Use `edit_file` with a short unique `old_string` copied exactly from the file. One logical change per edit.
5. **Verify.** `python3 -m py_compile <file>`, then run the targeted test file, then re-run your reproduction.
6. **Submit.** Check `git diff --name-only`. Restore any test path you touched with `git checkout -- <path>`. Then call `submit_patch`.

## Environment
- Offline; dependencies are installed. Never `pip install`. Available: git, grep, find, sed, awk, python3. **Not available: rg, tree.**
- Output is cut at 5,000 characters and `read_file` returns at most 150 lines. Read focused ranges; pipe long output through `head`.
- **Scratch files go in /tmp, and `write_file`/`edit_file` cannot write there.** Use a heredoc:
  `cat > /tmp/repro.py <<'EOF'` ... `EOF`. Never leave a scratch file in /workspace: it becomes part of your patch.
- Confirm you are testing the checkout before trusting a result: `cd /workspace && python3 -c "import <pkg>; print(<pkg>.__file__)"` must print a path under /workspace.
- Keep pytest's exit code: `python3 -m pytest <file> -q -x > /tmp/out.txt 2>&1; echo "EXIT=$?"; tail -40 /tmp/out.txt`. **Exit 5 means no tests were collected, not success, and a skipped test does not verify anything.**

## Budget
You have a limited number of turns. Spend them in the order above: most of them on steps 4 and 5, not on steps 2 and 3. If you have not started editing source by roughly the halfway point, edit your best current hypothesis and verify it. A verified partial fix beats an unsubmitted investigation.

Keep your reasoning short and act through tool calls.
"""


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main() -> int:
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    sysmd = DST / 'prompts' / 'system.md'
    io.open(sysmd, 'w', encoding='utf-8', newline='').write(SYSTEM_MD)

    diffs = [p.relative_to(SRC).as_posix() for p in sorted(SRC.rglob('*')) if p.is_file()
             and (not (DST / p.relative_to(SRC)).exists()
                  or not filecmp.cmp(p, DST / p.relative_to(SRC), shallow=False))]
    extra = [p.relative_to(DST).as_posix() for p in DST.rglob('*')
             if p.is_file() and not (SRC / p.relative_to(DST)).exists()]
    print('files differing from A:', diffs)
    print('files only in S       :', extra)
    if diffs != ['prompts/system.md'] or extra:
        print('UNEXPECTED difference set')
        return 1

    base = io.open(SRC / 'prompts' / 'system.md', encoding='utf-8').read()
    print(f"\nwords: A={len(base.split())}  S={len(SYSTEM_MD.split())}"
          f"  ({len(SYSTEM_MD.split()) - len(base.split()):+d})")
    print(f"chars: A={len(base)}  S={len(SYSTEM_MD)}")
    print(f"system.md sha256 A = {sha(SRC / 'prompts' / 'system.md')}")
    print(f"system.md sha256 S = {sha(sysmd)}")

    EXP.mkdir(parents=True, exist_ok=True)
    io.open(EXP / 'system_md.diff', 'w', encoding='utf-8', newline='\n').writelines(
        difflib.unified_diff(base.splitlines(True), SYSTEM_MD.splitlines(True),
                             fromfile='a/candidate_A/prompts/system.md',
                             tofile='b/candidate_S/prompts/system.md', n=2))
    print('wrote system_md.diff')

    # No task leakage, and the environment facts that matter are still present.
    flat = ' '.join(SYSTEM_MD.split())
    leak = [t for t in ('rich_3278', 'rich/ansi', 're_ansi', 'x1b7', 'private escape',
                        'Textualize', 'FAIL_TO_PASS', 'gold') if t.lower() in flat.lower()]
    checks = {
        'no task or gold leakage': not leak,
        'tests are reset, source only': 'reset before grading' in flat,
        '/tmp heredoc constraint kept': "cat > /tmp/repro.py <<'EOF'" in flat,
        'write tools cannot reach /tmp': 'cannot write there' in flat,
        'rg and tree unavailable': 'Not available: rg, tree' in flat,
        'pytest exit code preserved': 'EXIT=$?' in flat,
        'exit 5 is not success': 'Exit 5 means no tests were collected' in flat,
        'checkout import check kept': 'must print a path under /workspace' in flat,
        'safe editing: unique old_string': 'short unique `old_string`' in flat,
        'test paths restored before submit': 'git checkout -- <path>' in flat,
        'submit_patch is named': 'submit_patch' in flat,
        'shorter than A': len(SYSTEM_MD.split()) < len(base.split()),
    }
    print()
    for k, v in checks.items():
        print(('  OK   ' if v else '  MISS ') + k + ('' if v else f'   {leak}'))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
