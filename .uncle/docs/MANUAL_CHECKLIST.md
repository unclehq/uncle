# Manual checklist

## Coverage

### MC-102
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-decline
- Depends on: none
- Exact action: In a scratch repo with an existing non-empty CHANGE_REQUEST.md, run from-issue.sh change mode on a TTY and answer 'n', then empty Enter, then Ctrl-D (EOF), then 'y please'. Record sha256 of the file and a listing of .uncle/workflow before and after each run.
- Expected result: Each run exits nonzero with a message saying the existing request was left unchanged; the file hash and .uncle/workflow contents are identical to before.
- Evidence to capture: Transcripts, exit codes, and before/after hashes and listings.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-unattended
- Depends on: none
- Exact action: With an existing CHANGE_REQUEST.md, run from-issue.sh change mode once with the --unattended flag and once with UNCLE_UNATTENDED=1. Use stdin from a pipe that never writes, under a 10s timeout. Run each both without UNCLE_REPLACE_CHANGE_REQUEST and with UNCLE_REPLACE_CHANGE_REQUEST=1.
- Expected result: Without the opt-in, each run exits 1 within the timeout with a stderr message containing UNCLE_REPLACE_CHANGE_REQUEST=1, and the file is unchanged. With the exact value 1, each run proceeds and replaces the file. No run hangs.
- Evidence to capture: Exit codes, elapsed times, stderr text and file hashes for all four runs.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-optin
- Depends on: none
- Exact action: With an existing CHANGE_REQUEST.md and stdin not a TTY, run from-issue.sh change mode with request text piped in. Then try UNCLE_REPLACE_CHANGE_REQUEST set to 0, true, and empty on a TTY-less run. Finally set it to exactly 1 on a TTY.
- Expected result: Piped runs refuse with exit 1 and the opt-in message without consuming the piped input. The values 0, true and empty refuse. Exactly 1 proceeds with no prompt even on a TTY.
- Evidence to capture: Exit codes, stderr and file hashes for each run.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-skip
- Depends on: none
- Exact action: With an existing CHANGE_REQUEST.md, run from-issue.sh with UNCLE_NEW_WORKFLOW=1, with --seed-only, and as a resume of the same in-flight issue, using a TTY for each.
- Expected result: No prompt appears in any run. The resume leaves the file untouched, --seed-only does not overwrite the file, and the NEW_WORKFLOW run archives old evidence and reseeds.
- Evidence to capture: Terminal output and file hashes for each run.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-203
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the same unattended invocation with UNCLE_REPLACE_CHANGE_REQUEST=1, then with values 0, true, and empty, and also run interactively with UNCLE_REPLACE_CHANGE_REQUEST=1.
- Expected result: Exactly the value 1 replaces the file without any prompt (interactive and unattended); 0, true and empty refuse with exit 1 and leave the file unchanged.
- Evidence to capture: Transcript per value with exit code and file hash comparison.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run from-issue.sh change mode with a non-TTY stdin (piped content such as 'y') and an existing non-empty CHANGE_REQUEST.md, without the opt-in.
- Expected result: The guard refuses with exit 1 and the opt-in message, never consuming the piped input as an answer; file unchanged.
- Evidence to capture: Transcript showing exit code, stderr, and that the file hash is unchanged.
- Actual result: 
- Status: NOT RUN

### MC-205
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run from-issue.sh change mode where no prompt should occur: no CHANGE_REQUEST.md, a zero-byte one, UNCLE_NEW_WORKFLOW=1 fresh start, an in-flight same-issue resume, and SEED_ONLY=1 with an existing file.
- Expected result: No prompt text appears in any case; no-file and zero-byte cases write the file, resume leaves it untouched, NEW_WORKFLOW archives then reseeds, and SEED_ONLY leaves the existing file unmodified.
- Evidence to capture: Per-case stderr output (no prompt phrase) and resulting file state.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Place a whitespace-only CHANGE_REQUEST.md, then a symlink (to a separate target file), then a directory at that path; run interactively and answer 'n' for each, then answer 'y' for the symlink case.
- Expected result: Whitespace-only file prompts (treated as existing); symlink and directory also prompt; decline leaves everything intact; after 'y' the symlink target file is not clobbered.
- Evidence to capture: Transcript with prompts and the symlink target's hash before and after.
- Actual result: 
- Status: NOT RUN

## resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-142
- Depends on: MC-300
- Exact action: Recreate the scratch repo with an existing CHANGE_REQUEST.md, record its hash and a listing of .uncle/workflow, run from-issue.sh change mode on a TTY and answer 'n' (then repeat with an empty Enter and with Ctrl-D).
- Expected result: Each run exits nonzero with a message saying the existing request was left unchanged; the file hash and .uncle/workflow listing are identical to before.
- Evidence to capture: Transcripts, exit codes, and before/after hashes and listings.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-142
- Depends on: MC-302
- Exact action: Repeat the unattended run with UNCLE_REPLACE_CHANGE_REQUEST=1, then with values 0, true, and empty.
- Expected result: Only the exact value 1 replaces the file and proceeds without a prompt; 0, true and empty refuse with exit 1 and leave the file untouched.
- Evidence to capture: Per-value exit codes, stderr, and file hash.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: dir:scratch-repo-142
- Depends on: MC-303
- Exact action: Run from-issue.sh change mode on a repo with no CHANGE_REQUEST.md, and again with a zero-byte one, from a TTY.
- Expected result: No prompt appears in either case and the new request is written.
- Evidence to capture: Terminal transcript showing no prompt text and the written file.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch repo with no CHANGE_REQUEST.md, run scripts/from-issue.sh in change mode interactively on a TTY.
- Expected result: No replacement prompt appears on stderr and the new CHANGE_REQUEST.md is written as before.
- Evidence to capture: Terminal transcript showing no 'Proceed with the new change request and replace it? [y/N]' text and the written file.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch repo, seed a change request for issue N, then rerun from-issue.sh change mode for the same issue N so the in-flight run is current.
- Expected result: The run prints the Resuming message with no prompt, and CHANGE_REQUEST.md is byte-identical to before.
- Evidence to capture: Terminal transcript plus a hash of CHANGE_REQUEST.md before and after.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a scratch repo with an existing non-empty CHANGE_REQUEST.md, run from-issue.sh with UNCLE_NEW_WORKFLOW=1, and separately with --seed-only.
- Expected result: Neither run prompts. NEW_WORKFLOW archives the old evidence and reseeds. Seed-only leaves the existing file unmodified through the existing no-overwrite failure.
- Evidence to capture: Transcripts of both runs and the file hash after the seed-only run.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With an existing CHANGE_REQUEST.md, pipe request content into `uncle --change-request` (the stdin import path).
- Expected result: The import is rejected with the existing EXISTS message, no replacement prompt appears, and the file is unchanged.
- Evidence to capture: Command output and file hash before and after.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With an existing non-empty CHANGE_REQUEST.md from a different issue, run from-issue.sh change mode on a TTY, answer 'n', then rerun and answer 'y'.
- Expected result: The 'n' run exits nonzero with the file and .uncle/workflow unchanged. The 'y' run replaces the file and proceeds.
- Evidence to capture: Transcript of both runs, with hashes of the file and a listing of .uncle/workflow after the decline.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run from-issue.sh change mode with an existing CHANGE_REQUEST.md and stdin not a TTY (closed or piped from /dev/null), without UNCLE_REPLACE_CHANGE_REQUEST. Then repeat with UNCLE_REPLACE_CHANGE_REQUEST=1, and once more with --unattended.
- Expected result: Without the opt-in, each run exits 1 immediately with a stderr message naming UNCLE_REPLACE_CHANGE_REQUEST=1, never hangs, and leaves the file untouched. With the opt-in it proceeds and replaces.
- Evidence to capture: Transcripts with exit codes and file hashes.
- Actual result: 
- Status: NOT RUN
