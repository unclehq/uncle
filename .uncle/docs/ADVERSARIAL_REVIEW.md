## AR-001: The failure fallback contradicts the unconditional final-link lifetime guarantee.

- Severity: HIGH
- References: CHANGE_PLAN.json §12 keeps the earlier link on failure; CHANGE_SPEC.json §8 leaves failure unresolved, while INV-2 requires every last printed link to remain valid for at least 55 minutes after completion. An early link can already be expired in AC-1's 70-minute build; reconcile the spec, invariant, and failure tests with the chosen fallback.
- Failure: The failure fallback contradicts the unconditional final-link lifetime guarantee. Add: “If final renewal fails, complete the build with a warning, preserve any earlier link and its expiry, or report preview unavailable if none exists; the 55-minute guarantee applies only to successful renewal.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: “After the PR” leaves renewal undefined when publishing is declined or PR creation fails.

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 and CHANGE_SPEC.json §4 place renewal “after” the PR, and BH-2 only describes completion after a PR. The supplied workflow instructions make publishing and PR creation optional; specify the trigger so an otherwise completed build still receives a fresh preview without publishing.
- Failure: “After the PR” leaves renewal undefined when publishing is declined or PR creation fails. Add: “Run final preview renewal when build work completes, whether PR creation succeeds, fails, or is skipped; PR creation is not a prerequisite.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The request limit has conflicting scopes after a refused link.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-3 and BH-4 restrict the 3600-second assertion to builds where no link was refused, whereas INV-1 prohibits larger requests unconditionally and CHANGE_PLAN.json §2-3 states the host caps expiry at 3600 seconds. Remove the refusal qualification from the acceptance criterion and test retries against the same cap.
- Failure: The request limit has conflicting scopes after a refused link. Add: “Every signed-preview-url request, including retries after refusal, must use expiresInSeconds no greater than 3600.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The refresh-failure fallback can return an expired link, contradicting the unconditional 55-minute validity invariant an

- Severity: HIGH
- References: CHANGE_PLAN.json §12 keeps the earlier link and does not fail; CHANGE_SPEC.json §8 leaves that decision unresolved, while INV-2 requires the last printed link to remain valid for at least 55 minutes after completion. Reconcile the spec and plan and require a mocked refresh-failure regression test.
- Failure: The refresh-failure fallback can return an expired link, contradicting the unconditional 55-minute validity invariant and leaving failure tests without one expected outcome. Add: “If refresh fails, preserve the earlier expiry, warn without failing the build, and exempt this outcome from INV-2.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Final refresh is placed “after the PR,” leaving builds that skip optional publishing unspecified and risking retention o

- Severity: MEDIUM
- References: CHANGE_PLAN.json §1 and CHANGE_SPEC.json §4 locate refresh after the PR; BH-2 also describes only completion after PR creation. The supplied workflow instructions make publishing and PR creation optional; add a regression case that skips PR creation and still checks final-link lifetime and kept-sandbox expiry.
- Failure: Final refresh is placed “after the PR,” leaving builds that skip optional publishing unspecified and risking retention of the original expired link. Add: “Run final preview refresh on successful build completion even when PR creation is skipped.”
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Final-request failure has incompatible test oracles: fallback may print an expired link, while INV-2 requires 55 minutes

- Severity: HIGH
- References: CHANGE_PLAN.json §12 selects nonfatal fallback; CHANGE_SPEC.json §8 leaves fallback versus failure unresolved, and INV-2 unconditionally requires >=55 minutes of validity. Reconcile these statements so failure-path tests and review checks agree.
- Failure: Final-request failure has incompatible test oracles: fallback may print an expired link, while INV-2 requires 55 minutes of validity. Add: "On final-request failure, complete with an expiry warning, preserve the earlier expiry metadata, and exempt this fallback from INV-2; test this with an expired early link."
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The request-limit acceptance test excludes refused-link histories, although the invariant covers every request.

- Severity: MEDIUM
- References: CHANGE_SPEC.json AC-3 and BH-4 apply only when no link was ever refused; INV-1 says no signed-link request exceeds 3600 seconds, and CHANGE_PLAN.json §1 repeats that cap. Extend the test obligation to refused requests so conditional acceptance coverage cannot conceal an invariant violation.
- Failure: The request-limit acceptance test excludes refused-link histories, although the invariant covers every request. Add: "Test a refused signing request and any subsequent retries or fallback requests, asserting that every expiresInSeconds value remains at most 3600."
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
