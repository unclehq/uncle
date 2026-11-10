## AR-001: Plan never says what happens when filtering leaves a step with zero owns tokens.

- Severity: HIGH
- References: CHANGE_PLAN D-1/D-2 drop tokens with no empty-result rule; AC-2/AC-3 cover only mixed valid and invalid tokens.
- Failure: Plan never says what happens when filtering leaves a step with zero owns tokens. Settle it: 'If filtering empties a step's owns, the validator reports its normal missing-owns error, which triggers the single repair turn; the dropped-token warning prints first.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Marker lifecycle is inconsistent: D-3 removes it only on a pass, section 6 retains it on failure.

- Severity: HIGH
- References: CHANGE_PLAN D-3 vs section 6 ('marker retained'); CHANGE_SPEC Assumptions.
- Failure: Marker lifecycle is inconsistent: D-3 removes it only on a pass, section 6 retains it on failure. A human who fixes the plan by hand and resumes cannot get a fresh repair. Settle it: 'The marker stores the plan file hash; a different hash on resume gets one repair, the same hash exits 1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Marker state after a spending stop during repair is unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN D-3/D-4, section 6; CHANGE_SPEC AC-5 (no second repair on resume) vs AC-7.
- Failure: Marker state after a spending stop during repair is unspecified. D-4 exits without re-check, leaving the marker set, so a resume after budget is raised skips repair and fails. Settle it: 'On a spending stop during repair the marker is removed so resume repairs again.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The shape test is specified for backticked spans only; mixed lines (ticks plus plain prose) and the no-ticks route are l

- Severity: MEDIUM
- References: plan_steps.py lines 72-90 (shape test only in no-ticks branch); CHANGE_PLAN D-1.
- Failure: The shape test is specified for backticked spans only; mixed lines (ticks plus plain prose) and the no-ticks route are left ambiguous. Settle it: 'The shape filter runs on every candidate token from either route; a line with any ticks ignores unticked text.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Final-failure message leaves the step unspecified when the error has no step-N, several steps fail, or the plan is UPDAT

- Severity: MEDIUM
- References: CHANGE_PLAN D-5 (parsed from step-N); CHANGE_SPEC section 8 and AC-5.
- Failure: Final-failure message leaves the step unspecified when the error has no step-N, several steps fail, or the plan is UPDATED_PLAN. Settle it: 'Print every distinct step-N in the errors, or "step: unknown" if none.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Section 8 claims previously valid plans are unchanged, yet D-1 drops spaced backticked tokens the old parser kept.

- Severity: LOW
- References: CHANGE_PLAN section 8 vs D-1; CHANGE_SPEC section 7.
- Failure: Section 8 claims previously valid plans are unchanged, yet D-1 drops spaced backticked tokens the old parser kept. Warning channel and repetition are also unspecified. Settle it: 'Warnings go to stderr once per parse; a previously valid plan yields an identical owns list.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Tick-span shape test is narrower than what validate accepts (e.g.

- Severity: HIGH
- References: plan_steps.py:73-80 applies shape regex only to untick'd tokens; CHANGE_SPEC s7 vs CHANGE_PLAN D-1.
- Failure: Tick-span shape test is narrower than what validate accepts (e.g. `src/{a,b}.py`, `~`, `+`, `=`), so previously valid plans may lose owns. Say: 'The tick filter drops only spans with whitespace or a comment marker; any token that passed validate before is kept.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Plan does not say what happens when filtering drops every Owns token for a step (empty owns valid, or new validator fail

- Severity: MEDIUM
- References: CHANGE_PLAN D-1/D-2 give no empty-result behavior; INV-1 covers only kept tokens.
- Failure: Plan does not say what happens when filtering drops every Owns token for a step (empty owns valid, or new validator failure). Say: 'A step whose owns become empty is passed through as empty owns and the validator decides.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Retained marker makes a resumed run exit 1 without clarity on re-check; a user-edited plan or a different later failure

- Severity: MEDIUM
- References: CHANGE_PLAN s6 'resumed run goes straight to exit 1' vs D-3 marker removed only on passing check.
- Failure: Retained marker makes a resumed run exit 1 without clarity on re-check; a user-edited plan or a different later failure gets no repair. Say: 'On resume the check always re-runs first; the marker only suppresses the repair turn and is cleared when the plan hash changes.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Marker lifetime across stage restart or plan regeneration is unspecified; a regenerated plan may never get its one repai

- Severity: MEDIUM
- References: CHANGE_PLAN D-3 and s10 rollback 'harmless if left'.
- Failure: Marker lifetime across stage restart or plan regeneration is unspecified; a regenerated plan may never get its one repair, and 'harmless if left' contradicts AC-5. Say: 'Markers are cleared when the stage regenerates its plan.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Repair-turn outcomes besides spending stop (timeout, nonzero exit, deleted or empty plan file, error lacking step-N) are

- Severity: MEDIUM
- References: CHANGE_PLAN s9 and D-5 parse step from step-N only.
- Failure: Repair-turn outcomes besides spending stop (timeout, nonzero exit, deleted or empty plan file, error lacking step-N) are unspecified for the final-failure message. Say: 'If no step-N is parsable, the message omits the step and still names file and resume command.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: New stderr warnings from three Owns call sites may break existing tests asserting clean stderr while existing tests may

- Severity: LOW
- References: CHANGE_PLAN D-1, R-3, s12.
- Failure: New stderr warnings from three Owns call sites may break existing tests asserting clean stderr while existing tests may not be edited. Say: 'Warnings are emitted only when dropped is non-empty; existing suites are run against baseline after step 1.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Repair prompt embeds validator output and plan text (model-authored, possibly attacker-influenced) with no stated trust

- Severity: HIGH
- References: CHANGE_PLAN D-3 passes plan path plus exact validator output to run_initial_planning_agent; INV-5 is enforced only by prompt wording (R-4).
- Failure: Repair prompt embeds validator output and plan text (model-authored, possibly attacker-influenced) with no stated trust boundary, and the repair agent's write scope is unspecified. Plan should say: the prompt labels plan text and validator output as untrusted data, and the driver re-checks that only the plan file changed.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Marker file name uses <label> and the step number is parsed from validator error text, but neither is constrained.

- Severity: MEDIUM
- References: CHANGE_PLAN D-3 `$STATE_DIR/plan-check-repair-<label>`; D-5 parses `step-N` from error text.
- Failure: Marker file name uses <label> and the step number is parsed from validator error text, but neither is constrained. Plan should state that label is a fixed literal (project-plan or updated-plan) and the parsed step is digits-only before being printed or used in a path.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Dropped tokens are echoed to stderr verbatim in warnings.

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 prints `warning: step N owns: dropped <token>`; tokens come from model-written backticked spans.
- Failure: Dropped tokens are echoed to stderr verbatim in warnings. Plan should say the token is escaped or truncated (control characters and ANSI escapes stripped, max length) before printing.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: The shared path-shape predicate accepts tokens like `../../etc/x`; the old code only rejects a leading `/`.

- Severity: MEDIUM
- References: D-1 pattern `[\w./*?\[\]@-]+` allows `../` segments; plan_steps.py:88 only rejects a leading `/`.
- Failure: The shared path-shape predicate accepts tokens like `../../etc/x`; the old code only rejects a leading `/`. Plan should say whether `..` segments in an owned path are dropped, since owns drives which files a step may write.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: A stale marker from a prior run can suppress the one repair for a changed plan.

- Severity: LOW
- References: CHANGE_PLAN section 6: marker retained on failure; section 10: leftover marker 'harmless'.
- Failure: A stale marker from a prior run can suppress the one repair for a changed plan. Plan should state the marker is cleared whenever the plan file's content hash changes or a new run begins.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The plan does not say whether a later, different failure in the same run gets its own repair once the marker is cleared.

- Severity: HIGH
- References: CHANGE_PLAN D-3 ('Marker is removed when a check passes') against section 6 ('marker retained') and INV-2 'per plan check'.
- Failure: The plan does not say whether a later, different failure in the same run gets its own repair once the marker is cleared. Settle with: 'The marker is removed when a check passes; a later failure is a new failure and gets one repair; a failure with the marker present exits 1 with no agent call.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: The plan leaves unspecified a repair agent that crashes, times out, makes no edit, or empties the plan file.

- Severity: HIGH
- References: CHANGE_PLAN section 9 says only that a crash is a 'failed repair' and the re-check runs. No AC covers a crashed or no-op repair.
- Failure: The plan leaves unspecified a repair agent that crashes, times out, makes no edit, or empties the plan file. Settle with: 'A non-zero agent exit or an unchanged file skips the re-check and takes the final-failure path with the marker set.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: The dropped-token warning format is fixed loosely.

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 and D-2 against CHANGE_SPEC AC-2 and AC-3.
- Failure: The dropped-token warning format is fixed loosely. D-1 gives one text, AC-2/AC-3 say only 'names the step', and D-2 gives no JSON-route format. Settle with: 'Both routes emit exactly `warning: step <label> owns: dropped <token>` on stderr, one line per dropped token, in input order.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: The plan does not say what happens when every Owns span is dropped, or how a directory-like span such as `src/` is treat

- Severity: MEDIUM
- References: CHANGE_PLAN D-1 regex `[\w./*?\[\]@-]+` admits a trailing slash; CHANGE_SPEC INV-1 (plan_model.py:474-482) says directories are invalid.
- Failure: The plan does not say what happens when every Owns span is dropped, or how a directory-like span such as `src/` is treated. Settle with: 'All spans dropped gives an empty owns list and the validator's existing error applies; `src/` passes the shape test and the validator still rejects it.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: The final-failure diagnostic is untestable when the error names no step or several steps, and its stream and resume text

- Severity: MEDIUM
- References: CHANGE_PLAN D-5 ('parsed from step-N in the error') and CHANGE_SPEC AC-5.
- Failure: The final-failure diagnostic is untestable when the error names no step or several steps, and its stream and resume text are unspecified. Settle with: 'Print to stderr; with zero or several steps print them comma-separated or `step: n/a`; the resume command is the one the driver prints for other stage failures.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: The plan is ambiguous when `spending-stop` already exists before the repair starts, for example from a resumed run.

- Severity: MEDIUM
- References: CHANGE_PLAN D-4 and R-2 against AC-7 ('during the repair turn').
- Failure: The plan is ambiguous when `spending-stop` already exists before the repair starts, for example from a resumed run. It checks the flag only after the repair. Settle with: 'The flag is checked before launching the repair (stop without calling the agent) and after it (stop without re-checking).'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
