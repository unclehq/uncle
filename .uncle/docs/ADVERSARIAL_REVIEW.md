## AR-001: Plan never says what happens when main is already on the run branch or at its tip; the switch is a no-op and the summary

- Severity: HIGH
- References: CHANGE_PLAN s1.2.i4/i6 and CHANGE_SPEC S-1 cover only a strict-ancestor main branch.
- Failure: Plan never says what happens when main is already on the run branch or at its tip; the switch is a no-op and the summary wording is ambiguous. Settle: 'If main is already on the run branch, skip the switch and report project switched.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Dirty-main definition is unclear for untracked files and for untracked files that collide with run-branch files, which m

- Severity: HIGH
- References: CHANGE_SPEC Assumptions 'any non-ignored porcelain entry'; CHANGE_PLAN R-5 uses plain `git status --porcelain`.
- Failure: Dirty-main definition is unclear for untracked files and for untracked files that collide with run-branch files, which makes switch fail. Settle: 'Dirty main means any porcelain entry including untracked (--untracked-files=all); a switch failure after removal follows S-7.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Plan does not say whether a failed `git add -A` counts as a commit failure, or what a clean tree does at the commit step

- Severity: HIGH
- References: CHANGE_PLAN s1.2.i2 'if staged changes exist'; S-8 covers only commit failure.
- Failure: Plan does not say whether a failed `git add -A` counts as a commit failure, or what a clean tree does at the commit step. Settle: 'A failure of git add or git commit is S-8; a clean tree skips the commit silently.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Path-guard refusals run before the commit, yet AC-2 says output is already committed on refusal.

- Severity: MEDIUM
- References: CHANGE_PLAN s1.2.i1 orders guards before commit; CHANGE_SPEC AC-2 says 'run output already committed'.
- Failure: Path-guard refusals run before the commit, yet AC-2 says output is already committed on refusal. Settle: 'Guards run before the commit; on a guard refusal nothing is committed and the summary says kept, not switched.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The extracted worktree_path_refusal boundary is vague: the existing guard also refuses untracked files and unpushed comm

- Severity: MEDIUM
- References: from-issue.sh:267-294 untracked/unpushed checks follow path guards at 243-266; plan s1.2.i1 and N-6.
- Failure: The extracted worktree_path_refusal boundary is vague: the existing guard also refuses untracked files and unpushed commits, which would block the no-PR flow. Settle: 'worktree_path_refusal holds only path, symlink and managed-root checks; untracked and unpushed checks stay in auto_removal_refusal.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Summary line outcomes are not enumerated for commit failure, guard refusal or switch failure, so tests and README could

- Severity: MEDIUM
- References: CHANGE_PLAN s1.2.i7 and AC-4; S-7 and S-8 do not state the summary text.
- Failure: Summary line outcomes are not enumerated for commit failure, guard refusal or switch failure, so tests and README could assert different strings. Settle: 'Print exactly one summary line on every no-PR COMPLETE outcome, e.g. commit failure is kept; not switched, switch failure is removed; not switched.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan does not say how auto_removal_refusal is split when the path guards are extracted.

- Severity: HIGH
- References: CHANGE_PLAN s1 step 1 and s9.1; from-issue.sh:243-295 interleaves path guards (symlink check at 264-266) with untracked/unpushed checks.
- Failure: Plan does not say how auto_removal_refusal is split when the path guards are extracted. Settle: 'auto_removal_refusal = worktree_path_refusal then the unchanged untracked, tracked-change and unpushed checks, same order, same refusal strings.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: `git add -A` would commit .uncle/ runtime files (state, lock), yet worktree_remove refuses on a lock or non-COMPLETE sta

- Severity: HIGH
- References: CHANGE_PLAN s1 step 2; worktrees.sh:220-228 reads .uncle/workflow/lock and state; N-1 requires a clean status afterwards.
- Failure: `git add -A` would commit .uncle/ runtime files (state, lock), yet worktree_remove refuses on a lock or non-COMPLETE state. Settle: 'git add -A excludes .uncle/workflow runtime files; a remaining lock keeps the worktree.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Plan does not say what happens when the source HEAD is detached; switching away could lose the detached position.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 step 4 and s12.1 mention detached HEAD only for the worktree; S-5 covers only a non-ancestor branch.
- Failure: Plan does not say what happens when the source HEAD is detached; switching away could lose the detached position. Settle: 'If source HEAD is detached, keep the worktree and print git switch <branch>.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Plan does not state the gating for finalization or test no-commit/no-switch on driver failure.

- Severity: MEDIUM
- References: from-issue.sh:845 gates only on WORKTREE and state COMPLETE; AC-5 says driver-failure behaviour is unchanged; CHANGE_PLAN s14.1 lists no such test.
- Failure: Plan does not state the gating for finalization or test no-commit/no-switch on driver failure. Settle: 'finalize_no_pr_worktree runs only when state is COMPLETE and PR_CREATED=0; a test asserts no commit or switch when the driver fails or the state is not COMPLETE.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Plan does not specify the working directory for removal.

- Severity: MEDIUM
- References: from-issue.sh:183-185 (offer helper steps out of dir) and 854-856 (PR path cd with unreachable-source refusal); the plan's seven steps contain neither.
- Failure: Plan does not specify the working directory for removal. The new helper must leave the worktree dir before removal and handle a failed cd. Settle: 'finalize_no_pr_worktree cds to the source before removal; an unreachable source keeps the worktree.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Plan runs `git add -A` and `git commit` in the worktree, which can execute repo-controlled hooks and filter drivers in a

- Severity: HIGH
- References: CHANGE_PLAN s1.2.i2 and R-7; test strategy uses a rejecting hook, so hooks are implicitly in play.
- Failure: Plan runs `git add -A` and `git commit` in the worktree, which can execute repo-controlled hooks and filter drivers in an unattended, no-prompt run. Decision sentence: 'The automatic commit runs with the user's normal hooks enabled; a hook failure is a commit failure (S-8), and no hook or filter bypass flag is used.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: `git add -A` can stage secrets (.env, keys) that are untracked but not ignored and commit them to a branch that may late

- Severity: HIGH
- References: CHANGE_PLAN s1.2.i2; D-3 excludes only ignored files; AC-1 says all output including untracked is committed.
- Failure: `git add -A` can stage secrets (.env, keys) that are untracked but not ignored and commit them to a branch that may later be pushed. Decision sentence: 'Untracked non-ignored files are committed as-is, the summary lists the committed file count, and .uncle/workflow state is excluded by pathspec.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Plan does not say whether .uncle/workflow run state (lock, state, journal) is committed or excluded from the clean-statu

- Severity: MEDIUM
- References: CHANGE_PLAN s1.2.i2/i3 versus worktrees.sh:220-228 reading lock/state in the worktree.
- Failure: Plan does not say whether .uncle/workflow run state (lock, state, journal) is committed or excluded from the clean-status check. worktree_remove reads lock and state after the commit. Decision sentence: 'Driver state under .uncle/workflow is excluded from the commit and from the clean-status check.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Plan never says what happens when source HEAD is detached, or when the branch name is option-like and passed to `git swi

- Severity: MEDIUM
- References: CHANGE_PLAN s1.2.i4/i6; containment s12 lists detached HEAD only for the worktree, not source.
- Failure: Plan never says what happens when source HEAD is detached, or when the branch name is option-like and passed to `git switch`. Decision sentence: 'Source must be on a named branch; the branch is validated with git check-ref-format --branch and passed safely; otherwise keep.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: The main-clean and ancestor checks run before worktree_remove but the switch runs after, so main can change in between a

- Severity: MEDIUM
- References: CHANGE_PLAN s1.2.i4-i6 ordering; Concurrency section omitted.
- Failure: The main-clean and ancestor checks run before worktree_remove but the switch runs after, so main can change in between and the switch could conflict. Decision sentence: 'The main-clean check is repeated immediately before git switch, and the switch never uses --force.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Plan does not state that no add or commit happens when worktree_path_refusal refuses, nor how symlinks committed by add

- Severity: LOW
- References: CHANGE_PLAN s1.2.i1 precedes i2 only implicitly; the existing auto_removal_refusal untracked-file refusal is dropped from the new helper.
- Failure: Plan does not state that no add or commit happens when worktree_path_refusal refuses, nor how symlinks committed by add -A are treated. Decision sentence: 'If worktree_path_refusal returns a reason, no add or commit is performed.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The no-op commit case is unspecified: the plan does not say what happens when `git add -A` stages nothing.

- Severity: HIGH
- References: CHANGE_PLAN s1.2.i2 'if staged changes exist'; AC-1 verifies only the non-empty case.
- Failure: The no-op commit case is unspecified: the plan does not say what happens when `git add -A` stages nothing. Settle it with: 'If nothing is staged, no commit is created and finalization continues; tests assert HEAD is unchanged.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: The failure tests have no fixed mechanism for inducing the failure.

- Severity: HIGH
- References: CHANGE_PLAN s13.1 'e.g. lock file or stubbed...'; switch-fail has no stated mechanism (S-6, S-7).
- Failure: The failure tests have no fixed mechanism for inducing the failure. Settle it with: 'failed-removal uses a PATH-shimmed git that fails `worktree remove`, and switch-fail uses a shim that fails `switch`; both assert the exact manual command text and the unchanged exit status.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: The output wording for the manual commands is undefined, and it is unclear whether the old 'Worktree ...

- Severity: MEDIUM
- References: CHANGE_PLAN s1.2.i7 vs s1.2.i4/i5 and the existing from-issue.sh:859,862,872; AC-4.
- Failure: The output wording for the manual commands is undefined, and it is unclear whether the old 'Worktree ... kept; remove with:' line still prints. Settle it with: 'Each no-PR outcome prints one line `Branch <b>: worktree removed|kept; project switched|not switched.`, plus literal `git switch <b>` and/or `scripts/lib/worktrees.sh remove <dir>` on the keep and failure paths.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: The guard-refusal cases (symlink, unregistered worktree, detached HEAD, unresolvable path) have no spec row and no test,

- Severity: MEDIUM
- References: CHANGE_PLAN s1.2.i1 and s12.1 vs CHANGE_SPEC S-1..S-10 and the test list in s13.1.
- Failure: The guard-refusal cases (symlink, unregistered worktree, detached HEAD, unresolvable path) have no spec row and no test, and the order of guards versus commit is unclear. Settle it with: 'Guard refusals happen before the commit, so nothing is committed; they print the keep summary and the remove command, and each has a test.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: 'Dirty main' is ambiguous for untracked files and the project's own .uncle/ state, and the test fixture is unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN s1.2.i4 and R-5; CHANGE_SPEC assumptions; only one dirty-main case is listed.
- Failure: 'Dirty main' is ambiguous for untracked files and the project's own .uncle/ state, and the test fixture is unspecified. Settle it with: 'Any non-ignored porcelain entry in the source checkout, including untracked files, counts as dirty; tests cover a modified tracked file and an untracked-only case.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: The existing protected tests to be rewritten are named by approximate line number only, so a weakened assertion cannot b

- Severity: LOW
- References: CHANGE_PLAN s14.1 'lines ~341-342 ... ~654 ... ~663-666'.
- Failure: The existing protected tests to be rewritten are named by approximate line number only, so a weakened assertion cannot be told from a required update. Settle it with: 'Each updated expectation is replaced by an equally strict assertion of the new behavior and listed one by one in IMPLEMENTATION_NOTES.md.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
