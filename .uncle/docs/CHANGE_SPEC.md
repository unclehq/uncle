# Change Spec — Issue 178

Omitted sections: Migration (new files only); Prototype isolation (not a prototype); Performance (parity with Self Hosted)

## 1. Change type
Feature (with bounded refactor into a runner profile).

## 2. Problem / current / desired
Baseline B-1..B-5. Add runner `aws-bedrock` as a profile of the Self Hosted implementation: own labels, key file, env prefix, stored protocol, no temperature.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| BH-1 | ADD | Open main menu | No Bedrock | AWS Bedrock entry beside Self Hosted | menu-label test |
| BH-2 | ADD | Open Bedrock submenu | n/a | Same choices as Self Hosted, labels `AWS Bedrock Token`, `Bedrock URL`, plus `API Compatibility` (OpenAI/Anthropic/Converse; OpenAI default) | label test |
| BH-3 | ADD | Choose protocol | n/a | Persisted in Bedrock settings only | persistence test |
| BH-4 | ADD | Any Bedrock request, any protocol | n/a | No `temperature` key anywhere in body (incl. nested options/inferenceConfig); no temperature setting offered or read | per-protocol body test |
| BH-5 | ADD | Bedrock response, any protocol | n/a | Text, tool calls, usage, schema-constrained output parsed correctly | per-protocol parse tests with fixtures |
| BH-6 | PRESERVE | Self Hosted use | temperature sent | Unchanged incl. env/stage settings | existing suites + new regression test |
| BH-7 | ADD | Save Bedrock token/URL/protocol | n/a | Stored separately from Self Hosted | isolation test |
| BH-8 | ADD | Bedrock selected for a stage | n/a | Dispatch/discovery/performance behave as Self Hosted without temperature; performance code tolerates no temperature | dispatch + perf tests |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | NEW | Bedrock never emits temperature | all 3 protocols | body strip at transport boundary | body tests |
| INV-2 | EXISTING | Self Hosted always sends temperature | self-hosted | unchanged `temperature()` | regression test |
| INV-3 | NEW | Bedrock settings/keys isolated from Self Hosted | storage | profile key file/env prefix | isolation test |
| INV-4 | NEW | Missing/unknown profile never falls back silently to Self Hosted for a Bedrock run | dispatch | fail closed | dispatch test |
| INV-5 | STRENGTHENED | API key never appears in error text | HTTP errors | redaction in `_request` | redaction test |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Self Hosted env names, files, defaults unchanged. Unknown stored protocol value falls back to OpenAI compatible with a visible notice.

## 8. Errors
Invalid protocol, missing token/URL, or HTTP/parse failure produce the same error surfaces as Self Hosted, never expose the token.

## 10. Security
Token sent only as bearer (OpenAI/Anthropic: per protocol header) to the configured URL; redacted in errors/logs.

## 12. Rollback
Revert the change; Bedrock files are additive and inert for Self Hosted.

## 14. Non-goals
No new cloud SDK dependency (no boto3); no Bedrock model catalog beyond the Self Hosted discovery path; no Self Hosted behavior change.

## 15. Assumptions
A-1: Bearer-token (Bedrock API key) auth suffices for all three protocols; SigV4 is out of scope and documented as unsupported (decides the open question). A-2: Anthropic-compatible uses `x-api-key`/bearer + `anthropic-version` header against the configured URL; Converse uses `{URL}/model/{id}/converse`.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | Main menu shows an AWS Bedrock entry; its submenu mirrors Self Hosted with labels `AWS Bedrock Token`, `Bedrock URL` and an `API Compatibility` choice (OpenAI compatible default, Anthropic compatible, Converse API compatible). | Python test asserting menu labels/choices; manual TUI check. |
| AC-2 | Requests built by the Bedrock runner contain no `temperature` key (at any nesting) under OpenAI, Anthropic and Converse protocols, including constrained/final calls; no temperature setting or env is offered or read for Bedrock. | Per-protocol body tests walking the whole body; test that Bedrock ignores `WORKFLOW_SELF_HOSTED_TEMPERATURE` and `<stage>.temperature`. |
| AC-3 | Each protocol builds a valid request and parses responses correctly, including tool calls, usage, and schema-constrained output. | Fixture-based request/response tests for each protocol. |
| AC-4 | Self Hosted behavior is unchanged, including temperature handling. | Regression test asserting Self Hosted bodies still carry temperature; existing suites unchanged vs baseline. |
| AC-5 | Bedrock token, URL and chosen protocol are stored separately from Self Hosted's, and an unknown/missing Bedrock profile never falls back to Self Hosted. | Isolation and fail-closed tests on temp config dirs. |
| AC-6 | The performance module and stage dispatch (stage-config.sh, stagegate.sh, shims) work for Bedrock with no temperature present. | Python test of performance functions with no temperature; shell test of dispatch for `aws-bedrock`. |
| AC-7 | API keys are redacted from HTTP error messages; the SigV4 decision is documented in docs/aws-bedrock.md. | Redaction test; doc inspection. |

