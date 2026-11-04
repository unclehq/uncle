# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 scripts/tests/bug-report-test.py | PASS | Ran 21 tests, OK (was 7 failures, 6 errors before fix) | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8 |
| bash scripts/run-shell-tests.sh | DRIVER PENDING | Full suite owned by driver | AC-8 |
| bash scripts/run-python-tests.sh | DRIVER PENDING | Started once; output truncated, result not observed here. Driver authoritative. | AC-8 |
| formatter / type checker / linter | N/A | None configured for this change | None stated |
| integration, frontend build, migration, rollback, performance | N/A | Not applicable to this change | None stated |
| security check: scrub/residual tests in bug-report-test.py | PASS | Included in the 21 passing tests | AC-4 |

## Coverage gaps

- Real gh and GitHub not exercised
- No defect-injection run

## Next action

Driver runs the full regression block.
