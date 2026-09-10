## baseline result

| ID | Command and result |
|---|---|
| CT-1 | `bash -o pipefail -c 'bash scripts/tests/close-flow-test.sh 2>&1 &#124; tail -12'` — PASS, exit 0; 231 checks, 28 Python tests, 6 output lines. |
| CT-2 | `PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/pr-prompt-test.py -q` — PASS, exit 0; 5 tests, 4 output lines. |
| CT-3 | `bash -n scripts/change-workflow.sh scripts/from-issue.sh scripts/lib/change-pr.sh scripts/lib/issue-close.sh` — PASS, exit 0; 0 output lines. |
| CT-4 | `bash -o pipefail -c 'bash scripts/tests/tui-session-panel-test.sh 2>&1 &#124; tail -8'` — PASS, exit 0; 14 tests, 5 output lines. |

## targeted tests

| ID | Command and result |
|---|---|
| CT-5 | NOT RUN (post-change T-1/T-2; `CHANGE_PLAN.md` STOP-1 prevents implementation; baseline runs CT-1/2). |

## regression tests

| ID | Command and result |
|---|---|
| CT-6 | NOT RUN (new P-19 and framing regressions; S-1 blocked by R-2). |

## full test suite

| ID | Command and result |
|---|---|
| CT-7 | NOT RUN (S-3 blocked by STOP-1; only BASELINE_REPORT.md §8 commands executed). |

## formatting

| ID | Command and result |
|---|---|
| CT-8 | `git diff --check` — PASS, exit 0; 0 output lines. |

## compiler or type checker

| ID | Command and result |
|---|---|
| CT-9 | NOT RUN (broader compiler/type checks; no implementation; baseline shell syntax covered by CT-3). |

## linting

| ID | Command and result |
|---|---|
| CT-10 | NOT RUN (S-3 blocked; no source edits). |

## integration tests

| ID | Command and result |
|---|---|
| CT-11 | NOT RUN (live M-2 comment/closure evidence requires R-2 resolution and a disposable GitHub PR). |

## frontend build

| ID | Command and result |
|---|---|
| CT-12 | N/A (Bash/Python TUI; BASELINE_REPORT.md §2). |

## migration tests

| ID | Command and result |
|---|---|
| CT-13 | N/A (CHANGE_PLAN.md P-16 specifies no migration). |

## rollback test

| ID | Command and result |
|---|---|
| CT-14 | N/A (STOP-1 prevented source changes or publication to roll back). |

## performance checks

| ID | Command and result |
|---|---|
| CT-15 | NOT RUN (S-3 blocked; no changed runtime behavior). |

## security checks

| ID | Command and result |
|---|---|
| CT-16 | NOT RUN (new P-19 source-binding regressions blocked at S-1). |

## newly introduced warnings

| ID | Command and result |
|---|---|
| CT-17 | N/A (no implementation; no warnings in CT-1–4 output). |

## pre-existing failures

| ID | Command and result |
|---|---|
| CT-18 | N/A (CT-1–4 passed; no pre-existing failures observed in these commands). |

## untested areas

| ID | Command and result |
|---|---|
| CT-19 | NOT RUN (PRE-2 and M-1–3; resolve R-2 then execute CHANGE_PLAN.md S-1–3 to settle assumptions and acceptance). |
| CT-20 | `git diff --binary -- . ':!IMPLEMENTATION_NOTES.md' ':!CHANGE_TEST_REPORT.md' &#124; shasum -a 256` — PASS, exit 0; 1 output line; matches starting digest in IMPLEMENTATION_NOTES.md U-6. |
