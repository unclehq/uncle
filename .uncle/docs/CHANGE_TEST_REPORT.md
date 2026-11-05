# Change test report

## Command results

| Command | Status | Meaningful output | Requirements |
|---|---|---|---|
| bash scripts/run-shell-tests.sh | FAIL | Run by the driver, exit 1. ctions-driver-test.sh 76.2s gates-review-cache 74.8s scripts/tests/worktree-run-test.sh 66.8s scripts/tests/close-flow-test.sh#3of4 66.3s scripts/tests/close-flow-test.sh#4of4 66.2s scripts/tests/model-jobs-driver-test.sh 66.0s scripts/tests/stage-runner-test.sh 65.0s scripts/tests/early-checklist-flow-test.sh 62.5s scripts/tests/updated-plan-edits-driver-test.sh 61.6s scripts/tests/wave-prompts-test.sh 59.4s scripts/tests/updated-change-plan-ops-driver-test.sh 54.6s gates-verification-integrity | None stated |
| bash scripts/run-python-tests.sh | FAIL | Run by the driver, exit 1. cripts/tests/defer-regressions-test.py#3of6 41.3s scripts/tests/attestation-statement-test.py 39.9s scripts/tests/updated-plan-schema-order-test.py#2of3 35.1s scripts/tests/fast4-regressions-test.py#1of2 33.9s scripts/tests/fast3-regressions-test.py 33.6s scripts/tests/fast4-regressions-test.py#2of2 32.5s scripts/tests/defer-regressions-test.py#1of6 29.4s scripts/tests/defer-regressions-test.py#2of6 27.7s scripts/tests/defer-regressions-test.py#4of6 27.0s scripts/tests/adversarial-slices-test.py | None stated |

## Coverage gaps

- `bash scripts/run-shell-tests.sh` failed (exit 1); the driver verification is not green.
- `bash scripts/run-python-tests.sh` failed (exit 1); the driver verification is not green.

## Next action

Repair the failing command(s) and rerun the driver verification.
