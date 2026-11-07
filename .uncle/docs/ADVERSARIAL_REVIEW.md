## AR-001: Plan leaves the set of success reasons ambiguous (exact two vs 'published*' glob, empty/unset reason).

- Severity: HIGH
- References: CHANGE_PLAN s1(b) vs CHANGE_SPEC OB-3 'published*' and AC-3 exact reasons.
- Failure: Plan leaves the set of success reasons ambiguous (exact two vs 'published*' glob, empty/unset reason). Settle: 'In a worktree run, change_pr_complete returns 0 only if CHANGE_PR_EXTRAS_REASON is exactly published or published-draft-unreviewed; any other value, including empty, returns 1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: CLOSE_ISSUE=0 opt-out collides with the non-zero rule: OB-6/AC-6 say no publish, but s1(b) returns 1 on the 'handoff dis

- Severity: HIGH
- References: CHANGE_PLAN s1(b) vs CHANGE_SPEC OB-6, AC-6, INV-4.
- Failure: CLOSE_ISSUE=0 opt-out collides with the non-zero rule: OB-6/AC-6 say no publish, but s1(b) returns 1 on the 'handoff disabled' path. Settle: 'With WORKFLOW_CLOSE_ISSUE=0, worktree runs return 0 and the driver exits 0; the non-zero rule applies only when CLOSE_ISSUE=1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Attended worktree runs are unspecified when the user declines the PR dialog: INV-4 says never exit 0 without a PR, but O

- Severity: MEDIUM
- References: CHANGE_SPEC INV-4 vs OB-7; CHANGE_PLAN s1.
- Failure: Attended worktree runs are unspecified when the user declines the PR dialog: INV-4 says never exit 0 without a PR, but OB-7 says dialogs are unchanged. Settle: 'Attended worktree runs are exempt from INV-4; a declined dialog returns 0.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Worktree definition is ambiguous: the marker path depends on cwd/STATE_DIR, git-dir comparison also matches other layout

- Severity: MEDIUM
- References: CHANGE_PLAN s1, D-1, s22; CHANGE_SPEC s15.
- Failure: Worktree definition is ambiguous: the marker path depends on cwd/STATE_DIR, git-dir comparison also matches other layouts, and the spec says 'linked worktree'. Settle: 'A worktree run is one where the marker exists under STATE_DIR resolved to an absolute path, or git-dir differs from git-common-dir.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Behavior when an origin-less or failing worktree publish errors (push failure) and the extras-print count are left to th

- Severity: MEDIUM
- References: CHANGE_PLAN s6, s10 D-2 'implementer checks'.
- Failure: Behavior when an origin-less or failing worktree publish errors (push failure) and the extras-print count are left to the implementer. Settle: 'Push failure in a worktree run sets a failure reason, returns 1, and prints extras exactly once.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Scope-cut order lets the driver exit-code change be cut, contradicting INV-4/OB-3 requiring non-zero exit.

- Severity: LOW
- References: CHANGE_PLAN s21 vs CHANGE_SPEC INV-4, AC-3.
- Failure: Scope-cut order lets the driver exit-code change be cut, contradicting INV-4/OB-3 requiring non-zero exit. Settle: 'The driver exit-code change is not cuttable; only README wording may be cut.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Worktree detection (marker OR git-dir != git-common-dir) conflicts with 'non-worktree unchanged'.

- Severity: HIGH
- References: CHANGE_PLAN s1 and D-1 vs CHANGE_SPEC OB-5/R-2; AC-4 tests only a plain repo with no marker.
- Failure: Worktree detection (marker OR git-dir != git-common-dir) conflicts with 'non-worktree unchanged'. A stale marker in a plain repo, or an operator worktree, would now auto-publish. Plan should say: 'in_worktree is true only when git-dir != git-common-dir; the marker alone never qualifies.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The non-zero exit is not conditioned on UNATTENDED, so an attended worktree user who declines the dialog would now exit

- Severity: HIGH
- References: CHANGE_PLAN s1(b)/(c) say 'for worktree runs' with no unattended condition; OB-7 says attended is unchanged.
- Failure: The non-zero exit is not conditioned on UNATTENDED, so an attended worktree user who declines the dialog would now exit non-zero, contradicting 'attended dialogs unchanged'. Plan should say: 'pr_rc is non-zero only for unattended worktree runs; attended decline or skip returns 0.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The set of reasons that return 0 is unspecified for legitimate no-PR outcomes.

- Severity: MEDIUM
- References: CHANGE_PLAN s1(b) vs AC-3 ('any reason other than published*') and AC-6/OB-6.
- Failure: The set of reasons that return 0 is unspecified for legitimate no-PR outcomes. s1(b) treats 'handoff disabled' as a failure while AC-6 requires CLOSE_ISSUE=0 to be unchanged. Plan should say: 'CLOSE_ISSUE=0 returns 0; failures return 1 only when CLOSE_ISSUE=1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: D-2 leaves duplicate printing of extras to the implementer, and the effect of a non-zero exit on the on_exit handler and

- Severity: MEDIUM
- References: CHANGE_PLAN s10 D-2 'implementer checks on_exit duplicate print'; s7 'None in state files'.
- Failure: D-2 leaves duplicate printing of extras to the implementer, and the effect of a non-zero exit on the on_exit handler and re-run is unspecified. Plan should say: 'exit via pr_rc runs the normal exit trap, prints the reason once, and a re-run resumes from the journal.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: It is unstated whether an origin-less unattended worktree should publish a draft for an unreviewed verdict, or refuse on

- Severity: MEDIUM
- References: CHANGE_SPEC s8 'unreviewed verdict still publishes only as a draft'; AC-3 names only two success reasons.
- Failure: It is unstated whether an origin-less unattended worktree should publish a draft for an unreviewed verdict, or refuse on a non-READY verdict. Plan should say: 'unreviewed publishes as draft and returns 0; a failing verdict does not publish and returns 1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Plan widens unattended auto-publish to every worktree, including operator-made worktrees (D-1), which pushes the branch

- Severity: HIGH
- References: CHANGE_PLAN s1 (a) and s9 D-1 / Risks 'marker detection also matches operator worktrees; accepted'.
- Failure: Plan widens unattended auto-publish to every worktree, including operator-made worktrees (D-1), which pushes the branch and opens a PR with no human dialog. Plan should say: 'Auto-publish without origin applies only when the worktree-owned marker exists; git-dir comparison alone never triggers unattended publish.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Plan never states which remote and base branch a no-origin worktree run pushes to, or what happens with multiple or miss

- Severity: MEDIUM
- References: CHANGE_PLAN s6 says publish skips issue-eligibility when origin is empty; remote and base are not specified; R-4 relies on engine behavior at ~1668.
- Failure: Plan never states which remote and base branch a no-origin worktree run pushes to, or what happens with multiple or missing remotes. Plan should say: 'Unattended worktree publish pushes only to the configured default remote and fails non-zero with a reason if the remote is missing or ambiguous.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Without an origin file the issue-eligibility check is skipped, and the plan does not say issue-closing keywords are supp

- Severity: MEDIUM
- References: CHANGE_PLAN s6; INV-3 is scoped to 'issue runs' only in CHANGE_SPEC s6.
- Failure: Without an origin file the issue-eligibility check is skipped, and the plan does not say issue-closing keywords are suppressed in the PR body for non-issue runs. Plan should say: 'No-origin worktree publish never emits issue-closing references and never closes any issue.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Plan does not say that PR text and logs for unattended publish contain no tokens or env values.

- Severity: LOW
- References: CHANGE_PLAN s1(b) and s12 reuse existing reason strings; 'non-secret evidence' is stated only for manual verification (s19).
- Failure: Plan does not say that PR text and logs for unattended publish contain no tokens or env values. Plan should say: 'Published PR bodies and failure output never include credentials or environment values.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: AC-3 driver exit behavior is verified only by a grep on change-workflow.sh, which cannot show the driver exits non-zero.

- Severity: HIGH
- References: CHANGE_SPEC AC-3 verification says 'grep assertion on change-workflow.sh exit handling'; CHANGE_PLAN s16 lists only pr-auto-publish-test.sh cases.
- Failure: AC-3 driver exit behavior is verified only by a grep on change-workflow.sh, which cannot show the driver exits non-zero. Settle it: 'A shell test must run the completion path of change-workflow.sh with change_pr_complete stubbed to return 1 in a worktree fixture and assert exit status 1; it must also assert exit 0 for the same stub in a non-worktree fixture.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: The plan does not say which reasons count as failure in worktree runs, nor what happens when the reason is empty or unse

- Severity: HIGH
- References: CHANGE_PLAN s1(b) says 'not published or published-draft-unreviewed' and lists 'handoff disabled' and 'pending' without enumerating reasons. AC-3 stubs only 'a reason'.
- Failure: The plan does not say which reasons count as failure in worktree runs, nor what happens when the reason is empty or unset. Settle it: 'In a worktree run, change_pr_complete returns 0 only when CHANGE_PR_EXTRAS_REASON is exactly published or published-draft-unreviewed; any other value, including empty or unset, returns 1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: Two statements conflict on CLOSE_ISSUE=0 in a worktree.

- Severity: MEDIUM
- References: CHANGE_PLAN s1(b) vs CHANGE_SPEC OB-6 and AC-6, which assert only 'does not publish'.
- Failure: Two statements conflict on CLOSE_ISSUE=0 in a worktree. Section 1(b) says the handoff-disabled path returns 1, while OB-6 and AC-6 say CLOSE_ISSUE=0 is unchanged. Settle it: 'With WORKFLOW_CLOSE_ISSUE=0 in a worktree, change_pr_complete does not publish and returns 0; the new non-zero return applies only when CLOSE_ISSUE=1.' AC-6 should also assert rc 0.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: Worktree detection has no specified behavior for the marker present in a non-worktree dir, STATE_DIR unset versus overri

- Severity: MEDIUM
- References: CHANGE_PLAN s1 definition of change_pr_in_worktree; s16 'Fixture must override STATE_DIR' covers only the marker case.
- Failure: Worktree detection has no specified behavior for the marker present in a non-worktree dir, STATE_DIR unset versus overridden, or git failing outside a repo. Settle it: 'in_worktree is true if the marker exists, otherwise true if git-dir differs from git-common-dir, and false when git fails; tests must cover marker-only, git-dir-only, and neither.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: D-2 leaves duplicate printing of extras to the implementer, so no test can assert it.

- Severity: MEDIUM
- References: CHANGE_PLAN s12 D-2: 'implementer checks on_exit duplicate print and suppresses if repeated'.
- Failure: D-2 leaves duplicate printing of extras to the implementer, so no test can assert it. Settle it: 'On worktree publish failure the stopped-extras message is printed exactly once, and a test must count its occurrences in stderr.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: D-1 claims no double PR for issue worktrees, but the planned tests never exercise a worktree with an ORIGIN_FILE.

- Severity: LOW
- References: CHANGE_PLAN s10 D-1 versus s16, which lists a call-count test without a worktree-plus-origin fixture.
- Failure: D-1 claims no double PR for issue worktrees, but the planned tests never exercise a worktree with an ORIGIN_FILE. Settle it: 'An unattended issue-linked run inside a worktree must call change_pr_publish exactly once, asserted by a test with a worktree fixture that also has an ORIGIN_FILE.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
