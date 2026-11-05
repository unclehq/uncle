# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui --housekeeping`, `uncle --noui --issue <N>` and `echo 'change text' | uncle --noui --change-request` in separate scratch projects.
- Expected result: Each starts its matching workflow headlessly with plain text output. The change-request text is taken from stdin, and CHANGE_REQUEST.md is written, as in the TUI path.
- Evidence to capture: Output of each run, exit codes, and the created worktree and CHANGE_REQUEST.md.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run these refusal cases: `uncle --noui` alone, `uncle --noui --noinput --application x`, `uncle --noui --attended --application x < /dev/null`, `echo t | uncle --noui --attended --change-request`, and `uncle --noui --application ''`.
- Expected result: Each prints a reason on stderr and exits 2. No driver starts, no worktree is created, and the run never falls back to unattended mode or the menu.
- Evidence to capture: stderr text and exit code for each case, plus `git worktree list` before and after.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a real terminal, run `uncle --noui --attended --application "<tiny brief>"` until a human gate prompt appears. Type an approval line once, then repeat the run and press Enter on a blank line (or Ctrl-D) at the gate.
- Expected result: The gate prompt prints and one line is read from the terminal. The typed approval is recorded as a human approval, while a blank line or EOF counts as not approved and the run exits 3.
- Evidence to capture: Terminal transcript, exit codes, and the gate attestation record in the run state.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start a long `uncle --noui` run in a terminal and press Ctrl+C once. Then repeat with `kill -TERM <pid>`, and again where the driver ignores the first signal (send a second Ctrl+C during the grace period).
- Expected result: The runner exits 130 for SIGINT and 143 for SIGTERM. The driver process group is stopped, with an immediate kill on a second signal, and no orphan processes remain. The run state is resumable.
- Evidence to capture: Exit codes, `ps` listing showing no leftover children, and a resume attempt succeeding.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `UNCLE_NOUI=1 uncle --application x`, then `UNCLE_NOUI=0`, `UNCLE_NOUI=` and `UNCLE_NOUI=true` variants, each in a scratch project. Also run `uncle --help`.
- Expected result: Only `UNCLE_NOUI=1` runs headless. The other values start the normal TUI path silently. `--help` documents `--noui`, `UNCLE_NOUI`, the exit codes, the attended requirement, and how `--noui` differs from `--noinput`.
- Evidence to capture: Observed UI mode per variant and the help text.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui --application "tiny app"` unattended with stdin closed (`</dev/null`) and no tty, against a project whose first human gate is reached; note the exit status.
- Expected result: The run never reads stdin, records nothing as human-approved, names the gate on stderr and exits 3.
- Evidence to capture: Stderr text, `echo $?` output, and the gate state/attestation file showing no human approval.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a real terminal run `uncle --noui --attended --application "tiny app"`, answer the first gate prompt by typing an approval line, and later rerun and press Ctrl+D (EOF) or Enter on a blank line at a gate.
- Expected result: The typed approval is recorded as a human approval; EOF or blank answer is treated as not approved and the run stops with exit 3.
- Evidence to capture: Terminal transcript, exit statuses, and the recorded gate attestation entries.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run refusal cases and note stderr, exit status and that no files or worktree were created: `uncle --noui` (no action), `uncle --noui --noinput --issue 1`, `uncle --noui --attended --issue 1 </dev/null`, `uncle --attended --housekeeping` (no --noui), and `echo text | uncle --noui --attended --change-request`.
- Expected result: Each prints a reason on stderr, exits 2, starts no driver and writes no state.
- Evidence to capture: Each command's stderr, exit status, and `git status`/worktree listing before and after.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Start a long `uncle --noui --housekeeping` run in its own process group, send SIGTERM once, then repeat with SIGINT, and repeat with a driver that ignores SIGTERM sending a second signal during the grace period; list processes afterward with `ps`.
- Expected result: Exit codes are 143 for SIGTERM and 130 for SIGINT; no driver child processes remain; a second signal kills the group immediately; the run can be resumed.
- Evidence to capture: Exit statuses, `ps` output before and after, and timing of the second-signal kill.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `UNCLE_NOUI=1 uncle --housekeeping` and then `UNCLE_NOUI=0`, `UNCLE_NOUI=` and `UNCLE_NOUI=true` with the same action on a tty, observing whether the curses UI or plain text appears; also run `--noui` with a symlinked startup text file if reproducible.
- Expected result: Only exactly `1` gives plain headless output; other values silently start the normal TUI; an untrusted symlinked text file is refused with exit 2 and no driver starts.
- Evidence to capture: Screen observations or transcripts for each value and the refusal's stderr and exit status.
- Actual result: 
- Status: NOT RUN

## resources

### MC-303
- Required for acceptance: YES
- Exclusive resources: dir:noui-scratch-attended
- Depends on: none
- Exact action: In a real terminal run `uncle --noui --attended --application "hello"` and answer the first gate prompt by typing a line; then on a second run press Enter on a blank line (or Ctrl+D) at a gate.
- Expected result: The gate prompt is printed and the typed answer is read from the terminal and recorded as a human approval; a blank or EOF answer is treated as not approved and the run stops with exit code 3.
- Evidence to capture: Transcript of both runs, exit codes, and the recorded gate state showing human approval in the first run only.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noui --attended --application "x" < /dev/null`, `uncle --noui` with no action, `uncle --noui --noinput --application x`, and `uncle --noui --attended --change-request` with piped text; check each exit code and that no worktree or files were created.
- Expected result: Each prints a reason on stderr, exits 2, and starts no driver or state.
- Evidence to capture: stderr messages, exit codes, and directory listing before and after.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a real terminal (tty), run `uncle --application "tiny demo"` without `--noui` and observe the startup, then quit at the first opportunity.
- Expected result: The curses TUI starts as before, runs unattended by default, and no headless/plain-text runner output appears.
- Evidence to capture: Terminal screenshot or transcript showing the curses UI launching.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --noinput --application "tiny demo"` with stdin from /dev/null and stdout piped to a file, and then run `uncle --noui --noinput --application x`.
- Expected result: The first command still runs the TUI path in no-keyboard mode, unchanged. The second is refused with a message on stderr and exit code 2, and nothing is started.
- Evidence to capture: Exit codes, stderr text, and confirmation that no driver or worktree was created for the refused run.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle` with no startup action and stdin/stdout piped (no tty), feeding `q` or EOF on stdin. Then repeat with `UNCLE_NOUI=0`, `UNCLE_NOUI=` (empty) and `UNCLE_NOUI=true` set.
- Expected result: The line-based menu appears as before in every case. UNCLE_NOUI values other than exactly 1 are silently ignored, with no headless run and no error.
- Evidence to capture: Captured stdout of each invocation showing the line menu and exit codes.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a real terminal, run `uncle --change-request` against a project that already contains CHANGE_REQUEST.md, both with and without `--noui`.
- Expected result: Both refuse the existing CHANGE_REQUEST.md (CHANGE_REQUEST_EXISTS behavior) without overwriting it. The non-`--noui` run keeps its prior TUI behavior and the `--noui` run exits non-zero without starting a driver.
- Evidence to capture: Messages, exit codes, and unchanged CHANGE_REQUEST.md content.
- Actual result: 
- Status: NOT RUN
