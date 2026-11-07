# Change spec — Issue 182

Omitted sections: Performance (none); Migration of data stores beyond config (see section 11 inline); Prototype isolation (not a prototype)

## 1. Change type
Feature + Refactor + Security (AWS Bedrock runner only).

## 2. Problem statement
Bedrock Configure asks for a URL and wire protocol although the region determines endpoints and Converse works for all providers. Extra surface, extra failure modes, protocol-dependent discovery.

## 3. Current behavior
Baseline B1-B3.

## 4. Desired behavior
Connection = `region` + AWS Bedrock Token. Control `https://bedrock.<region>.amazonaws.com`, runtime `https://bedrock-runtime.<region>.amazonaws.com`. Always Converse. Model picker offers foundation model IDs and inference profile IDs (all pages).

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| S1 | MODIFY | Configure → AWS Bedrock (TUI and shell) | URL, token, API Compatibility | Only Region and AWS Bedrock Token; no URL/compat field or picker | TUI + shell configure tests |
| S2 | MODIFY | Set region + token | Discovery per protocol | Discovery GET `{control}/foundation-models` and `{control}/inference-profiles?maxResults=100` with `Authorization: Bearer`, following `nextToken` (URL-encoded) until absent; catalog = union of modelId and inferenceProfileId | discovery tests with fake transport |
| S3 | MODIFY | Any Bedrock stage request | OpenAI default; URL from config | POST `{runtime}/model/<quote(modelId,safe='')>/converse`, `content-type: application/json`, bearer auth; `:`→`%3A`; reply text from `output.message.content` | request-capture tests |
| S4 | PRESERVE | Any Bedrock request with temperature configured (config key, env, request-options, per-stage) | no temperature | body has no `temperature` anywhere in `inferenceConfig` or elsewhere; config ignored; reuse key not affected | body-inspection test (B4, I1, I2) |
| S5 | PRESERVE | Self Hosted request | temperature as before | unchanged | existing Self Hosted tests (B5) |
| S6 | MODIFY | Discovery failure (HTTP error, network, bad JSON, any page failing) | error | prior catalog kept; actionable error naming region/token | failure tests (B7) |
| S7 | ADD | Invalid region (not `^[a-z]{2,}(-[a-z]+)+-\d+$`-style) or multi-line token | n/a | rejected at save/settings with clear message; no request sent | validation tests |
| S8 | MODIFY | Existing config with `base_url`/`api_compatibility` and no region | works per protocol | region derived from legacy URL host when it matches a Bedrock host pattern; else a clear error telling the user to set Region in Configure → AWS Bedrock; legacy keys never used for requests and not an obscure failure | migration tests |
| S9 | REMOVE | `WORKFLOW_AWS_BEDROCK_API_COMPATIBILITY`, `UNCLE_AWS_BEDROCK_BASE_URL`, `aws-bedrock.base_url` | honored | ignored for Bedrock requests | tests |
| S10 | ADD | Region override | n/a | `UNCLE_AWS_BEDROCK_REGION` env and `aws-bedrock.region` config key | settings tests |
| S11 | PRESERVE | Token storage (B6), isolation from Self Hosted (B8), redaction (B9) | as baseline | unchanged | existing tests |
| S12 | MODIFY | Docs | describe URL/compat | docs/aws-bedrock.md and README describe region+token+Converse | doc grep test/inspection |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| V1 | STRENGTHENED | No Bedrock request contains any temperature/sampling field regardless of config/env | Bedrock only | body builder + `_strip_temperature` + `sampling` | outgoing-body test |
| V2 | EXISTING | Self Hosted temperature behavior unchanged | Self Hosted | unchanged code | existing suites |
| V3 | STRENGTHENED | Token only sent over https to hosts derived from a validated region; no http loopback exception | Bedrock | URL builders | URL tests |
| V4 | EXISTING | Token single-line | Bedrock | settings/save | tests |
| V5 | EXISTING | Failed discovery keeps prior catalog | Bedrock | refresh | tests |
| V6 | EXISTING | Bedrock never falls back to Self Hosted credentials | Bedrock | settings | tests |
| V7 | NEW | Configured temperature does not alter reuse/cache keys for Bedrock | Bedrock | self_hosted_performance.py | test |

RELAXED/REMOVED invariants: none. (Removal of the loopback http allowance in I3 is a strengthening.)

## 7. Compatibility
Self Hosted and other runners unchanged. Legacy Bedrock key files readable; stale fields ignored, not rewritten until user saves.

## 8. Error behavior
Actionable messages for: missing/invalid region, missing token, HTTP status on discovery (names region and token), unreachable endpoint, malformed response, Converse response lacking `output.message.content`.

## 10. Security
Bearer token https-only, no redirects on discovery, redaction preserved, key file 0600 and gitignored.

## 11. Migration
Legacy `base_url` → region derivation (S8); no automatic file rewrite.

## 12. Rollback
Revert commit; key file format additive (adds `region`), legacy readers ignore it.

## 14. Non-goals
SigV4/IAM credentials, other runners, streaming Converse, changing Self Hosted.

## 15. Assumptions
Default region when none: none — region required. Live Bedrock verification is manual only.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | No Bedrock request body ever contains a temperature (or sampling) field, even when temperature is configured globally, per stage, via env, or in request-options; configured values do not change Bedrock reuse keys. Self Hosted temperature handling is unchanged. | Python test inspects the outgoing Converse body with temperature configured in each place; existing Self Hosted temperature tests still pass. |
| AC-2 | Configure → AWS Bedrock (TUI and shell) asks only for Region and AWS Bedrock Token; no Bedrock URL or API Compatibility field, picker, or label remains. | TUI field-list test and shell configure test; grep for removed labels. |
| AC-3 | Region is validated (format) and token must be a single line; endpoints are https URLs derived only from the region. | Validation unit tests including invalid region, multi-line token, and URL builders. |
| AC-4 | Model discovery GETs {control}/foundation-models and {control}/inference-profiles?maxResults=100 with bearer auth, follows nextToken (URL-encoded) across all pages, and the catalog contains both modelId and inferenceProfileId values. | Fake-transport test with multi-page profiles incl. a token needing URL encoding. |
| AC-5 | A discovery failure (any page) keeps the prior catalog and surfaces an actionable error. | Failure-injection tests for HTTP error, network error, malformed JSON, and failure on page 2. |
| AC-6 | All Bedrock stage requests POST to https://bedrock-runtime.<region>.amazonaws.com/model/<url-encoded modelId>/converse with bearer auth and content-type application/json; ':' is encoded %3A; text, tool-call and schema outputs parse from the Converse response. | Request-capture test asserting URL, headers, body shape; response parsing tests. |
| AC-7 | Existing configs with base_url/api_compatibility are migrated: region derived from the old Bedrock host when possible, otherwise a clear message instructs setting Region; legacy fields and WORKFLOW_AWS_BEDROCK_API_COMPATIBILITY/UNCLE_AWS_BEDROCK_BASE_URL are never used for requests. | Migration tests with legacy key files and env vars. |
| AC-8 | OpenAI and Anthropic adapters and protocol selection are removed from Bedrock code. | grep shows no openai/anthropic adapter or api_compatibility reference in Bedrock code; protocols test updated. |
| AC-9 | docs/aws-bedrock.md and README describe region + token + Converse; Bedrock tests updated; both full suites show no new failures versus baseline. | Doc inspection; run-shell-tests.sh and run-python-tests.sh compared to baseline. |

