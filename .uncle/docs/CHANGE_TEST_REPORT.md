# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 scripts/tests/preflight-toolchain-test.py | PASS | 7 tests OK | AC-1, AC-2, AC-3 |
| python3 scripts/tests/toolchain-install-test.py | PASS | 10 tests OK | AC-4, AC-5, AC-7 |
| python3 scripts/tests/toolchain-wiring-test.py | PASS | 7 tests OK (4 prompt failures before adding hand-tracing sentence) | AC-6, AC-8 |
| bash scripts/run-shell-tests.sh && bash scripts/run-python-tests.sh | DRIVER PENDING | Driver owns full regression run | AC-3, AC-8 |
| formatter / type checker / lint / frontend build / migration / rollback / performance / security | N/A | No such tooling in this repository for this change | None stated |
| live hosted OCaml run | BLOCKED | BLOCKED-SETUP: needs hosted machine with sudo and apt | AC-7 |

## Coverage gaps

- Live hosted install not exercised; simulated with fake sudo/apt-get
- MC-901 change_class.py defect is out of scope

## Next action

Driver runs full regression block.
