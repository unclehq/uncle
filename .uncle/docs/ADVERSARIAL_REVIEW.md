## AR-001: The plan never says what rule 6 does when no warning page appears (non-Daytona host, link already opened).

- Severity: HIGH
- References: CHANGE_PLAN s4.1.r1 ('on first open of each link'); CHANGE_SPEC B-4 gives no host or opened-before condition.
- Failure: The plan never says what rule 6 does when no warning page appears (non-Daytona host, link already opened). Settle it: 'Rule 6 applies to every relayed Preview link and is worded conditionally ("if Daytona shows a warning page, continue past it").'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: The `warning-page` pattern has no defined match rule, so skill text, regex and removal case can read it differently.

- Severity: MEDIUM
- References: CHANGE_PLAN s4.1.r2 and R-1 ('no button name'); risk 'Pattern too loose'.
- Failure: The `warning-page` pattern has no defined match rule, so skill text, regex and removal case can read it differently. Settle it: 'The pattern is case-insensitive, matches warning\s+page, and quoted button labels fail the forbidden-phrase check.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: AC-3 requires the non-loopback answer 'when available', but the plan allows skipping the probe silently and cuts it firs

- Severity: MEDIUM
- References: CHANGE_SPEC AC-3 vs CHANGE_PLAN s4.1.r3 ('skip that probe') and s13.
- Failure: AC-3 requires the non-loopback answer 'when available', but the plan allows skipping the probe silently and cuts it first. Settle it: 'No non-loopback IPv4 means SKIP and the test passes; if one exists, a failed connection fails the test.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: The plan does not say which non-loopback address the probe uses, or how it handles multiple interfaces, IPv6-only hosts,

- Severity: MEDIUM
- References: CHANGE_PLAN s4.1.r3 ('probe non-loopback IP if found') and its flakiness risk.
- Failure: The plan does not say which non-loopback address the probe uses, or how it handles multiple interfaces, IPv6-only hosts, link-local addresses or blocked connects. Settle it: 'Probe the first non-loopback, non-link-local IPv4 with a 2s timeout; IPv6-only or timeout is SKIP.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The plan does not say where rule 6 sits relative to existing rules, or whether the 60-line cap covers the body or the wh

- Severity: LOW
- References: CHANGE_SPEC AC-1 ('body stays at or under 60 lines'); CHANGE_PLAN R-2 ('Keep rule to 1-2 lines').
- Failure: The plan does not say where rule 6 sits relative to existing rules, or whether the 60-line cap covers the body or the whole file. Settle it: 'Rule 6 is one line appended after rule 5; the body stays at or under 60 lines.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: The `warning-page` regex could match text that is not the new rule.

- Severity: MEDIUM
- References: CHANGE_PLAN s4.1.r2 lists 'Pattern too loose' as a risk with no stated mitigation; D-2 gives no exact wording.
- Failure: The `warning-page` regex could match text that is not the new rule. Decision: the pattern must match only the new rule-6 line containing both 'warning page' and 'continue', and the removal case must delete exactly that line.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: The 60-line cap and the new rule can collide, and the plan never gives the current line count.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1 and I-1 (<=60 lines); CHANGE_PLAN R-2 'Keep rule to 1-2 lines' with no baseline line count.
- Failure: The 60-line cap and the new rule can collide, and the plan never gives the current line count. Decision: if rule 6 would push the body over 60 lines, condense an existing non-rule line; never raise the cap and never drop rule 6.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: The non-loopback probe says 'if found' but not how it is found or what a skip looks like.

- Severity: MEDIUM
- References: CHANGE_PLAN s4.1.r3 'probe non-loopback IP if found' and 'skip that probe'; CHANGE_SPEC AC-3.
- Failure: The non-loopback probe says 'if found' but not how it is found or what a skip looks like. Decision: if a non-loopback IPv4 address exists, the test connects to it and fails on refusal; if none exists, it prints SKIP and the record-host assertions still run.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: The plan does not say whether the existing removal cases for rules 1-5 are kept.

- Severity: LOW
- References: CHANGE_SPEC AC-2 and AC-4; CHANGE_PLAN s4.1.r2.
- Failure: The plan does not say whether the existing removal cases for rules 1-5 are kept. Decision: the existing five removal cases stay unchanged and the new case is appended after them.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Rule 6 tells people to continue past Daytona's warning page but never limits that to the Preview link from the build out

- Severity: MEDIUM
- References: CHANGE_SPEC §10 only says the bearer-credential and untrusted-output rules must not be weakened. CHANGE_PLAN row s4.1.r1 says 'continue past it' with no limit.
- Failure: Rule 6 tells people to continue past Daytona's warning page but never limits that to the Preview link from the build output. Add: 'Rule 6 applies only to the Preview link from the build output; never tell the person to continue past a warning for any other URL.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: The wildcard test binds to 0.0.0.0 and probes a non-loopback address, but the plan does not say the probe must stay loca

- Severity: MEDIUM
- References: CHANGE_PLAN s4.1.r3: 'probe non-loopback IP if found'; risk column says skip when none. CHANGE_SPEC AC-3: 'when one is available'.
- Failure: The wildcard test binds to 0.0.0.0 and probes a non-loopback address, but the plan does not say the probe must stay local-only or what happens with no such address. Add: 'The probe uses only local interface addresses, makes no outbound calls, skips when none exists, and stops the server on pass and failure.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: No test checks that 0.0.0.0 stays out of the recorded url and chat output.

- Severity: LOW
- References: CHANGE_SPEC AC-3 and I-3 say the url stays on loopback. Row s4.1.r3 lists only the record-host assertion and the probe.
- Failure: No test checks that 0.0.0.0 stays out of the recorded url and chat output. Add: 'The wildcard test asserts the recorded url host is exactly 127.0.0.1 and 0.0.0.0 appears only in the host field of preview.json.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: The non-loopback probe is described as 'if found' and 'skip that probe', but the plan doesn't say how the test reports a

- Severity: HIGH
- References: CHANGE_PLAN change-impact row r3 ('skip that probe'); CHANGE_SPEC AC-3 ('when one is available').
- Failure: The non-loopback probe is described as 'if found' and 'skip that probe', but the plan doesn't say how the test reports a skip. A silent pass looks the same as a real pass. Settle with: 'With no non-loopback IPv4 address, the test prints SKIP, does not count the probe as passed, and does not fail.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: AC-1 and AC-2 only test that a regex such as 'warning-page' matches.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-1 ('without quoting a button name'); CHANGE_PLAN R-1.
- Failure: AC-1 and AC-2 only test that a regex such as 'warning-page' matches. They don't fix the matching wording or how the test catches a quoted button name. Settle with: 'The regex matches the phrase "warning page"; a forbidden pattern rejects quoted button labels, and a removal case proves a skill containing one is rejected.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: The plan says rule 6 is added and 'rules 1-5 remain', but not how the test confirms this.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-4 and AC-1 (60-line cap); CHANGE_PLAN R-2.
- Failure: The plan says rule 6 is added and 'rules 1-5 remain', but not how the test confirms this. Settle with: 'The chat-skill test asserts numbered rules 1 to 6 appear in order and the body is at most 60 lines; the current line count is recorded.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: AC-3 says the app 'answers' on a non-loopback address but doesn't define an answer, how the address is chosen, or the ti

- Severity: MEDIUM
- References: CHANGE_SPEC AC-3; CHANGE_PLAN row r3 ('probe non-loopback IP if found').
- Failure: AC-3 says the app 'answers' on a non-loopback address but doesn't define an answer, how the address is chosen, or the timeout. Settle with: 'GET http://<first non-loopback IPv4>:<port>/ must return HTTP 200 with the same body as loopback, within 5 seconds.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: AC-5 verifies with 'git diff --name-only against change-impact table', which has no pass/fail rule.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-5 verification.
- Failure: AC-5 verifies with 'git diff --name-only against change-impact table', which has no pass/fail rule. Settle with: 'AC-5 passes when the changed paths, ignoring .uncle/ workflow files, are exactly SKILL.md, chat-skill-test.py and host-preview-test.py.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: The plan claims the regression test fails before the edit and passes after, but gives no step to record that.

- Severity: LOW
- References: CHANGE_PLAN section 16/17.
- Failure: The plan claims the regression test fails before the edit and passes after, but gives no step to record that. The chat-skill suite is also outside the critical tier. Settle with: 'Implementation notes record the failing run ("missing rule: warning-page") before the SKILL.md edit and the passing run after; the chat-skill suite is run explicitly.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
