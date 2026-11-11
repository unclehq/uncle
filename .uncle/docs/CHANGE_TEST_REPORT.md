# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 scripts/tests/headless-preview-test.py | PASS | Ran 27 tests, OK (after local_env hardening; 3 failures before it were caused by ambient WORKFLOW_PREVIEW_OPEN_BROWSER=0) | AC-1, AC-2, AC-3, AC-4 |
| python3 scripts/tests/headless-preview-open-test.py | PASS | Ran 30 tests, OK | AC-3, AC-4 |
| bash scripts/run-python-tests.sh -- chat-skill | PASS | 1 passed, 0 failed | AC-5 |
| bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh (full suite) | DRIVER PENDING | Run by the driver green-check | AC-6 |
| formatter / type checker / linter / frontend build / migration / rollback / performance / security | N/A | No such tooling in this Python/shell change | None stated |
| baseline and pre-existing failures | NOT RUN | Left to the driver's baseline comparison | AC-6 |

## Coverage gaps

- Hosted live checks MC-100, MC-102, MC-300 require a real hosted environment and were not run.

## Next action

Driver runs the full regression block; a human performs the hosted manual checks.
