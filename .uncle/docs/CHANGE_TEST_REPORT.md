# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| bash scripts/tests/mode-resolution-test.sh | PASS | 87 checks passed | AC-3, AC-4, AC-5, AC-6, AC-8 |
| bash scripts/tests/mode-launcher-test.sh; bash scripts/tests/launcher-args-test.sh; bash scripts/tests/housekeeping-launcher-test.sh; bash scripts/tests/launcher-stdin-text-test.sh (UNCLE_LIB_DIR, UNCLE_RUNTIME_ROOT, UNCLE_TIMING_HELPER unset) | PASS | all exit 0 | AC-1, AC-2, AC-3, AC-4, AC-11 |
| python3 scripts/tests/mode-pty-test.py | PASS | exit 0; startup honors UNCLE_STARTUP_ATTENDED | AC-2, AC-3 |
| bash scripts/tests/unattended-test.sh; python3 scripts/tests/attestation-test.py | PASS | exit 0 | AC-7 |
| bash scripts/tests/housekeeping-workflow-test.sh (550s timeout) | FAIL | no failing cases printed; all ok lines through mutation-detected, then exit 124 on timeout | AC-10 |
| python3 scripts/tests/{chat,self-hosted,tui-complete-dialog,tui-housekeeping}-test.py | PASS | all exit 0 | AC-12 |
| bash scripts/tests/upgrade-test.sh | FAIL | FAIL: interactive startup under a pseudoterminal failed; script: tcgetattr/ioctl: Operation not supported on socket | AC-9 |
| bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh (full suite) | DRIVER PENDING | driver-owned | AC-12 |
| formatter, type checker, linter, frontend build, migration, rollback, performance, security | N/A | no such tooling in this shell/python repo | None stated |

## Coverage gaps

- AC-9 attended prompt path not observed passing (sandbox pty limitation)
- AC-7 defect injection not run
- No docs grep test for AC-11
- housekeeping-workflow-test.sh did not finish within 550s here

## Next action

Driver runs the full verification block; rerun upgrade-test.sh and housekeeping-workflow-test.sh in an environment with a real pty and longer timeout.
