## AR-001: The scope-cut instruction permits omitting mandatory acceptance criteria, leaving completion requirements contradictory.

- Severity: HIGH
- References: .uncle/workflow/documents/CHANGE_PLAN.json, section "Scope cuts under time pressure", permits cutting steps 2 and 3; CHANGE_SPEC.json AC-3 and AC-4 require their behaviors. Remove the unilateral scope cuts so implementation and verification apply the same completion criteria.
- Failure: The scope-cut instruction permits omitting mandatory acceptance criteria, leaving completion requirements contradictory. Replace it with: "Steps 1–4 are required for completion; deferring steps 2 or 3 requires an explicitly approved scope revision."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The plan leaves unclear whether existing repair attempts precede, follow, or consume schema-feedback retries, allowing d

- Severity: MEDIUM
- References: .uncle/workflow/documents/CHANGE_SPEC.json SB-2 describes current failure "after repair attempt", while AC-1 requires at most two feedback retries before raising; CHANGE_PLAN.json sections 6 and 12 do not reconcile these paths. Specify their ordering and shared termination rule so repair cannot silently extend the promised bound.
- Failure: The plan leaves unclear whether existing repair attempts precede, follow, or consume schema-feedback retries, allowing divergent request bounds. Add: "For non-bounded writers, schema-feedback retries replace the existing schema-error repair attempt; after two failed retries, save the final rejection and raise the existing schema ValueError without further repair."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The retry override has no defined range or invalid-input behavior, despite a hard maximum of two.

- Severity: MEDIUM
- References: .uncle/workflow/documents/CHANGE_PLAN.json restriction R-1 introduces UNCLE_SCHEMA_FEEDBACK_RETRIES without parsing or boundary semantics; CHANGE_SPEC.json AC-1 and SI-2 cap retries at two. Define zero, negative, excessive, empty, and nonnumeric inputs so configuration cannot bypass the bound or cause inconsistent failures.
- Failure: The retry override has no defined range or invalid-input behavior, despite a hard maximum of two. Add: "UNCLE_SCHEMA_FEEDBACK_RETRIES accepts only 0, 1, or 2; unset or invalid values use 2, and 0 disables schema-feedback retries; bounded writers always use 0."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The bounded-writer single-request assertion conflicts with preserving its existing recovery behavior and could cause rem

- Severity: HIGH
- References: CHANGE_PLAN.json §5 protects the bounded writer path, but §17 and CHANGE_SPEC.json AC-2 require a single request. The supplied scripts/lib/http_agent.py:1373–1383 permits a regrammar request after stream stops, and :1439–1458 permits relaxed-schema repair; restrict the single-request assertion to a completed, non-relaxed, schema-invalid response.
- Failure: The bounded-writer single-request assertion conflicts with preserving its existing recovery behavior and could cause removal of supported retries. Amend the plan: “Bounded writers perform zero schema-feedback retries; existing stream-stop regrammar recovery and relaxed-schema repair remain unchanged.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The plan does not settle whether schema feedback replaces, precedes, or follows existing repair, so implementations can

- Severity: HIGH
- References: CHANGE_PLAN.json §6 specifies validate failure followed by constrained_completion, while CHANGE_SPEC.json SB-2 describes the existing repair attempt without deciding its disposition. The supplied scripts/lib/http_agent.py:1451–1458 separates JSON errors from schema errors and invokes repair_final for repairable responses in both branches; specify ordering and test object-shaped schema failures and malformed JSON separately.
- Failure: The plan does not settle whether schema feedback replaces, precedes, or follows existing repair, so implementations can remove recovery or exceed the retry bound. Add: “For non-bounded schema-invalid answers, feedback replaces repair_final and allows at most two additional completions; malformed-JSON repair remains unchanged.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Raw validator feedback has no defined sanitization rule, so the retry implementation can violate the no-secrets requirem

- Severity: MEDIUM
- References: CHANGE_PLAN.json §6 appends a user message with the validator error; CHANGE_SPEC.json §10 requires "No secrets in feedback" but does not define safe error content. When an exception includes sensitive values or local context, forwarding its text can disclose that content to the provider; specify sanitized feedback and test that sensitive exception content is excluded.
- Failure: Raw validator feedback has no defined sanitization rule, so the retry implementation can violate the no-secrets requirement. Add: "Feedback must contain only a schema path and a fixed constraint description, excluding rejected values, local file paths, and raw exception text."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The retry limit has no testable relationship to existing repair attempts, so request-count tests can approve different b

- Severity: HIGH
- References: CHANGE_SPEC.json SB-2 describes the current repair attempt, while AC-1 counts retries and CHANGE_PLAN.json §6 adds a new loop without specifying repair precedence. Specify this ordering before implementing the request-count tests so an extra repair call cannot silently exceed the intended bound.
- Failure: The retry limit has no testable relationship to existing repair attempts, so request-count tests can approve different bounds. Add: "Schema failures use at most two additional constrained_completion calls and never invoke repair_answer; JSON parse failures retain existing handling."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The environment override has no defined range or invalid-value behavior, leaving the retry-bound tests without an oracle

- Severity: MEDIUM
- References: CHANGE_PLAN.json R-1 specifies both 'max 2' and UNCLE_SCHEMA_FEEDBACK_RETRIES, but neither AC-1 nor SI-2 defines override semantics. Add cases for unset, zero, one, two, negative, above-limit, empty, and malformed values to make the hard maximum verifiable.
- Failure: The environment override has no defined range or invalid-value behavior, leaving the retry-bound tests without an oracle. Add: "UNCLE_SCHEMA_FEEDBACK_RETRIES defaults to 2, accepts integers 0–2, and uses 2 for all other values; zero disables schema-feedback retries."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The schema-size assertion permits short ID enums even though AC-3 requires their removal, and can reject unrelated enums

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-3 requires removal of allowed-ID enums but verifies only 'no enum list over 8 entries' plus an unknown-ID rejection. Replace that proxy with field-specific assertions and valid/invalid membership cases; explicitly require that an empty allowed set rejects every supplied ID.
- Failure: The schema-size assertion permits short ID enums even though AC-3 requires their removal, and can reject unrelated enums. Add: "Tests assert absence of enums on every targeted ID field for allowed sets of sizes 0, 1, 8, and 9, and verify local membership against each supplied set."
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
