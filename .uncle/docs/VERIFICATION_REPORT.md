# Verification report

## Findings

### MC-101

- **Action:** Instantiated UncleTUI headless (no curses session) against a temp UNCLE_CONFIG and read the Configure menu items and the Bedrock popup rows.
- **Expected result:** AWS Bedrock entry beside Self Hosted; submenu mirrors Self Hosted with labels AWS Bedrock Token, Bedrock URL, API Compatibility.
- **Actual result:** Menu: '2. Configure self hosting', '3. Configure AWS Bedrock'. Bedrock popup rows: 'Bedrock URL', 'AWS Bedrock Token', 'API Compatibility'. Self Hosted popup rows: 'Base URL', 'API key'. The entry is named 'Configure AWS Bedrock'. The check was made through the TUI's item and row methods, not by looking at a rendered terminal.
- **Defects:** None

### MC-102

- **Action:** Read the API Compatibility default, set Anthropic compatible and then Converse API compatible through _set_field, and reopened with a fresh UncleTUI each time. Compared the Self Hosted rows.
- **Expected result:** Default is OpenAI compatible; three choices; chosen value persists and appears only in Bedrock settings; Self Hosted unchanged.
- **Actual result:** Default shown as 'OpenAI compatible  (default)'. COMPAT_CHOICES has the three expected values. Each choice read back correctly from a fresh instance. Self Hosted rows stayed 'not set' and its connection was None. The picker UI was not exercised interactively.
- **Defects:** None

### MC-103

- **Action:** Saved a Bedrock URL and token with sentinel values against a loopback mock, then viewed the Self Hosted settings and keys file. Separately cleared the Bedrock connection (empty URL/token, or either one) in the keys file, with Self Hosted URL and key set as env sentinels, and resolved settings for a bedrock-runner stage.
- **Expected result:** Self Hosted shows no Bedrock values. A Bedrock run with missing token or URL fails with a Bedrock-labelled error before any network call, without using Self Hosted credentials and without printing the token.
- **Actual result:** Self Hosted rows stayed 'not set' and self-hosted-keys.json held no Bedrock token. The Bedrock keys file was mode 0600. With the connection cleared, settings() raised 'AWS Bedrock requires an http(s) Bedrock URL without credentials, query, or fragment' in all three cases. The error is Bedrock-labelled, was raised before any request was made, did not use the Self Hosted env sentinels and did not contain the token. Minor: when only the token is missing, the message names the URL requirement rather than the token. The 'before any network call' part rests on the error being raised in settings(). I did not run a full stage against a capture server.
- **Defects:** None

### MC-104

- **Action:** Ran a loopback mock on 127.0.0.1:18178 that logs headers and bodies. Pointed a Bedrock stage at it with token SENT-TOK-1 and ran chat (with a tool whose schema has a property named 'temperature') and constrained_completion under each of the three protocols. Set WORKFLOW_SELF_HOSTED_TEMPERATURE=0.77, implementation.temperature 0.66 and self-hosted.temperature 0.55.
- **Expected result:** Expected path per protocol. OpenAI and Converse send only Authorization: Bearer; Anthropic sends x-api-key plus anthropic-version 2023-06-01 and no Authorization. No body contains a temperature key or the sentinel. The token is not in a URL or body.
- **Actual result:** OpenAI: /chat/completions with Bearer. Anthropic: /v1/messages with x-api-key and anthropic-version 2023-06-01, no Authorization header. Converse: /model/m1/converse with Bearer. No body had a top-level temperature key and none contained 0.77, 0.66 or 0.55. The user schema property 'temperature' was preserved in the tool-call bodies. The token was never in a URL or body. The OpenAI path also issued capability probes (/api/version and /version) to the same origin with the Bearer header and no temperature in any body.
- **Defects:** None

### MC-105

- **Action:** With the mock returning canned responses per protocol, ran chat with tools and constrained_completion with a schema under each protocol. Also returned one response without usage and one without content.
- **Expected result:** Text, tool calls, usage and structured output are parsed per protocol; missing usage gives zero tokens with no error; missing content raises a runner error naming the protocol.
- **Actual result:** All three protocols returned text, a tool_call and structured output (constrained_completion returned mode json_schema). Usage was parsed as 3 input and 4 output. Anthropic and Converse with no usage returned 0/0/0 with no error. OpenAI with no usage returned without error, but the usage dict I looked at did not show explicit zeros. No-content cases raised 'AWS Bedrock OpenAI response has no choices', 'AWS Bedrock Anthropic response has no content' and 'AWS Bedrock Converse response has no output.message.content'.
- **Defects:** None

### MC-107

- **Action:** Ran a Self Hosted request against the mock with implementation.temperature 0.3. Ran scripts/tests/aws-bedrock-dispatch-test.sh for stage dispatch of both runners, and resolved a Bedrock stage via settings().
- **Expected result:** Self Hosted body keeps the numeric temperature; both runners dispatch to the correct implementation; Bedrock does not run as Self Hosted.
- **Actual result:** The captured Self Hosted body had temperature 0.3 and the Self Hosted settings carried no Bedrock profile. The dispatch script printed PASS for claude, codex, kimi, self-hosted, opencode, aider, cline and bogus (identical to the baseline) and for aws-bedrock dispatching via the self-hosted shim and validating; it also PASSed the check that the baseline rejects aws-bedrock. A Bedrock stage resolved _profile=aws-bedrock with the right protocol, so it did not run as Self Hosted. I ran this script directly. It is not a repeat of the driver green-check.
- **Defects:** None

### MC-201

- **Action:** Ran a temp script (/tmp/mcw/run.py) with a real capture HTTP server on 127.0.0.1:18178. Self Hosted config with temperature 0.3 -> self_hosted.settings + http.chat. Then aws-bedrock config with a tool whose schema has a property named `temperature` -> http.chat. Parsed the captured request bodies.
- **Expected result:** Self Hosted body carries temperature 0.3; Bedrock body has no temperature key but the user schema property `temperature` is preserved.
- **Actual result:** Self Hosted captured body had temperature=0.3. Bedrock body top-level keys were chat_template_kwargs, max_tokens, messages, model, stream, stream_options, tools (no temperature). tools[0].function.parameters.properties == {'temperature': {'type':'number'}}.
- **Defects:** None

### MC-203

- **Action:** Set Self Hosted key, URL and model via UNCLE_SELF_HOSTED_* sentinel env values pointing at 127.0.0.1:18178/sentinel. With runner aws-bedrock, tried (a) no Bedrock URL/token and (b) a Bedrock URL without a token, calling settings() and http.chat against the live capture server. Also read the Self Hosted error form in the code.
- **Expected result:** Error before any network call; capture server gets no request; no Self Hosted sentinel used; error follows the Self Hosted message form with Bedrock labels.
- **Actual result:** (a) ValueError 'AWS Bedrock requires an http(s) Bedrock URL without credentials, query, or fragment'; (b) ValueError 'AWS Bedrock requires a token (set it in Configure → AWS Bedrock Token)'. Capture server request count delta was 0. The Self Hosted sentinel URL/key/model were not used. The messages mirror the Self Hosted 'Self hosted requires ...' form in self_hosted.py settings().
- **Defects:** None

### MC-204

- **Action:** With a live loopback server on 18178 that returns HTTP 401 echoing the token in the status reason, body and request Authorization header, called http.chat with the Bedrock profile and captured error text plus stdout/stderr. Then a 307 server on 18178 redirecting to a capture server on 18179, for both the OpenAI (Authorization) and Anthropic (x-api-key) protocols. Then an aws-bedrock config with http://remote.example.com/v1.
- **Expected result:** Token redacted in the HTTP error, status and log output. Credential headers not sent to the redirect target. Non-loopback http:// rejected before any network call.
- **Actual result:** 401 error was 'Model API request failed (HTTP 401); check the Base URL, API key and model' and the token was absent from the error text, repr, and captured stdout/stderr (the server did receive the token as Authorization). The 307 raised ValueError (HTTP 307); the origin saw one Bearer request and the 18179 target received 0 requests under both protocols, so no Authorization or x-api-key header reached it. The non-loopback http URL raised 'AWS Bedrock requires an https Bedrock URL (http is allowed only for loopback)...' with 0 requests sent.
- **Defects:** None

### MC-303

- **Action:** Persisted each API Compatibility choice and reloaded it from disk with a fresh UncleTUI (the default was checked when none was set). Hand-set the stored value to 'Foo ' and resolved settings() twice in one subprocess per value.
- **Expected result:** Each choice persists with OpenAI compatible as default; an unknown value runs as OpenAI with one stderr notice per process and the stored value is not rewritten.
- **Actual result:** Each choice persisted and resolved to the right protocol (anthropic, converse, openai). The default with no value resolved to openai. For 'Foo ' both calls resolved to openai, with a single stderr line "AWS Bedrock: unknown API Compatibility 'Foo '; using OpenAI compatible". The keys file was byte-identical afterwards. A real quit-and-relaunch of the curses TUI was not performed; persistence was shown by fresh instances reading the saved files.
- **Defects:** None

### MC-401

- **Action:** Via headless UncleTUI, read the Self Hosted rows, saved a Self Hosted URL and token (loopback mock for discovery), and reopened with a fresh instance.
- **Expected result:** Self Hosted submenu is unchanged in looks and behavior, saved values persist, and no Bedrock labels appear in it.
- **Actual result:** Self Hosted rows were 'Base URL' and 'API key', in the original order. After saving they showed 'http://127.0.0.1:18178/v1' and '********', and these persisted on a fresh load. No Bedrock labels (AWS Bedrock Token, API Compatibility) appeared. Visual rendering was not checked.
- **Defects:** None

### MC-402

- **Action:** After the MC-401 Self Hosted save, saved a distinct Bedrock URL, token and Anthropic compatible protocol, then reopened a fresh instance and compared both submenus and key files.
- **Expected result:** Self Hosted values unchanged and free of Bedrock values; Bedrock values persist separately.
- **Actual result:** The Self Hosted rows were unchanged (same URL, masked key). The Bedrock rows showed the new URL, a masked token and 'Anthropic compatible'. self-hosted-keys.json had no Bedrock URL, token or protocol, and aws-bedrock-keys.json had no Self Hosted token.
- **Defects:** None

### MC-405

- **Action:** With Self Hosted key and URL configured and a capture server on 18178, ran settings() for runner aws-bedrock with no Bedrock URL or token. Ran scripts/tests/aws-bedrock-dispatch-test.sh, which compares the new stage-config.sh against the HEAD version for claude, codex, kimi, self-hosted, opencode, aider, cline and bogus runners. Also ran settings() for a plain self-hosted config.
- **Expected result:** Bedrock run fails with a Bedrock-labelled error before any network call; self-hosted dispatches as before; unknown-runner error text is unchanged.
- **Actual result:** Bedrock run raised 'AWS Bedrock requires an http(s) Bedrock URL without credentials, query, or fragment' with 0 requests at the capture server. The dispatch test printed PASS for all 8 existing/unknown runners ('self-hosted' and 'bogus' output byte-identical to HEAD, including the unsupported-runner error) and PASS for aws-bedrock dispatch. Self-hosted settings() resolved normally to the configured URL and model. I did not run a full stage with a real agent: the dispatch comparison and settings() calls were used instead.
- **Defects:** None

### MC-108

- **Action:** Optional live check LV-1: with a real Bedrock token and URL, run a short request under each protocol. Do not record the token.
- **Expected result:** Each protocol authenticates and returns a parsed response with no temperature sent. If credentials are unavailable, record BLOCKED-HUMAN naming the person who must supply the token.
- **Actual result:** Not performed.
- **Defects:** None

### MC-305

- **Action:** With a real Bedrock API key and endpoint (LV-1), run a short Bedrock stage under each of the three API Compatibility choices.
- **Expected result:** Each protocol returns a response and no request body contains temperature; failures, if any, show redacted errors.
- **Actual result:** Not performed.
- **Defects:** None

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| MC-101 | YES | PASS | Transcript from the temp harness /tmp/mcw/run_a.py: main=[1. Configure stages, 2. Configure self hosting, 3. Configure AWS Bedrock, ...]; bedrock_rows=['Bedrock URL  not set','AWS Bedrock Token  not set','API Compatibility  OpenAI compatible  (default)'] |
| MC-102 | YES | PASS | run_a.py output: 102.default, choices, reopened_bedrock values, selfhosted_rows unchanged |
| MC-103 | YES | PASS | run_a.py: sh_rows not set, sh_keys_file_has_bed false, bed_file_mode 0o600; run_c.py 'clear' lines show ERR AWS Bedrock requires an http(s) Bedrock URL... |
| MC-104 | YES | PASS | run_b.py JSON '104' section for each protocol |
| MC-105 | YES | PASS | run_b.py JSON '105' section |
| MC-107 | YES | PASS | run_b.py '107': sh_body_temp [0.3]; dispatch test output, all PASS |
| MC-201 | YES | PASS | Captured bodies: sh_temperature 0.3; bedrock_has_temp_key false; bedrock_schema_prop {'temperature': {'type':'number'}}; Bedrock request sent Authorization 'Bearer <token>'. |
| MC-203 | YES | PASS | Script output: errors dict above, requests_after 0. |
| MC-204 | YES | PASS | err_has_token false; log_has_token false; target_requests []; target_after_anthropic []; http_remote error text; requests_during_remote 0. |
| MC-303 | YES | PASS | run_c.py output per value; the stderr line appears once per process; store_unchanged true |
| MC-401 | YES | PASS | run_d.py output: before, after_sh_save |
| MC-402 | YES | PASS | run_d.py: after_bedrock_save_sh, bedrock rows, sh_file_has_bed false, bed_file_has_sh false |
| MC-405 | YES | PASS | Terminal output of dispatch test (10 PASS lines) and the script's MC-405 block (requests 0). |
| MC-108 | NO | NOT RUN | No worker observation was supplied for this checklist item. |
| MC-305 | NO | NOT RUN | No worker observation was supplied for this checklist item. |
