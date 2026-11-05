# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 -B scripts/tests/repl-session-test.py | PASS | all rows ok incl. SIGTERM no-child and I-2 validation-removed injection detected; exit 0 | AC-2, AC-3, AC-4, AC-7, AC-9 |
| python3 -B scripts/tests/repl-pty-test.py | PASS | 12 rows ok: idle Ctrl-C, Ctrl-C in build, attended gate, no cursor/alt-screen bytes; exit 0 | AC-5, AC-6 |
| python3 -B scripts/tests/headless-equivalence-test.py | PASS | no FAIL lines; REPL, one-shot and TUI artifacts match | AC-8 |
| bash scripts/tests/launcher-noui-test.sh | PASS | 36 ok, 0 FAIL | AC-1 |
| python3 -B scripts/tests/headless-run-test.py | PASS | exit 0 (regression for one-shot headless) | AC-10 |
| python3 -B scripts/tests/no-housekeeping-test.py | FAIL | offender prompts/home-agent.md; file not touched by this change (assumed pre-existing) | AC-10 |
| bash scripts/run-shell-tests.sh && bash scripts/run-python-tests.sh | DRIVER PENDING | driver owns the full regression run | AC-10 |
| formatter / linter / type checker / frontend build / migration / rollback / performance / security | N/A | no such tooling configured for this change | None stated |

## Coverage gaps

- No live claude chat run; the real permission_denials fixture was not recorded.
- Defect injection only for I-2; I-3 (swapped precedence) and I-5 (ignored marker) injections not run.
- Interactive TUI and live-agent manual checks (MC-*) remain for a person.

## Next action

Driver runs the full regression block and compares against baseline.
