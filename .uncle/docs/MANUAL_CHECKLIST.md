# Manual checklist

## Coverage

### MC-101
- Required for acceptance: YES
- Exclusive resources: file:uncle-config-dir
- Depends on: none
- Exact action: Launch the Uncle TUI and open the main menu, then open the AWS Bedrock entry and its submenu.
- Expected result: An AWS Bedrock entry appears beside Self Hosted. Its submenu mirrors the Self Hosted choices, with labels `AWS Bedrock Token`, `Bedrock URL` and `API Compatibility`.
- Evidence to capture: Terminal screenshot or transcript of the main menu and the Bedrock submenu.
- Actual result: 
- Status: NOT RUN

### MC-102
- Required for acceptance: YES
- Exclusive resources: file:uncle-config-dir
- Depends on: MC-101
- Exact action: In the Bedrock submenu open API Compatibility, note the default, pick Anthropic compatible, leave and reopen the menu. Then repeat with Converse API compatible.
- Expected result: The default is OpenAI compatible. The three choices are OpenAI, Anthropic and Converse. The chosen value persists across reopening and appears only in Bedrock settings, with Self Hosted settings unchanged.
- Evidence to capture: Screenshots of the default, each selection and the reopened menu, plus the Self Hosted settings screen before and after.
- Actual result: 
- Status: NOT RUN

### MC-103
- Required for acceptance: YES
- Exclusive resources: file:uncle-config-dir
- Depends on: MC-101
- Exact action: Save a distinct token and URL in the Bedrock submenu using sentinel values. Open the Self Hosted settings. Then clear the Bedrock token and URL and try a Bedrock-selected stage run.
- Expected result: Self Hosted shows none of the Bedrock values. The Bedrock run with missing token or URL fails with a Bedrock-labelled error before any network call. It does not use Self Hosted credentials and does not print the token.
- Evidence to capture: Transcript of the settings screens and the error text.
- Actual result: 
- Status: NOT RUN

### MC-104
- Required for acceptance: YES
- Exclusive resources: file:uncle-config-dir
- Depends on: none
- Exact action: Run a local mock HTTP server on loopback that logs full request headers and bodies. Point Bedrock at it with a sentinel token, then run one request under each of OpenAI, Anthropic and Converse. Set a sentinel in the Self Hosted temperature env var and in the stage temperature setting before the runs.
- Expected result: Each protocol hits the expected path. OpenAI and Converse send only `Authorization: Bearer`. Anthropic sends `x-api-key` plus `anthropic-version: 2023-06-01` and no Authorization header. No body contains `temperature` or the sentinel. The token is not in any URL or body.
- Evidence to capture: The mock server's captured request log for the three protocols.
- Actual result: 
- Status: NOT RUN

### MC-105
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-104
- Exact action: With the mock server from MC-104 returning canned responses, run a schema-constrained request and a tool-call request under each protocol. Also return one response with no usage field and one with no content.
- Expected result: Text, tool calls, usage and structured output are parsed per protocol. Missing usage yields zero tokens without error. Missing content raises a runner error that names the protocol.
- Evidence to capture: Run output for each protocol and error case.
- Actual result: 
- Status: NOT RUN

### MC-107
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: MC-104
- Exact action: Run a Self Hosted request against the mock server with a temperature setting configured. Then run a Bedrock stage and a Self Hosted stage through the normal stage dispatch.
- Expected result: The Self Hosted body still carries the numeric temperature. Both runners dispatch to the correct implementation. Bedrock does not silently run as Self Hosted.
- Evidence to capture: The captured Self Hosted body and the dispatch output for each runner.
- Actual result: 
- Status: NOT RUN

### MC-108
- Required for acceptance: NO
- Exclusive resources: none
- Depends on: none
- Exact action: Optional live check LV-1: with a real Bedrock token and URL, run a short request under each protocol. Do not record the token.
- Expected result: Each protocol authenticates and returns a parsed response with no temperature sent. If credentials are unavailable, record BLOCKED-HUMAN naming the person who must supply the token.
- Evidence to capture: Redacted run output for each protocol, or the BLOCKED-HUMAN note.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-201
- Required for acceptance: YES
- Exclusive resources: port:18178
- Depends on: none
- Exact action: Run the same capture with the Self Hosted runner, with its temperature set to a known value such as 0.3. Then run a Bedrock request whose tool schema has a user property literally named `temperature`.
- Expected result: The Self Hosted body still carries temperature 0.3. The Bedrock body has no temperature key, but the user schema property named `temperature` is preserved.
- Evidence to capture: The captured Self Hosted body and the captured Bedrock body.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: port:18178
- Depends on: none
- Exact action: Set Self Hosted key, URL and env to sentinel values. Clear the Bedrock token or URL, then start a stage with the aws-bedrock runner against a capture server.
- Expected result: The run errors before any network call. The capture server receives no request and no Self Hosted sentinel is used, and the error follows the Self Hosted message form with Bedrock labels.
- Evidence to capture: The error text and the capture server's empty request log.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: port:18178, port:18179
- Depends on: none
- Exact action: Point Bedrock at a loopback server that returns an HTTP error echoing the token, then at a server that redirects to a different origin. Also try an `http://` non-loopback URL.
- Expected result: The token is redacted in the HTTP error, status and log output. Credential headers are not sent to the redirect target, and the non-loopback `http://` URL is rejected before any network call.
- Evidence to capture: The error and log text, and the second origin's request log showing no Authorization or x-api-key header.
- Actual result: 
- Status: NOT RUN

## Protocol persistence

### MC-303
- Required for acceptance: YES
- Exclusive resources: file:uncle-config-dir
- Depends on: none
- Exact action: In the TUI choose each API Compatibility option, quit and relaunch, then reopen the Bedrock submenu; then hand-edit the stored value to an unknown string such as 'Foo ' and start a Bedrock stage twice in one process.
- Expected result: Each choice persists across relaunch with OpenAI compatible as default; the unknown value runs as OpenAI with one stderr notice naming it per process and the stored value is not rewritten.
- Evidence to capture: Submenu screenshots after relaunch, stderr notice text, and the stored value after the run.
- Actual result: 
- Status: NOT RUN

## Live endpoint

### MC-305
- Required for acceptance: NO
- Exclusive resources: file:uncle-config-dir
- Depends on: none
- Exact action: With a real Bedrock API key and endpoint (LV-1), run a short Bedrock stage under each of the three API Compatibility choices.
- Expected result: Each protocol returns a response and no request body contains temperature; failures, if any, show redacted errors.
- Evidence to capture: Non-secret stage output per protocol; record BLOCKED-HUMAN if no credentials are available.
- Actual result: 
- Status: NOT RUN

## Regressions

### MC-401
- Required for acceptance: YES
- Exclusive resources: file:uncle-config-dir
- Depends on: none
- Exact action: In the TUI, open the main menu, then the Self Hosted submenu; set a Self Hosted token/URL and save, reopen the menu and confirm values persist; confirm the AWS Bedrock entry has not altered Self Hosted labels or ordering of its choices.
- Expected result: Self Hosted entry and submenu look and behave as before, saved Self Hosted token/URL persist, and no Bedrock labels (AWS Bedrock Token, API Compatibility) appear in Self Hosted.
- Evidence to capture: Screen captures or transcript of main menu, Self Hosted submenu before and after saving.
- Actual result: 
- Status: NOT RUN

### MC-402
- Required for acceptance: YES
- Exclusive resources: file:uncle-config-dir
- Depends on: MC-401
- Exact action: Save a distinct Bedrock token, URL and API Compatibility choice in the AWS Bedrock submenu, then reopen the Self Hosted submenu and view its token, URL and settings.
- Expected result: Self Hosted values are unchanged and show none of the Bedrock token, URL or protocol; Bedrock values persist separately.
- Evidence to capture: Screens of both submenus showing differing stored values (token masked).
- Actual result: 
- Status: NOT RUN

### MC-405
- Required for acceptance: YES
- Exclusive resources: port:18178
- Depends on: none
- Exact action: Run a stage with runner aws-bedrock with its Bedrock token or URL unset while Self Hosted token and URL are configured, with a capture server listening; then run a stage with an existing runner (self-hosted) and with an unknown runner name.
- Expected result: The Bedrock run fails with a Bedrock-labelled error before any network call and the capture server sees no request; the self-hosted run dispatches as before; the unknown runner error text is the same as before the change.
- Evidence to capture: Terminal output of the three runs and the capture server request log.
- Actual result: 
- Status: NOT RUN
