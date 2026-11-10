# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: dir:scratch-handoff-repo
- Depends on: MC-100
- Exact action: Apply the MC-100 hand-off changes to a copy of the base in a scratch repo, commit it with signing disabled, and run `uncle verify --tree <commit>`; repeat with a signer configured and with none.
- Expected result: Signed run exits 0; unsigned run reports an unauthenticated-attestation finding with the pinned exit code, never a 'no attestation' finding; the .sig is listed only for the signed run.
- Evidence to capture: Exit codes and verify output for both runs, plus the changes list showing .sig presence or absence.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: dir:scratch-handoff-repo
- Depends on: none
- Exact action: Run the hand-off on an envelope-enabled run whose final audit verdict is NOT READY without a matching release_skipped, then again with an empty envelopes directory.
- Expected result: Each run prints 'PR pending: Attestation blocked: ...', exits non-zero with reason handoff-failed, and no handoff.json is written.
- Evidence to capture: Console output, exit codes, and a directory listing showing no handoff.json.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: dir:scratch-handoff-repo
- Depends on: none
- Exact action: Run the hand-off twice in a row on the same journal, then attempt a normal publish on that journal; separately, on a journal in phase 'prepared', attempt the hand-off.
- Expected result: The rerun leaves audited_tree and tree unchanged; the normal publish after hand-off refuses with the 'handed off to the host' message; the hand-off on a prepared journal fails with handoff-failed.
- Evidence to capture: audited_tree and tree from both handoff.json files, plus the refusal messages and exit codes.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: dir:scratch-handoff-repo
- Depends on: none
- Exact action: Place a symlink at .uncle/attestation.json (then at .uncle/attestation.sig) pointing outside the repo, and run the hand-off.
- Expected result: The hand-off refuses with 'Attestation blocked: <path> is a symlink', writes nothing through the link, and creates no handoff.json.
- Evidence to capture: Console output and unchanged contents of the link target.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-202
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a hand-off on an envelope-enabled fixture whose audit is NOT READY with no matching release_skipped, and again with an empty envelopes directory (manifest present); also repeat the NOT READY case with a stale release_skipped set in the journal.
- Expected result: Each run exits non-zero printing `PR pending: Attestation blocked: ...`, reports handoff-failed, writes no handoff.json, and leaves no new `.uncle/attestation.*` files and an unchanged journal; the stale release_skipped is ignored.
- Evidence to capture: Exit codes, stderr/stdout text, directory listing showing no handoff.json or attestation files, journal before/after.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Place a symlink (including a dangling one) at `.uncle/attestation.json`, then separately at `.uncle/attestation.sig`, pointing outside the repo, and run the hand-off.
- Expected result: The hand-off refuses with `Attestation blocked: <path> is a symlink`, exits non-zero, does not write through the link (the target outside the repo is unchanged), and writes no handoff.json.
- Evidence to capture: Command output, exit code, target file hash before/after, absence of handoff.json.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: After a successful hand-off, attempt a normal publish on the same journal; separately, on a fixture whose journal phase is 'prepared', attempt the hand-off.
- Expected result: Normal publish after hand-off refuses with exit 3 `PR pending: this change was handed off to the host; ...`; hand-off after a prepared journal refuses non-zero with handoff-failed; neither changes files or journal, and no push/gh/remote call is made.
- Evidence to capture: Exit codes, messages, journal phase before/after, absence of remote or gh invocations.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: On a base that tracks `.uncle/allowed_signers` and a stale `.uncle/attestation.sig`, run an unsigned hand-off; then alter one `changes` entry in handoff.json, apply, and run `uncle verify --tree` on that commit.
- Expected result: Tracked allowed_signers is not deleted; the stale .sig appears as action `delete` with no content; a new untracked allowed_signers is listed `add`; the tampered applied tree makes verify report a digest mismatch.
- Evidence to capture: The `changes` rows for those paths and the verify output for the tampered tree.
- Actual result: 
- Status: NOT RUN

### MC-207
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a hand-off on a fixture whose run predates envelopes (no manifest), and on a PR-body case with an unattended-audit waiver and with an override recorded.
- Expected result: The no-envelope run exits 0 with a summary-only hand-off and no attestation files; waiver NOTE and override banners appear in `pr_body` and `commit_message` exactly as the normal path words them, and are absent when neither applies.
- Evidence to capture: Exit code, handoff.json keys and `pr_body` text for each case.
- Actual result: 
- Status: NOT RUN

## resources

### MC-302
- Required for acceptance: YES
- Exclusive resources: dir:scratch-handoff-repo
- Depends on: MC-301
- Exact action: In the scratch repo, make .uncle/attestation.json a symlink to a file outside the repo, run the hand-off; then repeat with a symlink at .uncle/attestation.sig.
- Expected result: Each run exits non-zero with 'Attestation blocked: <path> is a symlink', the outside file is unchanged, and no handoff.json is written.
- Evidence to capture: Command output, exit code, outside file hash before and after, handoff directory listing.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: dir:scratch-handoff-repo
- Depends on: MC-302
- Exact action: In the scratch repo, make the envelopes manifest present but the .uncle/workflow/envelopes directory empty, then run the hand-off; separately run it on a journal with a NOT READY blocking reason and no release_skipped.
- Expected result: Both runs exit non-zero with 'PR pending: Attestation blocked: ...', report handoff-failed, leave no handoff.json and leave no new .uncle/attestation.* files.
- Evidence to capture: Output text, exit codes, absence of handoff.json, directory listing of .uncle.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: dir:scratch-apply-repo
- Depends on: MC-301
- Exact action: Run a successful hand-off, apply handoff.json changes onto a copy of the base commit in a second scratch repo, commit it, and run scripts/uncle-verify.py with --tree on that commit; then alter one changes entry and repeat.
- Expected result: The unaltered tree gets past 'no attestation' to integrity checks (exit 0 if signed); the altered tree reports a digest mismatch and fails.
- Evidence to capture: uncle-verify output and exit codes for both runs.
- Actual result: 
- Status: NOT RUN

### MC-305
- Required for acceptance: YES
- Exclusive resources: dir:scratch-handoff-repo
- Depends on: MC-303
- Exact action: Run a normal publish attempt on a journal already hand-off-attested, then run the hand-off on a journal in phase 'prepared'.
- Expected result: Normal publish refuses with 'this change was handed off to the host'; the hand-off on a prepared journal refuses with handoff-failed; neither writes files or alters the journal.
- Evidence to capture: Output, exit codes, journal hash before and after each attempt.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch repo with no journal/PR binding, run the hand-off mode and observe the result.
- Expected result: Exit 1 with 'Hand-off failed' message about missing PR binding, and no handoff.json is written.
- Evidence to capture: stderr text, exit status, absence of handoff.json.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: After a successful envelope-enabled hand-off, attempt a normal publish on the same journal; separately, on a fresh journal already in phase 'prepared', attempt the hand-off.
- Expected result: Normal publish refuses with 'PR pending: this change was handed off to the host...'; hand-off on a prepared journal exits non-zero with handoff-failed; neither changes files or the journal.
- Evidence to capture: Both messages, exit statuses, and attestation file hashes before and after.
- Actual result: 
- Status: NOT RUN
