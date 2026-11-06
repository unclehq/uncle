# Verification report

## Findings

### MC-104

- **Action:** Built a fixture in /tmp/uncle-mc-fixture/ineligible: sourced the real scripts/lib/change-pr.sh, READY verdict, altered FINAL_AUDIT.json after classification (hash mismatch, real hash-compare stub for issue_close_eligible), stubbed gh/engine, ran change_pr_publish then finished_extras.py print.
- **Expected result:** No PR created; single 'PR not created: issue-not-eligible:' stderr line; finished block shows readable label.
- **Actual result:** rc=0; no handoff/gh call (gh log empty). Stderr contained exactly one line 'PR not created: issue-not-eligible: the issue is not eligible to close' (plus the existing 'changed after it was classified' message). Finished block: 'PR: not created (issue not eligible)'.
- **Defects:** None

### MC-106

- **Action:** Fixture /tmp/uncle-mc-fixture/draft: NOT_READY verdict, UNCLE_AUTO_PUBLISH=1, validate stub fails first (exit 3) then passes on revalidation (override path), stubbed handoff logging 'gh pr create --draft' and writing a created/draft journal; ran real change_pr_publish and finished_extras.py print.
- **Expected result:** Draft PR created; stderr 'PR published as unreviewed draft: published-draft-unreviewed: verdict <class>'; finished block does not say plain 'published'.
- **Actual result:** rc=0; gh log shows 'gh pr create --draft'. Stderr: 'PR published as unreviewed draft: published-draft-unreviewed: verdict NOT_READY (draft, not ready for review)'. Reason=published-draft-unreviewed. Finished block: 'PR: https://github.com/o/r/pull/3 (#3) [draft]' (URL with [draft] marker, not plain 'published').
- **Defects:** None

### MC-200

- **Action:** Built a disposable fixture (bare local remote, git repo with signing disabled, gh stubbed to log+fail, engine stubbed with handoff that would git push). Sourced scripts/lib/change-pr.sh under bash and called change_pr_publish 0 twice: (1) with a modified tracked file (a.txt) vs the attested tree; (2) validate returning 3 (non-READY) with override declined/unavailable.
- **Expected result:** No PR and no push in either case; existing diagnostics plus exactly one new line 'PR not created: tree-mismatch' or 'PR not created: verdict-not-ready'; function returns 0.
- **Actual result:** Case 1 stderr: 'tracked file not clean:  M a.txt', 'path differs from the attested tree (M): a.txt', 'Publish refused: the tree differs from the audited tree.', then exactly one 'PR not created: tree-mismatch: the tree differs from the audited tree'; rc=0. Case 2: exactly one 'PR not created: verdict-not-ready: the audit verdict is not READY and no override was given'; rc=0. git ls-remote on the bare remote returned no refs; handoff.log and gh.log were never created (no handoff, no gh call).
- **Defects:** None

### MC-201

- **Action:** Read scripts/tests/pr-publish-reason-test.sh and scripts/lib/change-pr.sh. The harness builds a disposable fixture, sources change-pr.sh, stubs issue_close_eligible and the handoff, and calls change_pr_publish. I ran the script once (bash scripts/tests/pr-publish-reason-test.sh) and read the assertions for the ineligible-issue case (STUB_ISSUE=1) and the empty-ORIGIN_FILE case (ORIGIN_EMPTY=1).
- **Expected result:** The ineligible-issue run records issue-not-eligible, prints exactly one 'PR not created: issue-not-eligible' line and makes no handoff or PR. The empty-ORIGIN_FILE run skips the issue gate, reaches handoff and never reports issue-not-eligible.
- **Actual result:** The script finished with 'pr-publish-reason-test: 156 passed, 0 failed'. In the ineligible-issue case, expect_nopr asserted reason issue-not-eligible, exactly one keyed 'PR not created: issue-not-eligible' stderr line with no token or URL, zero handoffs, and the issue gate invoked once. In the empty-origin case, the reason was 'published', handoffs were 1, issue-gate calls were 0, and stderr did not contain issue-not-eligible. Side note: the run printed non-fatal 'issue.calls: No such file or directory' stderr noise from the test harness (line 91). It did not affect any assertion.
- **Defects:** None

### MC-204

- **Action:** Ran scripts/tests/pr-publish-reason-test.sh (fixture publish with UNCLE_AUTO_PUBLISH=1 over non-READY verdict with stubbed succeeding handoff; finished_extras.py print with unknown/multi-line/credential-bearing reasons). Inspected change-pr.sh lines 189-198 and finished_extras.py REASONS/FALLBACK.
- **Expected result:** Reason is published-draft-unreviewed and stderr names verdict and states draft; unknown/malformed reason renders as publication-pending label and is never echoed verbatim.
- **Actual result:** Test output: 156 passed, 0 failed. change-pr.sh sets CHANGE_PR_EXTRAS_REASON=published-draft-unreviewed and emits stderr 'PR published as unreviewed draft: published-draft-unreviewed: verdict <class> (draft, not ready for review)'. Unknown values (including 'bad\nvalue', URL with token, 'published; rm -rf', empty) render 'PR: not created (publication pending)' with no echo. Benign 'No such file' stderr noise from test helper redirects (lines 90/91) did not affect results. I did not separately run the stub fixture by hand beyond the test.
- **Defects:** None

### MC-300

- **Action:** Ran a temp script (/tmp/mc300.sh) in a disposable git repo (signing disabled) with a bare local remote and a stub gh on PATH. It sourced the real scripts/lib/change-pr.sh with the real assert_tree_matches_attested and a hash-checking issue gate. The engine handoff was stubbed to git push and call stub gh pr create. Ran change_pr_publish with a READY verdict and a matching tree, then rendered the finished block with finished_extras.py print using the resulting reason.
- **Expected result:** Branch is pushed to the local remote, the stub gh pr create is invoked, the finished block shows the `published` label, and not `publication pending`.
- **Actual result:** rc=0; reason=published. The remote has refs/heads/feat. The gh stub log has 'gh pr create --title t --body b'. Stderr was 'PR created (verdict READY): ready for review.' with no 'PR not created' line. The finished block printed 'PR: published' and did not contain 'publication pending'.
- **Defects:** None

### MC-301

- **Action:** Read scripts/tests/pr-publish-reason-test.sh and ran it (fixture publish with stubbed engine/gh/gates). It drives change_pr_publish through each no-PR path: validate failure (exit 1, 2), verdict not READY with override declined (interactive and unattended), revalidate failure, issue_close_eligible failure, tree mismatch (stubbed and attested), and handoff nonzero exit (1 and 3). It also covers handoff-incomplete. It checks stderr, reason and return code.
- **Expected result:** Each path creates no PR and prints exactly one `PR not created: <key>: <detail>` line with a distinct key (validate-failed, verdict-not-ready, issue-not-eligible, tree-mismatch, handoff-failed). Existing diagnostics remain, the finished block shows the matching label, and the driver exits 0.
- **Actual result:** Test output: 'pr-publish-reason-test: 156 passed, 0 failed'. expect_nopr asserted rc 0, exact reason key, exactly one 'PR not created:' line starting with the key, and no canary or URL in the line. Handoff was not invoked for validate-failed, issue-not-eligible or tree-mismatch. Existing stderr 'tracked file not clean', 'path differs from the attested tree' and 'Publish refused' were retained. Section 8 of the script covers the finished_extras.py labels. Caveat: I did not separately view the rendered finished block by eye; label mapping is verified by the script's assertions only. The run also printed harmless 'No such file' noise for handoff.calls/issue.calls from the stub harness.
- **Defects:** None

### MC-302

- **Action:** Sourced scripts/lib/change-pr.sh in a temp fixture (origin bound, verdict NOT_READY), stubbed change_pr_engine (handoff writes a journal with phase=created, draft=true, and records a 'pr create --draft' marker), ran change_pr_publish with UNCLE_AUTO_PUBLISH=1, captured stderr, then rendered the finished block with scripts/lib/finished_extras.py print using the resulting reason.
- **Expected result:** Draft PR created; stderr reads 'PR published as unreviewed draft: published-draft-unreviewed: verdict <class>'; finished block says draft.
- **Actual result:** rc=0, reason=published-draft-unreviewed. stderr: 'PR published as unreviewed draft: published-draft-unreviewed: verdict NOT_READY (draft, not ready for review)'. Finished block: 'PR: https://github.com/o/r/pull/3 (#3) [draft]'. Caveat: the engine and gh were stubbed, so the real gh --draft flag was not exercised; the draft marker came from the stub's journal. Also pr-publish-reason-test.sh ran 156 passed, 0 failed.
- **Defects:** None

### MC-303

- **Action:** Ran scripts/tests/pr-publish-reason-test.sh. Its stub engine and gh emit CANARY-TOKEN-9f3a and https://user:CANARYPASS@example.com/x.git on stdout and stderr during failing handoff and published paths. It then checks the captured `PR not created:` reason and the `PR ` lines. I read the stub definitions at lines 17-18, 65-82 and the canary assertions at lines 102 and 151-154. I did not inspect a live finished block by eye.
- **Expected result:** No canary token, credentialed URL or gh/engine output appears in the reason line or finished block. Only the key, a static message and the numeric exit code appear.
- **Actual result:** The script finished with 156 passed, 0 failed. This includes the 'canary reason' and 'canary pr line' hasnt-CANARY assertions and the per-reason 'no token' assertions. The script printed harmless 'No such file or directory' noise for handoff.calls and issue.calls writes in stub subshells, with no effect on assertions.
- **Defects:** None

### MC-401

- **Action:** Ran change_pr_publish in attended mode (INTERACTIVE=1) from a temp script derived from scripts/tests/pr-publish-reason-test.sh harness, in a disposable git fixture (gpgsign disabled, attested FINAL_AUDIT.json hash bound to a READY verdict) using the REAL assert_tree_matches_attested; then rendered the finished block via finished_extras.py print --kind change --reason <reason>.
- **Expected result:** Handoff runs, finished block shows 'published' label rather than 'publication pending', and no 'PR not created:' line appears.
- **Actual result:** RC=0, reason=published, handoff invoked once. Stderr: 'PR created (verdict READY): ready for review.' with no 'PR not created:' line. Finished block line: 'PR: published' (not 'publication pending').
- **Defects:** None

### MC-402

- **Action:** Ran scripts/tests/pr-publish-reason-test.sh (stubbed gh/handoff fixture harness exercising change_pr_publish) and inspected its READY and auto-publish NOT_READY cases (lines 134-141) plus the source in scripts/lib/change-pr.sh. This is the project's fixture-based run, not a separate hand-built fixture repo with stdout/stderr transcripts.
- **Expected result:** Both runs publish without a dialog. READY reports 'published'. NOT_READY (UNCLE_AUTO_PUBLISH=1) creates a draft and reports published-draft-unreviewed with a stderr line naming the verdict and saying unreviewed draft. Neither reports 'publication pending'.
- **Actual result:** Harness finished: 156 passed, 0 failed. READY run: reason 'published', rc 0, handoff called once, no 'PR not created' line. Auto NOT_READY run (VCLASS=NOT_READY UNCLE_AUTO_PUBLISH=1): reason 'published-draft-unreviewed', stderr contains 'verdict NOT_READY'. The source emits 'PR published as unreviewed draft: published-draft-unreviewed: verdict <class> (draft, not ready for review)' (change-pr.sh:198). The test also asserts every reason label differs from the 'publication pending' label. Gaps: the harness does not set CLOSE_ISSUE=1 in the auto run, and I did not read the stubbed gh call log for draft vs ready. Draft state is only inferred from the stub's draft flag and the reason string. Some harmless 'No such file' stderr noise appeared from stub log reads.
- **Defects:** None

### MC-403

- **Action:** Ran scripts/tests/pr-publish-reason-test.sh (prepared probe; sources change_pr_publish with stubbed change_pr_engine, gh stub, disposable temp dirs) and inspected the decline/tree-mismatch scenarios: 'v3 declined' (INTERACTIVE=1, STUB_OVERRIDE=1), 'v3 auto declined', 'tree-mismatch' (STUB_TREE_FAIL=1) and 'tree-mismatch attested'.
- **Expected result:** Declined override and tree mismatch each: no handoff/PR creation, exactly one 'PR not created: <key>' stderr line (verdict-not-ready, tree-mismatch), existing 'Publish refused' and tree-differs messages still present, return/exit 0.
- **Actual result:** Probe finished with '156 passed, 0 failed'. Assertions covered rc 0, reason key, exactly one 'PR not created:' line with the right key, no token/URL leak, handoff call count 0, and retained stderr 'tracked file not clean: one', 'path differs from the attested tree', 'Publish refused'. Limitations: the probe stubs the engine functions and gh in-process rather than using a real git repo with a bare remote, and it does not explicitly assert a literal 'PR pending:' line. Harmless 'No such file' noise appeared for unwritten call-log files when no handoff/issue call occurred (expected).
- **Defects:** None

### MC-405

- **Action:** Ran scripts/tests/pr-publish-reason-test.sh, which sources scripts/lib/change-pr.sh in disposable fixtures with a stubbed handoff. It exercises STUB_HANDOFF=1 and STUB_HANDOFF=3 (nonzero handoff exits) and STUB_PHASE=created (rerun, handoff exit 0). I read the cases at lines 132-138 and the expect_nopr helper. I did not run a real gh or git push failure; the nonzero exit is stubbed.
- **Expected result:** Nonzero handoff runs report handoff-failed, and the stderr line includes the exit code. The already-created rerun reports published. In every case the driver still exits 0.
- **Actual result:** STUB_HANDOFF=1 and STUB_HANDOFF=3 both gave reason handoff-failed with return code 0. There was exactly one 'PR not created: handoff-failed' stderr line, it contained the exit code (1 and 3 respectively), and it leaked no token or URL. The STUB_PHASE=created rerun gave reason published. The plain published case had rc 0 and no 'PR not created' line. Result: 156 passed, 0 failed. Limitation: the two failure modes (consent declined, push failure) are modelled only as stubbed nonzero handoff exit codes, and 'driver exit 0' is checked as the return code of change_pr_publish, not of the full driver process. The run also printed harmless 'No such file or directory' noise for handoff.calls and issue.calls from the fixture temp directories.
- **Defects:** None

### MC-406

- **Action:** Ran scripts/tests/pr-publish-reason-test.sh (fixture harness sourcing change-pr.sh and exercising change_pr_complete in headless and completed-commit modes with stubbed publish), and inspected change-pr.sh lines 84-97 for the headless message and reason assignment.
- **Expected result:** With no completed commit, output says 'PR handoff disabled or unattended' and reason is handoff-disabled with no PR created. With a completed commit, the reason set by publish survives and is not overwritten with publication-pending.
- **Actual result:** Test run ended '156 passed, 0 failed'. Relevant cases: 'complete handoff-disabled' (resume fails -> reason handoff-disabled); 'complete headless keeps reason' (tree-mismatch) and 'keeps published' for unattended/headless/interactive; empty reason -> publication-pending only when publish set nothing. Source shows the no-commit branch echoes 'PR handoff disabled or unattended; no PR was created.' and sets CHANGE_PR_EXTRAS_REASON=handoff-disabled. The output message itself was verified by source inspection, not by captured output, because the test discards the function's stdout. Stderr noise (missing handoff.calls/issue.calls files at test lines 90-91) did not affect results.
- **Defects:** None

### MC-407

- **Action:** Ran scripts/tests/pr-publish-reason-test.sh (prepared fixture probe, read-only). It stubs gh and a remote URL with canary values (CANARY-TOKEN-9f3a, https://user:CANARYPASS@example.com/x.git), where the stubbed gh prints the canary to stdout and stderr and fails. It runs no-PR failure cases and a handoff-failure case (STUB_HANDOFF=3), then asserts on the 'PR not created:' line, the reason, and the PR line.
- **Expected result:** The 'PR not created:' line holds only the reason key, a static message and the exit code where applicable. The canary token, the credentialed URL and any gh output do not appear in it or in the finished block.
- **Actual result:** The script finished with '156 passed, 0 failed'. The expect_nopr assertions require exactly one 'PR not created' line, an exact reason key, no 'CANARY' and no '://' in the line. The canary assertions on the handoff-failed path found no CANARY in the reason or the PR line. The run also printed 'No such file or directory' warnings for handoff.calls and issue.calls inside the test's temp dirs. These come from the test harness's own stub bookkeeping, did not fail any assertion, and are not an application defect. I did not separately inspect the finished-block text by eye beyond the script's assertions.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-104 | YES | PASS | Fixture transcript: stderr 'PR not created: issue-not-eligible: the issue is not eligible to close'; reason=issue-not-eligible; gh log '(none)'; finished output 'PR: not created (issue not eligible)'. Fixture used stubbed gh/engine/issue_close_eligible, not a live GitHub. |
| MC-106 | YES | PASS | Fixture transcript as described; gh stub log 'gh pr create --draft'. Handoff/gh were stubs, not live GitHub. |
| MC-200 | YES | PASS | Script /tmp/mc200.sh output captured above; empty ls-remote; absent handoff/gh log files. |
| MC-201 | YES | PASS | Test output line 'pr-publish-reason-test: 156 passed, 0 failed'. Assertions are at scripts/tests/pr-publish-reason-test.sh lines 117-124. Gate code is at scripts/lib/change-pr.sh lines 138-157. The fixture stubs gh/handoff, so no real PR is created. |
| MC-204 | YES | PASS | pr-publish-reason-test: 156 passed, 0 failed; change-pr.sh:197-198; finished_extras.py REASONS/FALLBACK; test lines 190-205. |
| MC-300 | YES | PASS | git ls-remote: 4b7543880c393d653f74e84c3556513217558748 refs/heads/feat. gh.log: 'gh pr create --title t --body b'. Finished block: 'Total time: unknown / PR: published'. |
| MC-301 | YES | PASS | bash scripts/tests/pr-publish-reason-test.sh -> '156 passed, 0 failed'; assertions at scripts/tests/pr-publish-reason-test.sh lines 95-154 and section 8 (lines 188+). |
| MC-302 | YES | PASS | Fixture output: stderr line quoted above; finished block line quoted above; stub args file 'pr create --draft'; scripts/lib/change-pr.sh:195-199 and finished_extras.py pr_line. |
| MC-303 | YES | PASS | Output line: 'pr-publish-reason-test: 156 passed, 0 failed'. Canary assertions are at scripts/tests/pr-publish-reason-test.sh:102 and :153-154. This is a scripted simulation with an automated string check, not a by-eye inspection of a real run. |
| MC-401 | YES | PASS | Transcript: RC=0 REASON=published HANDOFFS=1; stderr contained 'PR created (verdict READY): ready for review.'; finished block 'Total time: unknown / PR: published'. Caveat: the harness stubs change_pr_engine (handoff, validate, commit-tree) and gh, and no real bare remote push was exercised; the 'push and PR create' step is a stubbed handoff call, not a real git push. The stub's canary token/URL printed to stdout/stderr come from the stub engine itself, not from the product's reason line. |
| MC-402 | YES | PASS | Test output tail: 'pr-publish-reason-test: 156 passed, 0 failed'; scripts/tests/pr-publish-reason-test.sh:132,139-141,190-195; scripts/lib/change-pr.sh:124,197-198. |
| MC-403 | YES | PASS | Terminal output of 'bash scripts/tests/pr-publish-reason-test.sh': 'pr-publish-reason-test: 156 passed, 0 failed'; test source lines 95-130 of scripts/tests/pr-publish-reason-test.sh. |
| MC-405 | YES | PASS | Output tail: 'pr-publish-reason-test: 156 passed, 0 failed', exit status 0. Assertions at scripts/tests/pr-publish-reason-test.sh:136-137 (handoff 1 and 3, including the exit-code check) and :135 (rerun created -> published). |
| MC-406 | YES | PASS | Test output tail 'pr-publish-reason-test: 156 passed, 0 failed'; scripts/lib/change-pr.sh:84-97; scripts/tests/pr-publish-reason-test.sh:157-186. |
| MC-407 | YES | PASS | Console output of the test run ended with 'pr-publish-reason-test: 156 passed, 0 failed' (exit 0). Assertions are at scripts/tests/pr-publish-reason-test.sh:96-103 and :151-154. |
