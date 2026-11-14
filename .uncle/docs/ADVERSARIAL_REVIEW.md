## AR-001: Option B permits documentation-only completion, but the implementation sequence and acceptance criteria still require an

- Severity: HIGH
- References: CHANGE_PLAN.json §BLOCKING PLANNING DECISION offers option B, while §Implementation sequence steps 2–3 require the external regression test and constant change, and §Scope cuts forbids cutting that test. CHANGE_SPEC.json AC-1 through AC-4 retain code-level acceptance, allowing incompatible interpretations of completion.
- Failure: Option B permits documentation-only completion, but the implementation sequence and acceptance criteria still require an external code fix and regression test. Add: “Option B requires a separately approved documentation-only spec and sequence; it does not satisfy AC-1 through AC-4 of this bug fix.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Zero-refusal acceptance also covers eventual success after a refusal, contradicting required retry success.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-2 says a build whose request is accepted makes no refused request, and S-2 requires zero refusals whenever a build gets its link; AC-3 and S-3 require a refused request followed by successful retry. CHANGE_PLAN.json §16 includes both scenarios without defining the exception.
- Failure: Zero-refusal acceptance also covers eventual success after a refusal, contradicting required retry success. Add: “AC-2 and S-2 apply when the host accepts the initial valid request; an injected initial refusal followed by success satisfies AC-3 and is exempt from the zero-refusal requirement.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The plan does not settle which attempt determines the displayed expiry or how second-level expiry matches minute-only ou

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 derives end time from the initial 3600-second constant, while CHANGE_SPEC.json S-3 preserves a shorter retry and S-4/V-2 require the Preview end time to match link expiry. S-4 fixes output to HH:MM UTC, leaving both retry attribution and minute precision unresolved for implementation and tests.
- Failure: The plan does not settle which attempt determines the displayed expiry or how second-level expiry matches minute-only output. Add: “Compute expiry from the successful request’s start time and lifetime, then format it as HH:MM UTC by truncating seconds; a successful retry uses its own start time and lifetime.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The retry test does not establish which request determines the printed expiry, allowing the changed initial constant to

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 derives end time from the initial constant, while §16 says only that retry works and Preview end time equals expiry; CHANGE_SPEC.json S-3 preserves a shorter retry and V-2 requires the actual link expiry. Resolve the retry case explicitly so implementation and regression assertions use the same successful request.
- Failure: The retry test does not establish which request determines the printed expiry, allowing the changed initial constant to produce an incorrect end time after fallback. Add: "After a successful retry, compute and verify the Preview end time using the successful request's lifetime and time origin."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The regression strategy covers refusal followed by success but omits exhausted retries, leaving preserved failure output

- Severity: MEDIUM
- References: CHANGE_SPEC.json §8 explicitly requires no Preview line and a reason when all attempts fail; CHANGE_PLAN.json §16 tests only immediate success and a single refusal followed by success. Add the exhausted-retry case to the planned mocked-publisher regression coverage.
- Failure: The regression strategy covers refusal followed by success but omits exhausted retries, leaving preserved failure output unprotected. Add: "When every permitted attempt is refused, verify that retries terminate, no Preview line is printed, and a failure reason is printed."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The zero-refusal requirement conflicts with the successful retry scenario, so tests can disagree about valid success.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-2 and S-2 require no refused requests when a build obtains its link, while AC-3 requires a refused request followed by a link. CHANGE_PLAN.json §16 includes both assertions without explicitly separating their applicability.
- Failure: The zero-refusal requirement conflicts with the successful retry scenario, so tests can disagree about valid success. Add: “Zero refusals applies only when the host accepts the first request; the forced-refusal test expects one refusal followed by a successful retry.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Expiry equality lacks a clock reference and rounding rule despite minute-only output, making the Preview assertion ambig

- Severity: MEDIUM
- References: CHANGE_SPEC.json S-4 specifies HH:MM UTC, while V-2 requires the printed end time to equal link expiry. CHANGE_PLAN.json §1 derives end time from the same lifetime value and §16 asserts equality, but neither defines the reference instant, minute rounding, or which request supplies the lifetime after retry.
- Failure: Expiry equality lacks a clock reference and rounding rule despite minute-only output, making the Preview assertion ambiguous. Add: “Freeze the mock clock at request acceptance; assert HH:MM UTC equals that instant plus the accepted request’s lifetime, truncated to the minute, including after retry.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: First-request assertions leave the every-request expiry invariant unverified, especially on retry.

- Severity: MEDIUM
- References: CHANGE_SPEC.json V-1 applies the integer 1..3600 constraint to every signed-link request, and S-3 preserves retry at a shorter lifetime. CHANGE_PLAN.json §16 explicitly checks only the first request’s upper bound and that retry works; mock range enforcement alone does not establish integrality or a shorter retry.
- Failure: First-request assertions leave the every-request expiry invariant unverified, especially on retry. Add: “In both success and forced-refusal tests, assert every recorded request has an integer expiresInSeconds in 1..3600, and assert the retry lifetime is shorter than the initial 3600 seconds.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
