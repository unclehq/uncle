## AR-001: Plan never says how argv is matched to an allowlist shape versus the model's `op` label.

- Severity: HIGH
- References: CHANGE_PLAN s1 (ops carry op and argv); AC-8 'exact command shapes'.
- Failure: Plan never says how argv is matched to an allowlist shape versus the model's `op` label. Settle: 'The policy derives the operation from argv alone; it refuses if argv matches no allowlist shape or the op label disagrees.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Floor and default disallow list are conflated; spec leaves the floor list UNRESOLVED while D-1 lists a smaller set.

- Severity: HIGH
- References: CHANGE_SPEC s15 UNRESOLVED; CHANGE_PLAN D-1; AC-7; I-7.
- Failure: Floor and default disallow list are conflated; spec leaves the floor list UNRESOLVED while D-1 lists a smaller set. Settle: 'Default list equals the change-request lists verbatim; the locked floor is exactly D-1 and always applies.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Remote branch delete is allowed, but deleting the default or current branch is unspecified.

- Severity: HIGH
- References: CHANGE_PLAN D-1, D-2, D-7; AC-8.
- Failure: Remote branch delete is allowed, but deleting the default or current branch is unspecified. Settle: 'git push origin --delete <branch> is refused for the default branch, HEAD, or refspec/colon forms.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Verify argv source is ambiguous: the model emits verify argv, yet D-4 says verify is deterministic.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 vs D-4 and D-6.
- Failure: Verify argv source is ambiguous: the model emits verify argv, yet D-4 says verify is deterministic. Settle: 'Verify argv comes from a fixed per-op template; model-supplied verify argv must equal it, and expected is compared by exact string.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Behavior after mid-run failure and process exit codes are undefined.

- Severity: MEDIUM
- References: CHANGE_PLAN s7 state transitions; spec s8; AC-6, AC-10.
- Failure: Behavior after mid-run failure and process exit codes are undefined. Settle: 'After a failure, read-only verify still runs for completed ops; exit is nonzero for REFUSED, FAILED, VERIFY_FAILED and zero for DECLINED and success.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Edge inputs unspecified: zero-op plan, duplicate or floor-equal patterns, user patterns versus the allowlist.

- Severity: MEDIUM
- References: CHANGE_PLAN D-5; AC-12; I-4, I-7.
- Failure: Edge inputs unspecified: zero-op plan, duplicate or floor-equal patterns, user patterns versus the allowlist. Settle: 'A zero-op plan is refused; duplicate or floor-equal patterns are rejected leaving the list unchanged; user patterns only add refusals.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan allows minimal edits to protected existing tests for usage/help text, but AC-14 requires the existing suites to pas

- Severity: HIGH
- References: CHANGE_PLAN section 10 and risk row 2 allow expected-string updates; AC-14 requires the suites to pass as at baseline.
- Failure: Plan allows minimal edits to protected existing tests for usage/help text, but AC-14 requires the existing suites to pass as at baseline. Settle with: 'Existing tests are never edited; usage changes must pass every existing assertion, otherwise stop for human re-approval.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Flag combinations beyond the three exclusive flags are unspecified, as is bare --housekeeping with empty TTY stdin.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1 and H-11 list only three exclusive flags; H-12 says existing flags are unchanged.
- Failure: Flag combinations beyond the three exclusive flags are unspecified, as is bare --housekeeping with empty TTY stdin. Settle with: 'Other flag combinations keep prior behavior; --housekeeping with no text and TTY stdin is refused as empty input.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The new Configure entry position in the line menu is unspecified, so existing numbered selections or item-count tests co

- Severity: MEDIUM
- References: CHANGE_PLAN section 10 says the entry is appended; H-9 places it in both menus without fixing its number.
- Failure: The new Configure entry position in the line menu is unspecified, so existing numbered selections or item-count tests could shift. Settle with: 'The entry takes the last number in each menu and no existing item moves.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The driver sources state.sh and reuses driver.lock, but the plan does not say whether it touches shared .uncle/workflow

- Severity: MEDIUM
- References: CHANGE_PLAN section 1 sources state.sh while section 7 says existing state is untouched; R-4 defers the lock helper choice.
- Failure: The driver sources state.sh and reuses driver.lock, but the plan does not say whether it touches shared .uncle/workflow state or releases the lock on refusal. Settle with: 'Housekeeping reads and writes no state or gate files outside .uncle/workflow/housekeeping/, and releases driver.lock on every exit path.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Writing housekeeping.disallow into the shared .uncle/config could disturb other keys; the plan does not say how they are

- Severity: LOW
- References: CHANGE_PLAN risk row 3 says the .uncle/config syntax is unknown; D-5 stores a JSON array string.
- Failure: Writing housekeeping.disallow into the shared .uncle/config could disturb other keys; the plan does not say how they are preserved. Settle with: 'Config writes change only the housekeeping.disallow entry and leave all other keys unchanged.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Allowlisted ops are said to match 'exact command shapes' but the argv grammar is undefined (global options, `--`, `git -

- Severity: HIGH
- References: CHANGE_SPEC AC-8 'exact command shapes'; CHANGE_PLAN s1 'matches program/subcommand/flag sets'.
- Failure: Allowlisted ops are said to match 'exact command shapes' but the argv grammar is undefined (global options, `--`, `git -c`, `gh --repo`, env prefixes). Decision: match the full argv exactly (program, subcommand, fixed flag set, exact positional arity); refuse any global option, unlisted flag or env-assignment token.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Remote `git push origin --delete` is allowed, but the plan doesn't protect the default branch or say how 'merged-only' i

- Severity: HIGH
- References: CHANGE_PLAN D-2/D-7; D-1 covers only force-push to the default branch.
- Failure: Remote `git push origin --delete` is allowed, but the plan doesn't protect the default branch or say how 'merged-only' is enforced for remotes. Decision: refuse `--delete` and `:ref` refspecs for the default branch, HEAD, main and master; require a merged check at execute time for any remote delete.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: The floor lists fixed strings, and variants are unspecified: `rm -fr`, `--recursive --force`, `/*`, `$HOME`, wrappers (`

- Severity: HIGH
- References: CHANGE_PLAN D-1; the D-2 allowlist contains no rm.
- Failure: The floor lists fixed strings, and variants are unspecified: `rm -fr`, `--recursive --force`, `/*`, `$HOME`, wrappers (`env`, `xargs`, `sh -c`), `+refspec`, `--force-with-lease`. Decision: rm and wrapper programs are never allowlisted; `--force-with-lease` and `+refspec` count as force.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Nothing binds the approved plan to the executed argv (TOCTOU), or says the displayed argv is escaped.

- Severity: MEDIUM
- References: CHANGE_PLAN s1 stages plan -> policy -> approval -> execute, with no integrity binding.
- Failure: Nothing binds the approved plan to the executed argv (TOCTOU), or says the displayed argv is escaped. Decision: hash the policy-checked plan, approve that hash, execute only it, and render argv with control characters escaped.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: The editable disallow config is unspecified for empty or over-broad patterns, and for whether it can do anything except

- Severity: MEDIUM
- References: CHANGE_PLAN D-5; CHANGE_SPEC I-4/I-7.
- Failure: The editable disallow config is unspecified for empty or over-broad patterns, and for whether it can do anything except add refusals. Decision: config can only add refusals; empty or bare `*` patterns are rejected; the floor is hard-coded, not read from config.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Read-only verify commands (`git ls-remote`, `gh issue view`) can take arbitrary URLs and targets, and the issue-triage c

- Severity: MEDIUM
- References: CHANGE_PLAN D-6; D-2 'issue-triage' has no defined command shape.
- Failure: Read-only verify commands (`git ls-remote`, `gh issue view`) can take arbitrary URLs and targets, and the issue-triage command shape is undefined. Decision: verify argv is limited to the same repo and refs as the operation; issue-triage allows only fixed label/close/comment shapes.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: Plan never says whether a plan-supplied verify argv is also checked against the disallow list, or what happens when it i

- Severity: HIGH
- References: CHANGE_PLAN D-6; CHANGE_SPEC section 10; AC-10 covers only mismatch, failure and not-run.
- Failure: Plan never says whether a plan-supplied verify argv is also checked against the disallow list, or what happens when it is off the verify allowlist (refuse whole plan vs NOT VERIFIED). Settle: 'A verify argv off the read-only verify allowlist or matching a disallow pattern refuses the whole plan before any command runs, in every mode.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: Floor patterns and the default branch are undefined, so AC-7 tests lack an oracle.

- Severity: HIGH
- References: CHANGE_PLAN D-1; CHANGE_SPEC section 15 marks the exact floor list UNRESOLVED.
- Failure: Floor patterns and the default branch are undefined, so AC-7 tests lack an oracle. Settle: 'Default branch means main, master, or origin HEAD; rm with any recursive or force flag spelling on /, /*, ~, $HOME is refused.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: Pattern grammar `program [subcommand...] [--flag...]` leaves open short-flag clusters, --flag=value, flags before subcom

- Severity: MEDIUM
- References: CHANGE_PLAN D-5; AC-7 'flag-order and quoting variants'; AC-12 invalid pattern.
- Failure: Pattern grammar `program [subcommand...] [--flag...]` leaves open short-flag clusters, --flag=value, flags before subcommand, and all-vs-any flags. Settle: 'A pattern matches when program and subcommands are a prefix of the command tokens and every pattern flag appears in any order, clusters expanded, --flag=value matched by name.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: A valid-JSON plan with zero ops, duplicate ids or missing fields is unspecified; only bad JSON is covered.

- Severity: MEDIUM
- References: CHANGE_PLAN risk table 'Plan model emits bad JSON'; section 7 has no schema rule.
- Failure: A valid-JSON plan with zero ops, duplicate ids or missing fields is unspecified; only bad JSON is covered. Settle: 'A plan that is invalid JSON, has zero ops, or has any op missing id, op, argv, expected or verify is REFUSED with exit 1 before approval.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: Exit statuses and whether verify runs after an execute failure are unspecified for DECLINED, FAILED, VERIFY_FAILED, NOT_

- Severity: MEDIUM
- References: CHANGE_PLAN section 7 transitions; CHANGE_SPEC section 8 gives exit 1 only for input refusals.
- Failure: Exit statuses and whether verify runs after an execute failure are unspecified for DECLINED, FAILED, VERIFY_FAILED, NOT_VERIFIED. Settle: 'After FAILED, executed ops are still verified and unexecuted ops are NOT_VERIFIED; exit 0 only for DECLINED or fully VERIFIED, else 1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: AC-13 static and mutation tests have no defined mechanism for a bash driver.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-13; CHANGE_PLAN section 16.
- Failure: AC-13 static and mutation tests have no defined mechanism for a bash driver. Settle: 'The driver executes plan commands only via one function that consumes the check_plan output; the static test asserts it is the sole execution call site and the mutation test removes the check_plan call and expects the suite to fail.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
