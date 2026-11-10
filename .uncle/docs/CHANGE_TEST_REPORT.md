# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| bash scripts/run-shell-tests.sh | FAIL | Run by the driver, exit 1. 32.6s gates-waivers 23.5s scripts/tests/worktree-run-test.sh#1of4 23.4s gates-verification-integrity-2 22.5s gates-waiver-integrity 22.2s scripts/tests/worktree-run-test.sh#2of4 22.2s scripts/tests/worktree-run-test.sh#3of4 21.7s gates-verification-integrity-4 20.8s gates-verification-integrity-3 18.0s scripts/tests/checklist-hedge-test.sh 16.6s gates-delivery-resume 16.5s scripts/tests/worktree-run-test.sh#4of4 14.8s gates-delivery 8.0s gates-baseline 6.2s scripts/tests/nested-run-guard-test.sh | None stated |
| bash scripts/run-python-tests.sh | FAIL | Run by the driver, exit 1. -commit-test.py#3of3 14.4s scripts/tests/pr-auto-commit-test.py#1of3 10.8s scripts/tests/repl-session-test.py 10.6s scripts/tests/host-preview-test.py 10.4s scripts/tests/early-branch-test.py 10.1s scripts/tests/attestation-statement-test.py#2of3 7.5s scripts/tests/headless-run-test.py 3.5s scripts/tests/supervisor-test.py 2.0s scripts/tests/shell-syntax-test.py 1.7s scripts/tests/worktree-branch-test.py 1.7s scripts/tests/pr-snapshot-managed-ignore-test.py 1.5s scripts/tests/project-git-test.py | None stated |
| bash scripts/run-python-tests.sh -- reviewer-prompt-file | PASS | Run by the driver, exit 0. Running 1 python suites with up to 7 workers. --- scripts/tests/reviewer-prompt-file-test.py --- ............... ---------------------------------------------------------------------- Ran 15 tests in 0.180s OK PASS scripts/tests/reviewer-prompt-file-test.py Python suites: 1 passed, 0 failed, 0 skipped. Slowest python suites: 0.3s scripts/tests/reviewer-prompt-file-test.py | None stated |
| bash scripts/run-python-tests.sh -- reviewer-prompt-kind | PASS | Run by the driver, exit 0. Running 1 python suites with up to 7 workers. --- scripts/tests/reviewer-prompt-kind-test.py --- ......... ---------------------------------------------------------------------- Ran 9 tests in 0.251s OK PASS scripts/tests/reviewer-prompt-kind-test.py Python suites: 1 passed, 0 failed, 0 skipped. Slowest python suites: 0.3s scripts/tests/reviewer-prompt-kind-test.py | None stated |

## Coverage gaps

- `bash scripts/run-shell-tests.sh` failed (exit 1); the driver verification is not green.
- `bash scripts/run-python-tests.sh` failed (exit 1); the driver verification is not green.

## Next action

Repair the failing command(s) and rerun the driver verification.
