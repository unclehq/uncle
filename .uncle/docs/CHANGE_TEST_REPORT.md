# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| bash scripts/tests/run-policy-test.sh | PASS | 72 checks, 0 failed (was 13 failed before fixes to marker bypass, opt-out notice, ROOT fallback, git switch -c) | AC-1, AC-2, AC-3, AC-4, AC-5, AC-8, AC-9 |
| python3 scripts/tests/run-policy-test.py | PASS | Ran 9 tests, OK (was 1 failure for create_app/run_app/stagegate.sh kinds) | AC-3, AC-7 |
| baseline result | N/A | Baseline recorded in BASELINE_REPORT.md; driver re-runs it | AC-6 |
| regression tests | DRIVER PENDING | Driver green-check runs both suites | AC-6 |
| bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh | DRIVER PENDING | Full suite owned by the driver | AC-6 |
| formatter / type checker / linter | N/A | No configured formatter, type checker or linter for these scripts | None stated |
| integration, frontend build, migration, rollback, performance, security | N/A | Not applicable to this change | None stated |

## Coverage gaps

- Full suites not run in this stage (driver-owned)
- Real launcher end-to-end (uncle, TUI) not exercised; covered by unit tests only
- No pre-existing failures observed in targeted runs

## Next action

Driver runs green-check; human reviews diff.
