# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| bash scripts/tests/pr-auto-publish-test.sh | PASS | 22 checks passed | AC-1, AC-2, AC-3, AC-4, AC-6 |
| bash scripts/tests/change-workflow-exit-status-test.sh | PASS | 4 passed | AC-3 |
| bash scripts/tests/pr-verdict-binding-test.sh | PASS | binding checks printed, rc 0 | AC-2 |
| python3 scripts/tests/pr-reconcile-test.py | PASS | OK | AC-5 |
| bash scripts/run-shell-tests.sh && bash scripts/run-python-tests.sh | DRIVER PENDING | Full suites owned by driver | AC-8 |
| formatter / type checker / linter / frontend build / migration / rollback / performance | N/A | Not applicable to this shell change | None stated |
| git diff grep for force push | PASS | no force flags added in code | AC-7 |

## Coverage gaps

- D-2 single-print, AR-015 secret sentinel, AR-011 verdict cases, R-6 closing-keyword body, remote/base selection are untested
- Live scratch-repo PR check not run
- Not verified: tests fail before the change (no revert run)

## Next action

Driver runs full regression block; human reviews diff.
