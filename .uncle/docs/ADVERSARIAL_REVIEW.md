## AR-001: The optional scope cuts contradict mandatory no-attestation behavior.

- Severity: HIGH
- References: CHANGE_PLAN.json §21 permits cutting D-7 while R-2 and CHANGE_SPEC.json AC-2/B-3 require that no attestation be produced, including outside the PR body; omitting this guard allows an explicitly forbidden artifact.
- Failure: The optional scope cuts contradict mandatory no-attestation behavior. Replace the cut rule with: “The stagegate attestation guard is mandatory and cannot be cut.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Resume behavior conflicts with the environment-based stagegate guard.

- Severity: HIGH
- References: CHANGE_PLAN.json §1/§15 and CHANGE_SPEC.json B-1 require subsequent actions to follow the journal, but D-7 conditions stagegate suppression on UNCLE_NO_FOOTPRINT=1; resuming without that environment value can produce attestation in a persisted no-footprint run.
- Failure: Resume behavior conflicts with the environment-based stagegate guard. Add: “On resume, stagegate attestation suppression uses the persisted journal mode; the environment selects the mode only when starting a new run.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The tracked-file vocabulary exception contradicts disclosure-only opt-in naming.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §22 allows 'uncle' when present in tracked project files, whereas CHANGE_SPEC.json AC-4 and B-9 permit naming only through explicit configuration and only in the disclosure line; implementations could consequently accept different titles, branches and messages.
- Failure: The tracked-file vocabulary exception contradicts disclosure-only opt-in naming. Replace the exception with: “Uncle is permitted only in the disclosure line when footprint.name_uncle is true; occurrence in tracked project files grants no exemption.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Empty disclosure overrides have no defined outcome despite the mandatory disclosure invariant.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §8/D-2 specifies override precedence without value validation; CHANGE_SPEC.json B-6 explicitly allows an empty trailer, while I-3 requires a body disclosure. Without this decision, configuration can either remove required disclosure or unexpectedly fall back to a default.
- Failure: Empty disclosure overrides have no defined outcome despite the mandatory disclosure invariant. Add: “An empty or whitespace-only disclosure override is rejected before publication; only the trailer may be empty.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The artifact exclusion contract lacks an exact path rule outside .uncle.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 names .uncle/**, FINAL_AUDIT.md and attestation files, while CHANGE_SPEC.json AC-1/B-2 additionally excludes workflow-document artifacts without defining their locations or extensions; independent implementations could leak root reports or remove legitimate source files with matching names.
- Failure: The artifact exclusion contract lacks an exact path rule outside .uncle. Add: “Bare snapshots also exclude root files whose stems are PROJECT_PLAN, CHANGE_PLAN, CHANGE_SPEC, IMPLEMENTATION_NOTES or VERIFICATION_REPORT; other paths outside .uncle are preserved except FINAL_AUDIT.md and explicitly identified attestation outputs.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The environment-based stagegate guard can change attestation behavior when resuming a journal created in the opposite mo

- Severity: HIGH
- References: .uncle/workflow/documents/CHANGE_PLAN.json D-7 skips attestation when UNCLE_NO_FOOTPRINT=1, while §15 and CHANGE_SPEC.json B-1 require the journal to control resumed behavior. With a default-mode journal and environment value 1, these rules permit skipping existing attestation behavior, violating AC-7.
- Failure: The environment-based stagegate guard can change attestation behavior when resuming a journal created in the opposite mode. Add: "On resume, stagegate derives its attestation decision from the persisted journal mode; the environment applies only when initializing a new run."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Existing tracked workflow artifacts have conflicting outcomes: bare snapshots remove them, but completion rejects tracke

- Severity: HIGH
- References: .uncle/workflow/documents/CHANGE_PLAN.json §1 omits artifacts from the snapshot, whereas §12 requires zero tracked/staged .uncle paths; CHANGE_SPEC.json B-12 requires local artifacts to remain untracked. Neither specifies entry behavior for repositories retaining artifacts from earlier default-mode runs, allowing implementations to create deletion diffs or fail only after work completes.
- Failure: Existing tracked workflow artifacts have conflicting outcomes: bare snapshots remove them, but completion rejects tracked paths. Add: "Before starting no-footprint mode, reject repositories with excluded artifacts tracked at HEAD or present in the user index, without altering either, and explain the conflicting paths."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The tracked-file vocabulary exception can silently disable the promised publication filter for existing projects.

- Severity: MEDIUM
- References: .uncle/workflow/documents/CHANGE_PLAN.json §22 permits 'uncle' when present in the project's tracked files, but CHANGE_SPEC.json B-9 allows it only in the opted-in disclosure line and AC-4 requires explicit opt-in. Existing repositories containing that word therefore receive incompatible filtering behavior depending on which rule implementation and regression tests follow.
- Failure: The tracked-file vocabulary exception can silently disable the promised publication filter for existing projects. Add: "Tracked project content does not exempt publication fields from scanning; only the disclosure line may name Uncle when footprint.name_uncle is true."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The publishing flow can invoke the user's signer through automatic_commit without explicit authorization.

- Severity: HIGH
- References: CHANGE_PLAN.json §6 routes handoff through automatic_commit; D-3 assigns commit-message composition to the driver but specifies no signing boundary. The binding Git-signing instructions prohibit automatic invocation of real signing keys; the plan must distinguish message preparation from signed commit execution.
- Failure: The publishing flow can invoke the user's signer through automatic_commit without explicit authorization. Add: "When a project commit requires signing, present the exact command for the user to run and verify its result; never invoke the signer automatically."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The tracked-file exception could allow Uncle attribution throughout published text, bypassing the disclosure-only permis

- Severity: MEDIUM
- References: CHANGE_PLAN.json §22 allows the word uncle if present in the project's tracked files, while CHANGE_SPEC.json B-9 permits it only in the disclosure line with explicit opt-in. The scan(fields, allow_uncle) contract does not resolve this conflict, allowing implementations to apply a field-wide exemption.
- Failure: The tracked-file exception could allow Uncle attribution throughout published text, bypassing the disclosure-only permission. Add: "Tracked project content grants no vocabulary exemption; footprint.name_uncle permits Uncle only in the rendered disclosure line."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: An empty or whitespace-only disclosure override has no defined handling and could remove the required AI disclosure.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §8 defines env-over-config disclosure resolution without value validation. CHANGE_SPEC.json B-6 explicitly permits an empty trailer but leaves empty disclosure behavior unspecified, while I-3 requires disclosure in the body. Define and test rejection so policy overrides cannot silently erase it.
- Failure: An empty or whitespace-only disclosure override has no defined handling and could remove the required AI disclosure. Add: "Reject empty or whitespace-only disclosure overrides before publication; only the commit trailer may be empty."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: The vocabulary exceptions give tests contradictory pass/fail criteria.

- Severity: HIGH
- References: .uncle/workflow/documents/CHANGE_PLAN.json §22 permits 'uncle' when present in tracked project files, whereas CHANGE_SPEC.json B-9 allows it only on the opted-in disclosure line. The same title or branch can therefore pass one oracle and fail the other; replace the plan's tracked-file exception.
- Failure: The vocabulary exceptions give tests contradictory pass/fail criteria. Add: "The only exception for Uncle naming is the disclosure line when footprint.name_uncle is true; occurrence in tracked project files grants no exemption."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: The scan's required ordering is not testable consistently: 'before any git write' differs from 'before commit/push.' Add

- Severity: HIGH
- References: .uncle/workflow/documents/CHANGE_SPEC.json AC-5 and B-7 prohibit any git/gh write before rejection, while CHANGE_PLAN.json §6 places snapshot before scan and §12 guarantees only no commit/push. AC-5's proposed test records commit/push/gh calls, leaving the broader guarantee untested; define the permitted preparatory writes explicitly.
- Failure: The scan's required ordering is not testable consistently: 'before any git write' differs from 'before commit/push.' Add: "Leak rejection precedes publication writes, including branch/index updates, commits, pushes and gh mutations; temporary-index snapshots and local object creation may occur before scanning."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: Empty disclosure overrides have no defined outcome, so override and disclosure-presence tests can disagree.

- Severity: MEDIUM
- References: .uncle/workflow/documents/CHANGE_SPEC.json B-6 permits disclosure overrides but explicitly defines empty behavior only for the trailer; I-3 requires body disclosure. CHANGE_PLAN.json §8 specifies precedence without validating empty values. Define rejection for both config and environment inputs so tests have one expected result.
- Failure: Empty disclosure overrides have no defined outcome, so override and disclosure-presence tests can disagree. Add: "An empty or whitespace-only disclosure override is invalid and rejects publication before publication writes; only the trailer may be empty."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The stagegate guard is both optional and required, leaving the no-attestation test oracle conditional on implementation

- Severity: MEDIUM
- References: .uncle/workflow/documents/CHANGE_PLAN.json §21 lists D-7's stagegate guard among first cuts while declaring R-2 no-attestation uncuttable; R-2 explicitly includes skipping stagegate attestation. CHANGE_SPEC.json AC-2 forbids producing attestation. Remove the cut permission so greenfield coverage has an unconditional expectation.
- Failure: The stagegate guard is both optional and required, leaving the no-attestation test oracle conditional on implementation scope. Add: "The stagegate attestation guard is mandatory and cannot be cut; greenfield runs in no-footprint mode must not invoke attestation generation."
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
