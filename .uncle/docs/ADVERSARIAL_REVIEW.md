## AR-001: Bedrock temperature env behavior is unspecified.

- Severity: HIGH
- References: CHANGE_SPEC AC-2/BH-4 name only Self Hosted settings; CHANGE_PLAN D-3 adds the WORKFLOW_AWS_BEDROCK_ prefix.
- Failure: Bedrock temperature env behavior is unspecified. Add: 'Bedrock never reads any temperature env var or stage setting, including WORKFLOW_AWS_BEDROCK_TEMPERATURE, and ignores them silently.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Invalid-protocol fallback is left two ways to read.

- Severity: HIGH
- References: CHANGE_SPEC section 7 and CHANGE_PLAN section 12 (OpenAI fallback with notice) vs INV-4 (fail closed); notice text, location and env case unspecified.
- Failure: Invalid-protocol fallback is left two ways to read. Add: 'An unknown or empty protocol value, from file or env, resolves to openai for that run, shows one notice naming the bad value, and is not rewritten to storage.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: The Anthropic auth header is ambiguous across sections.

- Severity: MEDIUM
- References: CHANGE_SPEC A-2 ('x-api-key/bearer') vs section 10 ('only as bearer'); CHANGE_PLAN R-4.
- Failure: The Anthropic auth header is ambiguous across sections. Add: 'OpenAI and Converse send Authorization: Bearer; Anthropic sends Authorization: Bearer plus anthropic-version: 2023-06-01 and no x-api-key.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: URL joining and per-protocol paths are unspecified apart from Converse.

- Severity: MEDIUM
- References: CHANGE_SPEC A-2 gives only '{URL}/model/{id}/converse'; CHANGE_PLAN risk list admits the endpoint paths are unverified.
- Failure: URL joining and per-protocol paths are unspecified apart from Converse. Add the exact path per protocol and per operation, including discovery, trailing-slash handling and model-id encoding.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: The scope of the temperature strip is ambiguous.

- Severity: MEDIUM
- References: CHANGE_SPEC AC-2 says 'at any nesting' and INV-1 says transport boundary; CHANGE_PLAN D-2 says builders plus transport.
- Failure: The scope of the temperature strip is ambiguous. Add: 'The strip removes only top-level temperature and inferenceConfig/options temperature; it never alters tool schemas, tool arguments or user schema property names.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: Unusual valid responses and constrained output are unspecified.

- Severity: LOW
- References: CHANGE_SPEC AC-3/BH-5; CHANGE_PLAN section 12 says only 'parse errors raise'.
- Failure: Unusual valid responses and constrained output are unspecified. Add: 'Missing usage yields zeros; missing content raises a runner error; constrained output uses a forced tool/schema per protocol.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan conflicts on where temperature is stripped: D-2 says builders and transport, INV-1 names only transport.

- Severity: HIGH
- References: CHANGE_PLAN D-2 vs CHANGE_SPEC INV-1 enforcement point; AC-4/INV-2.
- Failure: Plan conflicts on where temperature is stripped: D-2 says builders and transport, INV-1 names only transport. How the shared `_strip_temperature` is gated by profile is unstated. Add: `_strip_temperature` runs only for aws-bedrock and is a no-op for self-hosted, with a test that a Self Hosted body still carries temperature.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Default profile is undefined when shared functions get no profile argument.

- Severity: HIGH
- References: CHANGE_PLAN R-2 and D-4; INV-4.
- Failure: Default profile is undefined when shared functions get no profile argument. R-2 defaults to self-hosted; D-4 raises on unresolved Bedrock. Add: omitting the profile means self-hosted, while an explicit unknown profile string raises.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Uncommitted partial work already modifies source files that existing Self Hosted tests cover, and the plan never says wh

- Severity: MEDIUM
- References: CHANGE_PLAN Existing partial work paragraph and section 4; git status shows modified source files.
- Failure: Uncommitted partial work already modifies source files that existing Self Hosted tests cover, and the plan never says what to do if the baseline is already broken. Add: step 1 first runs both test runners and records deltas against BASELINE_REPORT. Fix Self Hosted failures in source, never in the tests.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: The plan does not say existing runner dispatch cases and unknown-runner errors stay unchanged when `aws-bedrock` is adde

- Severity: MEDIUM
- References: CHANGE_PLAN change-impact rows for stage-config.sh and stagegate.sh; AC-6 names no negative test.
- Failure: The plan does not say existing runner dispatch cases and unknown-runner errors stay unchanged when `aws-bedrock` is added. Add: dispatch adds only an `aws-bedrock` case and leaves existing cases, defaults and error text byte-identical, covered by a shell test.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Section 12 says an invalid protocol falls back to OpenAI with a notice, while INV-4 and D-4 say Bedrock never falls back

- Severity: MEDIUM
- References: CHANGE_PLAN section 12 vs D-4; CHANGE_SPEC section 7.
- Failure: Section 12 says an invalid protocol falls back to OpenAI with a notice, while INV-4 and D-4 say Bedrock never falls back silently. Add: only an unknown protocol value falls back to OpenAI with a notice. A missing or unknown profile always raises.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Header carrying the token per protocol is unspecified (A-2 says 'x-api-key/bearer'; Converse unmentioned).

- Severity: HIGH
- References: CHANGE_SPEC section 10 and A-2; R-4 says 'bearer header per protocol'.
- Failure: Header carrying the token per protocol is unspecified (A-2 says 'x-api-key/bearer'; Converse unmentioned). Plan should say: 'OpenAI and Converse send only Authorization: Bearer; Anthropic sends x-api-key plus anthropic-version and no Authorization; the token is never put in the URL or body.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Redaction (INV-5) is scoped to `_request` HTTP errors only.

- Severity: HIGH
- References: CHANGE_SPEC INV-5 'redaction in _request'; CHANGE_PLAN sections 12 and 19.
- Failure: Redaction (INV-5) is scoped to `_request` HTTP errors only. Plan should say: 'Every Bedrock error, log line and status string passes through one redactor that removes the token value; tests cover HTTP, parse and URL cases.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: The user-configured URL receives the token, but no https requirement, redirect handling or model-id encoding is stated.

- Severity: HIGH
- References: CHANGE_SPEC section 10 ('to the configured URL') and A-2 path template.
- Failure: The user-configured URL receives the token, but no https requirement, redirect handling or model-id encoding is stated. Plan should say: 'Bedrock URLs must be https (http only for loopback); redirects never forward credential headers; the model id is percent-encoded in the Converse path.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Storage protection for the Bedrock token is unspecified.

- Severity: MEDIUM
- References: CHANGE_PLAN D-3 and INV-3 describe isolation only, with no file mode.
- Failure: Storage protection for the Bedrock token is unspecified. Plan should say: 'The Bedrock key file is created mode 0600 in a 0700 directory, and the token is never written to config or logs.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: A missing Bedrock token or URL is not stated to fail before any network call, and could pick up Self Hosted credentials.

- Severity: MEDIUM
- References: CHANGE_SPEC INV-3/INV-4; CHANGE_PLAN D-4 and section 12 ('same message as Self Hosted').
- Failure: A missing Bedrock token or URL is not stated to fail before any network call, and could pick up Self Hosted credentials. Plan should say: 'A Bedrock run never reads Self Hosted key, URL or env, and errors before any network call if its own token or URL is missing.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: The plan does not say how Anthropic and Converse requests are authenticated.

- Severity: HIGH
- References: CHANGE_SPEC A-2 and §10 say 'x-api-key/bearer'. CHANGE_PLAN R-4 says 'bearer header per protocol'.
- Failure: The plan does not say how Anthropic and Converse requests are authenticated. Add this sentence: Anthropic sends `x-api-key` plus `anthropic-version: 2023-06-01` and no Authorization header; OpenAI and Converse send `Authorization: Bearer`.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: INV-1's enforcement point is named two ways.

- Severity: HIGH
- References: CHANGE_SPEC INV-1 says 'body strip at transport boundary'. CHANGE_PLAN D-2 and §16-18 target only `sampling`.
- Failure: INV-1's enforcement point is named two ways. The spec puts it at the transport strip; D-2 adds a second strip in `sampling`. Add this sentence: defect injection must break `sampling` and `_strip_temperature` separately, and a test that walks the sent body for all 3 protocols must fail each time.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: Unknown, empty or mis-cased stored protocol values are unspecified.

- Severity: MEDIUM
- References: CHANGE_SPEC §7 and CHANGE_PLAN §12 say only 'notice and OpenAI default'.
- Failure: Unknown, empty or mis-cased stored protocol values are unspecified. Add this sentence: normalize lowercase and trim; empty or missing means OpenAI silently; any other unknown value means OpenAI with one stderr notice per process; the stored value is never rewritten.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: Fixture contracts for Converse and Anthropic are undefined: schema-constrained request fields, usage mapping, and what c

- Severity: MEDIUM
- References: CHANGE_SPEC AC-3 says 'schema-constrained output'. CHANGE_PLAN §12 says 'parse errors raise runner errors'.
- Failure: Fixture contracts for Converse and Anthropic are undefined: schema-constrained request fields, usage mapping, and what counts as a parse error. Add this sentence: a table maps each protocol's request fields and usage fields to the common shape, and a missing required key raises a runner error naming the protocol.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: URL construction is ambiguous for trailing slashes, a base URL that already ends in `/converse`, model id encoding, and

- Severity: MEDIUM
- References: CHANGE_SPEC A-2 gives only 'Converse uses {URL}/model/{id}/converse'. The plan names no OpenAI or Anthropic paths.
- Failure: URL construction is ambiguous for trailing slashes, a base URL that already ends in `/converse`, model id encoding, and the OpenAI and Anthropic paths. Add this sentence: strip trailing slashes, append the per-protocol path exactly once, percent-encode the model id, and assert the final URL for each protocol.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: 'Unresolved profile' and 'no temperature setting read' cannot be tested as written.

- Severity: LOW
- References: CHANGE_PLAN D-4. CHANGE_SPEC AC-2 and AC-5.
- Failure: 'Unresolved profile' and 'no temperature setting read' cannot be tested as written. Add this sentence: the Bedrock runner raises a named exception when the profile tag is absent, and a test sets both Self Hosted temperature settings to a sentinel and asserts the sentinel is not in the body.
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
