## AR-001: Region regex conflicts: spec S7 says {2,}, plan D2 says {2}.

- Severity: HIGH
- References: CHANGE_SPEC S7 vs CHANGE_PLAN D2; D1 precedence (self_hosted.py:300).
- Failure: Region regex conflicts: spec S7 says {2,}, plan D2 says {2}. Trim/case handling and invalid-region precedence across env/stage/shared config are unspecified. Plan should say: 'Region is trimmed, lowercased and validated against one regex; an invalid value from any source raises ValueError, never falling through.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-002: Legacy migration precedence is undefined: D3 derives region from legacy base_url while S9/AC-7 say base_url is never use

- Severity: HIGH
- References: CHANGE_PLAN D3/D4, AC-7; settings() self_hosted.py:299-316.
- Failure: Legacy migration precedence is undefined: D3 derives region from legacy base_url while S9/AC-7 say base_url is never used. Plan should say: 'Region precedence: env, stage, shared config, stored connection region, then region_from_url(legacy base_url) only for bedrock(-runtime).<region>.amazonaws.com hosts; else raise the Set Region error.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-003: Unspecified whether region/token at request time come from the connection or per-model entries; D4 stores region per ent

- Severity: HIGH
- References: self_hosted.py:306-312; CHANGE_PLAN D4.
- Failure: Unspecified whether region/token at request time come from the connection or per-model entries; D4 stores region per entry and settings() prefers entry values, so stale entries could be used. Plan should say: 'Region and api_key come from the connection (env first), never per-model entries; entries supply only the model ID.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-004: Skipping the capabilities probe leaves the Bedrock mode list undefined; Converse replies lacking content or with stopRea

- Severity: MEDIUM
- References: self_hosted_http.py:1081-1095; CHANGE_PLAN section 1; CHANGE_SPEC section 8.
- Failure: Skipping the capabilities probe leaves the Bedrock mode list undefined; Converse replies lacking content or with stopReason max_tokens are unspecified. Plan should say: 'Bedrock uses one json_schema mode via Converse; missing output.message.content raises ValueError naming Converse; no rejected-mode fallback loop.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-005: Discovery edge cases are unspecified: empty union catalog, empty or repeated nextToken, and 3xx responses.

- Severity: MEDIUM
- References: CHANGE_PLAN D5, D8, section 1; AC-4/AC-5.
- Failure: Discovery edge cases are unspecified: empty union catalog, empty or repeated nextToken, and 3xx responses. Plan should say: 'An empty catalog is an error keeping the prior catalog; empty nextToken ends pagination and a repeated one errors; any 3xx is an error naming region.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-006: settings() still exposes base_url though the spec removes it; precedence of env/stored base_url vs derived value, and wh

- Severity: LOW
- References: CHANGE_PLAN sections 8-9 vs D3; CHANGE_SPEC section 7.
- Failure: settings() still exposes base_url though the spec removes it; precedence of env/stored base_url vs derived value, and whether saving drops legacy fields, are unspecified. Plan should say: 'Derived base_url always overrides any stored or env value; saving in Configure drops legacy base_url and api_compatibility.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-007: Plan never orders region sources for a stored model entry lacking region (legacy).

- Severity: HIGH
- References: self_hosted.py:307-316 takes base_url from the profile entry; D1/D3/D4 give no precedence among entry, connection, config and env.
- Failure: Plan never orders region sources for a stored model entry lacking region (legacy). Add: 'settings() resolves region as env, stage config, aws-bedrock config, entry.region, connection.region, then region_from_url(legacy base_url); else raises the D3 error.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-008: Plan removes the openai branch but never says which constrained modes Bedrock uses or how Converse treats ANSWER_CAP.

- Severity: HIGH
- References: self_hosted_http.py:163-178 and :1081-1088; STEP-3 says 'fixed mode list' without naming it.
- Failure: Plan removes the openai branch but never says which constrained modes Bedrock uses or how Converse treats ANSWER_CAP. Add: 'Bedrock uses only json_schema mode; ollama/vllm/json_object are never tried; max_tokens passes unchanged, with no reasoning reserve.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-009: Plan does not say whether settings() keeps the scheme/loopback URL check, which conflicts with V3, or how a cleared conn

- Severity: MEDIUM
- References: self_hosted.py:310-312 (cleared connection) and :322-323 (http loopback allowed) versus V3/R-2.
- Failure: Plan does not say whether settings() keeps the scheme/loopback URL check, which conflicts with V3, or how a cleared connection behaves. Add: 'Bedrock deletes the URL scheme/loopback check; empty connection region or token blanks both and raises the missing-region or missing-token error.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-010: Spec S7 regex `[a-z]{2,}` conflicts with plan D2 `[a-z]{2}`; trim and case rules are unstated.

- Severity: MEDIUM
- References: CHANGE_SPEC S7 versus CHANGE_PLAN D2.
- Failure: Spec S7 regex `[a-z]{2,}` conflicts with plan D2 `[a-z]{2}`; trim and case rules are unstated. Add: 'Region is trimmed and matched against D2's regex with no case folding; empty or uppercase is rejected before any request.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-011: Plan is silent on blank Region/token input in shell profile_menu and on a region change whose discovery fails.

- Severity: MEDIUM
- References: self_hosted.py:2036-2043 blank-keeps-old behaviour; plan only says 'commits only on success'.
- Failure: Plan is silent on blank Region/token input in shell profile_menu and on a region change whose discovery fails. Add: 'Blank input keeps the existing value; on discovery failure neither connection nor catalog changes, including region.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-012: Converse stopReason to finish_reason mapping and a reply without output.message.content are unspecified.

- Severity: LOW
- References: _bedrock_native_post (self_hosted_http.py:204-224) depends on parse_response reason; AC-6 only says 'parse'.
- Failure: Converse stopReason to finish_reason mapping and a reply without output.message.content are unspecified. Add: 'end_turn→stop, max_tokens→length, tool_use→tool_calls, others pass through; missing content raises ValueError naming the model.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-013: Legacy region_from_url on an arbitrary base_url could derive a region from a non-AWS host.

- Severity: HIGH
- References: CHANGE_PLAN D3 and s1.2.i1; self_hosted.py:318-323 currently allows arbitrary hosts.
- Failure: Legacy region_from_url on an arbitrary base_url could derive a region from a non-AWS host. Plan should say: region_from_url accepts only https hosts exactly matching bedrock(-runtime).<region>.amazonaws.com, and the result must pass validate_region.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-014: No-redirect rule is stated only for discovery; the Converse POST via _request has no redirect policy, so a 3xx could for

- Severity: HIGH
- References: CHANGE_PLAN s1.2.i2 (discovery only); s1.2.i3 reuses _request (self_hosted_http.py:216).
- Failure: No-redirect rule is stated only for discovery; the Converse POST via _request has no redirect policy, so a 3xx could forward the bearer token. Plan should say: all Bedrock requests refuse redirects and treat 3xx as an error.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-015: Region precedence and validation point are unspecified when stored entry region, config and env differ.

- Severity: MEDIUM
- References: CHANGE_PLAN D1/D4; self_hosted.py:307-316 merges entry fields with env overrides.
- Failure: Region precedence and validation point are unspecified when stored entry region, config and env differ. Plan should say: the final region is merged (env > stage > shared > entry), then validated with validate_region, and entry base_url is never read.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-016: Token validation covers only CR/LF, and token or response-body leakage in errors is not forbidden.

- Severity: MEDIUM
- References: CHANGE_SPEC V4/S7; self_hosted.py:326-327 checks only newline characters.
- Failure: Token validation covers only CR/LF, and token or response-body leakage in errors is not forbidden. Plan should say: token must be non-empty printable ASCII without whitespace or control characters, and no error or log may include the token or response body.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-017: Discovery handling of a repeated nextToken and malformed model IDs is unspecified.

- Severity: LOW
- References: CHANGE_PLAN D5 (page cap only); D8 filters whitespace and # only.
- Failure: Discovery handling of a repeated nextToken and malformed model IDs is unspecified. Plan should say: a repeated nextToken is an error and model IDs must be strings matching a safe pattern before storage or use in URLs.
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-018: D6 says tests patch `_request`/urlopen but never names the seam for discovery GETs or Converse capture.

- Severity: HIGH
- References: CHANGE_PLAN D6, R-3; self_hosted_http.py:216 calls _request(url, token, native, timeout, headers=...). The discovery GET transport is unnamed.
- Failure: D6 says tests patch `_request`/urlopen but never names the seam for discovery GETs or Converse capture. Settle: 'Tests patch one named seam, `self_hosted_http._request`, plus a named discovery GET helper, and assert captured url, headers and body.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-019: Region precedence and migration are unspecified.

- Severity: HIGH
- References: CHANGE_PLAN D1, D3, D4, Compatibility; settings() at self_hosted.py:299-316 merges env, stage, entry and connection values in a different order.
- Failure: Region precedence and migration are unspecified. D3 raises ValueError for legacy configs without a region while 'Legacy files read' says they work. Settle: 'Region precedence is env, then stage key, then aws-bedrock.region, then connection region, then entry region, then region_from_url(legacy base_url), else ValueError; a stale base_url is ignored when any region exists.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-020: The region regex differs between spec (`[a-z]{2,}`) and plan D2 (`[a-z]{2}`).

- Severity: MEDIUM
- References: CHANGE_SPEC S7 vs CHANGE_PLAN D2; AC-3 verification.
- Failure: The region regex differs between spec (`[a-z]{2,}`) and plan D2 (`[a-z]{2}`). Whitespace, case, empty value, and where validation fires are unspecified. Settle: 'Region is stripped, not lowercased, and matched against D2's regex; empty or invalid is rejected at TUI save, shell save and settings() with no network call.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-021: The 'fixed mode list' for Bedrock in constrained_completion is never named.

- Severity: MEDIUM
- References: CHANGE_PLAN section 1 (skips capabilities probe); self_hosted_http.py:1081-1094 (caps['modes'], REJECTED).
- Failure: The 'fixed mode list' for Bedrock in constrained_completion is never named. Tests and code may disagree on modes and on HTTPError fallback. Settle: 'Bedrock mode list is exactly [json_schema], with no fallback; an HTTPError raises the actionable ValueError.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-022: Discovery edge cases are unspecified: an empty catalog, a repeated nextToken, an oversized page, a redirect, and the 101

- Severity: MEDIUM
- References: CHANGE_PLAN section 1 and D5; AC-5 lists only HTTP, network, malformed JSON and page-2 failure.
- Failure: Discovery edge cases are unspecified: an empty catalog, a repeated nextToken, an oversized page, a redirect, and the 101st page. Settle: 'An empty union, redirect, oversized page, repeated token or 101st page raises an actionable ValueError and keeps the prior catalog.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## AR-023: V7 (temperature must not alter reuse keys) has no planned test and the reuse key is undefined for region.

- Severity: MEDIUM
- References: CHANGE_SPEC V7; CHANGE_PLAN R-1 says 'verify only' for self_hosted_performance.py.
- Failure: V7 (temperature must not alter reuse keys) has no planned test and the reuse key is undefined for region. Settle: 'aws-bedrock-test.py asserts the reuse key is identical with and without each temperature source and includes region.'
- Fix: Address in the plan.
- Verify: Re-run the check.

## Overall assessment

Review findings require disposition.
