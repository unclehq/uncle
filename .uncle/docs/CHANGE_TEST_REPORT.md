# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| bash scripts/run-python-tests.sh -- revalidate | PASS | PASS scripts/tests/revalidate-test.py (1 passed, 0 failed) | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8 |
| python3 scripts/tests/revalidate-integration-test.py | PASS | Ran 5 tests, OK (real change-workflow.sh resume, stub claude/codex; before fixture fix 3 failed on inherited env/no-commit fixture) | AC-4, AC-5, AC-9, AC-10 |
| baseline / regression: bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh | DRIVER PENDING | Driver owns full regression block; prior green-check recorded only PREEXISTING failures. | AC-10 |
| formatter / type checker / lint / frontend build / migration / rollback / performance / security | N/A | No such tooling configured for this shell/python repo. | None stated |

## Coverage gaps

- Default-runner resume through a real model stage (MC-104) not exercised; needs sandbox with real agent.
- Possible exit-75 to 'failed' mapping in default_runner unconfirmed.
- Integration drives real driver only at PLAN/WAIT_PLAN_APPROVAL states.

## Next action

Driver runs full shell and python runners and compares against baseline.
