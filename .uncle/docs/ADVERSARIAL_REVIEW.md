## AR-001: Exit code precedence is unspecified when several conditions hold at once (driver failure plus gate stop, a signal after

- Severity: HIGH
- References: CHANGE_SPEC AC-4, N-8; CHANGE_PLAN section 12 lists codes with no ordering.
- Failure: Exit code precedence is unspecified when several conditions hold at once (driver failure plus gate stop, a signal after a nonzero exit). Say: 'Precedence: signal (130/143), then gate/signing stop (3), then driver nonzero or failed check (1); 0 only if the driver exited 0 with no gate or check failure.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: How the runner tells a gate stop (3) from a plain driver failure (1) is undefined, though both are nonzero driver exits.

- Severity: HIGH
- References: CHANGE_PLAN section 12 and I-5 'classify_exit' with no input contract.
- Failure: How the runner tells a gate stop (3) from a plain driver failure (1) is undefined, though both are nonzero driver exits. Say: 'Exit 3 is chosen when classify_exit matches the gate/signing-handoff marker; every other nonzero exit is 1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Unattended behavior when the driver reaches a human gate is unspecified: stop, auto-delegate, or hang.

- Severity: MEDIUM
- References: CHANGE_SPEC N-4, N-8 versus I-2 ('delegated = delegated'); AC-4.
- Failure: Unattended behavior when the driver reaches a human gate is unspecified: stop, auto-delegate, or hang. Say: 'Unattended --noui never reads stdin; a run reaching a human gate stops and exits 3 naming the gate on stderr.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Input combinations are unspecified: empty text, multiple startup actions, --attended without --noui, --attended with --c

- Severity: MEDIUM
- References: CHANGE_SPEC AC-2, N-5, N-6; CHANGE_PLAN D-6 says CR consumes stdin and attended needs tty.
- Failure: Input combinations are unspecified: empty text, multiple startup actions, --attended without --noui, --attended with --change-request (stdin used for CR text yet D-6 needs a tty), and EOF or blank at a gate. Say: 'Multiple actions, empty text, or --change-request with --attended refuse exit 2; EOF or blank at an attended gate means not approved, exit 3.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Output rules conflict or are unclear: D-5 prefixes every line with elapsed time while AC-3 only requires progress lines

- Severity: MEDIUM
- References: CHANGE_PLAN D-5 versus CHANGE_SPEC AC-3; CHANGE_SPEC section 10 redaction has no AC.
- Failure: Output rules conflict or are unclear: D-5 prefixes every line with elapsed time while AC-3 only requires progress lines to; stderr merging is unspecified; secret redaction from the spec has no plan mechanism or test. Say: 'Every line is prefixed with elapsed time, driver stderr is merged into stdout, env secrets are redacted and tested.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: UNCLE_NOUI with empty or 0 value, and a second signal during the grace period, are unspecified.

- Severity: LOW
- References: CHANGE_SPEC AC-9, N-11; CHANGE_PLAN section 12 'group kill after grace' gives no length or second-signal rule.
- Failure: UNCLE_NOUI with empty or 0 value, and a second signal during the grace period, are unspecified. Say: 'UNCLE_NOUI other than exactly 1 is ignored silently; a second signal during grace kills the process group immediately.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: TUI delegation (cmd_for, _enter_run_worktree, _read_banner) is rated Medium-high risk but is covered only by existing su

- Severity: HIGH
- References: CHANGE_PLAN s16.1.r4 coverage 'existing TUI suites'; AC-10 only compares runner results to baseline.
- Failure: TUI delegation (cmd_for, _enter_run_worktree, _read_banner) is rated Medium-high risk but is covered only by existing suites. Plan should say: before step 3, capture golden outputs of the old functions for all four actions and issue/non-issue modes, and assert delegated versions match exactly.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: No rule for launcher behavior when --noui is absent.

- Severity: MEDIUM
- References: s16.1.r3 'Medium (argument order)'; AC-9 matrix covers only the enabling side.
- Failure: No rule for launcher behavior when --noui is absent. Plan should say: with no --noui and UNCLE_NOUI unset or not exactly '1' (including 0 and empty), the launcher produces the identical exec argv and exported env as before.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Compatibility keeps only the finish_decision re-export, but existing tests may patch other uncle_tui names that move to

- Severity: MEDIUM
- References: s8.1 names only finish_decision; s20.1.r1 says 'Keep re-exports' without a list.
- Failure: Compatibility keeps only the finish_decision re-export, but existing tests may patch other uncle_tui names that move to run_duties. Plan should say: every uncle_tui attribute referenced by existing tests stays on uncle_tui and delegation goes through it so patches still take effect.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Uncommitted prior-attempt edits to uncle and uncle_tui.py already exist, and the plan sets no baseline for them.

- Severity: MEDIUM
- References: git status shows M uncle and M uncle_tui.py; D-8 completes in place; AC-10 compares only to BASELINE_REPORT.
- Failure: Uncommitted prior-attempt edits to uncle and uncle_tui.py already exist, and the plan sets no baseline for them. Plan should say: the regression baseline is committed HEAD, and the step 1 audit must confirm the uncle_tui.py diff has no non-delegation behavior change.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Unattended --noui behavior at human gates is ambiguous (stop vs auto-approve).

- Severity: HIGH
- References: CHANGE_SPEC N-4/N-8, I-2: only implied by exit 3; no sentence forbids auto-approval.
- Failure: Unattended --noui behavior at human gates is ambiguous (stop vs auto-approve). Plan should say: 'Unattended --noui never answers a gate; it stops, records nothing as human, and exits 3.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Secret redaction is claimed but has no enforcement point or test.

- Severity: MEDIUM
- References: CHANGE_SPEC section 10; CHANGE_PLAN impact table and ACs contain no redaction component or test.
- Failure: Secret redaction is claimed but has no enforcement point or test. Plan should say: 'Headless redacts values of env vars matching *KEY*/*TOKEN*/*SECRET*/*PASSWORD* from all streamed output, with a byte-level test.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Text-file trust (V-1) is said to apply identically, but the runner re-reads env and the plan does not say where validati

- Severity: MEDIUM
- References: CHANGE_PLAN s1 'reads that same environment'; s10 trust failure -> exit 2, check location unstated.
- Failure: Text-file trust (V-1) is said to apply identically, but the runner re-reads env and the plan does not say where validation occurs (symlink, ownership, TOCTOU). Plan should say: 'Runner re-validates the text file with the shared trust check right before reading, exits 2 on failure.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: UNCLE_STARTUP_ACTION from env is a new trust boundary and the runner is directly invocable.

- Severity: MEDIUM
- References: CHANGE_PLAN s7 derives driver from UNCLE_STARTUP_ACTION; D-9 build_driver_command.
- Failure: UNCLE_STARTUP_ACTION from env is a new trust boundary and the runner is directly invocable. Plan should say: 'UNCLE_STARTUP_ACTION must be one of four allowlisted actions, otherwise exit 2; driver argv is never built from env-supplied paths.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Signal grace period and repeated-signal behavior are unspecified, risking orphans holding worktree locks.

- Severity: LOW
- References: CHANGE_PLAN s10 'group kill after grace'; AC-8.
- Failure: Signal grace period and repeated-signal behavior are unspecified, risking orphans holding worktree locks. Plan should say: 'Grace is 10s then SIGKILL to the group; a second signal triggers immediate SIGKILL.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Exit-code precedence is unspecified when several conditions hold (driver exit 0 but a check failed, gate stop plus signa

- Severity: HIGH
- References: CHANGE_SPEC AC-4/N-8 and CHANGE_PLAN s10.1 list codes but no ordering, and say 'driver failure' without defining how a failed check is detected from driver output.
- Failure: Exit-code precedence is unspecified when several conditions hold (driver exit 0 but a check failed, gate stop plus signal, driver nonzero plus signing handoff, signal during refusal/setup). Tests can't know the expected code. Plan should say: 'Precedence: signal (130/143) > gate/signing stop (3) > driver nonzero or failed check (1) > finished (0); refusal 2 occurs only before start.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
