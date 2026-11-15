# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 -I scripts/tests/oss-test.py | PASS | Ran 28 tests, OK | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10 |
| bash scripts/run-python-tests.sh -- oss | PASS | Python suites: 1 passed, 0 failed | AC-9 |
| python3 -I scripts/tests/no-footprint-test.py | PASS | Ran 14 tests, OK | AC-8 |
| bash -n scripts/change-workflow.sh | PASS | syntax ok | AC-7 |
| bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh (full suites) | DRIVER PENDING | driver owns the full regression block | AC-9 |
| formatter / linter / type checker / frontend build / migration / rollback / performance | N/A | none configured for this shell and Python repository | None stated |

## Coverage gaps

- Gate-stop verified by unit tests and an ordering check, not an end-to-end workflow run.
- Issue claimability needs an issue JSON file at .uncle/workflow/issue.json; absent file lists only plan and format conflicts.
- Title format application covers Conventional Commits only.

## Next action

Driver runs the full regression block and compares against baseline.
