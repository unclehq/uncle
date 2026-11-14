## AR-001: The required diagnostic would appear twice during normal feature extraction because counts are computed twice.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 places the diagnostic inside interpretation_counts and requires one line; supplied scripts/lib/change_class.py:257-258 invokes that function separately for criteria and requirements. The plan must specify reuse so implementation and stderr acceptance tests agree on diagnostic cardinality.
- Failure: The required diagnostic would appear twice during normal feature extraction because counts are computed twice. Add: "For app feature extraction, call interpretation_counts once, reuse both counts, and emit at most one unknown-count diagnostic."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: A valid interpretation with empty sections is present but receives no diagnostic under the plan, conflicting with AC-4.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-4 and §8 require logging when an interpretation exists but a count is zero; CHANGE_PLAN.json §1 logs only when interpretation() is non-empty. Supplied scripts/lib/change_class.py:215-223 returns {} for both empty sections and missing/invalid input. Align AC-4 with the explicit empty-object decision.
- Failure: A valid interpretation with empty sections is present but receives no diagnostic under the plan, conflicting with AC-4. Add: "Treat an empty sections object as absent for diagnostic purposes; valid non-empty sections with either count zero emit the diagnostic."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The plan permits cutting behavior that remains mandatory for acceptance.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §Scope cuts under time pressure says to cut the stderr diagnostic first, while CHANGE_SPEC.json AC-4 and OB-3 require it and CHANGE_PLAN.json §16 requires AC-4 tests. Remove the scope-cut permission so implementation cannot legitimately omit behavior that verification must require.
- Failure: The plan permits cutting behavior that remains mandatory for acceptance. Add: "The AC-4 diagnostic is required and may not be cut under time pressure."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Adding logging inside interpretation_counts produces duplicate diagnostics during normal feature extraction, contradicti

- Severity: MEDIUM
- References: scripts/lib/change_class.py:257-258 calls interpretation_counts separately for criteria and requirements. CHANGE_PLAN.json §1 places logging inside that function, while CHANGE_SPEC.json OB-3 requires one diagnostic line; a helper-only stderr test would miss the regression.
- Failure: Adding logging inside interpretation_counts produces duplicate diagnostics during normal feature extraction, contradicting the one-line requirement. Amend the plan: “features shall call interpretation_counts once per app feature extraction and reuse both counts; test that this emits exactly one diagnostic.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Mixed interpretations with IDs in only one section have ambiguous fallback behavior and compatibility guarantees.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 says “if the id count is 0” and “ids win over structure when present,” but §10 promises identical counts for id-bearing interpretations. scripts/lib/change_class.py:229-230 currently returns zero for an ID-less section even when the other section has IDs; per-section fallback changes that tuple and potentially the class. Narrow the compatibility promise to sections containing IDs.
- Failure: Mixed interpretations with IDs in only one section have ambiguous fallback behavior and compatibility guarantees. Amend the plan: “Apply ID precedence independently per section; preserve counts for sections containing IDs and use structural fallback for the other section, with tests for both mixed cases.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The diagnostic's emission scope is unspecified, so a helper-only test can pass while classification prints twice.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 places logging in interpretation_counts and promises one line; supplied change_class.py:257-258 calls interpretation_counts twice per app features() evaluation. AC-4's stderr test does not specify its entry point, leaving the observable line-count assertion ambiguous.
- Failure: The diagnostic's emission scope is unspecified, so a helper-only test can pass while classification prints twice. Add: "Each features() evaluation emits exactly one unknown-count diagnostic when either interpretation count is zero; test stderr through features()."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The plan both requires the diagnostic and permits removing it, leaving contradictory pass criteria.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-4 and OB-3 require a diagnostic for a present interpretation with a zero count. CHANGE_PLAN.json §16 requires AC-1..AC-4 tests, but 'Scope cuts under time pressure' explicitly allows cutting the AC-4 log; implementing that cut cannot satisfy the approved test oracle.
- Failure: The plan both requires the diagnostic and permits removing it, leaving contradictory pass criteria. Add: "The AC-4 diagnostic and its stderr assertion are mandatory and cannot be cut under time pressure."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Mixed-format interpretations lack an explicit fallback oracle: IDs in one section could suppress structural counting in

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 says 'if the id count is 0' and 'ids win over structure when present' without specifying section scope. Its §16 and implementation step 2 list id-less and id-bearing tests but no mixed case; different implementations could pass those tests while returning different counts for mixed inputs.
- Failure: Mixed-format interpretations lack an explicit fallback oracle: IDs in one section could suppress structural counting in the other. Add: "Apply ID precedence independently per section; test ID requirements with id-less criteria and id-less requirements with ID criteria."
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
