# Defects

## None. Two follow-ups: (1) Set up a real GitHub issue reachable by gh or network, or a stub, then rerun the `--issue` part. (2) Confirm whether exit 3 for a completed `--noui --housekeeping` run is intended.

- **Status:** BLOCKED-SETUP
- **Evidence:** Scratch dirs /tmp/mc101b-* and /tmp/mc101c-* with out.txt in each. Exit codes: change-request 124 (timeout after a successful start), housekeeping empty 2, housekeeping with text 3, issue 1. `git worktree list` showed only the main worktree in each scratch repo. The change-request scratch repo has .uncle/docs/CHANGE_REQUEST.md containing 'change text'.
- **Expected result:** Each workflow starts headlessly with plain text output. Change-request text comes from stdin and CHANGE_REQUEST.md is written. Issue run creates its worktree.
- **Actual result:** Change-request: PASS. Plain-text log with no curses, the stdin text was used, .uncle/docs/CHANGE_REQUEST.md contains 'change text', the change-plan agent launched, and the 25s timeout cut the run (exit 124). Housekeeping: bare use with no stdin was refused with 'Error: --housekeeping text cannot be empty' and exit 2. With text it started headlessly, printed plain text with [+hh:mm:ss] stamps, and the agent answered, but the runner ended with 'driver stopped without completing (gate or blocked); exit 3' after the agent's reply. The usage text says exit 0 on completion, so this exit code is unexplained and needs a look. Issue: the headless runner started and printed plain text. It stopped with exit 1 ('No git remote found' and then 'Failed to fetch issue unclehq/nonexistent-zz#1'). The issue-to-worktree path was not exercised because it needs a real GitHub issue with gh or network access, and this stage has network disabled (UNCLE_STAGE_NETWORK=false). No worktree was created.

## None. A person must run the attended command in a real terminal, type an approval at the gate once, then repeat with a blank line or Ctrl-D, and record the transcript and exit codes.

- **Status:** BLOCKED-HUMAN
- **Evidence:** None collected. Prepared PTY tests (scripts/tests/pty_helper.py, headless-run-test.py) may cover the gate-read logic through the driver green-check. They were not read or cited as covering this row, and they do not replace the real-terminal observation the row asks for.
- **Expected result:** The gate prompt prints and one line is read from the terminal. A typed approval is recorded as a human approval. A blank line or EOF counts as not approved and the run exits 3.
- **Actual result:** No live run was executed. This worker has no interactive terminal and cannot supply the human approval keystrokes. Running the full attended driver would also start real agent stages, which the compact worker policy does not allow.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** scripts/tests/headless-run-test.py lines 69-93 and 246-305 (exit-code mapping, SIGTERM-ignored driver killed, double SIGINT gives 130). No live transcript, ps listing or resume attempt was captured.
- **Expected result:** The runner exits 130 for SIGINT and 143 for SIGTERM. The driver process group is stopped, with an immediate kill on a second signal, and no orphan processes remain. The run state is resumable.
- **Actual result:** Not performed live. The checklist requires a human to press Ctrl+C in a real terminal and to observe the process list and a resume attempt on a long-running run. This worker has no interactive terminal and was told not to rerun the driver's automated tests. headless-run-test.py contains simulated-signal tests: exit 143 on SIGTERM, 130 on SIGINT, and a SIGTERM-ignoring driver being killed on a second signal. These are not live observations of the real command and do not show orphan-process or resume behaviour. The test file is evidence of what exists, not a PASS.

## None. Setup needed: a fixture or stub agent that leaves the first human gate unapproved (as headless-run-test.py does), so the exit-3 path can be exercised live with stdin closed.

- **Status:** BLOCKED-SETUP
- **Evidence:** rc.txt exit=0 in /var/folders/.../tmp.ifAzTVWamP; exit=2 attended refusal message on stderr in tmp.u32LWztcHG; exit=1 contaminated run in tmp.vhVuOiVyC0; exit=2 in tmp.y8VByDihch (stale installed runtime lacking uncle_headless.py). Default launcher mode text: 'Mode: unattended (default). Approval gates are delegated to the agent'.
- **Expected result:** The run never reads stdin, records nothing as human-approved, names the gate on stderr and exits 3.
- **Actual result:** Exit 3 was not produced. Default (unattended) run with stdin closed completed the whole build, exit 0, verdict READY_WITH_NON_BLOCKING_ISSUES; gates were delegated to the agent and approval files were written (.uncle/workflow/approvals/*.approved-by), so no gate stop occurred. `--attended` with closed stdin was refused up front: exit 2, 'attended mode needs an interactive terminal on stdin; piped, file or closed stdin cannot approve a gate'. A first run inheriting the outer worker env exited 1 (artifact delivery path collision) and is invalid. The exit-3 gate-stop path needs a setup where an unattended gate is deliberately left unmet; I could not arrange one with a real agent. Unit coverage of exit 3 exists in scripts/tests/headless-run-test.py (test_gate_named_on_stderr) but was not run by me. I did not verify the contents of the approved-by files, so I did not confirm who recorded the approvals.

## None. Waiting on the operator to run `uncle --noui --attended --application "tiny app"` in a real terminal, type an approval at the first gate, then rerun and press Ctrl+D or Enter on a blank line, and record the exit statuses and attestation entries.

- **Status:** BLOCKED-HUMAN
- **Evidence:** No commands run for this check. The row's evidence (terminal transcript, exit statuses, gate attestation entries) needs a human-driven session.
- **Expected result:** The typed approval is recorded as a human approval; EOF or a blank answer is treated as not approved and the run stops with exit 3.
- **Actual result:** Not performed. A human approval is the thing under test, and an agent-typed approval would not count as one.

## Proposed: `--noui --attended --issue 1 </dev/null` starts a driver instead of exiting 2, and `--attended --housekeeping` exits 1 instead of 2. Not yet in DEFECTS.md.

- **Status:** FAIL
- **Evidence:** Observed exits: A=2, B=2 (case 2), case 3 stdout 'Mode: attended...' followed by a Python 'can't open file .../uncle_headless.py' error, case 4 exit=1. git status --porcelain was identical before and after. The new-repo case 5 listing was empty apart from .git.
- **Expected result:** Each case prints a reason on stderr, exits 2, starts no driver and writes no state.
- **Actual result:** Case 1 (`--noui`): exit 2, 'needs a startup action', no state. Case 2 (`--noui --noinput --issue 1`): exit 2, 'cannot be combined with --noinput'. Case 5 (change-request with piped text): exit 2, 'attended mode needs an interactive terminal on stdin...', and the fresh repo had no files or worktrees created. Case 3 (`--noui --attended --issue 1 </dev/null`): NOT refused. It printed 'Mode: attended. Each approval gate waits for your decision.', started the driver and exited 1 on a missing /opt/homebrew/opt/uncle/libexec/scripts/lib/uncle_headless.py. Expected exit 2 with a refusal. Case 4 (`--attended --housekeeping`, no --noui): exit 1, not 2. The stderr says attended mode needs an interactive terminal; it does not say --attended requires --noui. No git status or worktree changes in the project. The `--noui --attended --issue` run failed because the launcher resolved to the Homebrew-installed libexec, which lacks the new headless module. Even so, the refusal was not issued before the driver started.

## None (exit codes and process cleanup passed; the resume clause and real-launcher path were not executed, so the row is not marked PASS)

- **Status:** NOT RUN
- **Evidence:** Shell loop output: term exit=143 after=0; int exit=130 after=0; ign exit=143 (second-signal elapsed 0s by `date +%s`) after=0. Scripts at /tmp/mc204/w.py. The first pass used an invalid `sleep` argument; the second pass with `sleep 301` confirmed 2 processes before and 0 after.
- **Expected result:** Exit 143 for SIGTERM and 130 for SIGINT; no driver child processes remain; a second signal kills the group immediately; the run can be resumed.
- **Actual result:** SIGTERM gave exit 143 and SIGINT gave exit 130. Before the signal, ps showed 2 processes (driver and child); afterward it showed 0 in every case. With the SIGTERM-ignoring driver, the second signal ended the run with exit 143 within about 1s, before the 3s grace period would have expired, and no processes remained. Not verified: resumability of the run after the signal, and the real `uncle --noui --housekeeping` launcher path, which was exercised only through the fake driver.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** The checklist row requires typed human input at a gate in a real terminal. No live run was made. The driver green-check was not cited because it was not read, so no automated PTY coverage is claimed.
- **Expected result:** The gate prompt is printed and the typed answer is read from the terminal and recorded as a human approval. A blank or EOF answer is treated as not approved and the run stops with exit code 3.
- **Actual result:** Not performed. The check needs a human at a real terminal to type an answer and then press Enter or Ctrl+D. No transcript, exit codes or gate state were captured.

## New: uncle --noui --attended --application x with non-tty stdin writes .uncle/docs/REQUIREMENTS.md before the stdin check rejects (exit 2)

- **Status:** FAIL
- **Evidence:** Case 1 clean-env: exit=2; find . -path ./.git -prune -o -print listed ./.uncle, ./.uncle/docs, ./.uncle/docs/REQUIREMENTS.md. Cases 2-4: exit=2, directory listing identical before/after (UNCHANGED).
- **Expected result:** Each prints a reason on stderr, exits 2, and starts no driver or state.
- **Actual result:** Cases 2, 3, 4 each printed a reason on stderr and exited 2 (case 2: '--noui needs a startup action...'; case 3: '--noui cannot be combined with --noinput'; case 4: 'attended mode needs an interactive terminal on stdin...'), with directory unchanged. Case 1 exited 2 with stderr 'uncle --noui: attended mode needs an interactive terminal on stdin; piped, file or closed stdin cannot approve a gate.', but it first printed 'Mode: attended...' on stdout and left a new .uncle/docs/REQUIREMENTS.md in the previously empty repo, so state was created before rejection, contradicting 'starts no state'. (Run without unsetting inherited driver env, case 1 instead tried to exec a nonexistent /opt/homebrew/opt/uncle/libexec/scripts/lib/uncle_headless.py - environment contamination, not counted.)

## None

- **Status:** NOT RUN
- **Evidence:** rc=2; /tmp/e402.txt begins 'Error: --noui cannot be combined with --noinput'; /tmp/o402.txt empty. Source: uncle:238-239, uncle:481-482. scripts/tests/launcher-noui-test.sh:16 asserts the same exit 2.
- **Expected result:** First command still runs the TUI path in no-keyboard mode, unchanged. Second is refused with a stderr message and exit 2, and nothing is started.
- **Actual result:** Second half observed: exit code 2, stdout empty, stderr 'Error: --noui cannot be combined with --noinput' followed by usage; nothing started. First half not executed live. Code inspection shows `--noinput` without `--noui` still goes to `uncle_run_tui python3 uncle_tui.py --noinput` (uncle:482).
