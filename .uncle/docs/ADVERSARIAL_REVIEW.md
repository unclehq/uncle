## AR-001: The unconditional PR delivery promise conflicts with sandbox builds and optional publishing.

- Severity: MEDIUM
- References: CHANGE_PLAN.json step-2 requires saying 'a pull request and a link to try the app' while deferring PRs for builds without a repository; CHANGE_SPEC.json AC-2 and AC-3 repeat these competing requirements. The user's publishing instruction makes PR creation optional, so repository selection alone cannot make a PR a guaranteed deliverable.
- Failure: The unconditional PR delivery promise conflicts with sandbox builds and optional publishing. Add: "Describe a build as providing a link to try the app; promise a pull request only when a repository is named and the user separately authorizes publishing."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The scope-cut policy permits dropping mandatory acceptance behavior.

- Severity: MEDIUM
- References: CHANGE_PLAN.json section 'Scope cuts under time pressure' permits cutting SB-2 wording, but CHANGE_SPEC.json AC-2 requires that wording and its removal variant to be rejected. Following the cut would leave implementation and acceptance checks enforcing different scopes.
- Failure: The scope-cut policy permits dropping mandatory acceptance behavior. Add: "SB-2 wording and all tests required by AC-1 through AC-5 remain mandatory under time pressure; defer completion rather than remove them."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The new unconditional link promise conflicts with preserved failure handling.

- Severity: HIGH
- References: CHANGE_PLAN.json step-2 says to end no-repository builds with the link; section 7 preserves the no-link rule. CHANGE_SPEC.json SB-4 and section 8 preserve handling when no link is produced. Without explicit precedence, the new first rule can regress truthful reporting on failed or malformed output.
- Failure: The new unconditional link promise conflicts with preserved failure handling. Add: "If a sandbox or hosted build produces no valid Preview line, the existing no-link and malformed-output rules take precedence; never invent a link or promise that this run produced one."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Line-removal tests cannot independently protect three behaviors placed on one new rule line.

- Severity: MEDIUM
- References: CHANGE_PLAN.json sections 1 and 10 place SB-1..SB-3 in rule 1 but specify defect tests that drop lines by needle. Removing that shared line erases all three behaviors, so redundant or overly broad patterns can pass the defect tests while accepting an individual behavior's removal.
- Failure: Line-removal tests cannot independently protect three behaviors placed on one new rule line. Add: "For each new REQUIRED ID, mutate only its corresponding clause while preserving the other two clauses and numbering, and assert rejection naming that ID."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The time-pressure cuts permit dropping required behavior and its regression protection.

- Severity: MEDIUM
- References: CHANGE_PLAN.json section 16 permits cutting the previews-impossible defect test and then SB-2 wording, while section 10 requires that test. CHANGE_SPEC.json AC-2 requires the PR-and-link wording and SI-3 prohibits denying preview availability; the cuts allow implementation and verification to target different requirements.
- Failure: The time-pressure cuts permit dropping required behavior and its regression protection. Add: "SB-2 wording and the previews-impossible defect test are mandatory and may not be cut without revising and reapproving the specification."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Whole-line deletion removes all three new requirements together, leaving partial omissions untested.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §10 specifies dropping lines by needle; implementation step 2 puts all three behaviors in rule 1. These mutations cannot establish that the checker rejects omission of expiry, the preview-request response, sandbox execution, or the deferred PR offer individually.
- Failure: Whole-line deletion removes all three new requirements together, leaving partial omissions untested. Add: “Independently mutate each required clause of AC-1 through AC-3 while preserving the other clauses, and assert rejection by its corresponding requirement ID.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The description change has no specified behavioral assertion.

- Severity: MEDIUM
- References: CHANGE_SPEC.json SB-6 and AC-4 require expanding the description, but CHANGE_PLAN.json §10 and step 1 specify no corresponding checker change. The supplied scripts/tests/chat-skill-test.py:107–111 only checks that description is nonempty, so the original description would still pass.
- Failure: The description change has no specified behavioral assertion. Add: “Check that the description covers offering a preview before a build and reporting it afterward; reject a variant restoring the original after-only description.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Sequential numbering does not prove the preview-offer rule occupies rule 1.

- Severity: MEDIUM
- References: CHANGE_SPEC.json SI-2 explicitly requires the new offer-preview rule to be rule 1. CHANGE_PLAN.json §10 specifies numbering 1–7 and a rule-7 warning regex, but no rule-1 content anchor; the supplied checker at scripts/tests/chat-skill-test.py:76–78 searches REQUIRED patterns anywhere in the body.
- Failure: Sequential numbering does not prove the preview-offer rule occupies rule 1. Add: “Require the offer-preview content within numbered rule 1 and reject a variant that swaps it with another rule while retaining sequential numbering.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
