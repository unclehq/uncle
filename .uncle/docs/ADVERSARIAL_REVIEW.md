## AR-001: The spec's stub text is `skipped: class <class>, no risk hits`, but the plan's console line is `Adversarial review skipp

- Severity: HIGH
- References: CHANGE_SPEC AC-5 and SB-1 give the stub text. CHANGE_PLAN section 19 gives the console line.
- Failure: The spec's stub text is `skipped: class <class>, no risk hits`, but the plan's console line is `Adversarial review skipped: class <class>, no risk hits`. Neither says which string is validated or rendered. Settle it: the stub overall_assessment is exactly `skipped: class <class>, no risk hits`, and the console line is that text prefixed with `Adversarial review `.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: AC-1 and AC-2 put the stale plan sha under build() rejection, but the plan checks the sha in the shell helper, and build

- Severity: HIGH
- References: CHANGE_PLAN section 1 and section 8 interface. AC-2 lists a stale plan sha under build rejection.
- Failure: AC-1 and AC-2 put the stale plan sha under build() rejection, but the plan checks the sha in the shell helper, and build() has no plan to compare. It doesn't say whether `skip-review` re-checks it. Settle it: `skip-review` re-verifies the stored plan_sha against the supplied plan and exits 1 on mismatch, and build() does not evaluate the sha.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The plan doesn't say how the doc/test path rule treats an empty set of owned files, or files that are neither doc nor te

- Severity: MEDIUM
- References: AC-1 says `for docs/test-only every owned file is doc/test respectively`. No behavior covers empty or mixed sets.
- Failure: The plan doesn't say how the doc/test path rule treats an empty set of owned files, or files that are neither doc nor test. It also doesn't say whether `small` has a path rule. Settle it: an empty owned-file set means full review, any non-doc or non-test file in a docs or test-only class means full review, and `small` has no path rule beyond the floor.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: D-4 says a recheck clears skip, but the plan doesn't say what happens if the plan changes after the stub is written or a

- Severity: MEDIUM
- References: SB-9 and D-4 cover the stale sha only before the review runs. CHANGE_PLAN sections 6-7 describe no re-entry.
- Failure: D-4 says a recheck clears skip, but the plan doesn't say what happens if the plan changes after the stub is written or approved. It doesn't say whether the stub is regenerated or discarded. Settle it: if the plan sha changes after the stub is written, the stub is discarded and the review state reruns the decision against the new sha.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The plan doesn't say what happens when the human declines at the review gate on a skipped review: rerun with a forced fu

- Severity: MEDIUM
- References: SB-6 says the `human can decline`, and D-3 creates a marker. No behavior defines the decline outcome.
- Failure: The plan doesn't say what happens when the human declines at the review gate on a skipped review: rerun with a forced full review, or stop. It also doesn't say whether the marker is cleared. Settle it: declining a skipped review reruns ADVERSARIAL_REVIEW as a full review, and the `review-skipped` marker is removed before the panel starts.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: AC-7 requires a cost ledger row, but the scope-cut list drops the ledger row first, so the two collide.

- Severity: LOW
- References: AC-7 requires the ledger row. CHANGE_PLAN section 21 lists the ledger row as the first cut.
- Failure: AC-7 requires a cost ledger row, but the scope-cut list drops the ledger row first, so the two collide. Settle it: the ledger row is not required to satisfy AC-7, and the change-class.json fields and the marker are the required records.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan never says what happens when a skip stub is declined at the gate or the run re-enters ADVERSARIAL_REVIEW.

- Severity: HIGH
- References: CHANGE_PLAN s6-7, D-3/D-4 cover only recheck clearing; SB-6 says the human can decline with no post-decline behavior.
- Failure: Plan never says what happens when a skip stub is declined at the gate or the run re-enters ADVERSARIAL_REVIEW. Decision: skip is recomputed from the current plan sha on every entry, and the review-skipped marker is deleted whenever a full review runs.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Stale plan sha check is placed in the shell helper per the Interface section, but AC-2 and SB-9 test it as Python build

- Severity: HIGH
- References: CHANGE_PLAN s1 and s8 versus CHANGE_SPEC AC-2/SB-9.
- Failure: Stale plan sha check is placed in the shell helper per the Interface section, but AC-2 and SB-9 test it as Python build behavior. Decision: the sha check lives in change_class_review_skipped and skip-review CLI only; build() does not evaluate it.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Other consumers of ADVERSARIAL_REVIEW.json (final audit, approval hashes) may assume non-empty findings; only updated-pl

- Severity: MEDIUM
- References: CHANGE_PLAN s5 Not modified and s22 risk; AC-9 covers updated-plan only.
- Failure: Other consumers of ADVERSARIAL_REVIEW.json (final audit, approval hashes) may assume non-empty findings; only updated-plan is proven by AC-9. Decision: tests must also run final-audit input and approval hashing on the stub, and the stub overall_assessment is non-empty.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Existing suites are said to be unchanged, yet may use classifier stubs or fixtures returning docs/small that would now e

- Severity: MEDIUM
- References: CHANGE_PLAN s17 versus s22 risk 3.
- Failure: Existing suites are said to be unchanged, yet may use classifier stubs or fixtures returning docs/small that would now emit skip. Decision: default test classifier stubs never emit review: skip, and any broken existing suite is changed only with renewed approval.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Validation of the optional classifier review field is unspecified for non-string, uppercase or unknown values.

- Severity: MEDIUM
- References: CHANGE_PLAN s8 classifier answer item; AC-3 covers only unusable whole answers.
- Failure: Validation of the optional classifier review field is unspecified for non-string, uppercase or unknown values. Decision: only the exact lowercase string skip is honored; any other value is treated as absent (full review) without invalidating the rest of the answer.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: s12 says a failing stub hits the existing format-retry/stop path, then says stop directly without retry.

- Severity: LOW
- References: CHANGE_PLAN s12 versus AC-8.
- Failure: s12 says a failing stub hits the existing format-retry/stop path, then says stop directly without retry. Decision: a failing stub stops the run immediately, with no retry and no fallback to full review.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: The skip floor sees only plan text and owned files, so a small or docs plan can skip review while touching sensitive cod

- Severity: HIGH
- References: CHANGE_SPEC AC-1 applies the path rule only to docs/test-only; class small has none. D-1 uses plan-text risk_hits.
- Failure: The skip floor sees only plan text and owned files, so a small or docs plan can skip review while touching sensitive code. Plan should say: skip fails closed when no owned files are declared, or any owned path is outside doc/test globs; for class small, auth/secret/shell/driver/gate paths force full review.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: The model's `review` value is the only positive skip signal, and the plan does not say how a malformed value or a prompt

- Severity: HIGH
- References: CHANGE_PLAN s8 lists optional "review":"skip"; D-2 trusts source model. AC-3 covers only failure or unusable answers.
- Failure: The model's `review` value is the only positive skip signal, and the plan does not say how a malformed value or a prompt-injected plan is handled. Plan should say: only the exact string "skip" counts; any other value, type or duplicate key means full; plan text is untrusted data in the classifier prompt.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The shell helper trusts stored review=skip plus a matching sha, so a hand-edited change-class.json or a race can bypass

- Severity: MEDIUM
- References: CHANGE_PLAN s8: skip-review only writes the stub and exits 1 if the decision is not skip; the helper checks stored review and sha.
- Failure: The shell helper trusts stored review=skip plus a matching sha, so a hand-edited change-class.json or a race can bypass the floor. Plan should say: skip-review recomputes the floor against the current plan in the same invocation that writes the stub, and never trusts stored review=skip alone.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: WORKFLOW_SKIP_REVIEW disables skip only when it equals 0, so empty, false or no leaves skip enabled, which fails open.

- Severity: MEDIUM
- References: CHANGE_PLAN s8: 'true only when env not 0'; SI-4 says any uncertainty runs full review.
- Failure: WORKFLOW_SKIP_REVIEW disables skip only when it equals 0, so empty, false or no leaves skip enabled, which fails open. Plan should say: skip is enabled only when WORKFLOW_SKIP_REVIEW is unset or exactly 1; any other value means full review.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: The plan does not say what happens to an existing ADVERSARIAL_REVIEW.json or marker on rerun or resume.

- Severity: MEDIUM
- References: CHANGE_PLAN s6-7 and s14 describe writing the stub and the marker .uncle/workflow/review-skipped but say nothing about reruns or stale files. D-4 clears skip on recheck only.
- Failure: The plan does not say what happens to an existing ADVERSARIAL_REVIEW.json or marker on rerun or resume. Plan should say: the stub is written only when no review exists or the existing one is a stub, a non-skip decision removes a stale stub and marker before the panel runs.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: AC-9 expects the updated-plan stage to accept zero findings, but the risk section leaves the failure case open ('emit no

- Severity: HIGH
- References: CHANGE_SPEC AC-9; CHANGE_PLAN s22 risk 2 conflicts with AC-5 'zero findings'.
- Failure: AC-9 expects the updated-plan stage to accept zero findings, but the risk section leaves the failure case open ('emit non-empty assessment, otherwise stop and ask'). Settle: 'If the updated-plan path rejects zero findings, the stub carries one informational finding; the plan stage is not modified.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: AC-1 requires every owned file to be doc/test, but the plan never defines how files are classified or what a plan with z

- Severity: HIGH
- References: CHANGE_SPEC AC-1 'every owned file is doc/test'; no rule source named in CHANGE_PLAN s1 or s8.
- Failure: AC-1 requires every owned file to be doc/test, but the plan never defines how files are classified or what a plan with zero owned files does. Settle: 'Owned-file classification reuses the existing floor path rules in change_class.py; a plan with no owned files is never skipped.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: AC-7 is assigned to the Python suite, but the marker and ledger row are written by the shell drivers, and the ledger row

- Severity: MEDIUM
- References: CHANGE_PLAN s16 'review-skip-test.py covers ... 7' vs D-3 and s21.
- Failure: AC-7 is assigned to the Python suite, but the marker and ledger row are written by the shell drivers, and the ledger row is the first scope cut. Settle: 'AC-7 is split: change-class.json is tested in the .py suite, marker and ledger in the .sh suite; if the ledger row is cut, AC-7 needs only json plus marker.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: Corrupted-stub behavior is stated two ways: 'existing format-retry/stop path' versus 'stop directly'.

- Severity: MEDIUM
- References: CHANGE_PLAN s12; CHANGE_SPEC AC-8 'stops the run like a bad review'.
- Failure: Corrupted-stub behavior is stated two ways: 'existing format-retry/stop path' versus 'stop directly'. Settle: 'A stub failing validation stops the run immediately with no retry, nonzero exit, and no model invocation, in both drivers.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: Stale plan sha handling is split: AC-2 puts it in build(), the plan puts it in the shell helper, and D-4 has recheck cle

- Severity: MEDIUM
- References: CHANGE_SPEC AC-2, SB-9 vs CHANGE_PLAN s8 and D-4.
- Failure: Stale plan sha handling is split: AC-2 puts it in build(), the plan puts it in the shell helper, and D-4 has recheck clearing skip. Missing plan_sha is unspecified. Settle: 'The sha check lives only in change_class_review_skipped; a missing plan_sha is a mismatch and yields full review; recheck independently clears skip.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: Other values of the classifier's review field (Skip, full, null, non-string) are unspecified.

- Severity: LOW
- References: CHANGE_PLAN s8 'optional review:skip'; no handling of other values.
- Failure: Other values of the classifier's review field (Skip, full, null, non-string) are unspecified. Settle: 'Only the exact lowercase string skip is honored; any other value or type is treated as full without error.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
