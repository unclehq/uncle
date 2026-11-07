# Change Request

Issue 178

Seeded from [unclehq/uncle#178](https://github.com/unclehq/uncle/issues/178).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Add AWS Bedrock runner (clone of Self Hosted, without temperature)

## Motivation

## Summary
Add a new runner named **AWS Bedrock** that behaves like the existing **Self Hosted** runner, except that it never sends a temperature, and that lets the user choose which Bedrock wire protocol to speak.

## Desired behavior
- A new **AWS Bedrock** option appears in the main menu, alongside Self Hosted.
- Its menu offers the same choices as the Self Hosted menu, with these differences:
  - the token option is named **AWS Bedrock Token** (instead of the Self Hosted token);
  - the Base URL option is named **Bedrock URL**;
  - a new **API Compatibility** choice selects the wire protocol (see below).
- Everything else (model discovery/refresh, connection settings, key storage, per-stage configuration, request options, performance behavior) matches Self Hosted.
- **Main difference:** the AWS Bedrock runner does not use temperature. No `temperature` value is sent in requests, and the temperature setting is not offered or read (no `WORKFLOW_SELF_HOSTED_TEMPERATURE`, `<stage>.temperature` or built-in per-stage default equivalent).

## API compatibility choice
The Bedrock menu offers three protocols; the choice is stored with the Bedrock connection settings (separately from Self Hosted):
- **OpenAI compatible** (default, recommended): reuses the existing Self Hosted HTTP transport (chat completions), minus temperature.
- **Anthropic compatible**: Anthropic Messages API request/response shape (tools, system prompt, `max_tokens`), minus temperature.
- **Converse API compatible**: Bedrock native Converse API (`messages`, `toolConfig`, `inferenceConfig` without `temperature`).
The selected protocol determines request building and response parsing (including tool calls, usage and schema-constrained output). Authentication for each is the AWS Bedrock Token unless a protocol requires otherwise (SigV4 for native Converse is to be decided in the plan).

## Implementation approach
- Introduce a runner profile (name, key file, env prefix, menu labels, `uses_temperature`, protocol) read by both Self Hosted and Bedrock instead of cloning ~4,000 lines.
- `temperature()` returns "none" for Bedrock and the request builders (`self_hosted_http.py` ~lines 988, 997, 1110) omit the key; guard `self_hosted_performance.py` (~lines 232, 257), which assumes a number.
- Add a per-protocol transport layer; OpenAI compatible is the existing path.

## Current behavior
Self Hosted always sends `temperature` (0 by default, configurable); see `scripts/lib/self_hosted_http.py` (`temperature()`, request payloads) and `scripts/lib/self_hosted.py`. Menu code lives in `uncle_tui.py`; the runner id `"self-hosted"` is hard-coded in many places there, in the shell shims and in `scripts/stagegate.sh`.

## Acceptance criteria
- Main menu shows an AWS Bedrock entry; its submenu mirrors Self Hosted with "AWS Bedrock Token" and "Bedrock URL" labels plus an API Compatibility choice (OpenAI / Anthropic / Converse).
- Requests made by the AWS Bedrock runner contain no temperature field under any of the three protocols.
- Each protocol builds a valid request and parses responses (including tool calls) correctly.
- Self Hosted behavior is unchanged (including its temperature handling).
- Bedrock credentials/settings, including the chosen protocol, are stored separately from Self Hosted's.
- Tests cover the menu labels, the protocol choice, and the absence of temperature in Bedrock requests for each protocol.

## Open questions
- Does native Converse need SigV4 signing, or is bearer-token auth sufficient for the target endpoints?

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
