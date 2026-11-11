# Manual checklist

## Freeze call-site execution

### MC-901
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In disposable fixture roots, exercise the actual publish branch in scripts/lib/change-pr.sh, finalize_no_pr_worktree in scripts/from-issue.sh, and completion merge branch in scripts/stagegate.sh. Mock network, commit, merge and signing operations. Record the target root and marker existence at each mocked operation. Exercise successful and failed push outcomes without publishing anything.
- Expected result: Successful publish freezes the intended project root after push success. Failed push creates no marker. Finalize and merge freeze the intended root before their mocked commit operations. No real signer is invoked.
- Evidence to capture: Call trace with root paths, operation order, marker existence and mocked outcomes.
- Actual result: 
- Status: NOT RUN

## Failed-operation recovery

### MC-902
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Exercise both finalize and merge failure branches in isolated disposable fixtures with commit and merge operations mocked to fail. Test an initially absent marker and a pre-existing marker separately. After failure, retry normalization through uncle_gitignore.ensure() in the continuing workflow environment, using an unchanged pre-attempt byte snapshot of a legacy .gitignore.
- Expected result: A marker created by the failed attempt is removed and retry normalization works. A pre-existing marker is preserved and .gitignore remains byte-identical. No real commit or signer is invoked.
- Evidence to capture: Before/after marker existence, original and resulting .gitignore bytes, inherited guard value and mocked failure trace for both call sites.
- Actual result: 
- Status: NOT RUN

## Freeze persistence failure

### MC-903
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In disposable roots with legacy and initially absent .gitignore cases, force marker creation to fail with a mocked permission error. Exercise freeze() followed by ensure() in-process, then each actual workflow call site's failure handling with publishing and commit operations mocked. Invoke the existing CLI in a child process and a resumed step inheriting that run's environment. Capture bytes or absence before invocation and do not refresh the snapshot.
- Expected result: freeze() returns false without raising. Each call site emits a visible warning. In-process, child-process and resumed-step normalization leave existing bytes unchanged and absent files absent through the in-process record or inherited UNCLE_GITIGNORE_FROZEN guard.
- Evidence to capture: Injected error, return values, warnings, child/resumed environment guard and unchanged byte snapshots or absence checks.
- Actual result: 
- Status: NOT RUN

## Fresh run preservation

### MC-904
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In an isolated fixture, freeze a project root containing a legacy .gitignore. Record marker existence and .gitignore bytes. Create fresh workflow run state on that same root through the normal restart path, then invoke the existing uncle_gitignore.py CLI against it without an inherited freeze environment variable.
- Expected result: Fresh run state preserves .uncle/workflow/gitignore-frozen, and .gitignore remains byte-identical to the original snapshot.
- Evidence to capture: Restart path used, marker existence before and after, CLI environment and byte comparison.
- Actual result: 
- Status: NOT RUN
