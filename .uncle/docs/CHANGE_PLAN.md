# Change Plan — Issue 178

Seeded from [unclehq/uncle#178](https://github.com/unclehq/uncle/issues/178).

Issue 178

Omitted sections: Schema/migration (additive files only); Concurrency (no new shared state); Feature flag (new runner is opt-in by selection)

## 1-3. Approach
Selected: a runner **profile** (`self-hosted`, `aws-bedrock`) read by existing Self Hosted code; `sampling(values)` returns `{}` for Bedrock; a small per-protocol adapter layer (openai = existing path, anthropic, converse) builds bodies and parses responses. Alternatives: clone ~4k lines (rejected: drift); separate runner module per protocol (rejected: duplicates discovery/keys). Preferred: smallest surface, Self Hosted untouched by default.

**Existing partial work:** uncommitted tree already contains `sampling()`, `_strip_temperature`, `_profile` plumbing, key redaction, a test file and doc. Step 1 audits it against ACs and completes the rest; it is not assumed correct.

## Decisions

| ID | Decision | Reason |
|---|---|---|
| D-1 | Bearer-token auth only; no SigV4, no boto3 | Open question resolved in scope; avoids dependency (A-1) |
| D-2 | Temperature is removed at two enforcement points, both for aws-bedrock only: builders (`sampling` returns `{}`) and the transport boundary (`_strip_temperature`) over the final sent body. `_strip_temperature` is gated by profile: it runs only for aws-bedrock and is a strict no-op for self-hosted (and when profile is omitted), so Self Hosted bodies still carry temperature. The strip removes only top-level `temperature` and `temperature` inside `inferenceConfig` (Converse) or `options` (OpenAI/Anthropic bodies); it never alters tool schemas, tool arguments or user schema property names (a user property literally named `temperature` is preserved). INV-1 is enforced at both points; either alone must keep temperature out. | Defense in depth for INV-1 while preserving INV-2 (Self Hosted unchanged), with a narrow strip scope so legitimate schema content is never corrupted. Defect injection must break `sampling` and `_strip_temperature` separately, and a test that walks the sent body for all 3 protocols (openai, anthropic, converse) must fail each time. |
| D-3 | Bedrock env prefix `WORKFLOW_AWS_BEDROCK_`, own key file, protocol key `API_COMPATIBILITY`. Bedrock never reads any temperature env var or stage setting (including `WORKFLOW_AWS_BEDROCK_TEMPERATURE` and the Self Hosted temperature settings) and ignores them silently. The Bedrock key file is created mode 0600 in a 0700 directory, and the token is never written to config or logs. | INV-3 (isolation); AR-015 (storage protection) |
| D-4 | Profile resolution: an omitted profile argument (None) means `self-hosted`; an explicit profile string that is not `self-hosted` or `aws-bedrock` raises a named exception; a Bedrock runner whose profile tag is absent raises, never defaults. This fail-closed rule covers the profile only: an unknown protocol value falls back to openai with one notice and no storage rewrite (see section 12). A Bedrock run never reads Self Hosted key, URL or env, and raises a runner error before any network call if its own token or URL is missing. | INV-3, INV-4: keeps existing callers unchanged (AC-4) while failing closed on bad explicit profiles; profile failure fails closed, protocol failure degrades to OpenAI with a notice; no credential leakage across profiles and no silent fallback |
| D-5 | New adapters live in new module `scripts/lib/bedrock_protocols.py` (pure functions) | Keeps domain logic separate from transport |

## Restrictions

| ID | source_kind | Source | Reqs | Property | Mechanism | Rationale | CAP | Feasibility evidence | Phase |
|---|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST Desired behavior | AC-2 | No temperature for aws-bedrock: Bedrock never reads any temperature env var or stage setting (including WORKFLOW_AWS_BEDROCK_TEMPERATURE) and ignores them silently; Self Hosted bodies still carry temperature; the Bedrock runner raises a named exception (e.g. `ProfileUnresolvedError`) when the profile tag is absent; a test sets both Self Hosted temperature settings to a sentinel value and asserts the sentinel appears nowhere in the sent Bedrock body | D-2 (profile-gated `_strip_temperature` plus `sampling`) | fail closed | CAP-PY | `sampling` in self_hosted_http.py (inspected) | CODING |
| R-2 | USER | CHANGE_REQUEST AC | AC-4 | Self Hosted unchanged | omitted profile argument = self-hosted (D-4); explicit unknown profile string raises | compat | CAP-PY | existing suites via runners | CODING |
| R-3 | REPOSITORY | CLAUDE.md/test naming | AC-1..7 | Python tests named `*-test.py` | `scripts/tests/aws-bedrock-test.py` | runner collects pattern | CAP-PY | scripts/run-python-tests.sh exists | CODING |
| R-4 | DESIGN | D-1 | AC-3 | Auth by token, header fixed per protocol | OpenAI and Converse send only `Authorization: Bearer <token>`. Anthropic sends `x-api-key: <token>` plus `anthropic-version: 2023-06-01` and no Authorization header. The token is never put in the URL, query string or request body. | no SigV4; unambiguous header contract per protocol, testable by asserting on captured request headers, URL and body for all 3 protocols | CAP-PY | AR-012; tests capture sent headers, URL and body per protocol and assert the exact header set and absence of the token elsewhere | CODING |
| R-5 | PLATFORM | live Bedrock | AC-3 | Live endpoint check | optional manual check with real token | credentials unavailable here | CAP-LIVE | non-secret evidence: none required; absence of token must not block coding | LIVE_VERIFICATION |

- Protocol contract table (fixtures in aws-bedrock-test.py assert each row). OpenAI: request `messages`, `response_format` json_schema for constrained output; response `choices[0].message.content` / `tool_calls`; usage `prompt_tokens`->input, `completion_tokens`->output. Anthropic: request `system`, `messages`, `max_tokens`, constrained output via forced `tools` + `tool_choice {type:tool,name}`; response `content[]` blocks (`text`, `tool_use`); usage `input_tokens`->input, `output_tokens`->output. Converse: request `system[]`, `messages[].content[]`, `inferenceConfig` (maxTokens only, never temperature), constrained output via `toolConfig.tools[].toolSpec.inputSchema.json` + forced `toolChoice.tool`; response `output.message.content[]` (`text`, `toolUse`); usage `inputTokens`->input, `outputTokens`->output.
- Parse-error rule: a missing required key (OpenAI `choices`; Anthropic `content`; Converse `output.message.content`) or non-JSON body raises a runner error naming the protocol, and never falls through to another protocol. Missing `usage` yields zero input/output tokens, not an error.

Selected runner/config binding: Python 3 stdlib only, existing runners `run-python-tests.sh` and `run-shell-tests.sh` (CAP-PY). Live Bedrock check ID LV-1: manual, uses user's token; no secrets recorded.

## 4. Components not to modify

Other runners, workflow drivers/stage logic, Self Hosted default values, existing tests (no test edits to protected existing tests; only new test file added). If existing Self Hosted tests fail against the uncommitted partial work, the source is fixed, never the tests.

## 6-8. Data flow / interfaces
Menu -> profile settings (token, URL, protocol) -> `_profile`-tagged values -> adapter builds body -> transport (`compatible_post`/`_request`) -> adapter parses -> common result shape (text, tool_calls, usage). New env: `WORKFLOW_AWS_BEDROCK_*`. Existing interfaces unchanged.

## 12. Error and recovery

Protocol value (file or env) is trimmed and lowercased; empty or missing means openai silently; any other unknown value means openai for that run only, with one stderr notice per process naming the bad value; the stored value is never rewritten. Only an unknown protocol falls back; a missing or unknown profile always raises and never falls back (per D-4/INV-4). Missing Bedrock token/URL -> error raised before any network call, using the same message form as Self Hosted with Bedrock labels, and never falling back to Self Hosted key, URL or env values; HTTP errors redacted; Converse/Anthropic parse errors raise runner errors, never fall through to another protocol. Unusual valid responses: missing usage yields zeros (input/output/total = 0) and is not an error; missing content (no text and no tool calls where the protocol requires one) raises a runner error naming the protocol. Constrained (schema) output uses a forced tool/schema per protocol: OpenAI response_format/json_schema (existing path), Anthropic a single forced tool via tool_choice, Converse toolConfig with a forced toolChoice; the tool input is returned as the structured result.

## 14. Rollback
`git revert` of the change; new files removable; stored Bedrock files are ignored by Self Hosted.

## 16-18. Test strategy
Automated: `bash scripts/run-python-tests.sh` (new `scripts/tests/aws-bedrock-test.py`: labels, protocol persistence, per-protocol body/parse fixtures, no-temperature walk, Self Hosted regression, isolation, fail-closed, perf no-temperature, redaction) and `bash scripts/run-shell-tests.sh` (dispatch). Defect injection: temporarily-free reasoning—tests must fail if `sampling` returns temperature for Bedrock (verified by test asserting on the body, not on helper). Manual: TUI menu inspection; optional LV-1 against a real endpoint.

## 19. Observability
Bedrock labels in status lines and logs; protocol name logged; token never logged.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/self_hosted.py` | Profile resolution, Bedrock key/config/protocol storage | INV-3/4 | High | aws-bedrock-test.py, Self Hosted suites |
| `scripts/lib/self_hosted_http.py` | `sampling`, strip, protocol dispatch, redaction | INV-1/5 | High | same |
| `scripts/lib/bedrock_protocols.py` | New pure adapters (anthropic, converse) | AC-3 | Low | aws-bedrock-test.py: fixtures per protocol contract table (request fields, constrained output, usage mapping, missing-key errors naming the protocol) |
| `scripts/lib/self_hosted_performance.py` | Tolerate absent temperature | AC-6 | Medium | aws-bedrock-test.py |
| `scripts/lib/stage-config.sh` | Accept `aws-bedrock` runner and env by adding only an `aws-bedrock` case; existing cases, defaults and unknown-runner error text stay byte-identical | AC-6 | Medium | shell suites incl. new negative dispatch test (existing runners and unknown-runner error unchanged) |
| `scripts/stagegate.sh` | Dispatch for `aws-bedrock` added as a new case only; existing runner cases, defaults and error text left byte-identical | AC-6 | Medium | shell suites incl. new negative dispatch test (existing runners and unknown-runner error unchanged) |
| `uncle_tui.py` | Menu entry, labels, API Compatibility choice | AC-1 | Medium | aws-bedrock-test.py |
| `scripts/tests/aws-bedrock-test.py` | New tests | AC-1..7 | Low | self |
| `docs/aws-bedrock.md` | Document runner, protocols, SigV4 decision | AC-7 | Low | inspection |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | BH-1, 2, 3 | INV-3 | uncle_tui.py | aws-bedrock-test.py (labels, menu, protocol persistence; protocol normalization: mixed case/whitespace/empty/unknown resolve as specified, one notice per process only for unknown values, stored value never rewritten) | TUI menu |
| AC-2: Bedrock requests never contain temperature; no temperature env var or stage setting (e.g. WORKFLOW_AWS_BEDROCK_TEMPERATURE) is read, and any such value is silently ignored. A missing profile tag raises a named exception. | BH-4 | INV-1 | self_hosted_http.py, bedrock_protocols.py | aws-bedrock-test.py: sentinel test (both Self Hosted temperature settings and any Bedrock temperature env var/setting set to a sentinel; sentinel absent from the sent body for every protocol, with no error or notice), aws-bedrock-test.py: walk the sent body for all 3 protocols; defect injection breaks `sampling` and `_strip_temperature` separately and the walk test must fail each time, aws-bedrock-test.py: named exception raised when profile tag is absent | LV-1 |
| AC-3: Anthropic and Converse request bodies, schema-constrained output (forced tool/schema per protocol), usage mapping and parse errors follow the section 3 protocol contract table; missing usage yields zeros, and a missing required key or missing content raises a runner error naming the protocol. | BH-5 | INV-1 | bedrock_protocols.py | aws-bedrock-test.py (per-protocol request/response/usage fixtures, forced tool/schema per protocol, missing-key/missing-content error naming protocol, missing usage -> zeros) | LV-1 |
| AC-4 | BH-6 | INV-2 | self_hosted*.py | existing suites + regression, aws-bedrock-test.py: Self Hosted body still carries temperature and `_strip_temperature` is a no-op for self-hosted | none |
| AC-5 | BH-7 | INV-3, 4 | self_hosted.py | aws-bedrock-test.py (incl. key file mode 0600, directory mode 0700, token absent from config and logs; and with Self Hosted key/URL/env set to sentinels and Bedrock token or URL missing, the Bedrock run raises before any network call and no sentinel is used or sent) | none |
| AC-6 | BH-8 | INV-4 | stage-config.sh, stagegate.sh, performance | shell suites + py, aws-bedrock-test.py: shared functions called with no profile behave as self-hosted; explicit unknown profile string raises, shell test: with aws-bedrock added, every existing runner still dispatches as before, defaults are unchanged, and an unknown runner yields the same error text byte-for-byte (compared against pre-change output) | none |
| AC-7: Every Bedrock error, log line and status string passes through one shared redactor that removes the token value (HTTP errors, parse errors, URLs, status lines); the redactor is not limited to `_request`. Runner is documented in docs/aws-bedrock.md. | BH-8 | INV-5 | self_hosted_http.py, docs | aws-bedrock-test.py: redaction cases for HTTP error, parse error, URL/status/log string | doc read |

## Implementation sequence

1. **Baseline audit of uncommitted tree** — Owns no source files. Run `bash scripts/run-python-tests.sh` and `bash scripts/run-shell-tests.sh` on the current uncommitted tree and record every delta against BASELINE_REPORT.md before any edit, so regressions from the partial work are attributed. Failures are fixed in source in step 1, never in tests.
2. First, before any edit, run `bash scripts/run-python-tests.sh` and `bash scripts/run-shell-tests.sh` on the current uncommitted tree and record every delta against BASELINE_REPORT.md. Any Self Hosted failure introduced by the partial work is fixed in the source files, never by editing or weakening existing tests. Then audit and complete profile core in `self_hosted.py` and `self_hosted_http.py`: resolve profile, Bedrock storage, `sampling`, strip, redaction (D-2,3,4; R-1). Ensure `_strip_temperature` is gated to aws-bedrock and is a no-op for self-hosted. INV-1 has two enforcement points (`sampling` and `_strip_temperature`); keep both so each can be defect-injected separately.
   Owns: `scripts/lib/self_hosted.py`
   Depends on: 1
3. Protocol adapters, pure functions (D-5; R-4). Auth headers are fixed per protocol: OpenAI and Converse send `Authorization: Bearer <token>`; Anthropic sends `x-api-key: <token>` plus `anthropic-version: 2023-06-01` and no Authorization header. Tests assert the exact header set sent for each protocol; the header assumption is also covered by the live-verification check LV-1.
   Owns: `scripts/lib/bedrock_protocols.py`
   Depends on: 2
4. Performance temperature guard. Consumes the profile contract from step 1 (omitted profile = self-hosted; explicit unknown profile raises).
   Owns: `scripts/lib/self_hosted_performance.py`
   Depends on: 2
5. Shell dispatch for `aws-bedrock`: add only an `aws-bedrock` case in `stage-config.sh` and `stagegate.sh`; leave existing cases, defaults and unknown-runner error text byte-identical. Add a shell test that captures existing-runner dispatch and the unknown-runner error before the edit and asserts identical output after.
   Owns: `scripts/lib/stage-config.sh`, `scripts/stagegate.sh`
   Depends on: 2
6. TUI menu, labels, API Compatibility
   Owns: `uncle_tui.py`
   Depends on: 2
7. Sole owner of `scripts/lib/self_hosted_http.py`: profile-gated `_strip_temperature` (aws-bedrock only, strict no-op for self-hosted), `sampling`, wiring of the step 2 adapters into transport, and calls to the single shared Bedrock redactor. The redactor itself lives in `self_hosted.py` (step 1) so step 2 adapters, this step and step 5 status strings all call it; step 1 therefore does not edit this file.
   Owns: `scripts/lib/self_hosted_http.py`
   Depends on: 2, 3
8. Tests and docs. New files only; existing suites stay unmodified. Python tests cover: temperature env/setting sentinels (incl. WORKFLOW_AWS_BEDROCK_TEMPERATURE) absent from all 3 bodies; a tool-schema property named `temperature` survives the strip; Self Hosted body still carries temperature; protocol normalization (mixed case, whitespace, empty, unknown -> resolved protocol, one notice only for unknown, storage unchanged); per-protocol missing-usage -> zeros, missing-content error, forced tool/schema for constrained output; per-protocol missing-required-key errors naming the protocol; captured request per protocol asserting exact headers and token absent from URL/body; parametrized final-URL assertions; https/loopback and redirect credential-drop; key file 0600/dir 0700; Self Hosted credentials ignored with pre-network error; redaction of HTTP, parse, URL and status strings with a token sentinel; omitted profile = self-hosted and explicit unknown profile raises. Shell test `aws-bedrock-dispatch-test.sh` (depends on step 4) asserts positive `aws-bedrock` dispatch plus unchanged existing-runner dispatch and unknown-runner error text.
   Owns: `scripts/tests/aws-bedrock-test.py`, `scripts/tests/aws-bedrock-dispatch-test.sh`, `docs/aws-bedrock.md`
   Depends on: 2, 3, 4, 5, 6, 7
9. Record deviations (if any) and launch metadata `.uncle/launch.json`
   
   After step 1 settles the profile contract, steps 2, 3, 4 are independent of each other and may be batched.
   Owns: `.uncle/docs/IMPLEMENTATION_NOTES.md`, `.uncle/launch.json`
   Depends on: 8

## Scope cuts under time pressure
Cut first: Converse tool-config edge cases, then LV-1 live check, then Anthropic streaming; never cut INV-1, INV-2, INV-4.

## Risks

- Missed hard-coded `self-hosted` strings (grep each file in step 4/5).
- Provider endpoint path and auth-header assumptions (A-2; Anthropic uses Bearer plus anthropic-version, no x-api-key) are unverified live; LV-1 mitigates the remainder. URL construction rule: strip trailing slashes from the configured base URL, append the per-protocol path exactly once (no double append if the base already ends in that path, e.g. `/converse`), percent-encode the model id in the Converse path, and tests assert the final URL for each of the three protocols (openai, anthropic, converse). Token-bearing URL safety rule: Bedrock URLs must be https (http allowed only for loopback hosts such as localhost/127.0.0.1/::1), otherwise the runner raises before any network call; redirects never forward credential headers (Authorization, x-api-key) to another origin and are not followed with credentials. aws-bedrock-test.py asserts each of these.
- Existing uncommitted partial work may contain defects; step 1 audits it.

**URL construction (AR-004).** Strip all trailing slashes from the configured base URL, then append the per-protocol suffix exactly once; if the base already ends with that suffix, do not append it again. Paths: openai chat = `/chat/completions`, discovery = `/models`; anthropic messages = `/v1/messages` (just `/messages` when the base already ends in `/v1`), discovery = `/v1/models` (same `/v1` rule); converse = `/model/{id}/converse`, where `{id}` is percent-encoded with no safe characters (so `:` and `/` are encoded). Converse has no discovery call: the configured model id is used as-is. The token is never placed in the URL. Tests assert the final URL string for each protocol and operation, including trailing-slash, already-suffixed base, and an id such as `anthropic.claude-3:0`.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Bedrock temperature env/stage-setting behavior was unspecified; a silent-ignore rule closes the gap and supports INV-1. | D-3 and R-1 state Bedrock never reads any temperature env var or setting; AC-2 test requirement added. |
| AR-002 | Accepted | Section 12 fallback and INV-4 fail-closed conflict; scoping fallback to unknown protocol values only (never profile) resolves it and fixes notice and storage behavior. | Edit s6.1 to define protocol fallback (openai, one notice, no rewrite); D-4 clarified that only the profile fails closed, not protocol. |
| AR-003 | Accepted | Auth header was ambiguous; the finding's rule (Bearer for all three protocols, anthropic-version for Anthropic, no x-api-key) matches the Bedrock bearer-token decision D-1. | Step 2 now fixes headers per protocol; risk s14.1.i2 notes header assumption is also covered by LV-1. |
| AR-004 | Accepted | Real gap: only the Converse path was specified; exact per-protocol paths, joining and encoding are needed to test URLs. | Added a URL-construction block under Risks (s14) and reworded the endpoint-path risk item to reference it. |
| AR-005 | Accepted | The strip scope was ambiguous between 'any nesting' and transport-only; a narrow, explicit scope protects tool schemas and user property names. | D-2 now states the strip scope (top-level and inferenceConfig/options temperature only; never tool schemas, arguments or user property names). |
| AR-006 | Accepted | Unusual-but-valid responses and constrained output were unspecified; stating the rules makes parse behavior testable. | Section 12 error/recovery (s6.1) and AC-3 traceability row now state missing-usage zeros, missing-content error, and forced tool/schema per protocol. |
| AR-007 | Accepted | D-2 and INV-1 disagreed on the strip location and the profile gating of the shared strip was unstated; Self Hosted must keep temperature. | D-2 now gates `_strip_temperature` to aws-bedrock (no-op for self-hosted); R-1 and the AC-2/AC-4 rows add a Self Hosted-keeps-temperature test; step-1 implements it. |
| AR-008 | Accepted | Default profile was undefined for shared functions called without a profile; omitted means self-hosted, explicit unknown raises. | Edit D-4 and R-2 to state omitted profile = self-hosted and explicit unknown profile string raises; add test to AC-6. |
| AR-009 | Accepted | Uncommitted partial work touches files covered by existing Self Hosted tests, so baseline deltas must be checked first and failures fixed in source. | Step 1 now first runs both test runners, records deltas vs BASELINE_REPORT, and fixes Self Hosted failures in source only; s4.1 states this. |
| AR-010 | Accepted | Real gap: adding aws-bedrock must not alter existing runner dispatch, defaults or unknown-runner error text, and AC-6 had no negative test. | Edited s10.1.r5, s10.1.r6, AC-6 and step-4 to add an additive-only dispatch rule with a byte-identical shell regression test. |
| AR-011 | Accepted | Section 12 (fallback to OpenAI) and D-4 (raise on unresolved profile) read as contradictory; they cover different values (protocol vs profile) and must be stated so. | Edit D-4 and s6.1 to state only an unknown protocol falls back to OpenAI with a notice; a missing or unknown profile always raises. |
| AR-012 | Accepted | The per-protocol credential header was ambiguous; the finding's explicit rule is adopted (it also overrides the conflicting AR-003 Bearer wording for Anthropic). | Edited R-4 (s3.1) to fix headers per protocol and forbid the token in URL or body. |
| AR-013 | Accepted | INV-5 redaction was scoped to _request HTTP errors only; Bedrock parse errors, URLs, logs and status strings could also leak the token. | AC-7 row requirement and tests now require one shared redactor for every Bedrock error, log line and status string, with HTTP, parse and URL tests. |
| AR-014 | Accepted | The user-configured URL receives the token, so transport safety (https, redirects, model-id encoding) must be stated and tested. | Reworded risk s14.1.i2 to state https-only (loopback http exempt), no credential forwarding on redirects, and percent-encoded Converse model id. |
| AR-015 | Accepted | Token storage protection was unspecified; owner-only file and directory modes are cheap and testable. | D-3 now requires key file mode 0600 in a 0700 directory and no token in config or logs; AC-5 test coverage updated. |
| AR-016 | Accepted | Real gap: nothing says Bedrock cannot read Self Hosted credentials or that missing config fails before any network call. | Edited D-4 and s6.1 to state Bedrock never reads Self Hosted key/URL/env and errors before any network call; added a test to AC-5. |
| AR-017 | Accepted | Plan left Anthropic/Converse auth headers unspecified; the finding's explicit header rule is adopted. | R-4 mechanism and step-2 text now state per-protocol headers: Anthropic x-api-key + anthropic-version, OpenAI/Converse Authorization: Bearer. |
| AR-018 | Accepted | INV-1 enforcement was named two ways; both layers are kept as defense in depth and each must be independently proven by defect injection. | Edit D-2 and step-1 to state the two enforcement points, and add the separate-defect-injection requirement to the test strategy via s13.1 and AC-2. |
| AR-019 | Accepted | Stored protocol value handling was unspecified; a normalize/fallback/notice rule makes it testable and consistent with fail-closed profile handling. | Section 12 (s6.1) now states the trim/lowercase rule, silent OpenAI for empty or missing, one stderr notice per process for unknown values, and no rewrite of storage. |
| AR-020 | Accepted | Fixture contracts for Converse and Anthropic were undefined; a field-mapping table and a named parse-error rule make fixtures testable. | Added section 3 mapping table block and parse-error rule; updated AC-3 requirement/tests and s10.1.r3 coverage. |
| AR-021 | Accepted | URL construction rules were unspecified; stating them makes the path assumption testable and removes ambiguity about slashes and encoding. | Reworded risk s14.1.i2 to define URL construction (strip slashes, append path once, percent-encode model id, assert final URL per protocol). |
| AR-022 | Accepted | 'Unresolved profile' and 'no temperature setting read' were untestable as written; a named exception and a sentinel test make them observable. | Updated R-1 and AC-2 (s3.1, s11.1) to require a named exception on absent profile tag and a sentinel-temperature body test. |
