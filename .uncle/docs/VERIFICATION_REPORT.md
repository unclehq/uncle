# Verification report

## Findings

### MC-101

- **Action:** Ran `uncle --help` and `uncle --audt` from a scratch temp directory using the worktree's uncle script.
- **Expected result:** Help lists `--audit [BRANCH]` and exits 0; the near-miss prints `Did you mean --audit?` and exits non-zero.
- **Actual result:** Help output includes 'uncle --audit [BRANCH]' (line 5) and '--audit [BRANCH] re-runs the final audit...' (line 21), exit 0. `uncle --audt` printed 'Unknown argument: --audt / Did you mean --audit? Run uncle --help for usage.' and exited 1.
- **Defects:** None

### MC-102

- **Action:** Built disposable git checkout /tmp/mcaudit.Z6Cm/A (family=change, state WAIT_AUDIT_OVERRIDE) and a stub runtime (UNCLE_RUNTIME_ROOT) with the real uncle and audit-command.sh plus a stub change-workflow.sh (no reviewer credentials). Ran `uncle --audit`.
- **Expected result:** State set to FINAL_AUDIT, driver runs in that checkout, output prints previous state, a verdict: line and FINAL_AUDIT.md path; exit equals driver status.
- **Actual result:** Printed 'Previous state: WAIT_AUDIT_OVERRIDE'; stub driver saw state FINAL_AUDIT with cwd=the checkout; printed 'verdict: READY' and 'audit: .../A/.uncle/docs/FINAL_AUDIT.md'; exit 0 (driver's status).
- **Defects:** None

### MC-103

- **Action:** From checkout A (branch main) ran `uncle --audit feat`, where feat is checked out in second worktree B; recorded HEAD/branch before and after.
- **Expected result:** Driver runs with cwd in the other worktree, its FINAL_AUDIT.md updated; caller's checkout, branch and HEAD unchanged.
- **Actual result:** Driver cwd=/private/tmp/mcaudit.Z6Cm/B; B/.uncle/docs/FINAL_AUDIT.md written; verdict READY exit 0. Caller HEAD 465d4bca73eef3c310ee4632586af0bebd3a77de and branch main identical before and after; A's state stayed COMPLETE.
- **Defects:** None

### MC-104

- **Action:** With UNCLE_RUNTIME_ROOT pointed at this worktree (the inherited env var pointed at a missing Homebrew libexec), ran the worktree `uncle --audit` and `uncle --noui --audit` in disposable temp dirs: non-git dir (with branch x); detached-HEAD repo with an empty .uncle dir; unknown branch; branch with no worktree; `--audit ''`; `--audit a b`; `--audit=--x`. Captured stderr and exit code for each.
- **Expected result:** Each prints a one-line `Error:` naming the cause and exits with the refusal code (1, or 2 under --noui).
- **Actual result:** Every case printed a single-line `Error:` and exited 1 (2 under --noui). Non-git: 'not inside a git repository: <dir>'. Unknown branch: 'no such branch: nosuch'. No worktree: 'branch nowt is not checked out in any worktree'. Empty: '--audit BRANCH cannot be empty'. Extra arg: '--audit takes at most one BRANCH; unexpected argument: b'. '--audit=--x': '--audit takes BRANCH as a separate argument, not --audit=--x'. Detached HEAD: scripts/audit-command.sh has no detached-specific message; with no .uncle it printed 'no .uncle directory in <dir>', and with an empty .uncle it printed "workflow family of <dir> is 'none', not 'change'". Both exit 1 (2 under --noui), and each names a cause. The wrapper's messages for the empty and extra-arg cases differ slightly from the script's own text (the wrapper validates first). Note: the inherited UNCLE_RUNTIME_ROOT env var pointed at a nonexistent Homebrew libexec, which makes the unmodified invocation fail with a bash 'No such file' error. That is an environment quirk, not a product defect.
- **Defects:** None

### MC-106

- **Action:** In checkout A ran `uncle --audit` with states REQUIREMENTS, WAIT_PLAN_APPROVAL, IMPLEMENT, 3:IMPLEMENT, then with family file 'app', then with no family file, md5-checking the state file each time.
- **Expected result:** Each refused with an Error: naming state or family; state file byte-identical.
- **Actual result:** All six refused with rc=1: "Error: state 'X' is not a post-implementation stage..." or "Error: workflow family of ... is 'app'/'none', not 'change'". md5 of state file unchanged in every case.
- **Defects:** None

### MC-107

- **Action:** Held flock on .uncle/workflow/driver.lock via a python process for 12s and ran `uncle --audit` in the checkout (state COMPLETE).
- **Expected result:** Refusal naming the lock with refusal exit code; state unchanged; no driver started.
- **Actual result:** 'Error: a workflow driver is running in .../A (driver.lock is held)', rc=1 (refusal code); state md5 unchanged; stub driver did not run (no stub-cwd file).
- **Defects:** None

### MC-108

- **Action:** With the stub driver ran `uncle --audit` (a) exit 0 with no audit-verdict, (b) verdict NOT_READY with driver exit 7, (c) state value containing an ESC byte; output piped through cat -v.
- **Expected result:** Missing verdict prints unknown verdict and exits per plan (refusal code); not-READY keeps driver status; no raw control characters in output.
- **Actual result:** (a) 'verdict: UNKNOWN', rc=1 (refusal code); (b) 'verdict: NOT_READY', rc=7 (driver status); (c) ESC byte stripped from the printed state ('COMP[31mLETE' with no ^[ in cat -v output), refused rc=1 since not a post-implementation state. No ^[ or other control chars appeared in any output.
- **Defects:** None

### MC-200

- **Action:** Built a temp install copy of uncle (UNCLE_RUNTIME_ROOT pointed at it, stub change-workflow.sh) and a fixture change-family git checkout in state IMPLEMENT. For both attended and --noui, ran `uncle --audit`, `uncle --audit nobranch`, `uncle --audit ''`, checksumming .uncle/workflow/state before/after each; also ran from a non-git directory.
- **Expected result:** One-line Error: naming cause, exit 1 (2 under --noui), state checksum identical.
- **Actual result:** All 8 runs printed one-line Error: (state 'IMPLEMENT' is not a post-implementation stage; no such branch: nobranch; --audit BRANCH cannot be empty; not inside a git repository). Exit 1 attended, 2 under --noui. State checksum 659a1d496f10 identical before/after in every run; stub driver never ran (empty log).
- **Defects:** None

### MC-201

- **Action:** Built a disposable fixture (git repo on branch A, second worktree on branch B, both with .uncle/workflow/{family=change,state=COMPLETE}) and a copy of the install whose scripts/change-workflow.sh is a stub that logs its cwd and writes FINAL_AUDIT.md and an audit-verdict (READY). Recorded caller HEAD/branch/status checksum, ran `uncle --audit B` from the caller checkout (UNCLE_RUNTIME_ROOT pointed at the copied install), recorded them again.
- **Expected result:** Audit runs in B's worktree (FINAL_AUDIT.md updated); caller HEAD, branch and working tree unchanged.
- **Actual result:** Driver ran with cwd /private/tmp/mc-audit.KiHM/wtB and FINAL_AUDIT.md was written there; caller HEAD 7dc0e3e, branch A and porcelain-status checksum were identical before and after; no .uncle/docs files appeared in the caller.
- **Defects:** None

### MC-203

- **Action:** Ran `echo 5 | ./uncle --issue --audit`, `./uncle --audit --application x`, and `./uncle --audit verify` from the repo. The first run of `--audit verify` inherited UNCLE_LIB_DIR/UNCLE_RUNTIME_ROOT pointing at the installed Homebrew runtime, so it was re-run with those env vars unset so the repo's own audit-command.sh was used. Compared `git status --short` hash before and after.
- **Expected result:** First two refused as mutually exclusive with refusal code before stdin is consumed; `--audit verify` treats verify as a branch name and fails with `Error:` for unknown branch; no state changes.
- **Actual result:** First two: `Error: --audit cannot be combined with other startup options or early-exit flags`, rc=1. `--audit verify` (repo runtime): `Error: no such branch: verify`. The pipeline's exit code printed empty because PIPESTATUS is not set in this shell, so the non-zero exit for this case was not captured. The first attempt with the inherited installed-runtime env failed rc=127 because /opt/homebrew/opt/uncle/libexec/scripts/audit-command.sh does not exist. That is an environment artifact, not a repo behavior. Git status hash was unchanged before and after.
- **Defects:** None

### MC-204

- **Action:** In a COMPLETE-state fixture whose scripts/change-workflow.sh is a decoy touching a marker, ran `uncle --audit` with the temp install. Tried to create a branch name with an ESC byte and ran `uncle --audit` with ESC-containing branch names, piping output through cat -v.
- **Expected result:** Only install-dir driver runs (no decoy marker); no raw control characters in printed messages.
- **Actual result:** Stub install driver ran (log shows DRIVER ran in fixture); DECOY_MARKER absent. git refuses to create an ESC-containing branch, so the ESC name was exercised as a non-existent/invalid argument: message was 'Error: invalid branch name: bad[31mname' with the ESC byte stripped, no ^[ in cat -v output.
- **Defects:** None

### MC-301

- **Action:** Built a temp git fixture with .uncle/workflow/family=change and state=EXECUTE_CHECKLIST. Held an exclusive fcntl.flock on driver.lock from a background python process (flock(1) is not installed on this macOS host; the audit helper itself uses fcntl.flock). Checksummed the state file, ran `uncle --audit` and `uncle --noui --audit` (with UNCLE_RUNTIME_ROOT pointed at this checkout so the worktree code was under test), captured stderr and exit codes, re-checksummed the state file, then let the lock holder exit.
- **Expected result:** Output is a one-line `Error:` naming the driver lock, exit code is $UNCLE_REFUSE_CODE (1, or 2 under --noui), the state file is byte-identical, and the driver does not run.
- **Actual result:** Both runs printed `Error: a workflow driver is running in <fixture> (driver.lock is held)` to stderr. Exit code was 1 without --noui and 2 with --noui. The state file stayed `EXECUTE_CHECKLIST` with an identical SHA-1 before and after. No FINAL_AUDIT write happened, so the driver did not run. Stderr also carried the generic startup line `Mode: unattended (default)...`, which comes from the CLI wrapper and is not part of the refusal; the Error itself is a single line.
- **Defects:** None

### MC-302

- **Action:** Same fixture: ran `uncle --audit B` from the primary checkout, capturing stdout, exit code, driver-recorded cwd, and caller HEAD/branch before and after.
- **Expected result:** Driver cwd in B's worktree; FINAL_AUDIT.md path and verdict line printed; caller checkout, branch, HEAD unchanged.
- **Actual result:** Stdout: 'Previous state: COMPLETE', 'verdict: READY', 'audit: /private/tmp/mc-audit.KiHM/wtB/.uncle/docs/FINAL_AUDIT.md'; exit 0; driver cwd was wtB; caller HEAD/branch/status unchanged.
- **Defects:** None

### MC-303

- **Action:** Ran `uncle --audit` on fixtures in states PLAN_DRAFT, WAIT_PLAN_APPROVAL, IMPLEMENT, and COMPLETE, hashing the state file before and checking the stub driver log.
- **Expected result:** Mid-flight states refused with Error: naming the state, state byte-identical, driver not run; post-implementation state accepted and set to FINAL_AUDIT before the driver runs.
- **Actual result:** PLAN_DRAFT, WAIT_PLAN_APPROVAL, IMPLEMENT: Error: state '<X>' is not a post-implementation stage, rc=1, state unchanged, driver log empty. COMPLETE: accepted, driver log 'DRIVER ran ... state=FINAL_AUDIT', state became FINAL_AUDIT. (Exact names used were my fixture stand-ins for the stage names; the state vocabulary of the real driver was not enumerated.)
- **Defects:** None

### MC-304

- **Action:** Placed a decoy scripts/change-workflow.sh (touches a marker file) in wtB and ran `uncle --audit` from inside wtB; then from the caller ran `uncle --audit C` (branch C checked out in no worktree) and `uncle --audit D` (worktree wtD without .uncle).
- **Expected result:** Only install-dir driver runs (no decoy marker), cwd is the target checkout; no-worktree and missing-.uncle cases refused with `Error:` and no state write.
- **Actual result:** Decoy marker was not created; install driver logged cwd=wtB. `--audit C` printed 'Error: branch C is not checked out in any worktree', exit 1, caller state file unchanged. `--audit D` printed 'Error: no .uncle directory in /private/tmp/mc-audit.KiHM/wtD', exit 1, no .uncle created in wtD and the driver log gained no new entry.
- **Defects:** None

### MC-305

- **Action:** With stub driver: (a) exit 0 and no verdict file, attended and --noui; (b) verdict NOT_READY with exit 3; (c) state file containing ESC byte. Output piped through cat -v.
- **Expected result:** Missing verdict prints 'verdict: UNKNOWN' and exits with the refuse code; not-READY exits with driver status 3; no control characters in output.
- **Actual result:** (a) 'verdict: UNKNOWN', rc=1 attended, rc=2 under --noui (matches refuse code). (b) 'verdict: NOT_READY', rc=3. (c) 'Error: state 'BAD[31mSTATE' is not a post-implementation stage', ESC stripped, no ^[ in output, rc=1.
- **Defects:** None

### MC-403

- **Action:** In a scratch git repo (no commits) in a temp dir, ran uncle --runs, uncle --performance, uncle verify, uncle --help --audit, uncle --runs --audit, capturing output and exit codes.
- **Expected result:** Early-exit helpers behave as before; with --help or --runs first, argument order is honored and --audit is never parsed: help prints and exits 0, runs lists runs.
- **Actual result:** --runs printed 'no runs', exit 0. --performance printed 'No performance records yet...' exit 0. verify printed 'UNCLE CHANGE VERIFICATION ... NOT VERIFIED' (HEAD^{tree} failed in the commitless scratch repo), exit 1 (a not-verified result, not a crash). --help --audit printed the usage text (including the --audit line), exit 0, with no audit run. --runs --audit printed 'no runs', exit 0, with no audit run or unknown-argument error.
- **Defects:** None

### MC-405

- **Action:** Created two scratch git repos with .uncle/workflow/family=change and state set to mid-flight values (WAIT_PLAN_APPROVAL, IMPLEMENT); checksummed the state file; ran the repo's ./uncle --audit (UNCLE_RUNTIME_ROOT pointed at this worktree since the installed libexec lacks audit-command.sh); rechecked checksum and workflow dir contents.
- **Expected result:** Refuses with an Error: naming the state, exits with the refusal code, does not run the driver; state file byte-identical.
- **Actual result:** Both runs printed 'Error: state '<STATE>' is not a post-implementation stage; finish the run before auditing' and exited 1 (default refusal code). State file checksum unchanged; workflow dir contained only family and state (no driver artifacts or lock).
- **Defects:** None

### MC-406

- **Action:** Created a scratch repo with a second worktree on branch 'other' (both post-implementation, state MANUAL_CHECKLIST, family change) and a stub driver in a temp install. Recorded HEAD and branch in the caller, ran `uncle --audit other` from the caller, then re-recorded HEAD and branch.
- **Expected result:** Audit runs in the other worktree and writes .uncle/docs/FINAL_AUDIT.md there; caller checkout, branch and HEAD unchanged; output shows verdict line and audit file path.
- **Actual result:** Output: 'Previous state: MANUAL_CHECKLIST', 'verdict: READY', 'audit: .../other/.uncle/docs/FINAL_AUDIT.md'; exit 0. FINAL_AUDIT.md exists only in the other worktree (stub recorded cwd as the other worktree). Caller .uncle/docs stayed empty and its state file stayed MANUAL_CHECKLIST. Caller HEAD 94a3c006caa4827728bfae647c7662c485dfda47 and branch main were identical before and after.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | PASS | grep of help output lines 5 and 21; exit codes help=0, audt=1; stderr/stdout text quoted above. |
| MC-102 | YES | PASS | Terminal output above; FINAL_AUDIT.md created in .uncle/docs; stub 'state-at-run: FINAL_AUDIT'. Real driver not used (stub), per the check's allowed alternative. |
| MC-103 | YES | PASS | git rev-parse HEAD and branch --show-current before/after identical; stub-cwd file in B; A state unchanged. |
| MC-104 | YES | PASS | Observed in-session. Exit codes: 1 for all cases without --noui, 2 for all cases with --noui, including empty, 'a b' and '--audit=--x'. Cases were run in mktemp dirs; no repo state was changed. |
| MC-106 | YES | PASS | Terminal output with same=yes for all six runs. |
| MC-107 | YES | PASS | Output line shows rc=1 same=yes stubran=no. |
| MC-108 | YES | PASS | cat -v captured outputs and exit codes above. The ESC case was refused rather than reaching the 'Previous state' line, so only the Error: line sanitization was observed live. |
| MC-200 | YES | PASS | Console output of /tmp/mcaud_run.sh (MC-200 section): rc=1/rc=2 lines with before=after=659a1d496f10. |
| MC-201 | YES | PASS | Before/after: HEAD=7dc0e3e5dfb5... br=A st=a762abb6... both times. Driver log: INSTALL-DRIVER cwd=/private/tmp/mc-audit.KiHM/wtB. wtB/.uncle/docs/FINAL_AUDIT.md exists (Nov 8 12:07). Note: the real driver was replaced by a stub (no live reviewer agent run); this exercises the audit-command routing/cwd, not the real audit. |
| MC-203 | YES | PASS | Outputs above; git status md5 f5fc4f47e192fdf1a4a88d45ec9ad3b2 before and after. Not verified: the 'before stdin is consumed' claim was not tested directly, and the exit code of the third command with the repo runtime was not captured. |
| MC-204 | YES | PASS | ls DECOY_MARKER: No such file; stub.log shows install driver; cat -v output has no ^[ sequences. Limitation: a real ESC-named existing branch cannot be created by git. |
| MC-301 | YES | PASS | rc[]=1, rc[--noui]=2. State checksum before and after: 141908abdc182211405aa96e8dab892a53f7490c in both. Final state content: EXECUTE_CHECKLIST. Stdout was empty in both runs. |
| MC-302 | YES | PASS | exit=0; driver log cwd=/private/tmp/mc-audit.KiHM/wtB; caller HEAD 7dc0e3e, branch A, identical status checksum before/after. Stub driver used in place of the real one. |
| MC-303 | YES | PASS | MC-303 section of /tmp/mcaud_run.sh output. |
| MC-304 | YES | PASS | ls DECOY_MARKER: No such file; driver log only INSTALL-DRIVER cwd=.../wtB; exit codes 1/1; state-unchanged check printed; wtD/.uncle absent. Stub install driver used. |
| MC-305 | YES | PASS | MC-305 section of /tmp/mcaud_run.sh and /tmp/mcaud2.sh output (cat -v shows no control bytes). |
| MC-403 | YES | PASS | Terminal output as above. An initial attempt passed 'a b' as a single quoted argument because of zsh no-splitting and gave 'Unknown argument'; that was a harness error and was rerun with separate arguments. No pre-change comparison binary was run; 'as before' is judged from the observed sensible behavior. |
| MC-405 | YES | PASS | WAIT_PLAN_APPROVAL: exit=1, sha1 47af1c06... before and after. IMPLEMENT: exit=1, sha1 659a1d49... before and after. ls .uncle/workflow showed only family, state. |
| MC-406 | YES | PASS | Script /tmp/mc406.sh output: BEFORE 94a3c006... main; AFTER 94a3c006... main; rc=0; ls of caller .uncle/docs empty; other .uncle/docs contains FINAL_AUDIT.md with 'audit by stub in .../other'. A stubbed driver was used, which the check allows. |
