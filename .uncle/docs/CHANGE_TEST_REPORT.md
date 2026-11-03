# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| bash scripts/tests/change-request-exists-prompt-test.sh | PASS | 104 ok, 0 FAIL, exit 0 | AC-1, AC-2, AC-3, AC-4, AC-5 |
| bash scripts/tests/issue-document-test.sh | PASS | exit 0, 0 FAIL | AC-3 |
| bash scripts/tests/worktree-auto-seed-test.sh | PASS | exit 0, 0 FAIL | AC-5 |
| bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh | DRIVER PENDING | Driver owns the full regression block. | AC-6 |
| bash -n scripts/from-issue.sh | PASS | syntax ok | AC-1 |
| formatter, lint, frontend build, migration, rollback, performance, security | N/A | No such tooling for shell scripts in this repo. | None stated |

## Coverage gaps

- Live attended run of the prompt outside the pty fixture not performed.
- Test needed UNCLE_* env scrubbing because driver-run builds export UNCLE_UNATTENDED=1.

## Next action

Driver runs the full regression block.
