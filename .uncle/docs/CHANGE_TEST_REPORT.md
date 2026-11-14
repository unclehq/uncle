# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| bash scripts/run-python-tests.sh -- updated-plan-ops (env -u UNCLE_PLAN_KIND) | PASS | exit 0; 44 tests | AC-2, AC-3, AC-4 |
| bash scripts/run-python-tests.sh -- updated-plan-fast-path (env -u UNCLE_PLAN_KIND) | PASS | exit 0; 8 tests; failed on `bash -e` before the fix | AC-1, AC-2 |
| bash scripts/run-python-tests.sh -- plan-context-protected (env -u UNCLE_PLAN_KIND) | PASS | exit 0 | AC-5 |
| bash scripts/run-shell-tests.sh -- updated-plan-merge-conflict | PASS | exit 0 | AC-6 |
| bash scripts/run-python-tests.sh -- updated-plan-writer-retries (regression) | PASS | exit 0 | AC-7 |
| bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh (full suite) | DRIVER PENDING | Run by the driver after this stage. | AC-7 |
| baseline result | DRIVER PENDING | Compared by the driver against BASELINE_REPORT. | AC-7 |
| formatting / type checker / lint / frontend build / migration / rollback / performance / security | N/A | No such tooling for these shell/Python scripts; no persisted format changed. | None stated |
| integration tests | NOT RUN | Optional hosted rerun with scripts/check-*.sh plans not performed (LIVE_VERIFICATION). | AC-3 |

## Coverage gaps

- Hosted end-to-end rerun not performed.
- Suites must run with UNCLE_PLAN_KIND unset; in a change-plan stage environment ops tests fail for unrelated environmental reasons.
- No newly introduced warnings observed; pre-existing failures: none observed in targeted suites.

## Next action

Driver runs the full verification block and compares against baseline.
