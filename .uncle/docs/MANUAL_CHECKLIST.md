# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a fixture git repo whose tracked .gitignore lacks the managed block, launch the Uncle TUI, let it load config, touch .uncle/config to trigger a config-stamp reload, then switch projects and back; run `git status --porcelain --untracked-files=no` and diff .gitignore after each step.
- Expected result: Tracked status stays empty and .gitignore bytes never change; .git/info/exclude holds the canonical managed block exactly once.
- Evidence to capture: Terminal output of git status after each step, the .gitignore checksum before and after, and the contents of .git/info/exclude.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a fixture repo whose tracked .gitignore holds a legacy bare `.uncle` line, start the TUI, then reload config and switch projects twice for the same root; capture stderr.
- Expected result: Exactly one stderr line naming `.gitignore` and `worktree` appears for that root in the process, no further notice on later reloads, and the tracked .gitignore is unchanged.
- Evidence to capture: Captured stderr text showing one notice line, plus the .gitignore checksum before and after.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a real change request with no PR publish to completion, then run `git status --porcelain --untracked-files=no` in the checkout.
- Expected result: The run reaches COMPLETE and tracked status is empty. The completion guard prints nothing on stderr.
- Evidence to capture: Run completion output and the empty git status output.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: During a change run, after the audit and attestation, modify the worktree's tracked .gitignore (add a managed line) and also stage an extra file `.uncle/secret`, then attempt publish.
- Expected result: Publish stops with a nonzero, non-COMPLETE result, and stderr names `.gitignore` and `.uncle/secret` with the reason; no PR is created from the altered tree.
- Evidence to capture: The publish command output, exit status, and the stderr lines naming the offending paths.
- Actual result: 
- Status: NOT RUN

### MC-106
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: After a completed run's PR is published, make an unrelated tracked file dirty in the finished worktree and trigger automatic post-PR removal; then repeat with a clean worktree.
- Expected result: Removal is refused and names the dirty tracked file in the dirty case; the clean worktree is removed.
- Evidence to capture: The removal output for both cases and the worktree listing afterward.
- Actual result: 
- Status: NOT RUN

### MC-107
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a fixture repo with a linked worktree and no legacy bare `.uncle` line, create files under `.uncle/docs/`, `.uncle/workflow/` and `.uncle/attestation.json` after the TUI has run; run `git status` and `git check-ignore -v` for each path in the main root and in the linked worktree.
- Expected result: `.uncle/docs/` and the attestation file show as visible (not ignored) in both checkouts, and `.uncle/workflow/` is ignored.
- Evidence to capture: The git status and check-ignore output for each path in both checkouts.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-200
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a disposable fixture git repo with a tracked .gitignore lacking the managed block, launch the Uncle TUI on it, trigger a config-stamp reload by touching .uncle/config, then switch projects away and back; run `git status --porcelain --untracked-files=no` and compare .gitignore bytes after each step.
- Expected result: Tracked status stays empty and .gitignore bytes are unchanged after startup, reload and project switch; the canonical managed block appears exactly once in .git/info/exclude.
- Evidence to capture: Before/after checksums of .gitignore, porcelain output after each step, and the contents of .git/info/exclude.
- Actual result: 
- Status: NOT RUN

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a fixture repo whose tracked .gitignore contains a legacy bare `.uncle` line, start the TUI, reload twice and switch projects away and back, noting stderr output and then `git status --porcelain --untracked-files=no`.
- Expected result: The TUI prints at most one stderr line per project root that contains both `.gitignore` and `worktree`; no tracked file is modified and the run is not treated as a failure.
- Evidence to capture: Captured stderr showing the single notice line, plus unchanged .gitignore checksum and empty porcelain output.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: fixture:change-run-nopr
- Depends on: none
- Exact action: Complete a change run in a fixture project without creating a PR, then run `git status --porcelain --untracked-files=no` in the checkout.
- Expected result: Tracked status is empty and the run reports completion; if any tracked file were dirty, the run would name it and not report COMPLETE.
- Evidence to capture: Completion output and porcelain output.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: fixture:change-run-publish
- Depends on: none
- Exact action: In a run that has been audited and attested, modify .gitignore (for example append a managed line) in the worktree after attest and then attempt to publish the PR.
- Expected result: Publish stops with a nonzero exit and a stderr message naming .gitignore; no PR commit is created; the same refusal occurs for any other modified tracked file.
- Evidence to capture: Publish command output including exit status and the offending path message.
- Actual result: 
- Status: NOT RUN

### MC-206
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run `git check-ignore -v` against .uncle/docs/ files and .uncle/workflow/ files in a root without legacy lines and in a linked worktree after worktree creation, then in a root with a legacy bare `.uncle` line.
- Expected result: In the no-legacy root and the linked worktree, .uncle/docs/ and attestation files are not ignored while .uncle/workflow/ is ignored; in the legacy root docs are reported hidden, which is the documented expected case.
- Evidence to capture: check-ignore output for each location and path.
- Actual result: 
- Status: NOT RUN

### MC-207
- Required for acceptance: YES
- Exclusive resources: fixture:change-run-pr
- Depends on: MC-202
- Exact action: After a completed PR run, let the post-PR automatic worktree removal proceed; then repeat in a second worktree with an extra tracked file modified.
- Expected result: The clean finished worktree is removed automatically; the worktree with another dirty tracked file is refused and kept.
- Evidence to capture: Removal command output and `git worktree list` before and after for both cases.
- Actual result: 
- Status: NOT RUN

## resources

### MC-300
- Required for acceptance: YES
- Exclusive resources: dir:fixture-repo-tui
- Depends on: none
- Exact action: In a disposable fixture git repo whose tracked .gitignore lacks the managed block, start the Uncle TUI, then trigger a config-stamp reload (touch .uncle/config) and a project switch to another fixture repo and back. Afterwards run `git status --porcelain --untracked-files=no` and diff .gitignore against its original bytes in each repo.
- Expected result: No tracked file is modified in either repo and .gitignore bytes are unchanged; .git/info/exclude holds the canonical managed block exactly once.
- Evidence to capture: Terminal output of git status, a diff/checksum of .gitignore before and after, and the contents of .git/info/exclude.
- Actual result: 
- Status: NOT RUN

### MC-301
- Required for acceptance: YES
- Exclusive resources: dir:fixture-repo-legacy
- Depends on: none
- Exact action: In a disposable fixture repo whose tracked .gitignore holds a legacy bare `.uncle` line, start the TUI and reload the project twice. Observe stderr/terminal output and run `git status --porcelain --untracked-files=no`.
- Expected result: Exactly one deferral notice line mentioning .gitignore and worktree appears for that root in the process; no tracked file is modified.
- Evidence to capture: Captured terminal output showing a single notice line, plus git status and .gitignore checksum.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: dir:fixture-repo-run
- Depends on: MC-302
- Exact action: After the run in a fixture repo reaches attestation but before publish, append a line to a tracked file (and separately to .gitignore, only a managed line), then resume publish each time.
- Expected result: Publish refuses and exits non-COMPLETE, printing each offending file name and reason on stderr; no PR commit includes the altered content.
- Evidence to capture: Stderr output naming the files, the exit status, and the absence of the altered content in the commit tree.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: dir:fixture-repo-removal
- Depends on: none
- Exact action: After a PR is published from a finished run worktree, let auto-removal run; then repeat in another fixture where a tracked file is left dirty in the worktree.
- Expected result: The clean worktree is removed automatically; the worktree with a dirty tracked file is refused removal with a message naming the dirty file.
- Evidence to capture: Terminal output for both cases and `git worktree list` afterward.
- Actual result: 
- Status: NOT RUN

### MC-305
- Required for acceptance: YES
- Exclusive resources: dir:fixture-repo-ignore
- Depends on: none
- Exact action: In a fixture repo, create a linked worktree after the TUI has written the exclude block, add files under .uncle/docs/, .uncle/workflow/ and .uncle/attestation.json, and run `git status --short` and `git check-ignore -v` on each from both the main checkout and the linked worktree.
- Expected result: .uncle/workflow/ is ignored; .uncle/docs/ and attestation files appear as untracked and are not reported ignored, in both checkouts.
- Evidence to capture: git status and check-ignore output from both checkouts.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a throwaway git repo whose tracked .gitignore lacks the managed block, launch the Uncle TUI against it, switch config (touch .uncle/config), switch projects and back, then run `git status --porcelain --untracked-files=no` and `git diff -- .gitignore`.
- Expected result: No tracked file is modified and .gitignore bytes are unchanged; `.uncle/docs/` files still appear in `git status` while `.uncle/workflow/` stays ignored.
- Evidence to capture: Terminal transcript of the git status/diff output and `git status --porcelain --ignored` showing docs visible and workflow ignored.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a throwaway repo whose tracked .gitignore has a legacy bare `.uncle` line, start the TUI, reload config and switch projects twice, and watch stderr and the TUI output.
- Expected result: The tracked .gitignore is untouched; exactly one deferral notice mentioning .gitignore and worktree appears per project root per process, and no repeat on later reloads.
- Evidence to capture: Captured stderr/TUI text showing a single notice, plus unchanged .gitignore bytes.
- Actual result: 
- Status: NOT RUN

### MC-404
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Complete a real change request end to end with PR publication, then in the main checkout and the finished worktree run `git status --porcelain --untracked-files=no`; confirm the worktree is auto-removed after the PR.
- Expected result: Both checkouts report empty tracked status, the PR .gitignore equals the audited one, and the worktree is removed without a refusal.
- Evidence to capture: Run completion log, git status output, and worktree list after removal.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: After audit/attest in a fixture run, modify .gitignore (add one line) and separately stage a file under .uncle/ (e.g. .uncle/secret), then attempt to publish each time.
- Expected result: Publish exits non-COMPLETE each time, with stderr naming .gitignore or .uncle/secret as the offending path, and no PR commit is created.
- Evidence to capture: Publish command output with exit codes and stderr text.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Complete a change run with no PR in a fixture repo and check `git status --porcelain --untracked-files=no`; then repeat after dirtying another tracked file before completion.
- Expected result: The clean run completes with empty tracked status; the dirty run is not reported COMPLETE and names the dirty file.
- Evidence to capture: Completion output for both runs and the git status output.
- Actual result: 
- Status: NOT RUN

### MC-407
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: With a finished worktree after PR, dirty an unrelated tracked file and trigger post-PR auto-removal; then revert it and trigger removal again.
- Expected result: Removal is refused while the unrelated tracked file is dirty and succeeds once the worktree is clean.
- Evidence to capture: Removal output for both attempts and the worktree list.
- Actual result: 
- Status: NOT RUN
