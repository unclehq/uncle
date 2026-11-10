# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 -B scripts/tests/handoff-export-test.py | PASS | Ran 25 tests, OK | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8 |
| bash scripts/tests/unattended-test.sh | PASS | 76 checks passed | AC-10 |
| grep -n 'Not yet covered' -A1 GITHUB_INTEGRATION.md | PASS | lists only planning without a git remote | AC-9 |
| bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh | DRIVER PENDING | Driver owns the full regression run. | AC-10 |
| formatter / type checker / lint / frontend build / migration / rollback / performance / security | N/A | No such tooling applies to these shell/python changes. | None stated |

## Coverage gaps

- gates-repair group 5 red on clean HEAD, unrelated.
- Signed-path e2e uses a fixture signer; no real ssh-keygen/cosign run.

## Next action

Driver runs the full regression block and compares against baseline.
