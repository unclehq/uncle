# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 scripts/tests/repl-session-test.py | PASS | exit 0, no FAIL lines (158 ok) | AC-1, AC-2, AC-3, AC-4 |
| defect injection: disable len(hits)==1 expansion in uncle_repl.py | PASS | 30 FAIL lines (mutant caught); file restored, cmp clean | AC-2 |
| defect injection: remove sorted(hits) (candidate order) | PASS | 3 FAIL lines (caught); restored | AC-3 |
| defect injection: drop .lower() on name | PASS | 2 FAIL lines (caught); restored | AC-3 |
| baseline result | N/A | see BASELINE_REPORT.md; no source change | AC-5 |
| bash scripts/run-shell-tests.sh; bash scripts/run-python-tests.sh (full suite) | DRIVER PENDING | driver green-check runs these | AC-5 |
| formatting / type check / lint / frontend build / migration / rollback / performance / security | N/A | no such tooling for this change; rollback is reverting the test file | None stated |
| integration tests | NOT RUN | covered by driver suite | AC-5 |

## Coverage gaps

- Mutants for expansion after quit and ambiguity-reported-as-unknown not run separately; the latter is asserted directly.
- Ambiguity order wording in the plan is inconsistent; tests pin alphabetical.
- Pre-existing failures: none observed in the targeted file.

## Next action

Driver runs the full regression block and compares against baseline.
