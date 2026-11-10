## AR-001: D-3 precedence contradicts itself: 'only when no non-spending failure occurred' then 'a mix returns 75 too'.

- Severity: HIGH
- References: CHANGE_PLAN D-3 vs CHANGE_SPEC AC-8, SB-10, SI-6.
- Failure: D-3 precedence contradicts itself: 'only when no non-spending failure occurred' then 'a mix returns 75 too'. AC-8/SB-10 keep fallback on other failures. Say: 'If any worker exits 75 the scheduler returns 75 even if others failed otherwise; fallback is skipped and failed sections rerun on resume.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Plan never says how resume tells a complete section from a partial one; a killed or failed worker may leave a non-empty

- Severity: HIGH
- References: D-5 skips on 'exists and is non-empty'; spec section 8 assumes a killed worker leaves its section missing.
- Failure: Plan never says how resume tells a complete section from a partial one; a killed or failed worker may leave a non-empty file that D-5 skips. Say: 'A section is finished only if its worker exited 0 and wrote via temp file plus atomic rename; partial outputs are deleted at stage start.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Stopped message is undefined when the 402 body lacks figures.

- Severity: MEDIUM
- References: SB-6 template needs $X and $Y; D-1 fields are optional; AC-1 says 'limit and suggested increase (or balance)'.
- Failure: Stopped message is undefined when the 402 body lacks figures. SB-6 gives only the budget_reached template. Say: 'For balance_exhausted print the balance wording; omit any clause whose figure is missing and never print None or $0.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: budget_cap leaves rounding, remaining <= 0, typical <= 0, and running-versus-new workers unspecified.

- Severity: MEDIUM
- References: D-6 and AC-7 say only 'remaining/typical-cost (minimum 1)'.
- Failure: budget_cap leaves rounding, remaining <= 0, typical <= 0, and running-versus-new workers unspecified. Say: 'cap = max(1, floor(remaining/typical)); typical<=0 uses 400000; the cap bounds total concurrent workers and never exceeds configured concurrency.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: D-6 says the budget header goes into 'the same marker/side file' as the stop marker, but section 8 lists two separate en

- Severity: MEDIUM
- References: D-2 UNCLE_SPENDING_STOP_FILE vs D-6 UNCLE_BUDGET_REMAINING_FILE vs section 8.
- Failure: D-6 says the budget header goes into 'the same marker/side file' as the stop marker, but section 8 lists two separate env vars. Parallel workers can race on one file and stale files can persist. Say: 'Each worker writes its own file per name; the scheduler clears stale files at stage start and reads the minimum remaining value.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Plan does not say whether exit 75 is treated as a spending stop in stages other than PROJECT_PLAN that share the schedul

- Severity: LOW
- References: D-3 and D-4 scope handling to schedulers and the PROJECT_PLAN case.
- Failure: Plan does not say whether exit 75 is treated as a spending stop in stages other than PROJECT_PLAN that share the schedulers. Say: 'Only PROJECT_PLAN treats 75 as a spending stop; other stages treat it as an ordinary failure.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Exit 75 is returned by the runner for all callers, but only PROJECT_PLAN handling is specified.

- Severity: HIGH
- References: CHANGE_PLAN D-2/D-3 vs D-4; the change-impact table lists no other stagegate callers.
- Failure: Exit 75 is returned by the runner for all callers, but only PROJECT_PLAN handling is specified. Plan should say: 'Only PROJECT_PLAN interprets 75; every other caller treats any nonzero exit, including 75, as an ordinary failure as before.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: D-3 contradicts itself on mixed failures: it says 75 is returned 'only when no non-spending failure occurred', then says

- Severity: HIGH
- References: CHANGE_PLAN D-3 final sentence versus CHANGE_SPEC AC-8, SI-4 and SI-6.
- Failure: D-3 contradicts itself on mixed failures: it says 75 is returned 'only when no non-spending failure occurred', then says a mix returns 75 too. Plan should say: 'If any worker hit a spending stop, return 75 regardless of other failures; the fallback never runs.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: D-5 skip-if-output-exists applies to every run, so a stale non-empty section from an old or failed run is silently reuse

- Severity: MEDIUM
- References: CHANGE_PLAN D-5 has no condition; SB-10/AC-8 require unchanged non-spending behavior.
- Failure: D-5 skip-if-output-exists applies to every run, so a stale non-empty section from an old or failed run is silently reused, breaking the baseline where reruns redo all sections. Plan should say: 'Skipping applies only when stop-reason is spending_limit; otherwise sections are removed as today.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: A section partially written by a worker killed during the stop passes the 'non-empty' test and is reused on resume.

- Severity: MEDIUM
- References: CHANGE_SPEC section 8 assumes a killed worker's section is missing; CHANGE_PLAN D-5 tests only exists and non-empty.
- Failure: A section partially written by a worker killed during the stop passes the 'non-empty' test and is reused on resume. Plan should say: 'Workers write to a temp name and rename on success; resume checks only the final name.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The shared UNCLE_BUDGET_REMAINING_FILE is written by up to 14 concurrent workers with no atomicity or ordering rule, and

- Severity: MEDIUM
- References: CHANGE_PLAN D-6 gives a single shared side file with no cleanup; AC-7 says an absent header leaves concurrency unchanged.
- Failure: The shared UNCLE_BUDGET_REMAINING_FILE is written by up to 14 concurrent workers with no atomicity or ordering rule, and a stale file from a prior run could cap a resumed run. Plan should say: 'The file is removed at stage start, written atomically, and the most recent value wins.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The _EXTERNAL_CAPACITY patterns 'status\s*402' and 'http\s*402' can match unrelated validator output that mentions 402.

- Severity: LOW
- References: CHANGE_PLAN D-7 versus AC-6, which requires false for ordinary validator failures.
- Failure: The _EXTERNAL_CAPACITY patterns 'status\s*402' and 'http\s*402' can match unrelated validator output that mentions 402. Plan should say: 'The pattern is anchored to the client error prefix, e.g. HTTP 402:.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: D-3 contradicts itself on mixed failures: it says 75 is returned only when no non-spending failure occurred, then says a

- Severity: HIGH
- References: CHANGE_PLAN D-3. AC-8 covers only the pure non-spending case.
- Failure: D-3 contradicts itself on mixed failures: it says 75 is returned only when no non-spending failure occurred, then says a mix returns 75 too. Settle it: 'If any worker reports a spending stop, the scheduler returns 75 regardless of other failures, and the stop-reason also records the count of non-spending failures.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Exit 75 alone is trusted as the spending signal, and the plan never says who creates or protects the marker and budget s

- Severity: HIGH
- References: D-2, D-3, D-6 name the env vars without ownership; section 12 maps a missing marker to 'details unavailable' instead of ordinary failure.
- Failure: Exit 75 alone is trusted as the spending signal, and the plan never says who creates or protects the marker and budget side files. Another child exiting 75 (EX_TEMPFAIL) would stop the stage. Settle it: 'Stagegate creates both files under a per-run 0700 dir and removes them at stage end; exit 75 counts as a spending stop only if its marker parses, else it is an ordinary failure.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Marker fields come from the remote 402 body and flow unvalidated into stderr and stop-reason, so control characters or o

- Severity: MEDIUM
- References: D-1 lists the fields; spec section 10 says nothing about sanitizing host values.
- Failure: Marker fields come from the remote 402 body and flow unvalidated into stderr and stop-reason, so control characters or oversized strings could be injected. Settle it: 'Only the two fixed codes and integer atomic fields are accepted; any other field type invalidates the SpendingStop, and scope is truncated to 64 printable ASCII characters.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Resume skips any non-empty section file, so a truncated or stale section left by a killed worker would be reused as vali

- Severity: MEDIUM
- References: D-5 'exists and is non-empty'; spec section 8 assumes a killed worker leaves its section missing, which is not guaranteed.
- Failure: Resume skips any non-empty section file, so a truncated or stale section left by a killed worker would be reused as valid. Settle it: 'Workers write to a temp file and rename atomically on success; resume skips only renamed finals and deletes leftover temp files.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: D-3 precedence contradicts itself: 75 only when no non-spending failure, then 'a mix returns 75 too'.

- Severity: HIGH
- References: CHANGE_PLAN D-3 vs CHANGE_SPEC AC-8/SB-10.
- Failure: D-3 precedence contradicts itself: 75 only when no non-spending failure, then 'a mix returns 75 too'. Settle: 'If any worker exits 75 the scheduler returns 75 regardless of other failures; fallback runs only when no worker exited 75.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: Mixed outcomes (75 plus other failures) are untested; tests cover only pure cases.

- Severity: HIGH
- References: CHANGE_PLAN section 16 test table; D-3 mix clause.
- Failure: Mixed outcomes (75 plus other failures) are untested; tests cover only pure cases. Settle: 'The shell test includes a mixed case asserting exit 75, no fallback, finished sections kept.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: Budget cap is not testably defined: rounding, remaining=0, remaining<typical, no finished call yet, bad header.

- Severity: HIGH
- References: CHANGE_PLAN D-6; AC-7 mentions a scheduler test but section 16 lists only the pure function test.
- Failure: Budget cap is not testably defined: rounding, remaining=0, remaining<typical, no finished call yet, bad header. Settle: 'cap=max(1,floor(remaining/typical)); typical=400000 until a call finishes then integer mean; remaining<=0 gives 1; non-integer header ignored.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: D-5 skip rule is ambiguous for partial outputs (killed mid-write, .json without .md).

- Severity: MEDIUM
- References: CHANGE_PLAN D-5 vs CHANGE_SPEC section 8 'killed before writing'.
- Failure: D-5 skip rule is ambiguous for partial outputs (killed mid-write, .json without .md). Settle: 'Skip only if all output files exist and are non-empty; otherwise rerun and overwrite.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: Marker file contract is undefined: JSON schema, stale marker from a prior run, concurrent writers, and the USD conversio

- Severity: MEDIUM
- References: CHANGE_PLAN D-2, section 12; CHANGE_SPEC SB-6.
- Failure: Marker file contract is undefined: JSON schema, stale marker from a prior run, concurrent writers, and the USD conversion/rounding for the Stopped line. Settle: 'Markers are per-worker paths cleared at stage start; USD=atomic/1e6 to 2 decimals rounded up; missing field renders unknown.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: 402 matching variants are unspecified: code casing or nesting, valid code with missing numeric fields.

- Severity: LOW
- References: CHANGE_PLAN D-1; CHANGE_SPEC AC-1/AC-2.
- Failure: 402 matching variants are unspecified: code casing or nesting, valid code with missing numeric fields. Settle: 'Match is exact, case-sensitive on top-level code; missing numeric fields yield a SpendingStop with those fields None.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
