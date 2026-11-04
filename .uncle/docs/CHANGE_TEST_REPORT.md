# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| bash scripts/tests/launcher-stdin-text-test.sh (UNCLE_RUNTIME_ROOT unset) | PASS | all launcher stdin text checks passed; before the trap typo fix 32-85 checks failed | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-11 |
| python3 scripts/tests/startup-action-test.py | PASS | Ran 13 tests, OK | AC-10 |
| python3 scripts/tests/housekeeping-input-test.py | PASS | Ran 8 tests, OK | AC-4, AC-7 |
| bash scripts/tests/launcher-args-test.sh; bash scripts/tests/housekeeping-launcher-test.sh; bash scripts/tests/housekeeping-workflow-test.sh; python3 scripts/tests/housekeeping-policy-test.py; python3 scripts/tests/tui-housekeeping-test.py | PASS | launcher-args all passed; housekeeping-launcher no non-PASS lines; workflow all passed; policy exit 0; tui-housekeeping 6 OK | AC-5, AC-8 |
| bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh | DRIVER PENDING | Full suite owned by the driver green-check | None stated |
| formatter, type checker, linter, frontend build, migration, rollback, performance | N/A | none configured or applicable to this change | None stated |
| bash -n uncle | PASS | syntax ok | None stated |

## Coverage gaps

- No live attended TUI observation
- Tests must run with UNCLE_RUNTIME_ROOT unset; when inherited it points at the installed launcher
- Full suite not run here (driver pending)

## Next action

Driver runs the full regression block and the human reviews the diff.
