# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 scripts/tests/aws-bedrock-test.py | PASS | Ran 53 tests OK | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7 |
| mutant: early return in _strip_temperature, then python3 scripts/tests/aws-bedrock-test.py | PASS | FAILED (errors=3): test_token_only_to_configured_url, test_anthropic_headers_url_no_temperature, test_converse_headers_url; file restored, 53 OK | AC-2 |
| bash scripts/run-shell-tests.sh && bash scripts/run-python-tests.sh | DRIVER PENDING | Driver owns the full suite; prior run showed pre-existing failures (D-1) | AC-4 |
| formatter / type checker / linter / frontend build / migration / rollback / performance | N/A | No such tooling configured for this change | None stated |
| live stub-server and TUI manual checks | NOT RUN | Belong to manual verification stage | AC-1, AC-6 |

## Coverage gaps

- Only one crude mutant run; no per-test defect injection
- Live stub-server and TUI checks not executed
- Pre-existing failures D-1 not investigated

## Next action

Driver runs full regression block; manual verification stage executes MC checks.
