## AR-001: The plan never says what an app build does on a repo with commits and a detached HEAD.

- Severity: HIGH
- References: CHANGE_SPEC BH-5 and D-5. The spec covers detached HEAD only for change runs, in section 8.
- Failure: The plan never says what an app build does on a repo with commits and a detached HEAD. D-5 defines main as a branch name. Settle it with: 'Detached HEAD on an app build is refused as not on main, naming the detached commit.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: A change run in place on a feature branch not created for it is unspecified.

- Severity: HIGH
- References: CHANGE_PLAN D-3 and risk row 2, against CHANGE_SPEC BH-1/BH-2.
- Failure: A change run in place on a feature branch not created for it is unspecified. BH-1 says switch to a new branch; BH-2 and risk T3 say the engine adopts a non-default branch. Settle it with: 'An in-place change run on any branch not recorded in run-branch creates a new branch from HEAD, even with a remote.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The WORKFLOW_WORKTREE combinations for app builds are not fully specified.

- Severity: MEDIUM
- References: CHANGE_SPEC BH-7; CHANGE_PLAN D-7 and D-8. Neither says whether the notice is skipped on resume.
- Failure: The WORKFLOW_WORKTREE combinations for app builds are not fully specified. BH-7 covers only an explicit =1, and D-8 puts the notice in the driver. Settle it with: 'The notice prints only for an explicit =1 on a fresh app start; =0, unset, and resume print nothing.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: D-6 does not say how untracked, ignored, or staged entries count, or what is printed past 10 paths.

- Severity: MEDIUM
- References: CHANGE_PLAN D-6 (`git status --porcelain` minus three paths) and CHANGE_SPEC BH-6 ('lists up to 10 paths').
- Failure: D-6 does not say how untracked, ignored, or staged entries count, or what is printed past 10 paths. Settle it with: 'Untracked files count as uncommitted changes, ignored files do not, and the message lists the first 10 paths then "and N more".'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Edge states for the app preflight have no combined rule: a repo with only master, and a linked worktree on main.

- Severity: MEDIUM
- References: CHANGE_PLAN D-5, D-7 and CHANGE_SPEC BH-10/A1. Each state is covered separately and linked worktrees are never mentioned.
- Failure: Edge states for the app preflight have no combined rule: a repo with only master, and a linked worktree on main. Settle it with: 'Preflight is skipped for non-git and unborn-HEAD projects; master counts as main only when no local main exists; a linked worktree on main is treated like any checkout.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: INV-4 and AC-4 say a refused app start writes nothing, but the plan runs the policy after `uncle_ensure_project_git`, wh

- Severity: MEDIUM
- References: CHANGE_PLAN section 1 ('after uncle_ensure_project_git') against CHANGE_SPEC INV-4. The AC-4 test only checks .uncle/workflow.
- Failure: INV-4 and AC-4 say a refused app start writes nothing, but the plan runs the policy after `uncle_ensure_project_git`, which may write. Settle it with: 'Preflight runs before any driver write; "nothing written" means no new files or edits beyond what the launcher created before the driver started.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Change-run guard vs.

- Severity: HIGH
- References: change-pr.sh:1376 `target = current_branch if current_branch != default`; plan s15.1.r2 only says 'covered by an interplay case' without stating expected outcome.
- Failure: Change-run guard vs. engine start_build ordering is unspecified: guard runs before change_pr_engine start and switches to a new branch, but start_build then sees a non-default current branch and adopts it as head. Plan should say: when the guard created the branch, the engine adopts it as head_branch with no second branch (BH-2/BH-3 interplay).
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Plan says app preflight runs only when no $STATE_FILE exists, but the TUI/headless/uncle launchers for app kind skip the

- Severity: HIGH
- References: D-6 excludes only `.uncle/`, `REQUIREMENTS.md`, `CHANGE_REQUEST.md`; a prior merged run commits `.uncle/docs/CHANGE_REQUEST.md` (run_duties.py:212) and a second app build after a first would see tracked/untracked source from the earlier build. Add sentence: preflight on a completed-run checkout with an archived state is evaluated by the same dirty rule.
- Failure: Plan says app preflight runs only when no $STATE_FILE exists, but the TUI/headless/uncle launchers for app kind skip the worktree and then run the driver on a dirty or off-main checkout. A legacy owned app worktree (worktree-owned marker) or a prior-run leftover (.uncle/docs from a finished run, committed or uncommitted) is not defined as clean vs dirty.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Existing ~50 driver suites that run stagegate.sh in fixtures off main, dirty or with commits will now be refused by pref

- Severity: MEDIUM
- References: Plan s15.1.r1 says protected tests may need to change and the implementer must 'stop'; no env override or fixture contract is stated, and AC-6 requires no new failures.
- Failure: Existing ~50 driver suites that run stagegate.sh in fixtures off main, dirty or with commits will now be refused by preflight; plan resolves this by 'stop' rather than a decision. Specify an opt-out or fixture rule so regression results are deterministic.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: worktree_auto kind arg is optional and absent keeps current behavior, but run_duties.prepare_worktree(kind=None) and any

- Severity: MEDIUM
- References: Plan s6.1 'absent = current behavior'; run_policy_kind returns `unknown`; uncle_headless.py:410 gates only on github_issue.
- Failure: worktree_auto kind arg is optional and absent keeps current behavior, but run_duties.prepare_worktree(kind=None) and any caller omitting kind (e.g. headless with UNCLE_STARTUP_ACTION unset) still create app worktrees, contradicting INV-2 'an app build never creates a worktree'. State what an unknown/absent kind does.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Change-run guard for a worktree run via WORKFLOW_WORKTREE default vs.

- Severity: MEDIUM
- References: change-pr.sh:1350 returns early on detached HEAD or no remote; plan D-2 numbers `-2..-64`, spec s8 says detached creates branch but no test row exists.
- Failure: Change-run guard for a worktree run via WORKFLOW_WORKTREE default vs. detached HEAD, name collisions beyond -64, and dirty tree are unspecified: failure of branch-name exhaustion or `git switch -c` with conflicting index is not described, and BH-1 says a run with remote uses engine while no-remote uses guard, leaving remote-but-detached-HEAD uncovered.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Notice for WORKFLOW_WORKTREE=1 on app builds is printed by the stagegate driver only (D-8), but the TUI/headless launche

- Severity: LOW
- References: BH-7 trigger is 'set explicitly'; D-8 gives no condition on the variable.
- Failure: Notice for WORKFLOW_WORKTREE=1 on app builds is printed by the stagegate driver only (D-8), but the TUI/headless launchers have already skipped the worktree and an explicit --worktree flag path or WORKFLOW_WORKTREE=1 with UNCLE_PROJECT_ROOT_LOCKED is not stated. Say whether the notice prints when WORKFLOW_WORKTREE is unset (it must not).
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Branch names come from run-branch-name (slug of untrusted brief/issue text), but the plan never says the name is validat

- Severity: HIGH
- References: CHANGE_PLAN D-2/D-4; change-pr.sh run-branch-name (label_prefix+slug of origin); spec section 8 mentions 'name invalid' but the plan gives no check.
- Failure: Branch names come from run-branch-name (slug of untrusted brief/issue text), but the plan never says the name is validated before `git switch -c`. Say: 'run_policy_change_branch runs `git check-ref-format --branch`, rejects a leading '-', and calls `git switch -c -- <name>`; failure exits 1 before any stage.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: BH-6 lists up to 10 paths in a message, but the plan never states filenames are sanitized or that porcelain -z is used.

- Severity: MEDIUM
- References: CHANGE_SPEC BH-6 'lists up to 10 paths'; D-6 uses plain `git status --porcelain`.
- Failure: BH-6 lists up to 10 paths in a message, but the plan never states filenames are sanitized or that porcelain -z is used. Say: 'Paths in the BH-6 message are parsed from `git status --porcelain -z` and printed with control characters stripped.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The dirty-check exclusion is path-based, so a modified tracked file under .uncle/, REQUIREMENTS.md or CHANGE_REQUEST.md

- Severity: MEDIUM
- References: D-6 excludes whole paths; run_duties.archive_change_request notes CHANGE_REQUEST.md can be committed as .uncle/docs/CHANGE_REQUEST.md.
- Failure: The dirty-check exclusion is path-based, so a modified tracked file under .uncle/, REQUIREMENTS.md or CHANGE_REQUEST.md passes as clean. Say: 'Exclusions apply only to untracked entries; a modified tracked file at those paths counts as uncommitted.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Skip markers (run-branch, worktree-owned, journal, STATE_FILE) live in the working tree and are trusted on existence alo

- Severity: MEDIUM
- References: D-3 and D-7 skip on marker existence; a marker naming a nonexistent or reused branch is unspecified.
- Failure: Skip markers (run-branch, worktree-owned, journal, STATE_FILE) live in the working tree and are trusted on existence alone, so a stale or planted one bypasses the refusal or guard. Say: 'run-branch is honored only if it names an existing local branch equal to the current branch; otherwise it is ignored.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Behavior for kind `unknown` is unspecified, and the kind can derive from env (UNCLE_STARTUP_ACTION).

- Severity: LOW
- References: CHANGE_PLAN section 1 run_policy_kind returns app|change|issue|unknown; uncle_headless.py reads UNCLE_STARTUP_ACTION from the environment.
- Failure: Behavior for kind `unknown` is unspecified, and the kind can derive from env (UNCLE_STARTUP_ACTION). Say: 'run_policy_kind matches exact strings only; unknown behaves as today and never skips worktree creation as app.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: Plan never says what an app build does on a non-git or unborn-HEAD repo when WORKFLOW_WORKTREE=1 is set, or whether the

- Severity: HIGH
- References: CHANGE_SPEC BH-7, BH-10; CHANGE_PLAN D-4, D-8.
- Failure: Plan never says what an app build does on a non-git or unborn-HEAD repo when WORKFLOW_WORKTREE=1 is set, or whether the BH-7 notice prints. Add: 'Preflight skips on non-git or unborn HEAD; the BH-7 notice prints whenever WORKFLOW_WORKTREE=1 is set on an app build.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: Dirty check is ambiguous for untracked, ignored, renamed or space-containing paths, and for excluded files that are trac

- Severity: HIGH
- References: CHANGE_PLAN D-6; CHANGE_SPEC BH-6, A3.
- Failure: Dirty check is ambiguous for untracked, ignored, renamed or space-containing paths, and for excluded files that are tracked. Add: 'Untracked files outside the excluded set count as uncommitted; ignored files do not; exclusions match exact top-level paths, tracked or untracked.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: App build on a detached HEAD is undefined: BH-5 says message 'names current branch' but there is none.

- Severity: HIGH
- References: CHANGE_SPEC section 8 covers detached HEAD for change runs only; BH-5.
- Failure: App build on a detached HEAD is undefined: BH-5 says message 'names current branch' but there is none. Add: 'App build on detached HEAD refuses with exit 1 and a message saying HEAD is detached.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: D-3 skip conditions can conflict with INV-3/AC-1: a stale run-branch file, journal or worktree-owned marker lets a chang

- Severity: MEDIUM
- References: CHANGE_PLAN D-3 vs CHANGE_SPEC INV-3.
- Failure: D-3 skip conditions can conflict with INV-3/AC-1: a stale run-branch file, journal or worktree-owned marker lets a change run stay on main. Add: 'Guard skips only if the current branch equals run-branch and is not the default branch; a marker or journal on main does not suppress it.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: Exhausted name range -2..-64 and empty or invalid derived names are unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN D-2; CHANGE_SPEC section 8.
- Failure: Exhausted name range -2..-64 and empty or invalid derived names are unspecified. Add: 'If no free name exists or check-ref-format rejects it, exit 1 before any stage naming the cause.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: BH-6 lists 'up to 10 paths' without saying order or what shows beyond 10, so tests cannot assert output.

- Severity: MEDIUM
- References: CHANGE_SPEC BH-6.
- Failure: BH-6 lists 'up to 10 paths' without saying order or what shows beyond 10, so tests cannot assert output. Add: 'Paths in git status order, first 10, then "and N more" when over 10.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
