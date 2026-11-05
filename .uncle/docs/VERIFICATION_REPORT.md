# Verification report

## Findings

### MC-105

- **Action:** Not performed live: requires an interactive TUI session plus a real long-running housekeeping agent run. Only the script's lock refusal was exercised (see MC-202).
- **Expected result:** TUI posts 'Housekeeping already running' (not FAILED); first terminal run unaffected.
- **Actual result:** TUI half not observed. Script half: with housekeeping.lock held by another process, housekeeping-workflow.sh exited 1 with 'housekeeping: another housekeeping run is active'. uncle_tui.py:1589 contains a ValueError('Housekeeping already running') path (code inspection only).
- **Defects:** None

### MC-202

- **Action:** Held housekeeping.lock with a separate python flock process (stand-in for the first run, not a real housekeeping run), then ran scripts/housekeeping-workflow.sh --unattended chore2.
- **Expected result:** Second invocation exits 1 with a lock-held message; first run continues and completes normally.
- **Actual result:** Second invocation exited 1 with 'housekeeping: another housekeeping run is active'. A real first housekeeping run was not started, so its continuation/completion was not observed.
- **Defects:** None

### MC-203

- **Action:** Not performed in a TUI; only the script half (lock held elsewhere, script run) was exercised.
- **Expected result:** Script exits 1 and TUI posts 'Housekeeping already running', no FAILED notice.
- **Actual result:** Script exited 1 with the lock message. TUI chat notice and .uncle/workflow/housekeeping/tui.out were not observed; needs an interactive TUI session.
- **Defects:** None

### MC-205

- **Action:** Did not drive a live TUI. Ran only the narrow prepared test module scripts/tests/tui-housekeeping-test.py (mocked Popen/hk_proc) to see what it asserts for DONE, FAILED, signal and quit behavior.
- **Expected result:** A successful run posts exactly one DONE notice with code 0. A failed or killed run posts exactly one FAILED notice with its exit code or signal. Quitting the TUI terminates the live run and posts no completion notice.
- **Actual result:** The live scenario was not performed: no real background housekeeping run was started, and no real quit or process listing was captured. The mocked tests all passed (16 tests OK), including test_exit_zero_posts_single_done_notice, test_nonzero_exit_posts_failed_notice_with_code, test_signal_killed_run_reported_failed and test_quit_with_live_hk_proc_stops_tree_and_posts_no_notice. They cover the logic only, not real processes, so they do not satisfy the required process-listing evidence.
- **Defects:** None

### MC-303

- **Action:** Not performed: requires issuing /housekeeping twice in a live TUI with a real background run. Only the second-terminal script lock refusal was exercised.
- **Expected result:** TUI shows 'Housekeeping already running' and starts no second process; second-terminal script exits 1 with lock message; first run unaffected.
- **Actual result:** Second-terminal script exited 1 with 'housekeeping: another housekeeping run is active'. TUI behavior and a live first run were not observed.
- **Defects:** None

### MC-401

- **Action:** Inspected whether the live TUI flow (`/housekeeping list merged branches` with attended preference, observing the confirmation prompt and foreground completion) can be driven from this non-interactive worker. It cannot: it needs an interactive terminal session and a live reviewer/agent run with a human answering the attended confirmation prompt. I did not launch the TUI. I only located the automated test scripts/tests/tui-housekeeping-test.py::test_foreground_path_when_build_idle_or_exited, which covers the foreground-versus-background routing at unit level. It does not cover the confirmation prompt or the real completion.
- **Expected result:** Foreground path runs as before, including the attended confirmation prompt, and finishes with its normal result; no background-start notice appears.
- **Actual result:** Not observed live. The terminal capture of the confirmation prompt and foreground completion was not produced.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-105 | YES | BLOCKED-SETUP | Script output/exit=1 from narrow lock probe; grep of uncle_tui.py. No TUI interaction performed. |
| MC-202 | YES | BLOCKED-SETUP | exit=1; stderr message 'housekeeping: another housekeeping run is active'. |
| MC-203 | YES | BLOCKED-SETUP | Script exit=1 from lock probe. No TUI evidence. |
| MC-205 | YES | NOT RUN | Unit test run output: 'Ran 16 tests ... OK'. The driver green-check lists bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh as PREEXISTING; it has no live-TUI evidence. No chat transcript or ps listing exists for this check. |
| MC-303 | YES | BLOCKED-SETUP | Script exit=1 from lock probe. No TUI evidence. |
| MC-401 | YES | BLOCKED-HUMAN | No terminal capture. The only related evidence is the driver green-check test for foreground routing, which I did not re-run. It is not a substitute for the human-visible prompt observation. |
