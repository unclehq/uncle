# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --help` and then `uncle --audt` in a scratch directory.
- Expected result: Help lists `--audit [BRANCH]` and exits 0; the near-miss prints `Did you mean --audit?` and exits non-zero.
- Evidence to capture: Captured stdout/stderr and exit codes of both commands.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: file:audit-target-checkout-state
- Depends on: none
- Exact action: In a finished change-family worktree whose state is a post-implementation stage, run `uncle --audit` (or against a stub driver install via UNCLE_RUNTIME_ROOT if reviewer credentials are unavailable).
- Expected result: State is set to FINAL_AUDIT, the driver runs in that checkout, output prints the previous state, a `verdict:` line and the `.uncle/docs/FINAL_AUDIT.md` path; exit equals the driver's status.
- Evidence to capture: Terminal output, exit code, and the resulting FINAL_AUDIT.md and audit-verdict files.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: file:audit-target-checkout-state
- Depends on: none
- Exact action: From a different checkout run `uncle --audit <branch>` for a branch checked out in a second worktree, noting the caller's branch and HEAD before and after.
- Expected result: The driver runs with cwd in the other worktree and its FINAL_AUDIT.md is updated; the caller's checkout, branch and HEAD are unchanged.
- Evidence to capture: Before/after `git rev-parse HEAD` and branch name, plus the output summary.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --audit` in a non-git directory, in detached HEAD, with an unknown branch, with a branch that has no worktree, with `--audit ''`, with `--audit a b`, and with `--audit=--x`.
- Expected result: Each prints a one-line `Error:` naming the cause and exits with the refusal code (1, or 2 under --noui).
- Evidence to capture: Stderr and exit code per case.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: file:audit-target-checkout-state
- Depends on: none
- Exact action: For targets whose state file is a mid-flight state (planning, approval gate, implementation in progress) and for a checkout lacking change-family state, run `uncle --audit`, checksumming the state file before and after.
- Expected result: Each is refused with an `Error:` naming the state or family and the state file is byte-identical.
- Evidence to capture: Error text and before/after checksums.
- Actual result: 
- Status: NOT RUN

### MC-107
- Required for acceptance: YES
- Exclusive resources: file:audit-target-checkout-state
- Depends on: none
- Exact action: Hold the target's `.uncle/workflow/driver.lock` with flock in another terminal and run `uncle --audit` there.
- Expected result: Refusal naming the lock with the refusal exit code; state file unchanged and no driver started.
- Evidence to capture: Error text, exit code, state checksum before/after.
- Actual result: 
- Status: NOT RUN

### MC-108
- Required for acceptance: YES
- Exclusive resources: file:audit-target-checkout-state
- Depends on: none
- Exact action: Run `uncle --audit` where the driver exits 0 but writes no audit-verdict, then where the verdict is not READY, and with a state value containing an ESC byte.
- Expected result: Missing verdict prints unknown verdict and exits per the plan; not-READY keeps the driver's status; no raw control characters appear in output.
- Evidence to capture: Output captured with `cat -v` and exit codes.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: file:fixture-state
- Depends on: none
- Exact action: In a fixture change-family checkout whose state is a mid-flight stage (e.g. plan approval or implementation in progress), checksum .uncle/workflow/state, run `uncle --audit`, then checksum again. Repeat for a non-git directory, an unknown branch, and `uncle --audit ''`.
- Expected result: Each run prints a one-line `Error:` naming the cause, exits with the refusal code (1, or 2 under --noui), and the state file checksum is identical before and after.
- Evidence to capture: Stderr text, exit code and before/after checksum for each refusal case.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: file:fixture-worktrees
- Depends on: none
- Exact action: With two worktrees (main checkout on branch A, second worktree on branch B, both with finished change state), record `git rev-parse HEAD` and `git branch --show-current` in the caller checkout, run `uncle --audit B`, then record them again.
- Expected result: The audit runs in B's worktree (its state and FINAL_AUDIT.md are updated), while the caller checkout's HEAD, branch and working tree are unchanged.
- Evidence to capture: Before/after HEAD and branch output, plus timestamps of FINAL_AUDIT.md in each worktree.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --issue --audit` with `echo 5 |` piped on stdin, and `uncle --audit --application x`, and `uncle --audit verify`.
- Expected result: The first two are refused as mutually exclusive with the refusal code before stdin is consumed; `--audit verify` treats verify as a branch name (not running the verifier) and fails with an `Error:` for an unknown branch. No state changes.
- Evidence to capture: Output and exit code of each command.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: file:fixture-state
- Depends on: none
- Exact action: In a fixture checkout with a decoy `scripts/change-workflow.sh` that writes a marker file, run `uncle --audit` on a finished-state checkout using the installed uncle, then check for the marker. Also create a branch name containing an ESC byte and run `uncle --audit` with it, inspecting output.
- Expected result: Only the install-dir driver runs (no marker from the decoy), and no raw control characters appear in any printed message.
- Evidence to capture: Marker file presence and a hexdump (`| cat -v`) of the output.
- Actual result: 
- Status: NOT RUN

## resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: file:fixture-driver.lock
- Depends on: none
- Exact action: In a fixture change-family checkout whose state is a post-implementation stage, hold driver.lock from a background process (flock), snapshot the state file bytes, then run `uncle --audit` and release the lock afterward.
- Expected result: Output is a one-line `Error:` naming the driver lock, exit code is $UNCLE_REFUSE_CODE (1, or 2 under --noui), the state file is byte-identical, and the driver does not run.
- Evidence to capture: Captured stderr, exit code, and before/after checksum of .uncle/workflow/state.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: file:fixture-worktrees
- Depends on: none
- Exact action: In a fixture repo with a second worktree on branch B (state post-implementation), run `uncle --audit B` from the primary checkout, recording HEAD and current branch of the caller before and after.
- Expected result: The driver runs with cwd in B's worktree, FINAL_AUDIT.md path and a verdict line are printed, and the caller's checkout, branch and HEAD are unchanged.
- Evidence to capture: Stdout, exit code, driver-recorded cwd, and caller `git rev-parse HEAD` and branch before/after.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: file:fixture-state
- Depends on: none
- Exact action: Run `uncle --audit` against fixtures whose state is each of: planning, a plan approval gate, implementation in progress, and a post-implementation stage; snapshot the state file bytes before each.
- Expected result: Mid-flight states are refused with `Error:` naming the state, state is byte-identical and the driver is not run; the post-implementation state is accepted and set to FINAL_AUDIT before the driver runs.
- Evidence to capture: Per-state stderr, exit code, state checksums, and driver invocation record.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: file:fixture-worktrees
- Depends on: none
- Exact action: With a decoy scripts/change-workflow.sh placed in the target worktree that writes a marker file, run `uncle --audit` there; also run it once with a branch checked out in no worktree and once with a worktree lacking .uncle.
- Expected result: Only the install-dir driver runs (no decoy marker), cwd is the target checkout, and the no-worktree and missing-.uncle cases are refused with `Error:` and no state write.
- Evidence to capture: Presence/absence of marker file, driver-recorded cwd, stderr, exit codes, and state checksums.
- Actual result: 
- Status: NOT RUN

### MC-305
- Required for acceptance: YES
- Exclusive resources: file:fixture-state
- Depends on: none
- Exact action: Run `uncle --audit` with a stub driver that writes no audit-verdict file and exits 0, then with one writing a not-READY verdict and exiting 3, and with a state file value containing an ESC byte.
- Expected result: Missing verdict prints `verdict: UNKNOWN` and exits $UNCLE_REFUSE_CODE; the not-READY run exits with the driver's status 3; no control characters appear in any printed output.
- Evidence to capture: Stdout/stderr (checked for control bytes via hexdump), and exit codes.
- Actual result: 
- Status: NOT RUN

### MC-403
- Exclusive resources: none
- Depends on: none
- Exact action: Run `uncle --runs`, `uncle --performance` and `uncle verify` from a scratch checkout, and run `uncle --help --audit` and `uncle --runs --audit`.
- Expected result: The three early-exit helpers behave as before. With `--help` or `--runs` first, they act in argument order and `--audit` is never parsed: help prints and exits 0, and runs lists runs.
- Evidence to capture: Outputs and exit codes of each invocation.
- Actual result: 
- Status: NOT RUN

### MC-405
- Exclusive resources: file:scratch-state
- Depends on: none
- Exact action: In a scratch change-family checkout, set the state to a mid-flight value such as an approval gate or implementation in progress, and checksum the state file. Run `uncle --audit`, then recheck the checksum.
- Expected result: The command refuses with an `Error:` naming the state, exits with the refusal code, and does not run the driver. The state file is byte-identical.
- Evidence to capture: Error message, exit code, and state checksum before and after.
- Actual result: 
- Status: NOT RUN

### MC-406
- Exclusive resources: file:scratch-worktrees
- Depends on: none
- Exact action: With two worktrees of a repo, record `git rev-parse HEAD` and `git branch --show-current` in the caller worktree. Run `uncle --audit OTHER_BRANCH` from the caller, where OTHER_BRANCH is checked out in the other worktree and in a post-implementation state. Use a stubbed or real driver.
- Expected result: The audit runs in the other worktree and writes its `.uncle/docs/FINAL_AUDIT.md` there. The caller's checkout, branch and HEAD are unchanged. The output shows the verdict line and the audit file path.
- Evidence to capture: Command output, exit code, and the caller's HEAD and branch before and after.
- Actual result: 
- Status: NOT RUN
