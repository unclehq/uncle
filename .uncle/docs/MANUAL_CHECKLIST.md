# Manual checklist

## Coverage

### MC-100
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a working tree with uncommitted changes (not clean main), run `scripts/stagegate.sh --version` and `scripts/change-workflow.sh --version`, then `--help` and `-h` on both; note stdout, exit codes.
- Expected result: Each version call prints `0.1.0` and exits 0; each help call prints usage that mentions `--unattended` and exits 0, with no run-policy refusal.
- Evidence to capture: Terminal output and exit code of all eight invocations.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: file:.gitignore
- Depends on: none
- Exact action: Run `python3 -B scripts/tests/attestation-statement-test.py` once with the host .gitignore containing a `.uncle` line and once with it clean, hashing .gitignore before and after and restoring it byte-for-byte.
- Expected result: Both runs pass; the .gitignore hash is identical to the original after restoration.
- Evidence to capture: Both run results and the three hashes.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a suite that requires an external tool (e.g. worktree-run-test.sh) with that tool removed from PATH, capturing stderr and exit code.
- Expected result: stderr contains `missing prerequisite: <tool>`, exit is nonzero and not 127, and it is reported as FAILED, never passed or skipped.
- Evidence to capture: Stderr text and exit code.
- Actual result: 
- Status: NOT RUN

### MC-107
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `python3 -B scripts/tests/home-actions-test.py` and `python3 -B scripts/tests/early-branch-test.py`, and `python3 -B scripts/tests/supervisor-test.py`.
- Expected result: All pass: resume with worktree listing failure shows a refusal without exception, early-branch skip contexts create no ref, and the signing audit reports no unflagged fixture commits.
- Evidence to capture: Pass/fail summaries for each suite.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With a required tool (e.g. git) hidden from PATH, run the worktree-run and gates-verification-integrity suites, plus any suite that previously exited 127.
- Expected result: Stderr shows `missing prerequisite: <tool>`, and the exit code is nonzero and not 127. The suite is not reported as passed or skipped.
- Evidence to capture: Stderr text and exit code for each suite, and how the suite is reported.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: YES
- Exclusive resources: file:.gitignore
- Depends on: none
- Exact action: Run `python3 -B scripts/tests/attestation-statement-test.py` once with the host .gitignore containing a `.uncle` line and once without. Record the .gitignore hash before and after, and restore it byte-for-byte.
- Expected result: Both runs pass, and the .gitignore hash is identical to its original after restoring.
- Evidence to capture: Pass/fail output for both runs and the before/after hashes.
- Actual result: 
- Status: NOT RUN

## Resources

### MC-300
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a throwaway temp copy of the project with uncommitted changes (dirty tree), run `scripts/stagegate.sh --version`, `scripts/stagegate.sh --help`, `scripts/change-workflow.sh --version` and `scripts/change-workflow.sh --help`, recording exit codes.
- Expected result: Each exits 0; --version prints 0.1.0; --help prints usage that documents --unattended; no run-policy refusal appears.
- Evidence to capture: Terminal transcript with stdout, stderr and exit code of all four commands.
- Actual result: 
- Status: NOT RUN

### MC-305
- Required for acceptance: YES
- Exclusive resources: file:host-gitignore
- Depends on: none
- Exact action: Hash the host .gitignore, run `python3 -B scripts/tests/attestation-statement-test.py` once with the host .gitignore containing a `.uncle` line and once with it clean, then restore the original and re-hash.
- Expected result: Both runs pass; the restored .gitignore hash equals the original hash.
- Evidence to capture: Both run results and the before/after hashes.
- Actual result: 
- Status: NOT RUN

### MC-306
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run home-actions-test.py and early-branch-test.py, then in a non-repo temp directory trigger the TUI resume action and observe the screen.
- Expected result: Both suites pass; the TUI shows a refusal message when worktree listing fails, without a traceback and without changing state.
- Evidence to capture: Suite output and the TUI refusal screen text or capture.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In the dirty working tree, run `scripts/stagegate.sh --version` and `scripts/change-workflow.sh --version`, then `--help` on both; record stdout and exit codes.
- Expected result: Version prints `0.1.0` with exit 0; help prints usage including `--unattended` with exit 0; no run-policy refusal appears.
- Evidence to capture: Terminal output and exit codes of the four commands.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: file:.gitignore
- Depends on: none
- Exact action: Run `python3 -B scripts/tests/attestation-statement-test.py` once with the host .gitignore containing a `.uncle` line and once with it clean, hashing .gitignore before and after and restoring it byte-for-byte.
- Expected result: Both runs pass, and the .gitignore hash after restoration equals the original.
- Evidence to capture: Both run outputs with exit codes and the before/after hashes.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `python3 -B scripts/tests/home-actions-test.py` and trigger a TUI resume where `git worktree list` fails (non-repo project).
- Expected result: The suite passes; the resume path shows a refusal message without a traceback or `WorktreeListError` escaping, and no state is changed.
- Evidence to capture: Test output and the refusal message text.
- Actual result: 
- Status: NOT RUN

### MC-407
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run worktree-run-test.sh with a required tool removed from PATH.
- Expected result: Stderr shows `missing prerequisite: <tool>` and the exit code is nonzero and not 127; the result is not a pass or skip.
- Evidence to capture: Stderr text and exit code.
- Actual result: 
- Status: NOT RUN
