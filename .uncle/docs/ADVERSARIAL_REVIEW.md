## AR-001: Plan lists reason keys but not which publish exit maps to which.

- Severity: HIGH
- References: change-pr.sh:120-129 has four return-0 branches; CHANGE_PLAN s7 lists keys without a mapping.
- Failure: Plan lists reason keys but not which publish exit maps to which. Decision: validate exit 3 with no override, or a declined or failed verdict-override -> verdict-not-ready; any other validate failure, including the post-override re-validate -> validate-failed.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Plan says 'stop overwriting' the reason but not which lines change.

- Severity: HIGH
- References: change-pr.sh:70 and :98 overwrite after change_pr_publish; spec AC-3 gives no line scope.
- Failure: Plan says 'stop overwriting' the reason but not which lines change. Decision: delete the post-publish publication-pending assignments at change-pr.sh:70 and :98; set publication-pending only if publish left the reason empty; keep handoff-disabled.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: 'published' on successful handoff is ambiguous: handoff exit 0 can occur when a PR already exists, and a declined consen

- Severity: MEDIUM
- References: change-pr.sh:1457-1465 returns 0 for an already-created PR; :1508-1509 raises on decline; :1783-1790 exits 1.
- Failure: 'published' on successful handoff is ambiguous: handoff exit 0 can occur when a PR already exists, and a declined consent exits 1. Decision: published means handoff exit 0 only; any nonzero exit, including declined consent, is handoff-failed, and the stderr line includes the exit code.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Plan does not state the reason when ORIGIN_FILE is empty, when the verdict is non-READY under an override, or when commi

- Severity: MEDIUM
- References: change-pr.sh:130-159: the case branches and the attested=...||"" fallback at line 158 are unspecified in the plan.
- Failure: Plan does not state the reason when ORIGIN_FILE is empty, when the verdict is non-READY under an override, or when commit-tree is empty. Decision: issue-not-eligible is set only when issue_close_eligible runs and fails; an empty commit-tree that fails assert_tree_matches_attested records tree-mismatch.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: 'One stderr line per no-PR path' conflicts with existing stderr and stdout messages.

- Severity: MEDIUM
- References: change-pr.sh:159 already echoes 'Publish refused' to stderr; engine prints 'PR pending:' to stdout at :1778 and :1789; spec AC-2.
- Failure: 'One stderr line per no-PR path' conflicts with existing stderr and stdout messages. Decision: add exactly one new line, formatted 'PR not created: <key>: <detail>', to stderr; leave existing messages untouched.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Stale reason across direct change_pr_publish calls is unspecified.

- Severity: LOW
- References: change-pr.sh:56 resets only in change_pr_complete; SI4 demands a non-empty key on every no-PR return of publish.
- Failure: Stale reason across direct change_pr_publish calls is unspecified. Decision: change_pr_publish clears CHANGE_PR_EXTRAS_REASON on entry and sets it on every return path.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: change_pr_complete's unattended and headless branches force publication-pending after change_pr_publish, so AC-3 is ambi

- Severity: HIGH
- References: change-pr.sh:69-70 and 97-98 overwrite the reason; line 104 does not.
- Failure: change_pr_complete's unattended and headless branches force publication-pending after change_pr_publish, so AC-3 is ambiguous about which call sites are fixed. Plan should say: remove the unconditional assignment at both sites; set publication-pending only if publish left the reason empty.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: change_pr_publish has several silent returns the plan does not map to reason keys: validate failure other than 3, status

- Severity: HIGH
- References: change-pr.sh:120-129 returns 0 in four places with no reason; plan section 8 lists keys but no mapping.
- Failure: change_pr_publish has several silent returns the plan does not map to reason keys: validate failure other than 3, status 3 with no override, declined override, and re-validate after override. Plan should say: rc 3 with no or declined override sets verdict-not-ready; any other validate failure sets validate-failed.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The plan does not say when 'published' is recorded.

- Severity: MEDIUM
- References: change-pr.sh:1457-1465 exits 0 on already-created; lines 150-154 proceed to handoff on override.
- Failure: The plan does not say when 'published' is recorded. Handoff exits 0 on an already-created rerun, and a non-READY override proceeds to handoff. Plan should say: published is set only when handoff exits 0, including the rerun path and override-created PRs.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Handoff exit 0 does not always mean a ready PR: unattended mode publishes a draft over a failed audit.

- Severity: MEDIUM
- References: change-pr.sh:1480-1492 and 1514-1518 handle release_skipped/draft; lines 1777-1790 map exits 3 and 1 to 'PR pending'.
- Failure: Handoff exit 0 does not always mean a ready PR: unattended mode publishes a draft over a failed audit. Plan should say: handoff-failed covers any nonzero rc; published requires rc 0, and the stderr line states whether the PR is a draft.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The reason is reset only in change_pr_complete, so a stale value could survive a direct change_pr_publish call.

- Severity: LOW
- References: change-pr.sh:56 resets it; change_pr_publish at line 107 does not.
- Failure: The reason is reset only in change_pr_complete, so a stale value could survive a direct change_pr_publish call. Plan should say: change_pr_publish clears CHANGE_PR_EXTRAS_REASON on entry.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Plan adds a stderr line per no-PR path but never says whether handoff failure output (engine, gh, remote URLs) may be ec

- Severity: MEDIUM
- References: CHANGE_PLAN s12 and s19: 'handoff exit status captured ... then reported'; 'One stderr line per no-PR path'. Content of the line is not constrained.
- Failure: Plan adds a stderr line per no-PR path but never says whether handoff failure output (engine, gh, remote URLs) may be echoed; tokens or credentialed URLs could leak. Say: 'The stderr reason line has only the reason key and a static message, never engine/gh output, URLs or env values.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Reason keys flow via CHANGE_PR_EXTRAS_REASON into finished_extras.py, but the render rule for unknown or malformed value

- Severity: MEDIUM
- References: CHANGE_SPEC s7 'Unknown reason keys already fall back safely' is unverified; CHANGE_PLAN s7 fixes the key set but not the render rule.
- Failure: Reason keys flow via CHANGE_PR_EXTRAS_REASON into finished_extras.py, but the render rule for unknown or malformed values is unstated and the spec's 'fall back safely' claim is uncited. Say: 'finished_extras.py renders only allowlisted keys; any other value renders as publication-pending, never verbatim.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Unattended path publishes a draft PR over a non-READY verdict via UNCLE_AUTO_PUBLISH; once complete stops overwriting, i

- Severity: MEDIUM
- References: change-pr.sh:66-71, 122 and 1747-1750 (override written, unattended notice printed). Plan s7 lists only 'published'.
- Failure: Unattended path publishes a draft PR over a non-READY verdict via UNCLE_AUTO_PUBLISH; once complete stops overwriting, it would report 'published' for an unreviewed draft. Say: 'Publishing over a non-READY verdict by override or auto-publish records published-draft-unreviewed, and the stderr line names the verdict.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: AC-5 allows fixing 'any proven defect' on the skip path but does not say whether the fix may touch the SI1/SI2 gates in

- Severity: LOW
- References: CHANGE_PLAN s1(d) and R-1 versus change-pr.sh:139-148, where a wrong gate input already caused a silent skip.
- Failure: AC-5 allows fixing 'any proven defect' on the skip path but does not say whether the fix may touch the SI1/SI2 gates in the wrapper (issue_close_eligible and tree assertion `|| return 0`). Say: 'AC-5 may correct gate inputs but may not remove or loosen any gate; that is a deviation needing human approval.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Stubbing issue_close_eligible and assert_tree_matches_attested hides the likely skip.

- Severity: HIGH
- References: CHANGE_PLAN s16-17 lists the stubs; change-pr.sh:145-148 and :159 are the silent return 0 sites.
- Failure: Stubbing issue_close_eligible and assert_tree_matches_attested hides the likely skip. Plan sentence: 'The AC-5 regression test runs the real issue_close_eligible and assert_tree_matches_attested on a fixture; only gh and network are stubbed.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Reasons for the early returns after validate are unspecified.

- Severity: HIGH
- References: change-pr.sh:120-129 has four silent return 0 paths; CHANGE_PLAN s7 names only validate-failed and verdict-not-ready.
- Failure: Reasons for the early returns after validate are unspecified. Plan sentence: 'validate exit 1 or a failing second validate sets validate-failed; exit 3 with no override or a declined override sets verdict-not-ready.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: How change_pr_complete preserves the reason on every path is unspecified.

- Severity: MEDIUM
- References: change-pr.sh:69-71 and :97-99 overwrite it; :104 does not. AC-3 and SI4 do not separate these paths.
- Failure: How change_pr_complete preserves the reason on every path is unspecified. Plan sentence: 'change_pr_complete never assigns CHANGE_PR_EXTRAS_REASON after change_pr_publish returns, except publication-pending when it is empty.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: 'One stderr line' collides with existing multi-line output from assert_tree_matches_attested and the engine's stdout 'PR

- Severity: MEDIUM
- References: change-pr.sh:31-49 prints several stderr lines; :1778-1789 prints to stdout. AC-2 says one explanatory stderr line.
- Failure: 'One stderr line' collides with existing multi-line output from assert_tree_matches_attested and the engine's stdout 'PR pending'. Plan sentence: 'Each no-PR path adds exactly one stderr line beginning "PR not created: <key>", in addition to existing diagnostics.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: Handoff exit 0 does not mean a PR was created (declined or early-return paths).

- Severity: MEDIUM
- References: CHANGE_PLAN s12 detects success by exit status only; change-pr.sh:1464-1465 and :1507-1509 return without creating a PR.
- Failure: Handoff exit 0 does not mean a PR was created (declined or early-return paths). Plan sentence: 'published is set only when handoff exits 0 and the journal phase is created; otherwise handoff-incomplete.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: The empty ORIGIN_FILE case, where the issue gate is skipped, is untested and has no stated reason.

- Severity: MEDIUM
- References: change-pr.sh:130 and :143-155; the CHANGE_PLAN test list covers only AC-1..4 paths.
- Failure: The empty ORIGIN_FILE case, where the issue gate is skipped, is untested and has no stated reason. Plan sentence: 'When ORIGIN_FILE is empty the issue gate is skipped, and the test matrix includes that case.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
