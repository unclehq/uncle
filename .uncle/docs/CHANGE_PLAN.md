# Change plan — Issue 182

Seeded from [unclehq/uncle#182](https://github.com/unclehq/uncle/issues/182).

Issue 182

Omitted sections: Schema migration tooling (no rewrite); Feature flag (none, direct replacement); Concurrency (no change); Observability (no change)

## 1. Selected technical approach

Keep Bedrock a profile of the Self Hosted runner. Converse becomes the only transport.

- Pure helpers in `bedrock_protocols.py`: `validate_region`, `control_url(region)`, `runtime_url(region)`, `region_from_url(url)` (legacy; accepts only https URLs whose host exactly matches `bedrock.<region>.amazonaws.com` or `bedrock-runtime.<region>.amazonaws.com` with no credentials, port, query or fragment, and the extracted region must pass `validate_region`; anything else returns None), `build_headers(token)`, `build_url(region, model)`, converse-only `build_body`/`parse_response`, `parse_models(foundation, profiles)`.
- `self_hosted.py`: connection stores `region` + `api_key`; `settings()` for Bedrock takes region and api_key from the connection (env first) and the model ID from the selected entry, never region/token from per-model entries; derives `base_url=runtime_url(region)`, which always overrides any stored or env base_url (so downstream code keeps working), sets `_protocol='converse'`; discovery function `discover_bedrock_models(region, token)` does foundation-models + paginated inference-profiles, no redirects (any 3xx is an error naming the region), 2 MB cap per page (an oversized page is an error), page cap 100 (a 101st page is an error), an empty or absent nextToken ends pagination, a repeated nextToken is an error, and an empty union catalog is an error; every such failure raises an actionable ValueError and keeps the prior catalog; `refresh_models` commits only on success.
- `self_hosted_http.py`: `compatible_post` always routes Bedrock to `_bedrock_native_post` (converse); every Bedrock request (Converse POST and discovery GETs) goes through a no-redirect opener so the bearer token is never forwarded, and any 3xx raises an actionable ValueError without echoing the token or response body; `constrained_completion` skips the `capabilities()` probe for Bedrock and uses a mode list of exactly `[json_schema]` via Converse, with no rejected-mode fallback loop (ollama/vllm/json_object are never tried); any HTTPError raises the actionable ValueError naming region and token; a Converse reply lacking `output.message.content` raises a ValueError naming Converse; `_strip_temperature`/`sampling` unchanged.
- `uncle_tui.py`: `@bedrock` fields `[region, api_key]`; remove `api_compatibility` picker/COMPAT_CHOICES/help text; labels "Region" and "AWS Bedrock Token"; saving drops legacy `base_url` and `api_compatibility` from the stored connection.
- Shell Configure: `profile_menu` Bedrock branch prompts Region + token (shell `uncle` unchanged, it delegates).

## 2. Alternatives considered
- Keep protocols but default Converse: rejected, leaves surface the issue removes.
- Env endpoint override for tests: rejected, violates https-only invariant V3; tests patch the transport instead.

## 3. Why preferred
Smallest surface, one code path, endpoints fully determined by region.

## Decisions

| ID | Decision | Reason |
|---|---|---|
| D1 | Region config key `aws-bedrock.region`, env `UNCLE_AWS_BEDROCK_REGION`; stage key `<stage>.region`. Single precedence order in `settings()`: env, then stage key `<stage>.region`, then `aws-bedrock.region`, then stored connection `region`, then entry `region`, then `region_from_url(legacy base_url)` (used only as the last fallback, for exact AWS hosts), else ValueError "Set Region in Configure → AWS Bedrock" (D3). The first non-empty source wins and is validated (D2); an invalid non-empty value from any source raises and never falls through to a later source. A stale base_url is ignored whenever any region exists. Per-model entries never supply region. Full ordering is also stated in D9. | One ordered rule removes ambiguity between env, stage, shared, connection, entry and legacy values; consistent with D2, D3 and D9. |
| D2 | One region regex `^[a-z]{2,}(-[a-z]+)+-\d+$` (covers `us-east-1`, `us-gov-west-1`; same regex as spec S7). Region is trimmed of surrounding whitespace and never case-folded; empty-after-trim counts as unset, and any other non-matching value (including uppercase) is rejected by `validate_region` with an actionable ValueError before any network request, at TUI save, shell save and `settings()`, regardless of source. | Matches AWS format; resolves the spec/plan regex conflict with a single rule and states strip, case and validation points. |
| D9 | For Bedrock, settings() deletes the URL scheme/loopback/credentials check (the URL is derived from a validated region, always https). A cleared connection (empty region or token) blanks both and raises the missing-region or missing-token error; stale entry values are not revived. | V3: token never sent over http; avoids reviving cleared credentials |
| D3 | Legacy migration at read time only, in `settings()` and TUI load, as the last fallback in the D9/D1 region order: `region_from_url(base_url)` is used only when no other region source yields a value. It accepts only https hosts exactly `bedrock.<region>.amazonaws.com` or `bedrock-runtime.<region>.amazonaws.com` whose region passes `validate_region` (arbitrary or non-AWS hosts yield None); if none, raise ValueError "Set Region in Configure → AWS Bedrock". The legacy base_url is never used as a URL and is ignored whenever any other region source exists; the derived `base_url=runtime_url(region)` always overrides any stored or env base_url. The file is not rewritten on read; saving in Configure/shell drops legacy `base_url` and `api_compatibility` from the connection. Legacy files with a derivable region keep working. | S8, safe; migration is the last fallback so base_url is never preferred over a stored region, and no region is derived from arbitrary hosts |
| D4 | Stored model entries keep `model`, `api_key`, plus `region`. Region and bearer token resolve per D1/D9 with the connection/env value first; an entry `region` is only the lowest-precedence stored source and an entry `api_key` never overrides the connection/env token. A stale entry `base_url` is read only as the D9 last-resort legacy fallback (exact AWS host) when no region source exists, and `api_compatibility` is ignored. The resolved region is validated with `validate_region`. | compat; stale entries must not override connection or env configuration |
| D5 | Discovery edge cases: pagination is capped at 100 pages (the 101st page is an error); an empty or absent nextToken ends pagination; a repeated nextToken is an error (no loop); any 3xx response is an error naming the region (no redirect followed); an oversized page (>2 MB) is an error; an empty union catalog is an error. Every such error is an actionable ValueError and keeps the prior catalog and connection. | avoid loops, token forwarding via redirects, and silently empty catalogs |
| D6 | Tests patch exactly two named seams, never a production endpoint override: `self_hosted_http._request` for Converse POST capture, and a named discovery GET helper in `self_hosted.py` (`_discovery_get(url, headers)`) used by `discover_bedrock_models`. Tests assert the captured url, headers and body. | V3 |
| D7 | Keep file `bedrock_protocols.py` (converse-only) rather than deleting | fewer import churn |
| D8 | Dedupe and sort catalog IDs; each model ID must be a string matching `^[A-Za-z0-9][A-Za-z0-9._:/-]*$` (this excludes whitespace and `#`), checked before storage or use in a URL; non-conforming IDs are skipped | existing filter, tightened to a safe pattern |
| D10 | Bedrock token must be non-empty printable ASCII (0x21-0x7E) with no whitespace or control characters; validated in `settings()`, TUI save and shell save. No error message or log may include the token or any response body. | AR-016: stops header injection and secret leakage. |
| D11 | Bedrock constrained completion uses only `json_schema` mode via Converse; ollama_format, vllm and json_object modes are never tried. `max_tokens` passes unchanged with no reasoning reserve. | Names the fixed mode list and ANSWER_CAP treatment so code and tests agree. |

## Restrictions

| R- | source_kind | Source | Req | Required property | Mechanism | Rationale | CAP | Phase |
|---|---|---|---|---|---|---|---|---|
| R-1 | USER | CHANGE_REQUEST "Never use temperature" | AC-1, V1 | No temperature in Bedrock body; unaffected by config; Self Hosted unchanged | existing `_strip_temperature`+`sampling`, converse `build_body` never emits one, perf key already excludes | verified at self_hosted_http.py:1033-1045, self_hosted_performance.py:256-264 | CAP-1 | CODING |
| R-2 | USER | CHANGE_REQUEST "token only over https" | AC-3 | https only | URL builders hardcode https and validated region; remove http loopback path | V3 | CAP-1 | CODING |
| R-3 | REPOSITORY | CLAUDE.md protected tests | AC-9 | Tests changed only as authorized by request ("Bedrock tests are updated") | edit only the five Bedrock test files | request-authorized | CAP-2 | CODING |
| R-4 | DESIGN | self_hosted.py discovery | AC-4,5 | Prior catalog kept | commit after full success | I6 | CAP-1 | CODING |
| R-5 | PLATFORM | Bedrock REST API | AC-4,6 | Real endpoint behavior | live verification only, cannot run here | no credentials | CAP-3 | LIVE_VERIFICATION |

R-2 amendment (D9): the https-only mechanism also removes the settings() URL scheme/loopback check for Bedrock; no http URL, including loopback, is ever accepted. V7 reuse-key rule (AR-023): the Bedrock reuse key must be identical with and without each temperature source (env, stage config, shared config, request body) and must include the region. `aws-bedrock-test.py` asserts both: same key across temperature sources, different key when the region differs.

Runner/config binding: Bedrock profile only, key file `.uncle/aws-bedrock-keys.json`. Feasibility evidence: inspected symbols above (self_hosted_http.py:158-224, self_hosted.py:167-221, uncle_tui.py:1276-1404). Live auth (CAP-3) is unavailable here and is not a coding prerequisite; live check LV-1: `curl` reference script from CHANGE_REQUEST with `AWS_BEARER_TOKEN_BEDROCK` set (non-secret evidence: region and model ID only).

## 4. Components to modify / 5. Not to modify

See change-impact table. Not modified: Self Hosted code paths in `discover_models`, `stage-config.sh`, `uncle` shell script, `supervisor*.py`. `self_hosted_performance.py` is not edited by default: its reuse key already excludes temperature and, for Bedrock, is built from the derived runtime `base_url` (which embeds the region) plus model, so it changes when the region changes. V7 is enforced by a test (see step 5), not by inspection; if that test shows the key lacks region or varies with temperature, the minimal fix in `self_hosted_performance.py` is allowed and must be recorded in IMPLEMENTATION_NOTES.md.

## 6-7. Data flow / state

Region resolved per D1 order (env, stage key, aws-bedrock.region, connection region, entry, legacy base_url host used only as last fallback for exact AWS hosts, else missing-region error; first non-empty source wins, no fall-through) and validated per D2 (strip, no case folding; an invalid value from any source raises before any request) → `settings()` → runtime URL → converse POST. Cleared connection (empty region or token) raises the missing-region/token error. Discovery: region+token → control URL → union catalog → key file.

Region resolution: merge env > stage key > shared config > entry/connection region, then validate with `validate_region` (D9); entry `base_url` is never read. Token validation per D10; errors and logs name the field or HTTP status only, never the token or response body.

## 8-9. Interface and persistence
Key file connection `{region, api_key}`; entries `{model, api_key, region}`. Removed: `base_url`, `api_compatibility`, env `WORKFLOW_AWS_BEDROCK_API_COMPATIBILITY`, `UNCLE_AWS_BEDROCK_BASE_URL`. Settings dict still exposes `base_url` (derived) and `_protocol='converse'` for internal consumers.

## 10. Compatibility

Legacy files are read. Region precedence is defined once in D1/D3: legacy `base_url` is only the last fallback, used when no higher-precedence region exists and its host is an exact bedrock(-runtime).<region>.amazonaws.com https host (region derived via region_from_url); any other legacy file with no region raises the Set Region error. Stale `base_url`/`api_compatibility` fields are ignored whenever any region exists, are never used as a URL, and are never rewritten on read (D3/D4).

## 12. Error and recovery
Actionable ValueErrors for region, token, HTTP code (names region/token), network, malformed JSON, page-cap overflow; failures keep prior catalog.

## 13-14. Migration and rollback
Read-time migration only. Rollback: revert the change; added `region` fields ignored by old code.

## 16-17. Automated and regression tests

Update `aws-bedrock-test.py` (converse URL/headers/body, temperature matrix, V7 reuse key, discovery, region validation, migration, https-only, token validation), `aws-bedrock-protocols-test.py` (converse-only adapters), `aws-bedrock-configure-test.py/.sh` (fields Region + Token only), `aws-bedrock-dispatch-test.sh`. Required cases, all with the transport patched at `self_hosted_http._request` and `self_hosted._discovery_get`, asserting captured url/headers/body: (1) table-driven region matrix (whitespace trimmed, uppercase, empty, `us-gov-west-1`, invalid from each source) asserting ValueError and zero transport calls, plus ordered precedence env > stage > shared > connection > entry > legacy URL and the Set Region error when none resolves; (2) cleared connection raises missing-region/token error and no http/loopback URL is produced or accepted; (3) `region_from_url` accepts only https bedrock(-runtime).<region>.amazonaws.com and returns None for other hosts, http, or invalid regions; (4) token rejection of whitespace, control and non-ASCII values, and no error or captured output contains the token or response body; (5) 3xx on both discovery GET and Converse POST raises an error with no second request carrying the token; (6) discovery: empty union, empty nextToken, repeated nextToken, oversized page (>2 MB) and 101st page each raise ValueError with the prior catalog kept; (7) constrained_completion for Bedrock makes exactly one json_schema Converse call, never calls capabilities, and does not retry on HTTPError; (8) protocols-test stopReason cases end_turn, max_tokens, tool_use, unknown value, and missing output.message.content raising ValueError; (9) shell menu: blank input keeps existing values and a failed discovery after a region change leaves the key file byte-identical; (10) V7 reuse key identical with and without each temperature source and different per region. Regression: Self Hosted suites run unchanged. Commands are the baseline's two runners (grouped `1 2`).

## 18. Manual verification
TUI: Configure → AWS Bedrock shows Region and Token only; LV-1 live reference script when a token is available.

## Change-impact table

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| `scripts/lib/bedrock_protocols.py` | converse-only; region/URL/model-list helpers | S2,S3 | Medium | protocols-test |
| `scripts/lib/self_hosted.py` | region connection, discovery, settings, migration, shell menu | S1,S2,S7,S8 | High | aws-bedrock-test, configure tests |
| `scripts/lib/self_hosted_http.py` | always converse, skip capabilities probe | S3,S4 | Medium | aws-bedrock-test |
| `uncle_tui.py` | Region/Token fields; remove compat picker | S1 | Medium | configure tests |
| `docs/aws-bedrock.md` | rewrite config/settings | S12 | Low | inspection |
| `README.md` | one-line pointer update | S12 | Low | inspection |
| `scripts/tests/aws-bedrock-test.py` | update: patch `self_hosted_http._request` and `_discovery_get`; assert captured url, headers, body; repeated nextToken and unsafe model-ID cases | R-3 | Low | itself |
| `scripts/tests/aws-bedrock-protocols-test.py` | update | R-3 | Low | itself |
| `scripts/tests/aws-bedrock-configure-test.py` | update | R-3 | Low | itself |
| `scripts/tests/aws-bedrock-configure-test.sh` | update | R-3 | Low | itself |
| `scripts/tests/aws-bedrock-dispatch-test.sh` | update if it references removed settings | R-3 | Low | itself |

## Traceability

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | S4, S5 | V1, V2, V7 | self_hosted_http.py, bedrock_protocols.py | aws-bedrock-test.py | LV-1 |
| AC-2 | S1 | — | uncle_tui.py, self_hosted.py | configure tests | TUI look |
| AC-3 | S7 | V3, V4 | bedrock_protocols.py | aws-bedrock-test.py asserts region precedence order (env > stage > shared > connection > entry > legacy URL), strip without lowercasing, empty/uppercase/invalid rejected with no network call at settings(), TUI save and shell save, and legacy URL fallback only for AWS hosts | — |
| AC-4 | S2 | V5 | self_hosted.py | aws-bedrock-test.py | LV-1 |
| AC-5 discovery failures (HTTP error, network, malformed JSON, page-2 failure, empty union, redirect, oversized page, repeated nextToken, 101st page) raise an actionable ValueError and keep the prior catalog | S6 | V5 | self_hosted.py | aws-bedrock-test.py | — |
| AC-6: Bedrock Converse replies are parsed into the OpenAI-shaped response with stopReason mapped end_turn→stop, max_tokens→length, tool_use→tool_calls (others pass through); a reply missing output.message.content raises ValueError naming the model. | S3 | V1, V3 | self_hosted_http.py | aws-bedrock-test.py | LV-1 |
| AC-7 | S8, S9, S10 | V6 | self_hosted.py | aws-bedrock-test.py | — |
| AC-8 | S3 | — | bedrock_protocols.py | protocols-test | — |
| AC-9 | S12 | — | docs | both runners | doc read |

## Implementation sequence

CAP-1 = pure-Python code edits (available). CAP-2 = editing the five Bedrock tests (authorized by request). CAP-3 = live Bedrock token (LIVE_VERIFICATION only).

1. **STEP-1 Converse-only helpers: region validation (strip, no case folding, D2 regex), endpoint builders, legacy region derivation, headers, body/parse, model-list parsing (R-1,R-2; D2,D7)**
   Owns: `scripts/lib/bedrock_protocols.py`
2. **STEP-2 Connection, discovery with pagination (no redirects, any 3xx errors), `settings()` region resolved in the D1 precedence order and validated per D2/D9 (region and api_key from the connection, env first; entries supply only the model ID), token validated per D10, derivation + migration via strict `region_from_url`, delete the Bedrock URL scheme/loopback check and blank cleared connections (D9), shell `profile_menu`, remove `discover_anthropic_models`/`_BEDROCK_COMPAT_NOTICED`/URL check; errors never include token or response body (AC-2..5,7; D1-D5,D8-D10)** — Implement region precedence per D1 (env, stage, shared, connection, legacy URL host fallback used only as the last fallback for exact AWS hosts), with no fall-through from an invalid value to a lower-precedence source; validation per D2 (single regex `{2,}`, trim without case folding, an invalid value from any source raises); and legacy migration per D3. Per-model entries never supply region (D4). Shell `profile_menu` Bedrock branch: blank Region or token input keeps the existing value; Region is validated before any request; on discovery failure neither the connection (including region and token) nor the model catalog is changed, and nothing is saved.
   Owns: `scripts/lib/self_hosted.py`
   Depends on: 1
3. **STEP-3 Transport: `compatible_post` always converse using `runtime_url`, Converse POST via no-redirect opener (3xx is an error, token never forwarded; D9), remove `_require_choices` Bedrock openai branch, skip `capabilities` probe for Bedrock; mode list is exactly `['json_schema']` with no fallback loop, max_tokens unchanged, no reasoning reserve (D10); missing `output.message.content` raises ValueError naming Converse; HTTPError raises the actionable ValueError (AC-1,6)** — Converse POST goes through the single seam `self_hosted_http._request`, so tests patch that name (D6). Converse `parse_response` maps stopReason to finish_reason: end_turn→stop, max_tokens→length, tool_use→tool_calls, any other value passes through unchanged. A reply lacking `output.message.content` raises a ValueError naming the model (and Converse), never an IndexError/KeyError.
   Owns: `scripts/lib/self_hosted_http.py`
   Depends on: 1
4. **STEP-4 TUI: fields `[region, api_key]`, labels, remove `COMPAT_CHOICES`, picker, help text, menu text, refresh on region/token change (AC-2)**
   Owns: `uncle_tui.py`
   Depends on: 2
5. **STEP-5 Update Bedrock tests: patch `self_hosted_http._request` and `_discovery_get`, assert captured url/headers/body; cover repeated nextToken, unsafe model IDs, and a V7 reuse-key test (key identical with and without each temperature source, key changes with region) (R-3,D5,D6,D8)** — Cases enumerated in section 16-17 (items 1-10) are all required; tests patch only `self_hosted_http._request` and `self_hosted._discovery_get`.
   Owns: `scripts/tests/aws-bedrock-test.py`, `scripts/tests/aws-bedrock-protocols-test.py`, `scripts/tests/aws-bedrock-configure-test.py`, `scripts/tests/aws-bedrock-configure-test.sh`, `scripts/tests/aws-bedrock-dispatch-test.sh`
   Depends on: 1, 2, 3, 4
6. **STEP-6 Docs (AC-9)** — Steps 2, 3 and 6 are independent after step 1 (distinct files) and may run in parallel; step 4 builds on step 2's connection shape.
   Owns: `docs/aws-bedrock.md`, `README.md`
   Depends on: 1

## Rollback plan
Revert the change set; no data migration to undo since legacy fields are never deleted and `region` is additive.

## 21. Scope cuts under time pressure

Cut first: README wording, dispatch-test tweaks. Never cut: temperature invariant test, V7 reuse-key test, https-only and no-redirect tests, pagination and page-cap/oversized-page tests, region and token validation tests, migration error message.

## 22. Risks and unresolved questions
- Existing aws-bedrock-test.py uses loopback servers; step 5 must repoint to patched transport (D6). Risk Medium.
- Hidden consumers of Bedrock `base_url` (grep during step 2/3); derived value keeps them working.
- Live Bedrock unverified (CAP-3). No blocking planning decisions remain.

## Adversarial review dispositions

| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Real conflict between spec {2,} and plan {2}; one regex and one invalid-value rule are needed. | D2 sets one regex `{2,}`, trim without case folding, invalid value from any source raises; D1 states the no-fall-through rule. |
| AR-002 | Accepted | Legacy migration precedence was undefined and D3 conflicted with the 'base_url never used' statement. | D3, D1, s7.1, s9.1 and step-2 state one region precedence; legacy base_url is used only as the last fallback for exact AWS hosts. |
| AR-003 | Accepted | Entries storing region/token let stale entries override the connection; the connection must be the single source. | D4 and s1.2.i2 now say region and api_key come from the connection (env first) and entries supply only the model ID. |
| AR-004 | Accepted | The fixed mode list and Converse reply handling were unnamed, so tests and code could disagree. | s1.2.i3 and STEP-3 now fix mode list to [json_schema], no fallback loop, and missing output.message.content raises ValueError naming Converse. |
| AR-005 | Accepted | Discovery edge cases (empty catalog, nextToken handling, 3xx) were unspecified and are real gaps. | Edit D5 and s1.2.i2 to specify empty-catalog error, empty/repeated nextToken, and 3xx-as-error behavior, keeping the prior catalog. |
| AR-006 | Accepted | Precedence of derived base_url and legacy-field handling on save were unstated. | Edit D3 and s1.2.i2/i4 so derived base_url always overrides stored/env values and Configure saves drop legacy base_url and api_compatibility. |
| AR-007 | Accepted | Region source ordering for entries lacking region was unspecified; one explicit ordering removes ambiguity. | Added decision D9 and updated D1/D3/D4 and STEP-2 with the region resolution order and legacy fallback. |
| AR-008 | Accepted | STEP-3 referred to an unnamed fixed mode list; Bedrock modes and cap handling must be explicit. | Added decision D10 and updated STEP-3 to name json_schema as the only mode and pass max_tokens unchanged. |
| AR-009 | Accepted | settings() currently allows http loopback and scheme checks that conflict with V3; the cleared-connection behavior must be explicit. | Added D9 and a Restrictions note amending R-2; step-2 deletes the Bedrock scheme/loopback check and raises missing-region/token on a cleared connection. |
| AR-010 | Accepted | Spec and plan regexes conflict; one rule with trim and no case folding is needed. | Updated D2 to the {2,} regex with strip and no case folding, rejected before any request; step-1 and s7.1 aligned. |
| AR-011 | Accepted | Real gap: blank-input and failed-discovery behavior in the shell Configure menu was unspecified; the existing blank-keeps-old behavior should be preserved explicitly. | STEP-2 now states blank Region/token keeps existing values and a failed discovery changes neither connection, region nor catalog. |
| AR-012 | Accepted | Converse stopReason mapping and missing-content handling were unspecified though _bedrock_native_post depends on parse_response's reason. | STEP-3 and AC-6 now state the stopReason to finish_reason mapping and that missing output.message.content raises ValueError naming the model. |
| AR-013 | Accepted | Legacy base_url is arbitrary today; deriving a region from a non-AWS host would be unsafe, so the parser must be strict. | s1.2.i1 and D3 now require region_from_url to accept only https bedrock(-runtime).<region>.amazonaws.com hosts and pass validate_region. |
| AR-014 | Accepted | A redirect on the Converse POST could forward the bearer token, so the no-redirect rule must cover every Bedrock request. | s1.2.i2/i3, new decision D9 and step-3 now require all Bedrock requests to refuse redirects and treat any 3xx as an error. |
| AR-015 | Accepted | Region merge order and validation point were unspecified; entry base_url must never be read. | Add D9 and edit D4/s7/step-2: merged region validated with validate_region; entry base_url never read. |
| AR-016 | Accepted | Token validation only covered CR/LF and error leakage was unforbidden. | Add D10 and edit s7/step-2: token printable ASCII, no whitespace/control; no error or log includes token or response body. |
| AR-017 | Accepted | A repeated nextToken and unsafe model IDs are real unspecified discovery edge cases. | Edit D5 and D8 to make a repeated nextToken an error and require model IDs to be strings matching a safe pattern. |
| AR-018 | Accepted | Naming the test seam makes the transport tests deterministic and keeps V3 intact. | Edit D6, step-3, step-5 and the test row to patch `self_hosted_http._request` plus a named discovery GET helper and assert captured url, headers and body. |
| AR-019 | Accepted | Region precedence and legacy migration were genuinely unspecified and inconsistent between D1, D3, D4 and the compatibility section. | D1 sets one precedence order; D3, D4 and s9.1 aligned; s7.1 and step-2 updated. |
| AR-020 | Accepted | The spec and D2 regexes conflicted and strip/case/validation points were unstated. | D2 fixes regex, strip-without-lowercase, and validation points; AC-3 tests row aligned. |
| AR-021 | Accepted | The Bedrock mode list was unnamed, so code and tests could disagree on modes and on HTTPError fallback. | s1.2.i3 and step-3 name the mode list exactly [json_schema] with no fallback; an HTTPError raises the actionable ValueError. |
| AR-022 | Accepted | Discovery edge cases were unspecified; each must fail closed and keep the prior catalog. | s1.2.i2, D5 and AC-5 now list the empty union, redirect, oversized page, repeated token and 101st page as errors that keep the prior catalog. |
| AR-023 | Accepted | V7 had no planned test and the reuse key's region dependence was undefined; a test pins both. | Edited s6.1 (reuse key, region), added a block under s5 and extended step-5 with the reuse-key test in aws-bedrock-test.py. |
