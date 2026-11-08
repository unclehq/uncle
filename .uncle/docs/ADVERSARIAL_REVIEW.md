## AR-001: Mode handling is contradictory: the plan forwards a mode flag to the driver, yet the driver is untouched and nothing say

- Severity: HIGH
- References: CHANGE_PLAN s8 'forwarded to the driver' and s20 step 1 'run driver with mode flag' vs s5 not modifying change-workflow.sh.
- Failure: Mode handling is contradictory: the plan forwards a mode flag to the driver, yet the driver is untouched and nothing says it accepts one. Settle: 'The helper passes mode only via exported UNCLE_UNATTENDED, adds no driver CLI flags; unset means driver default.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Unspecified: target state already mid-flight (implementation, pending gate).

- Severity: HIGH
- References: CHANGE_SPEC s8 refusal list has no stage condition; plan s7 writes FINAL_AUDIT unconditionally after preconditions.
- Failure: Unspecified: target state already mid-flight (implementation, pending gate). Overwriting with FINAL_AUDIT could skip approval gates. Settle: 'Refuse unless state is a post-implementation stage or FINAL_AUDIT; otherwise Error: and state untouched.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Exit contract conflicts: AC-2 says driver's status, but a driver exit 0 with missing verdict file or a not-READY verdict

- Severity: MEDIUM
- References: CHANGE_SPEC s15 'Exit status equals the driver's' vs s8 'not-READY audit ... nonzero exit'; AC-2.
- Failure: Exit contract conflicts: AC-2 says driver's status, but a driver exit 0 with missing verdict file or a not-READY verdict has no stated output or code. Settle: 'If audit-verdict is missing print UNKNOWN and exit $UNCLE_REFUSE_CODE; otherwise exit with driver status.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: D-1 leaves cases open: empty-string BRANCH, 'uncle --audit verify', and a single-dash token.

- Severity: MEDIUM
- References: CHANGE_PLAN s8/s10 D-1; uncle line 244 treats 'verify' as an early exec case.
- Failure: D-1 leaves cases open: empty-string BRANCH, 'uncle --audit verify', and a single-dash token. Settle: 'Token after --audit is BRANCH iff present, non-empty and not starting with -; empty is refused; verify is refused as extra positional.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Branch checked out in zero or multiple worktrees, or BRANCH equal to the current branch, is not defined.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-3 and s8 list only 'not checked out in any worktree'; plan step 1 does not define ambiguity.
- Failure: Branch checked out in zero or multiple worktrees, or BRANCH equal to the current branch, is not defined. Settle: 'Resolve via worktree_branch_dir; zero or multiple matches are refused; BRANCH equal to current branch audits the current checkout.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Placement of the exclusivity check is unspecified; the pre-scan only counts three options, so --audit with stdin-reading

- Severity: LOW
- References: uncle lines 219-227 pre-scan only --application/--issue/--change-request; plan step 2 gives no placement.
- Failure: Placement of the exclusivity check is unspecified; the pre-scan only counts three options, so --audit with stdin-reading options could read stdin first. Settle: 'Add --audit to the pre-scan exclusivity loop so combinations are refused before any stdin read.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The plan does not say how the existing exclusivity pre-scan treats --audit.

- Severity: HIGH
- References: uncle:217-227 counts only three flags; :276-285 --issue treats a following --* token as 'read stdin', so `--issue --audit` is ambiguous.
- Failure: The plan does not say how the existing exclusivity pre-scan treats --audit. Settle with: '--audit counts as a startup action in the pre-scan, so --audit with --application/--issue/--change-request is refused before any stdin read.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The exit code for --audit combined with another startup action is stated two ways.

- Severity: MEDIUM
- References: AC-4 and plan section 8 say $UNCLE_REFUSE_CODE; uncle:224-227 and :253-256 use literal exit 1.
- Failure: The exit code for --audit combined with another startup action is stated two ways. Settle with: 'Combining --audit with another startup action exits $UNCLE_REFUSE_CODE (2 under --noui).'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: BRANCH token parsing is unspecified for edge values.

- Severity: MEDIUM
- References: Plan section 8 excludes only '--' prefixes; uncle:244 has a `verify` case; `-x` and '' are undefined.
- Failure: BRANCH token parsing is unspecified for edge values. Settle with: 'BRANCH is the next token only if non-empty and not starting with -; `verify` is taken as BRANCH; an empty string is refused; a second positional hits the Error path.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Ordering of --audit relative to early-exit flags is undefined.

- Severity: MEDIUM
- References: uncle:242-246 exec during the parse loop; CHANGE_SPEC section 7 says only 'not combinable'.
- Failure: Ordering of --audit relative to early-exit flags is undefined. Settle with: 'Early-exit flags (--help, verify, --runs, --performance) act in argument order as today; --audit after them is never parsed; --audit before them is refused as a combination.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The plan does not say whether the upgrade check and other pre-dispatch steps run on the --audit path.

- Severity: MEDIUM
- References: Plan section 1 dispatches after uncle:~381 while section 16 sets UNCLE_SKIP_UPGRADE=1, implying an upgrade step sits on the path.
- Failure: The plan does not say whether the upgrade check and other pre-dispatch steps run on the --audit path. Settle with: 'The --audit path skips upgrade checks and never reads stdin or starts the TUI.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The summary is undefined when the driver exits 0 but audit-verdict is missing or stale.

- Severity: LOW
- References: CHANGE_SPEC section 15 says the verdict is printed 'for information'; plan step 1 reads .uncle/workflow/audit-verdict with no missing-file behavior.
- Failure: The summary is undefined when the driver exits 0 but audit-verdict is missing or stale. Settle with: 'If audit-verdict is absent or older than the run, print verdict: unknown and still return the driver status.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Plan validates BRANCH with check-ref-format but never states how git is invoked with it.

- Severity: HIGH
- References: CHANGE_PLAN s8 says BRANCH is 'not starting with `--`'; CHANGE_SPEC s10 relies on `git check-ref-format --branch`, which expands '@{-N}' forms.
- Failure: Plan validates BRANCH with check-ref-format but never states how git is invoked with it. Settle: 'Git calls pass the branch only as refs/heads/<name> after "--", and BRANCH beginning with "-" (not just "--") is refused.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Checkout path from worktree_branch_dir is never required to be verified.

- Severity: HIGH
- References: CHANGE_PLAN s1 and step 1: 'checkout via current branch or worktree_branch_dir'; no validation of the returned path.
- Failure: Checkout path from worktree_branch_dir is never required to be verified. Settle: 'Target dir comes only from `git worktree list --porcelain` of the caller repo, is realpath-resolved, must exist and contain .uncle owned by the current user, else refuse.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Which change-workflow.sh runs is ambiguous: install dir copy or the target worktree's copy (branch-controlled content).

- Severity: MEDIUM
- References: CHANGE_PLAN s1 'runs the existing scripts/change-workflow.sh there'; CHANGE_SPEC s10 'No new env override for the driver path'.
- Failure: Which change-workflow.sh runs is ambiguous: install dir copy or the target worktree's copy (branch-controlled content). Settle: 'The helper always runs $ROOT/scripts/change-workflow.sh from the install dir, never a script from the target checkout.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Lock probe then state write is a check-then-act race that can alter state under a live driver, contradicting I-6.

- Severity: MEDIUM
- References: CHANGE_PLAN s11 D-2 and s7: the driver lock is the final guard only after the state write in step 1.
- Failure: Lock probe then state write is a check-then-act race that can alter state under a live driver, contradicting I-6. Settle: 'The state write happens while holding the driver lock, or is restored if the driver cannot acquire it.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Echoed previous state, branch names and paths may carry terminal escapes.

- Severity: LOW
- References: CHANGE_PLAN s7 'Previous state is printed'; CHANGE_SPEC s8 error messages naming the cause.
- Failure: Echoed previous state, branch names and paths may carry terminal escapes. Settle: 'Any branch name, path or state value printed has control characters stripped.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: AC-6 defect injection is vague: stubbing the whole precondition block can fail without proving each refusal test catches

- Severity: HIGH
- References: CHANGE_PLAN s16 'precondition block stubbed out'; CHANGE_SPEC AC-6 says 'one precondition removed'.
- Failure: AC-6 defect injection is vague: stubbing the whole precondition block can fail without proving each refusal test catches its own check. Plan should say: 'One mutant per AC-4 refusal; each must fail its matching test.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: AC-4 refusals are split between launcher and helper with no stated owner, and defect injection targets only the helper.

- Severity: HIGH
- References: CHANGE_PLAN s20 steps 1 and 2; s16 stubs only the helper.
- Failure: AC-4 refusals are split between launcher and helper with no stated owner, and defect injection targets only the helper. Plan should say: 'Argument-shape, exclusivity and home-agent refusals live in uncle; git, state and lock refusals in audit-command.sh; injection covers both.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: Output and exit are unspecified when the verdict file is absent or unparsable, or when the verdict is not READY and the

- Severity: MEDIUM
- References: CHANGE_SPEC AC-2 and A2; s16 stub 'may write a verdict file'.
- Failure: Output and exit are unspecified when the verdict file is absent or unparsable, or when the verdict is not READY and the driver exits 0. Plan should say: 'Missing verdict prints "verdict: unknown"; exit always equals the driver status.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: Lock probe is left unresolved with a fallback, so the AC-4 lock test cannot be written deterministically (helper vs driv

- Severity: MEDIUM
- References: CHANGE_PLAN s11 D-2 and s22 non-blocking probe item.
- Failure: Lock probe is left unresolved with a fallback, so the AC-4 lock test cannot be written deterministically (helper vs driver refusal differ in message and code). Plan should say: 'Helper refuses via a non-blocking flock probe on driver.lock with $UNCLE_REFUSE_CODE; test holds the lock in a background process.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: Unspecified inputs: empty-string BRANCH, --audit combined with verify/--runs/--performance (which exec early and swallow

- Severity: MEDIUM
- References: uncle:244-246 early exec for verify, --performance, --runs; CHANGE_SPEC s8 refusal list omits them.
- Failure: Unspecified inputs: empty-string BRANCH, --audit combined with verify/--runs/--performance (which exec early and swallow it), and an existing FINAL_AUDIT state. Plan should say: 'Empty BRANCH is refused; --audit with those flags is refused; existing FINAL_AUDIT state is accepted and re-run.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: D-1 (--audit --attended parses as no BRANCH) conflicts with the spec's 'BRANCH beginning with --' refusal; the test expe

- Severity: LOW
- References: CHANGE_PLAN s10 D-1 and s8 versus CHANGE_SPEC s8.
- Failure: D-1 (--audit --attended parses as no BRANCH) conflicts with the spec's 'BRANCH beginning with --' refusal; the test expectation is ambiguous. Plan should say: 'A -- token after --audit is never a BRANCH and falls to the existing handler; the option-like refusal applies only to --audit=--x.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
