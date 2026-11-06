# Manual checklist

## Coverage: no-PR reasons

### MC-104
- Required for acceptance: YES
- Exclusive resources: dir:/tmp/uncle-mc-fixture
- Depends on: none
- Exact action: In the fixture, make the recorded issue ineligible to close (for example, alter the audit artifact after classification) with a READY verdict, then run publish.
- Expected result: No PR is created. A single `PR not created: issue-not-eligible:` line appears on stderr, and the finished block shows a readable label rather than a silent exit.
- Evidence to capture: Stderr transcript, finished block text, and the gh stub log.
- Actual result: 
- Status: NOT RUN

## Coverage: unattended draft

### MC-106
- Required for acceptance: YES
- Exclusive resources: dir:/tmp/uncle-mc-fixture
- Depends on: none
- Exact action: In the fixture, run an unattended finish (UNCLE_AUTO_PUBLISH path) with a non-READY audit verdict and gates otherwise satisfied.
- Expected result: A draft PR is created. The stderr line reads `PR published as unreviewed draft: published-draft-unreviewed: verdict <class>`, and the finished block does not say plain `published`.
- Evidence to capture: Stderr transcript, finished block text, and the gh stub log showing the draft flag.
- Actual result: 
- Status: NOT RUN

### MC-200
- Exclusive resources: none
- Depends on: none
- Exact action: In a disposable fixture git repo (signing disabled, bare local remote, gh stubbed), source the finished change-pr.sh and call change_pr_publish with a tree that differs from the attested tree (modify a tracked file), then with a non-READY verdict and override unavailable; observe stderr and whether handoff/push occurs.
- Expected result: No PR is created and no push happens in either case; each shows existing diagnostics plus exactly one new line beginning 'PR not created: tree-mismatch' or 'PR not created: verdict-not-ready'; function still returns 0.
- Evidence to capture: Captured stderr/stdout, return code, and the remote's ref list showing no pushed branch.
- Actual result: 
- Status: NOT RUN

### MC-201
- Exclusive resources: none
- Depends on: none
- Exact action: In a disposable fixture repo with a ready verdict, an ORIGIN_FILE for an ineligible issue and gh stubbed, call change_pr_publish; then repeat with an empty ORIGIN_FILE and a passing tree.
- Expected result: First run records issue-not-eligible, prints one 'PR not created: issue-not-eligible' line and creates no PR; the empty-ORIGIN_FILE run skips the issue gate, reaches handoff, and never reports issue-not-eligible.
- Evidence to capture: Stderr output and reported reason for each run, plus whether the stubbed gh pr create was invoked.
- Actual result: 
- Status: NOT RUN

### MC-204
- Exclusive resources: none
- Depends on: none
- Exact action: Run the fixture publish unattended (UNCLE_AUTO_PUBLISH=1) over a non-READY verdict with a stubbed handoff that succeeds, then render the finished block with CHANGE_PR_EXTRAS_REASON set to an unknown multi-line value.
- Expected result: The reason is published-draft-unreviewed and stderr names the verdict and states draft; the unknown/malformed value renders as the publication-pending label and is never echoed verbatim.
- Evidence to capture: Stderr line and finished-block output for both runs.
- Actual result: 
- Status: NOT RUN

## resources

### MC-300
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a disposable temp git repo (signing disabled) with a bare local remote and a stub `gh` on PATH, run a finished change through change_pr_publish with a READY verdict and a matching tree; capture stderr and the finished-block text.
- Expected result: Branch is pushed to the local remote, the stub gh pr create is invoked, the finished block shows the `published` label, and not `publication pending`.
- Evidence to capture: Remote ref listing, stub gh call log, stderr and finished-block output.
- Actual result: 
- Status: NOT RUN

### MC-301
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a fixture repo, trigger each no-PR path in turn (validate failure, verdict not READY with override declined, issue_close_eligible failure, tree differing from attested, handoff exit nonzero); capture stderr and finished-block output for each.
- Expected result: Each path creates no PR, prints exactly one new line `PR not created: <key>: <detail>` with a distinct key (validate-failed, verdict-not-ready, issue-not-eligible, tree-mismatch, handoff-failed), existing diagnostics remain, and the finished block shows the matching label; the driver exits 0.
- Evidence to capture: Per-path stderr, stub gh log showing no pr create, finished-block text, exit status.
- Actual result: 
- Status: NOT RUN

### MC-302
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the unattended path (UNCLE_AUTO_PUBLISH=1) in a fixture with a NOT_READY verdict and a stubbed gh that reports success, then view stderr and the finished block.
- Expected result: A draft PR is created, the stderr line reads `PR published as unreviewed draft: published-draft-unreviewed: verdict <class>`, and the finished block says draft, not ready or plain published.
- Evidence to capture: stderr line, stub gh args showing draft flag, finished-block text.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Make the stub engine and gh emit a canary token and a credentialed URL (https://user:SECRET@host/repo) during a failing handoff, then inspect the `PR not created:` line and the finished block by eye.
- Expected result: Neither the canary token, the credentialed URL, nor any gh/engine output appears in the reason line or the finished block; only the key, a static message and the numeric exit code.
- Evidence to capture: Captured stderr and finished block with the canary searched for visually.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a disposable fixture repo (signing disabled, local bare remote, gh stubbed on PATH) with a READY verdict and an attested tree, run the finished-run publish path in attended mode and note the finished block and stderr.
- Expected result: Handoff runs (push and PR create via the stubbed gh), the finished block shows the 'published' label rather than 'publication pending', and no 'PR not created:' line appears.
- Evidence to capture: Terminal transcript of stdout and stderr, the stubbed gh call log, and the finished block text.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a fixture repo, run the unattended publish path (UNCLE_AUTO_PUBLISH=1, origin recorded, CLOSE_ISSUE=1) twice: once with a READY verdict and once with a NOT_READY verdict. Record stdout, stderr and the finished block each time.
- Expected result: Both runs publish without opening a dialog. The READY run reports 'published'. The NOT_READY run creates a draft and reports published-draft-unreviewed, with a stderr line naming the verdict and saying it is an unreviewed draft. Neither run reports 'publication pending'.
- Evidence to capture: Transcripts of both runs, the stubbed gh call log showing draft vs ready, and the finished block text.
- Actual result: 
- Status: NOT RUN

### MC-403
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a fixture repo with a non-READY verdict, run attended publish and decline the override prompt. Then repeat with a modified tracked file so the tree differs from the attested tree.
- Expected result: Neither run pushes or creates a PR; the gh stub is never called for PR creation. Each prints exactly one new 'PR not created: <key>: <detail>' stderr line (verdict-not-ready, then tree-mismatch) alongside the existing 'PR pending:' and 'Publish refused' messages, which still appear. The driver still exits 0.
- Evidence to capture: Stderr and stdout transcripts for both runs, the gh stub call log (empty for PR creation), and the exit status.
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: In a fixture repo, make the stubbed gh or the git push fail so that handoff exits nonzero (once by declining consent, once by a push failure). Then run a rerun case where the PR was already created and handoff exits 0 with the journal phase 'created'.
- Expected result: Nonzero handoff runs report handoff-failed, and the stderr line includes the exit code. The already-created rerun reports published. In every case the driver still exits 0.
- Evidence to capture: Stderr transcripts and finished blocks for each scenario, plus the driver exit status.
- Actual result: 
- Status: NOT RUN

### MC-406
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the headless path (no TTY, no completed signed commit) in a fixture repo. Then run it with a completed signed commit present and a publish that sets a reason.
- Expected result: With no completed commit, the output says 'PR handoff disabled or unattended' and the reason is handoff-disabled, with no PR created. With a completed commit, the reason set by publish survives and is not overwritten with publication-pending.
- Evidence to capture: Stdout and stderr transcripts and the finished block text for both runs.
- Actual result: 
- Status: NOT RUN

### MC-407
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a no-PR failure case and a handoff-failure case in a fixture whose stub remote URL contains a canary token (https://user:CANARY-TOKEN@example.invalid/repo.git) and where the stubbed gh prints CANARY-TOKEN on failure. Inspect the full stderr and finished block by eye.
- Expected result: The 'PR not created:' line holds only the reason key, a static message, and the numeric exit code where applicable. The canary token, the credentialed URL and any gh output do not appear in it or in the finished block.
- Evidence to capture: Full stderr and finished-block transcripts with a search for CANARY-TOKEN showing no match in the reason line or finished block.
- Actual result: 
- Status: NOT RUN
