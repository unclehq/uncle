# Implementation notes

## Step 1

### Files changed

- `scripts/lib/reviewer-prompt.sh` — Add reviewer_prompt_kind helper and document it in the header comment; Step 1 (D1/D2/D3); AC-1: positional allowlist match prints file/argv; zero/empty args print argv

### Unresolved concerns

- Call sites, tests, CI not yet changed (later steps).

## Step 2

### Files changed

- `scripts/stagegate.sh` — run_codex_review computes prompt_kind via reviewer_prompt_kind, keeping the python3-first clause OR'd (D1); local prompt_kind=argv and race marker text preserved; Step 2 (D1, D3); AC-2; B1 preserved; set -u safe empty client_cmd

### Unresolved concerns

- AC-2 change-workflow side, AC-3..AC-7 tests/CI are later steps.

## Step 3

### Files changed

- `scripts/change-workflow.sh` — Replaced the two prompt_kind case patterns with reviewer_prompt_kind (helper alone, D2); source line and wait "$!" markers kept; Step 3 (D2, D3); AC-2; set -u safe empty client_cmd

### Unresolved concerns

- Wrapper launch tests (AC-3..AC-5), CI and suite registration are later steps.

## Step 4

### Files changed

- `scripts/tests/reviewer-prompt-kind-test.py` — New suite: helper table incl. python3-first divergence row, driver wiring grep, empty client_cmd under set -u, real wrapper launch with 200000-byte prompt through both drivers' extracted launch lines, offline hosted resolution (fails if wrapper unresolved), wrapper-elsewhere negative, guard boundary 120000/120001; Step 4; AC-1..AC-6

### Deviations

- `scripts/tests/reviewer-prompt-kind-test.py`: Driver launch blocks are tested by extracting the prompt_kind lines from stagegate.sh/change-workflow.sh and executing them in bash with the real wrapper, not by running the full drivers. Pre-change run (drivers temporarily reverted via stash, restored) gave 4 errors (no helper call line found) and 1 assertion failure; output summary in .uncle/workflow/kind-test-pre.txt. Tests 2-4 failed by StopIteration error rather than assertion on the unmodified tree.

### Unresolved concerns

- AC-7 (CI/critical-suites registration) is step 5.

## Step 5

### Files changed

- `scripts/tests/critical-suites.txt` — Register reviewer-prompt-kind in the critical tier after reviewer-prompt-file; 5; AC-7
- `.github/workflows/linux-tests.yml` — Add a step running the reviewer-prompt-kind suite; 5; AC-7

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | IMPLEMENTED | helper table test | python3 scripts/tests/reviewer-prompt-kind-test.py: 9 tests OK |
| AC-2 | IMPLEMENTED | CallSites grep test | same run OK; failed before steps 2-3 |
| AC-3 | IMPLEMENTED | WrapperLaunch.test_stagegate_block | OK |
| AC-4 | IMPLEMENTED | WrapperLaunch.test_changeworkflow_block | OK |
| AC-5 | IMPLEMENTED | Hosted test | OK |
| AC-6 | IMPLEMENTED | GuardBoundary test | OK |
| AC-7 | IMPLEMENTED | critical-suites.txt lists reviewer-prompt-kind; linux-tests.yml has a step running it | bash scripts/run-python-tests.sh -- reviewer-prompt-kind: OK, 1 passed, 0 failed |
