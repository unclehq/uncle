# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 scripts/tests/aws-bedrock-protocols-test.py | PASS | Ran 12 tests, OK | AC-3, AC-6, AC-8 |
| python3 scripts/tests/aws-bedrock-test.py | PASS | Ran 70 tests, OK | AC-1, AC-4, AC-5, AC-6, AC-7 |
| python3 scripts/tests/aws-bedrock-configure-test.py | PASS | Ran 15 tests, OK | AC-2, AC-7 |
| bash scripts/tests/aws-bedrock-configure-test.sh | PASS | 0 FAIL lines in output | AC-2 |
| bash scripts/tests/aws-bedrock-dispatch-test.sh | FAIL | 'FAIL baseline unexpectedly accepts aws-bedrock': test diffs against git HEAD stage-config.sh, which already accepts aws-bedrock; file and test unchanged by this change (pre-existing, DRV-1) | AC-9 |
| grep -rniE 'api_compatibility\|COMPAT_CHOICES\|Bedrock URL\|bedrock_native' uncle_tui.py scripts/lib README.md docs/aws-bedrock.md | PASS | Only self_hosted.py:107 legacy-URL error text and one docs sentence | AC-2, AC-8 |
| bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh | DRIVER PENDING | Full suites owned by the driver green-check | AC-9 |
| formatter, type checker, linter, frontend build, migration, rollback, performance, security | N/A | No such tooling configured in this repository | None stated |

## Coverage gaps

- Live Bedrock calls not run (no credentials; manual only)
- Defect-injection against HEAD not run in this stage
- Full-suite comparison versus baseline pending driver

## Next action

Driver runs the full verification commands and compares them with the baseline.
