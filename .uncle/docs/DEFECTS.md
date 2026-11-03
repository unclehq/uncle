# Defects

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** None. Driver green-check may cover related script tests but does not replace this live attended end-to-end observation.
- **Expected result:** No y/N prompt; worktree dir gone; main project on run branch with changed and untracked files; exactly one 'Branch <b>: worktree removed; project switched.' line.
- **Actual result:** Not performed. No observation made.

## None

- **Status:** NOT RUN
- **Evidence:** None.
- **Expected result:** Commit made, worktree removed, main switched, success summary printed once, no prompt, no 'Worktree ... kept; remove with:' line.
- **Actual result:** Not performed. No observation made.

## None. Setup needed: a real or stubbed-driver no-PR COMPLETE --worktree run on a clean project, executed once under a pty and once with --unattended, with transcripts captured.

- **Status:** BLOCKED-SETUP
- **Evidence:** Source read of scripts/from-issue.sh lines ~955-980 only; green-check.md shows FIXED for run-shell-tests.sh and run-python-tests.sh, which is not a pty transcript.
- **Expected result:** No 'Remove worktree <dir>? [y/N]' prompt and no 'Worktree <dir> kept; remove with:' line on the no-PR path; single final line 'Branch <b>: worktree removed; project switched.'; exit status matches driver's.
- **Actual result:** Not executed live. A real run needs a full change-workflow driver with agent CLIs, a GitHub issue and a pty harness, which this lane cannot set up; the fixture suite scripts/tests/worktree-run-test.sh is covered only by the driver green-check, not a live observation of captured pty/unattended transcripts.
