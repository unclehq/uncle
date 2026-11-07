# Manual checklist

## Configure UI

### MC-101
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Open the TUI, go to Configure → AWS Bedrock, and observe the fields and pickers shown.
- Expected result: Only 'Region' and 'AWS Bedrock Token' fields appear; no Bedrock URL, API Compatibility field, picker or help text is visible.
- Evidence to capture: Screenshot or terminal capture of the Configure → AWS Bedrock screen.
- Actual result: 
- Status: NOT RUN

## Validation

### MC-103
- Required for acceptance: YES
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: In the TUI Configure → AWS Bedrock, enter an uppercase or malformed region such as 'US-East-1' and a token containing a space, then save.
- Expected result: Each is rejected with a clear actionable message; no network request is made and nothing is saved.
- Evidence to capture: Screenshot of the error messages and unchanged key file.
- Actual result: 
- Status: NOT RUN

## Discovery failure

### MC-105
- Required for acceptance: YES
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: With an invalid or revoked token and a valid region set, trigger Refresh models in Configure → AWS Bedrock after a prior catalog exists.
- Expected result: An actionable error naming region/token appears (no token or response body shown) and the previously listed models remain in the picker.
- Evidence to capture: Screenshot of the error and the model picker still listing prior models.
- Actual result: 
- Status: NOT RUN

## Live discovery

### MC-106
- Required for acceptance: NO
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: Per LV-1, with a real Bedrock token and region, refresh models in Configure → AWS Bedrock and open the model picker.
- Expected result: Catalog includes both foundation model IDs and inference profile IDs (including profiles beyond the first page, if any).
- Evidence to capture: Screenshot of the picker listing and count of each ID kind; region and model IDs only, no token.
- Actual result: 
- Status: NOT RUN

## Live Converse

### MC-107
- Required for acceptance: NO
- Exclusive resources: none
- Depends on: none
- Exact action: Per LV-1, with a real token, select a model and run a small stage request with temperature set globally in .uncle/config, then check the response.
- Expected result: The request succeeds via Converse with text output and no temperature-related error; the Configure screens show no temperature option for Bedrock.
- Evidence to capture: Stage output excerpt and region/model ID used; no token.
- Actual result: 
- Status: NOT RUN

## Invariants

### MC-201
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run a Self Hosted stage request with temperature configured and capture its outgoing body.
- Expected result: The Self Hosted body still carries the configured temperature exactly as before the change.
- Evidence to capture: Captured Self Hosted request body showing temperature.
- Actual result: 
- Status: NOT RUN

### MC-202
- Required for acceptance: YES
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: Via Configure → AWS Bedrock (shell and TUI), enter region 'US-East-1', then ' us-east-1 ', then 'us-east-1' with a token containing a space, then a multi-line/control-character token; observe each result and any network activity.
- Expected result: Uppercase region and bad tokens are rejected with actionable messages that do not echo the token and send no request; the whitespace-padded region is trimmed and accepted.
- Evidence to capture: Screen/terminal output of each attempt and confirmation that no request was made.
- Actual result: 
- Status: NOT RUN

### MC-203
- Required for acceptance: YES
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: With a stub discovery returning an HTTP 302 redirect (and separately a 302 on a Converse POST), run Refresh models and a Bedrock stage request; observe errors and any second request.
- Expected result: Both fail with an actionable error naming the region; no request follows the redirect and the token is never sent elsewhere; prior catalog is kept.
- Evidence to capture: Error text and request log showing a single request each.
- Actual result: 
- Status: NOT RUN

### MC-204
- Required for acceptance: YES
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: Seed a valid connection and catalog, then in Configure → AWS Bedrock change region and token while discovery is stubbed to fail (HTTP error, empty catalog, repeated nextToken, 101st page, oversized page, page-2 failure); afterwards view the key file bytes and model picker.
- Expected result: Each failure shows an actionable error, and the connection, region and catalog are unchanged (key file byte-identical).
- Evidence to capture: Key file hash before and after plus error text for each failure case.
- Actual result: 
- Status: NOT RUN

## Resources

### MC-301
- Required for acceptance: YES
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: Create a scratch project with a legacy .uncle/aws-bedrock-keys.json (base_url, api_compatibility, token, no region), run the shell Configure for AWS Bedrock (`python3 scripts/lib/self_hosted.py models <config> aws-bedrock`), and press Enter at the Region and token prompts.
- Expected result: Only Region and AWS Bedrock Token are prompted (no URL or API Compatibility); blank input keeps existing values, and when discovery fails the key file stays byte-identical.
- Evidence to capture: Terminal transcript of prompts plus the key-file checksum before and after.
- Actual result: 
- Status: NOT RUN

### MC-303
- Required for acceptance: YES
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: In the TUI Configure → AWS Bedrock, enter an invalid Region ('US-EAST-1'), then a token containing a space, then try to save each.
- Expected result: Each value is rejected with a clear message and no discovery request is made; the stored key file is unchanged.
- Evidence to capture: Screenshot of the error messages and key-file checksum before and after.
- Actual result: 
- Status: NOT RUN

### MC-304
- Required for acceptance: YES
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: With a valid-format Region and a real Bedrock bearer token (when available), run Configure refresh, then open the model picker.
- Expected result: The picker lists both foundation model IDs and inference profile IDs from all pages; with a bad token an actionable error naming region/token shows and the prior catalog is kept.
- Evidence to capture: Picker contents (model IDs only, no token) and the error text from a bad-token attempt.
- Actual result: 
- Status: NOT RUN

### MC-305
- Required for acceptance: YES
- Exclusive resources: none
- Depends on: none
- Exact action: Run the CHANGE_REQUEST LV-1 curl reference against bedrock-runtime.<region>.amazonaws.com Converse with a chosen model, then run one Bedrock-configured stage with temperature set in config and env.
- Expected result: The Converse call returns text and the stage completes using Converse only; no temperature is sent. This is BLOCKED-HUMAN if no token is available.
- Evidence to capture: Region, model ID, HTTP status and reply excerpt (never the token).
- Actual result: 
- Status: NOT RUN

### MC-401
- Exclusive resources: none
- Depends on: none
- Exact action: In the interactive TUI, open Configure for the Self Hosted (OpenCode) runner and observe its fields, then open Configure for another non-Bedrock runner.
- Expected result: Self Hosted still shows Base URL, API key and its existing fields and model picker unchanged; no Region field or Bedrock wording appears there.
- Evidence to capture: Screenshot or terminal capture of the Self Hosted Configure screen and the other runner's screen.
- Actual result: 
- Status: NOT RUN

### MC-402
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: In the TUI, open Configure → AWS Bedrock with a legacy key file containing base_url and api_compatibility but no region (base_url an exact https bedrock-runtime.us-east-1.amazonaws.com host), and view the fields.
- Expected result: Only Region and AWS Bedrock Token appear, with no Bedrock URL, API Compatibility field or picker; Region is pre-filled with us-east-1 derived from the legacy URL, and the key file is not rewritten until Save.
- Evidence to capture: Screenshot of the field list and a before/after hash of .uncle/aws-bedrock-keys.json.
- Actual result: 
- Status: NOT RUN

### MC-403
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: Using a legacy Bedrock key file whose base_url is a non-AWS host (e.g. https://example.com/v1) and no region, start a stage or open Configure → AWS Bedrock and attempt to use it.
- Expected result: A clear message tells the user to set Region in Configure → AWS Bedrock; no network request is made to example.com and the token is not shown in the message.
- Evidence to capture: Terminal capture of the message and confirmation that no request was sent.
- Actual result: 
- Status: NOT RUN

### MC-404
- Exclusive resources: file:.uncle/aws-bedrock-keys.json
- Depends on: none
- Exact action: In the shell Configure flow for AWS Bedrock, press Enter on Region and token prompts leaving existing values, then enter a changed Region with an invalid value (e.g. US-East-1) and then a valid region that fails discovery.
- Expected result: Blank input keeps existing values; the uppercase region is rejected with an actionable message before any request; a failed discovery leaves the key file byte-identical and the prior model catalog intact.
- Evidence to capture: Terminal transcript and before/after checksum of .uncle/aws-bedrock-keys.json.
- Actual result: 
- Status: NOT RUN

### MC-405
- Exclusive resources: none
- Depends on: none
- Exact action: Set a temperature in config, per-stage config and via env, then run a Bedrock stage (live token if available, otherwise observe the outgoing request through the available request log or proxy) and also run one Self Hosted stage with the same temperature.
- Expected result: The Bedrock Converse request contains no temperature anywhere in the body, while the Self Hosted request still sends the configured temperature as before.
- Evidence to capture: Captured request bodies for both runners with token redacted.
- Actual result: 
- Status: NOT RUN

### MC-406
- Exclusive resources: none
- Depends on: none
- Exact action: With a valid Bedrock token and region (live reference per LV-1), run Configure → AWS Bedrock model refresh and select a model, including an inference profile ID containing ':'.
- Expected result: Catalog lists both foundation model IDs and inference profile IDs from all pages; a stage request completes via Converse at bedrock-runtime.<region>.amazonaws.com; if no token is available this is recorded BLOCKED-HUMAN, not passed.
- Evidence to capture: Model list excerpt and stage output with region and model ID only; no token.
- Actual result: 
- Status: NOT RUN
