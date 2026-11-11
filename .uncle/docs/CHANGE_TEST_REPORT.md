# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| baseline (BASELINE_REPORT.md commands) | DRIVER PENDING | Driver re-runs the baseline list. | AC-6 |
| bash scripts/run-shell-tests.sh -- pr-closes-refs | PASS | 60 checks passed; 1 suite passed | AC-1, AC-2, AC-3 |
| python3 scripts/tests/attestation-test.py | PASS | Ran 39 tests, OK | AC-4 |
| bash scripts/run-shell-tests.sh -- pr-auto-publish | PASS | 1 suite passed | AC-3, AC-6 |
| full suite: bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh | DRIVER PENDING | Driver-owned regression block. | AC-6 |
| formatting | N/A | No formatter configured for shell/Python scripts. | None stated |
| bash -n scripts/lib/change-pr.sh | PASS | syntax ok | AC-1 |
| linting | N/A | No linter configured. | None stated |
| integration tests | N/A | Covered by pr-auto-publish suite above. | None stated |
| frontend build | N/A | No frontend. | None stated |
| migration tests | N/A | No migration. | None stated |
| rollback test | N/A | Revert the commit; no data migration. | None stated |
| performance checks | N/A | None applicable. | None stated |
| security checks | PASS | Injection fixture in pr-closes-refs (Fixes/Closes text and newlines never reach the body) is part of the 60 checks. | AC-2 |
| grep -n Refs scripts/README.md | PASS | README line 409 documents Closes vs Refs. | AC-5 |

## Coverage gaps

- Suite drives the extracted closing_trailer helper, not the full publish flow.
- Real FINAL_AUDIT.md Verdict line format unverified against a live audit.
- Pre-existing failures: none observed in targeted runs; full suites not run here.

## Next action

Driver runs the full regression block; human confirms a READY audit still yields Closes.
