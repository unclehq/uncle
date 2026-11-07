# Defects

## None. A person must supply a real Bedrock bearer token and region (LV-1).

- **Status:** BLOCKED-HUMAN
- **Evidence:** Harness output for the 401 mode and the stubbed 'Loaded 2 AWS Bedrock models'.
- **Expected result:** Picker lists foundation and inference-profile IDs from all pages; with a bad token an actionable error naming region/token shows and the prior catalog is kept.
- **Actual result:** Bad-token half verified: HTTP 401 gives 'check the Region and token', the prior catalog is kept and the key file is byte-identical. Stubbed discovery loaded both foundation and profile IDs, but the live multi-page listing needs a real token.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** env grep for AWS_BEARER_TOKEN_BEDROCK returned a count of 0. No region, model ID, HTTP status or reply excerpt was captured because no request was made.
- **Expected result:** The Converse call returns text and the stage completes using Converse only; no temperature is sent. This is BLOCKED-HUMAN if no token is available.
- **Actual result:** No Bedrock bearer token is available in the environment (AWS_BEARER_TOKEN_BEDROCK is unset). The live call needs a human to supply a token, so it was not performed.

## None

- **Status:** BLOCKED-HUMAN
- **Evidence:** uncle_tui.py:372-377 PROFILES, :1275-1277 stage_fields for @bedrock vs generic '@' stage, :1457 and :1462-1465 menu items, :1491-1494 _stage_items. Headless output: ['base_url', 'api_key'] / Base URL / API key / ['Connection — Base URL and API key', 'Refresh supported models (0 loaded)'].
- **Expected result:** Self Hosted still shows Base URL, API key and its existing fields and model picker unchanged; no Region field or Bedrock wording appears there.
- **Actual result:** Headless: Self Hosted connection fields are ['base_url','api_key'], labelled 'Base URL' and 'API key'. The Configure > 'Configure self hosting' menu rows are 'Connection — Base URL and API key' and 'Refresh supported models (0 loaded)', with no Region or Bedrock text. Region and Bedrock wording sits only in the separate @bedrock stage and the 'Configure AWS Bedrock' menu. Other HTTP-runner stage fields are ['runner','effort','model'] (the model picker is intact). The live screen was not seen and no screenshot was captured. The 'other non-Bedrock runner' screen (claude/codex/kimi) was not opened live; code shows its fields are runner/effort/(network)/model with no Region.

## None. The operator must supply a valid Bedrock bearer token and region (live reference LV-1) and rerun this check.

- **Status:** BLOCKED-HUMAN
- **Evidence:** env grep for bedrock/AWS_BEARER returned a count of 0. ls .uncle/aws-bedrock-keys.json returned 'No such file or directory'.
- **Expected result:** Catalog lists foundation model IDs and inference profile IDs from all pages; a stage request completes via Converse at bedrock-runtime.<region>.amazonaws.com; if no token is available this is recorded BLOCKED-HUMAN, not passed.
- **Actual result:** No Bedrock token or region is configured. The environment has no matching variables and .uncle/aws-bedrock-keys.json does not exist, so the live model refresh and Converse request could not be run.

## MC-106

- **Status:** NOT RUN
- **Evidence:** No worker observation was supplied for this checklist item.
- **Expected result:** Catalog includes both foundation model IDs and inference profile IDs (including profiles beyond the first page, if any).
- **Actual result:** Not performed.

## MC-107

- **Status:** NOT RUN
- **Evidence:** No worker observation was supplied for this checklist item.
- **Expected result:** The request succeeds via Converse with text output and no temperature-related error; the Configure screens show no temperature option for Bedrock.
- **Actual result:** Not performed.
