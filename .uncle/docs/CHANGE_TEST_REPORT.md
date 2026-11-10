# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 -B scripts/tests/supervisor-test.py | FAIL | Ran 81 tests; 1 failure: SigningAuditTests.test_every_fixture_commit_and_tag_disables_signing, in other test files (tree-attested-final-audit-test.sh, build-attestation-test.py, handoff-export-test.py) not touched here. All new unknown-key, CLI and hosted-notice tests pass. | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6 |
| grep -n 'OPENAI_BASE_URL\\|SEREN_MODEL' README.md docs/supervision.md | PASS | names present in both files | AC-7 |
| bash scripts/run-python-tests.sh -- supervisor | FAIL | Fails only on the signing audit above. | AC-6 |
| bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh (full suites) | DRIVER PENDING | driver runs the full block | AC-6 |
| formatter, type checker, linter, frontend build, migration, rollback, performance, security | N/A | not configured for this repository; sentinel-not-echoed test covers the secret leak risk | None stated |

## Coverage gaps

- Wrapped-run stderr output tested via config_notices, not an end-to-end supervised run
- Signing audit failure assumed pre-existing; not compared against baseline here

## Next action

Driver runs full regression and compares against baseline.
