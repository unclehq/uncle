# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| baseline (BASELINE_REPORT.json) | N/A | Pre-change baseline owned by the driver. | AC-9 |
| python3 scripts/tests/check-record-test.py | PASS | Ran 22 tests, OK | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7 |
| bash scripts/tests/green-check-test.sh | PASS | 45 checks passed (new assertion: green-check.json entries 1:1 2:0 3:7 trusted) | AC-1, AC-5 |
| python3 scripts/tests/build-attestation-test.py | PASS | Ran 9 tests, OK | AC-2, AC-4 |
| bash scripts/tests/tree-attested-final-audit-test.sh | PASS | exit 0 | AC-8 |
| bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh | DRIVER PENDING | Full suites run by the driver. | AC-9 |
| formatter | N/A | No formatter configured for scripts. | None stated |
| type checker / lint | N/A | None configured. | None stated |
| integration, frontend build, migration, rollback, performance | N/A | Not applicable to this change (additive scripts). | None stated |
| security check: allow-list canary | PASS | check-record-test.py canary tests OK | AC-6 |

## Coverage gaps

- Hosted manual checks MC-100, MC-102, MC-300 are BLOCKED-HUMAN and unrelated to this change.
- green_run does not pass an isolated-copy snapshot to assemble (AC-3 unit-tested only).
- No assertion on the RERUN_RESULT.json prompt text in stagegate.sh.
- Parallel-path record emission is covered by check-record-test.py, not by an end-to-end green_run parallel test.

## Next action

Driver runs the full regression block and human diff review.
