# Change Request

Issue 182

Seeded from [unclehq/uncle#182](https://github.com/unclehq/uncle/issues/182).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Bedrock: configure with region + bearer token only; always use the Converse API

## Motivation

## Summary

Simplify the AWS Bedrock runner configuration to **a region and a Bedrock bearer token only**. The runner always talks to Bedrock through the **Converse API**. Remove the Bedrock URL field and the API Compatibility choice (OpenAI / Anthropic / Converse).

## Motivation

Today Configure → AWS Bedrock asks for a Bedrock URL, a token and a wire protocol. Bedrock's endpoints are fully determined by the region, and Converse works uniformly across model providers, so the URL and protocol choices add configuration surface (and failure modes) without adding capability. Model discovery also currently differs per protocol.

## Proposed behavior

**Configuration**
- Bedrock connection = `region` (e.g. `us-east-2`) + `AWS Bedrock Token` (the `AWS_BEARER_TOKEN_BEDROCK` bearer token).
- Derived endpoints:
  - control plane: `https://bedrock.<region>.amazonaws.com`
  - runtime: `https://bedrock-runtime.<region>.amazonaws.com`
- Remove `base_url` and `api_compatibility` from the Bedrock connection (TUI, shell Configure menu, config keys, env vars such as `WORKFLOW_AWS_BEDROCK_API_COMPATIBILITY`, docs/aws-bedrock.md, README).
- Validate region format and a single-line token; the token is only ever sent over https.

**Listing available models** (bearer auth: `Authorization: Bearer <token>`)
- `GET {control}/foundation-models` → `.modelSummaries[].modelId` (+ `providerName`).
- `GET {control}/inference-profiles?maxResults=100` → `.inferenceProfileSummaries[].inferenceProfileId` (+ `inferenceProfileName`); **paginate** by following `nextToken` (URL-encoded) until absent.
- The picker should offer both foundation model IDs and inference profile IDs (e.g. `us.anthropic.claude-haiku-4-5-20251001-v1:0`), since some models are only invocable through a profile.

**Inference**
- `POST {runtime}/model/<url-encoded modelId>/converse` with `content-type: application/json`; the `:` in the model ID is encoded as `%3A`.
- Minimal body: `{"messages":[{"role":"user","content":[{"text":"..."}]}]}`; reply text at `.output.message.content[0].text`.
- **Never use temperature (AWS Bedrock runner only; Self Hosted and other runners keep their existing temperature behavior)**: the Converse request must not include `inferenceConfig.temperature` (or any temperature/sampling field), regardless of any `temperature` config key or environment variable; configured values are ignored for Bedrock and must not affect request caching/reuse keys. This is an invariant covered by a test that inspects the outgoing request body.
- Anthropic and OpenAI adapters in `scripts/lib/bedrock_protocols.py` become unused for Bedrock and can be removed.

**Reference script** (list models, list inference profiles, run a Converse request):

```bash
#!/usr/bin/env bash
set -euo pipefail

REGION="us-east-2"
AUTH="Authorization: Bearer ${AWS_BEARER_TOKEN_BEDROCK:?Set AWS_BEARER_TOKEN_BEDROCK first}"
CONTROL="https://bedrock.${REGION}.amazonaws.com"
RUNTIME="https://bedrock-runtime.${REGION}.amazonaws.com"

echo "Foundation models:"
curl -sf "${CONTROL}/foundation-models" -H "$AUTH" \
  | jq -r '.modelSummaries[] | "  \(.modelId)  (\(.providerName))"'

echo
echo "Inference profiles:"
NEXT=""
while :; do
  URL="${CONTROL}/inference-profiles?maxResults=100"
  [[ -n "$NEXT" ]] && URL="${URL}&nextToken=$(jq -rn --arg t "$NEXT" '$t|@uri')"
  PAGE=$(curl -sf "$URL" -H "$AUTH")
  echo "$PAGE" | jq -r '.inferenceProfileSummaries[] | "  \(.inferenceProfileId)  (\(.inferenceProfileName))"'
  NEXT=$(echo "$PAGE" | jq -r '.nextToken // empty')
  [[ -z "$NEXT" ]] && break
done

echo
# The ":" in the model ID is URL-encoded as %3A, as boto3 does.
MODEL_ID="us.anthropic.claude-haiku-4-5-20251001-v1%3A0"

curl -s "${RUNTIME}/model/${MODEL_ID}/converse" \
  -H "$AUTH" \
  -H "content-type: application/json" \
  -d '{"messages":[{"role":"user","content":[{"text":"what day is it"}]}]}' \
  | jq -r '.output.message.content[0].text // .'
```

## Acceptance criteria
- No Bedrock request ever contains a temperature, even when a temperature is configured for the stage or globally. Self Hosted temperature handling is unchanged.
- Configure → AWS Bedrock (TUI and shell) asks only for Region and AWS Bedrock Token; no URL or compatibility field.
- Model discovery lists foundation models and all pages of inference profiles; failures keep the prior catalog and show an actionable error.
- All Bedrock stage requests use the Converse endpoint derived from the region, with no temperature.
- Existing configs that have `base_url`/`api_compatibility` are handled with a clear migration path (derive region from the old URL where possible, otherwise prompt) rather than failing obscurely.
- `docs/aws-bedrock.md`, README and the Bedrock tests are updated.

## Notes
- Related: #179, #181 (Bedrock runner), and the recent change that made Anthropic-protocol discovery use `/foundation-models?byProvider=Anthropic` — superseded by this.

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
