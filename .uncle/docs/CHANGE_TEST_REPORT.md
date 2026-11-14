# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 scripts/tests/edit-schema-limits-test.py | PASS | 24 tests OK. Defect injection: dropping the relaxed clause from the bounded-writer guard failed 2 tests. | AC-1, AC-2, AC-4, AC-5, AC-6 |
| env -u UNCLE_PLAN_KIND python3 scripts/tests/updated-plan-ops-test.py (and updated-plan-writer-retries, write-once, aws-bedrock, plan-table-cells) | PASS | All OK after two recorded test-shape adaptations. | AC-3 |
| for every scripts/tests/*.py naming worker_schemas, plan_model, self_hosted_http or http_agent | PASS | All OK (run with UNCLE_PLAN_KIND unset). | AC-3 |
| bash scripts/run-python-tests.sh -- edit-schema-limits \| updated-plan-ops \| updated-plan-fast-path | PASS | No failures listed. | AC-1, AC-3 |
| bash scripts/run-shell-tests.sh -- updated-plan-merge-conflict | PASS | No failures listed. | AC-3 |
| bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh (full suite) | DRIVER PENDING | Run by the driver after this stage. | AC-3 |
| baseline result | DRIVER PENDING | Compared by the driver against BASELINE_REPORT. | AC-3 |
| formatting / type checker / lint / frontend build / migration / rollback / performance / security | N/A | No such tooling for these Python/shell scripts; nothing persisted changes. | None stated |
| integration tests (hosted rerun against a real server) | NOT RUN | Needs a live relaxed-schema server; not available here. | AC-4 |

## Coverage gaps

- No live server returned x-seren-schema-relaxed; the header path is covered through a stubbed transport.
- Suites must run with UNCLE_PLAN_KIND unset.

## Next action

Driver runs the full verification block and compares against baseline.
