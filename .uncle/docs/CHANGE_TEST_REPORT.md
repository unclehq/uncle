# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 scripts/tests/runners-none-installed-test.py | PASS | Ran 5 tests, OK | AC-1, AC-2, AC-3 |
| same test with fallback reverted (defect injection, restored after) | PASS | FAILED (failures=3): test detects the original defect | AC-1, AC-2 |
| bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh | DRIVER PENDING | Driver owns the full regression run | AC-4 |
| formatter, type checker, lint, integration, frontend build, migration, rollback, performance, security | N/A | Not applicable to a one-line Python change | None stated |

## Coverage gaps

- Unconfigured self-hosted vs existing configuration guard (plan case 6) not separately verified

## Next action

Driver runs the full regression block.
