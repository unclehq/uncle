# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| python3 -B scripts/tests/gitignore-clean-end-test.py | PASS | Ran 16 tests, OK | AC-1, AC-2, AC-4, AC-5, AC-7 |
| bash scripts/tests/pr-auto-publish-test.sh | PASS | 10 checks passed (2 new for AC-3) | AC-3 |
| python3 -B scripts/tests/gitignore-tolerance-test.py | PASS | OK (unmodified regression) | AC-4 |
| bash scripts/tests/uncle-gitignore-test.sh | PASS | one canonical block, legacy spellings retired, idempotent | AC-4 |
| M-1: copy of repo in /tmp/m1 with uncle_gitignore.ensure() re-added in _ensure_uncle_gitignored; python3 -B scripts/tests/gitignore-clean-end-test.py | PASS | Test run FAILED (failures=5) as required, incl. test_tui_reload_leaves_gitignore_unchanged | AC-6 |
| M-2: copy with assert_tree_matches_attested returning 0; same test file | PASS | Test run FAILED (failures=9) as required, incl. 4 Guard tests | AC-2, AC-6 |
| bash scripts/tests/worktree-run-test.sh | NOT RUN | self-skips while an uncle build drives this checkout (needs UNCLE_TEST_ALLOW_NESTED=1) | AC-4 |
| bash scripts/run-shell-tests.sh && bash scripts/run-python-tests.sh | DRIVER PENDING | driver owns the full regression run | AC-1, AC-2, AC-3, AC-4, AC-5, AC-7 |
| formatter / linter / type checker / frontend build / migration / rollback / performance / security | N/A | no such tooling is configured for this change | None stated |

## Coverage gaps

- The attestation signature is not verified by the guard (no verify API in attestation.py).
- The legacy-snapshot strip_managed publish mode (R-5) is not implemented.
- The guard is not exercised by a real publish flow; only the sourced function is tested in fixture repos.
- The TUI load_config, reload and project-switch paths are not each driven separately; only _ensure_uncle_gitignored is called.
- gitignore-tui-test.py and gitignore-publish-guard-test.py were not created (cases are in gitignore-clean-end-test.py).
- The live manual check (real change request completes with a clean checkout) is not run.

## Next action

The driver runs the full regression block and compares against baseline; a person runs the manual check and decides on signature verification and legacy-snapshot tolerance.
