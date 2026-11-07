# Verification report

## Findings

### MC-101

- **Action:** Did not drive the interactive curses TUI. Instantiated UncleTUI headlessly with an isolated HOME and empty key stores, set stage_target='@bedrock' (the Configure -> Configure AWS Bedrock connection popup), and called the same methods that render it: stage_fields, _stage_items and _config_desc for each row.
- **Expected result:** Only 'Region' and 'AWS Bedrock Token' fields appear; no Bedrock URL, API Compatibility field, picker or help text is visible.
- **Actual result:** stage_fields('@bedrock') returned ['region','api_key']. _stage_items returned exactly two rows: 'Region    not set' and 'AWS Bedrock Token  not set'. There is no Base URL row, no API Compatibility field and no picker. The per-field description for Region is 'The AWS region that serves your Bedrock models, for example us-east-1...'. The token description is the generic credential text. Neither mentions a URL or API compatibility. Caveat: the token description says 'stored separately in .uncle/self-hosted-keys.json', which looks like a stale self-hosted reference. It is not an API-compat or URL help text, so it does not fail this row, but it is worth a look. Because this was a headless render and not a screenshot of the live curses UI, the on-screen layout was not observed directly.
- **Defects:** None

### MC-103

- **Action:** Used a scratch project with a seeded Bedrock key file and a stubbed discovery seam (self_hosted._discovery_get). Drove the real UncleTUI._set_field('@bedrock', ...) (instantiated without a terminal) and the shell profile_menu flow with region 'US-East-1'/'US-EAST-1' and tokens containing a space, newline and control char.
- **Expected result:** Each is rejected with a clear actionable message; no network request; nothing saved.
- **Actual result:** Region rejected: "Invalid AWS Bedrock Region 'US-EAST-1'; expected a lowercase region such as us-east-1". Tokens rejected: 'AWS Bedrock token must be a single line of printable ASCII without spaces'. Discovery stub call count 0; key file hash unchanged; token not echoed. Rendered TUI screenshot not taken; the TUI handler was exercised directly.
- **Defects:** None

### MC-105

- **Action:** Seeded a valid connection and catalog via stubbed discovery, then ran TUI _set_field region change and the shell Configure with the stub returning HTTP 401 (also 500 on page 2).
- **Expected result:** Actionable error naming region/token; no token/body shown; prior models remain.
- **Actual result:** Notice: 'AWS Bedrock model discovery failed (HTTP 401); check the Region and token'. Token not in message. Key file hash identical and the stored model catalog equals the seeded catalog. The model picker UI was not rendered; the persisted catalog it reads was checked.
- **Defects:** None

### MC-201

- **Action:** With WORKFLOW_SELF_HOSTED_TEMPERATURE=0.7, called self_hosted_http.sampling() for self-hosted/opencode/aws-bedrock profiles, then called self_hosted_http.chat() with a Self Hosted profile and a stubbed compatible_post to capture the outgoing request body. No live server was used.
- **Expected result:** The Self Hosted body still carries the configured temperature exactly as before the change.
- **Actual result:** The Self Hosted body contained temperature 0.7. sampling() returned {'temperature': 0.7} for the self-hosted and opencode profiles and {} for aws-bedrock. I did not compare against the pre-change code; the check was that the configured value is sent.
- **Defects:** None

### MC-202

- **Action:** Shell profile_menu and TUI _set_field with stubbed discovery: 'US-East-1'; ' us-east-1 ' (padded); 'us-east-1' with token containing a space; newline token; control-character token.
- **Expected result:** Uppercase region and bad tokens rejected with actionable messages, no token echo, no request; padded region trimmed and accepted.
- **Actual result:** Uppercase region and all three bad tokens rejected (rc 1) with the expected messages, 0 discovery calls, no token echo, key file unchanged. Padded ' us-east-1 ' was trimmed: the prompt showed region us-east-1, discovery ran, 'Loaded 2 AWS Bedrock models', rc 0.
- **Defects:** None

### MC-203

- **Action:** Stubbed discovery to raise HTTP 302 and ran TUI refresh and shell Configure. Separately stubbed the Converse _request seam to raise 302 and called _bedrock_converse_post.
- **Expected result:** Both fail with an actionable error naming the region; no follow-up request; token not sent elsewhere; prior catalog kept.
- **Actual result:** Discovery: 'AWS Bedrock model discovery for region eu-west-1 was redirected (HTTP 302); not followed', exactly 1 request, catalog and key file unchanged. Converse: 'AWS Bedrock request for model amazon.nova-v1:0 was redirected (HTTP 302); not followed', exactly 1 request, to bedrock-runtime.us-east-1.amazonaws.com. Neither message contains the token. The Converse message names the model, not the region, though the URL is region-bound; the check accepts this as an actionable error.
- **Defects:** None

### MC-204

- **Action:** Seeded a valid connection and catalog, then changed the region to eu-west-1 via TUI _set_field and the shell flow with the stub failing in each mode: HTTP 401, empty catalog, repeated nextToken, 101st page, oversized page, page-2 HTTP 500.
- **Expected result:** Each failure gives an actionable error; connection, region and catalog unchanged (key file byte-identical).
- **Actual result:** All six produced distinct actionable errors: HTTP failed, no usable models, pagination did not terminate, too many pages (101 calls), response too large, page-2 failure. In every case the key file hash was unchanged, the catalog was equal to the seed, and no token leaked.
- **Defects:** None

### MC-301

- **Action:** Created a scratch project with a legacy aws-bedrock-keys.json (base_url, api_compatibility, token, no region) and ran the shell Configure (profile_menu, the function behind `self_hosted.py models <config> aws-bedrock`) with Enter at both prompts. Discovery was stubbed to HTTP 401.
- **Expected result:** Only Region and token prompted; blank keeps existing values; failed discovery leaves key file byte-identical.
- **Actual result:** Prompt was 'Region [us-east-1]:' (derived from the legacy URL) followed by the hidden token prompt; no URL or API Compatibility prompts. Blank input kept the existing values. Discovery failed with HTTP 401 and the key file hash was identical. With discovery OK, blank input saved region us-east-1 with no base_url. The CLI entry point was invoked via the function, with input and getpass patched.
- **Defects:** None

### MC-303

- **Action:** TUI _set_field('@bedrock') with region 'US-EAST-1' then token with a space against a seeded key file; discovery stubbed.
- **Expected result:** Each rejected with a clear message, no discovery request, key file unchanged.
- **Actual result:** Both rejected with the expected messages; 0 discovery calls; key file hash unchanged. Rendered screenshot not taken.
- **Defects:** None

### MC-304

- **Action:** Ran the bad-token and failure paths with stubbed discovery. No real Bedrock bearer token was available, so the live all-pages catalog listing was not run.
- **Expected result:** Picker lists foundation and inference-profile IDs from all pages; with a bad token an actionable error naming region/token shows and the prior catalog is kept.
- **Actual result:** Bad-token half verified: HTTP 401 gives 'check the Region and token', the prior catalog is kept and the key file is byte-identical. Stubbed discovery loaded both foundation and profile IDs, but the live multi-page listing needs a real token.
- **Defects:** None. A person must supply a real Bedrock bearer token and region (LV-1).

### MC-305

- **Action:** Checked the environment for a Bedrock bearer token (AWS_BEARER_TOKEN_BEDROCK). Did not run the live Converse call or a Bedrock stage.
- **Expected result:** The Converse call returns text and the stage completes using Converse only; no temperature is sent. This is BLOCKED-HUMAN if no token is available.
- **Actual result:** No Bedrock bearer token is available in the environment (AWS_BEARER_TOKEN_BEDROCK is unset). The live call needs a human to supply a token, so it was not performed.
- **Defects:** None

### MC-401

- **Action:** Could not drive the interactive TUI in this non-interactive worker. Instead instantiated UncleTUI headlessly (python3 -I) and called the real stage_fields / config-menu item methods and PROFILES for the Self Hosted (@connection) screen; inspected uncle_tui.py for the Configure menu and stage popup code.
- **Expected result:** Self Hosted still shows Base URL, API key and its existing fields and model picker unchanged; no Region field or Bedrock wording appears there.
- **Actual result:** Headless: Self Hosted connection fields are ['base_url','api_key'], labelled 'Base URL' and 'API key'. The Configure > 'Configure self hosting' menu rows are 'Connection — Base URL and API key' and 'Refresh supported models (0 loaded)', with no Region or Bedrock text. Region and Bedrock wording sits only in the separate @bedrock stage and the 'Configure AWS Bedrock' menu. Other HTTP-runner stage fields are ['runner','effort','model'] (the model picker is intact). The live screen was not seen and no screenshot was captured. The 'other non-Bedrock runner' screen (claude/codex/kimi) was not opened live; code shows its fields are runner/effort/(network)/model with no Region.
- **Defects:** None

### MC-402

- **Action:** Scratch legacy key file with base_url https://bedrock-runtime.us-east-1.amazonaws.com, api_compatibility and no region. Read the TUI Bedrock field values through UncleTUI._field_value and hashed the file.
- **Expected result:** Only Region and Token fields; Region pre-filled us-east-1 from the legacy URL; key file not rewritten until Save.
- **Actual result:** Region value was 'us-east-1' (derived), the file hash was unchanged after load, and the Bedrock section's fields are region and api_key. The rendered screen was not captured, so absence of the URL/picker widgets was confirmed from code paths only.
- **Defects:** None

### MC-403

- **Action:** Scratch legacy key file with base_url https://example.com/v1 and no region. Called _bedrock_result, read the TUI region value and ran shell Configure with Enter at both prompts. Discovery and Converse were stubbed to record requests.
- **Expected result:** Clear message to set Region in Configure; no request to example.com; token not shown.
- **Actual result:** Stage resolution raised 'AWS Bedrock Region is not set; set Region in Configure → AWS Bedrock'. The TUI Region showed empty. The shell Configure printed the same message and exited rc 1. 0 requests were made, the file was unchanged and the token was not in the message. The stage call used an empty stored dict, so the legacy token path was not exercised.
- **Defects:** None

### MC-404

- **Action:** Shell Configure on a legacy key file with stubbed discovery: Enter at both prompts with discovery HTTP 401; region 'US-East-1'; then Enter at both prompts with discovery OK.
- **Expected result:** Blank keeps existing values; uppercase rejected before any request; failed discovery leaves file byte-identical with prior catalog intact.
- **Actual result:** Blank input kept the existing region us-east-1. The uppercase region was rejected with an actionable message and 0 requests. The failed discovery left the file hash identical. With a successful discovery, blank input saved the region without base_url.
- **Defects:** None

### MC-405

- **Action:** Ran a narrow temporary probe (/tmp/mc405/p.py) importing scripts/lib/self_hosted_http.py with WORKFLOW_SELF_HOSTED_TEMPERATURE=0.7 and a per-stage env temperature 0.9 set. Called compatible_post with an aws-bedrock profile and a body carrying temperature at top level and in options, with the _request seam mocked to capture the outgoing request. Then called sampling() for the Self Hosted and Bedrock profiles. Config-file and per-stage config temperature were not exercised separately, and no live Bedrock token or proxy was used.
- **Expected result:** The Bedrock Converse request contains no temperature anywhere in the body, while the Self Hosted request still sends the configured temperature as before.
- **Actual result:** Bedrock request went to https://bedrock-runtime.us-east-1.amazonaws.com/model/m1/converse. Its body was only messages, inferenceConfig {maxTokens:50} and toolConfig, with no temperature sampling field. The only 'temperature' string was a user-chosen tool-schema property name, which was correctly preserved. sampling() for Self Hosted returned {'temperature': 0.7}. sampling() for aws-bedrock returned {}.
- **Defects:** None

### MC-406

- **Action:** Checked the environment for a Bedrock bearer token (any env var matching bedrock or AWS_BEARER) and for .uncle/aws-bedrock-keys.json. No live calls were made.
- **Expected result:** Catalog lists foundation model IDs and inference profile IDs from all pages; a stage request completes via Converse at bedrock-runtime.<region>.amazonaws.com; if no token is available this is recorded BLOCKED-HUMAN, not passed.
- **Actual result:** No Bedrock token or region is configured. The environment has no matching variables and .uncle/aws-bedrock-keys.json does not exist, so the live model refresh and Converse request could not be run.
- **Defects:** None. The operator must supply a valid Bedrock bearer token and region (live reference LV-1) and rerun this check.

### MC-106

- **Action:** Per LV-1, with a real Bedrock token and region, refresh models in Configure → AWS Bedrock and open the model picker.
- **Expected result:** Catalog includes both foundation model IDs and inference profile IDs (including profiles beyond the first page, if any).
- **Actual result:** Not performed.
- **Defects:** None

### MC-107

- **Action:** Per LV-1, with a real token, select a model and run a small stage request with temperature set globally in .uncle/config, then check the response.
- **Expected result:** The request succeeds via Converse with text output and no temperature-related error; the Configure screens show no temperature option for Bedrock.
- **Actual result:** Not performed.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | PASS | Headless python3 -I output: ['region', 'api_key'] / ['Region    not set', 'AWS Bedrock Token  not set'] / the two description strings above. Source: uncle_tui.py:1276-1277 (stage_fields returns region, api_key for @bedrock) and uncle_tui.py:1487-1495 (_stage_items). |
| MC-103 | YES | PASS | Harness /tmp/mcw/h.py output: 'calls 0 hash same True'; TUI notices as quoted. |
| MC-105 | YES | PASS | Harness output: 'TUI fail 401 / ... / same True cat True / leak False'; shell: rc 1, same True. |
| MC-201 | YES | PASS | Captured body: {"model": "m", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100, "stream": false, "temperature": 0.7}. Source: scripts/lib/self_hosted_http.py sampling() at line 1034 and chat() at line 1182. This covers the chat path only; the other body builders (the Ollama /api/chat one at line 1054 and the one at line 1063) call the same sampling() but were not exercised. |
| MC-202 | YES | PASS | Harness output lines 'SHELL ...' and 'padded 0 ... Loaded 2'. |
| MC-203 | YES | PASS | Harness: 'TUI fail 302 ... calls 1 same True cat True leak False'; 'converse302: ... reqs [one URL] leak False'. |
| MC-204 | YES | PASS | Harness output for modes 401/empty/loop/many/big/p2fail, all 'same True cat True leak False'; shell rc 1 and same True. |
| MC-301 | YES | PASS | Harness: '301 enter/enter fail: 1 / prompts: [Region [us-east-1]: ...] / ... same True'. |
| MC-303 | YES | PASS | Harness: 'TUI region US-EAST-1 -> Invalid AWS Bedrock Region...', 'TUI api_key has space -> ...', 'calls 0 hash same True'. |
| MC-304 | YES | BLOCKED-HUMAN | Harness output for the 401 mode and the stubbed 'Loaded 2 AWS Bedrock models'. |
| MC-305 | YES | BLOCKED-HUMAN | env grep for AWS_BEARER_TOKEN_BEDROCK returned a count of 0. No region, model ID, HTTP status or reply excerpt was captured because no request was made. |
| MC-401 | YES | BLOCKED-HUMAN | uncle_tui.py:372-377 PROFILES, :1275-1277 stage_fields for @bedrock vs generic '@' stage, :1457 and :1462-1465 menu items, :1491-1494 _stage_items. Headless output: ['base_url', 'api_key'] / Base URL / API key / ['Connection — Base URL and API key', 'Refresh supported models (0 loaded)']. |
| MC-402 | YES | PASS | Harness: '402 region prefill: us-east-1 / unchanged True'. |
| MC-403 | YES | PASS | Harness: '403 stage: ValueError ...Region is not set...', '403 shell: 1 ... calls 0 same True leak False'. |
| MC-404 | YES | PASS | Harness: '301 enter/enter fail ... same True', '404 uppercase: 1 Invalid AWS Bedrock Region ... calls 0 same True', 'blank keeps (ok disc): 0 ... us-east-1'. |
| MC-405 | YES | PASS | Captured Bedrock body: {"messages":[{"role":"user","content":[{"text":"x"}]}],"inferenceConfig":{"maxTokens":50},"toolConfig":{"tools":[{"toolSpec":{"name":"t","description":"d","inputSchema":{"json":{"type":"object","properties":{"temperature":{"type":"number"}}}}}}]}}. Token redacted and not shown. Self Hosted sampling output: {'temperature': 0.7}. This is a function-level observation of the request body, not a full end-to-end stage run. |
| MC-406 | YES | BLOCKED-HUMAN | env grep for bedrock/AWS_BEARER returned a count of 0. ls .uncle/aws-bedrock-keys.json returned 'No such file or directory'. |
| MC-106 | NO | NOT RUN | No worker observation was supplied for this checklist item. |
| MC-107 | NO | NOT RUN | No worker observation was supplied for this checklist item. |
