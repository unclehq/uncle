# Change Request

Issue 180

Seeded from [unclehq/uncle#180](https://github.com/unclehq/uncle/issues/180).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Offer the AWS Bedrock runner everywhere a runner can be selected

## Motivation

## Summary
AWS Bedrock was added as a runner (#179), but it is not offered consistently wherever users choose a runner. Users should be able to select it in every runner picker, with the same behavior as Self hosted where that applies.

## Current behavior
- The full-screen TUI (`uncle_tui.py`) lists `aws-bedrock` in `AGENT_RUNNERS` / `REVIEWER_RUNNERS` and has a "Configure AWS Bedrock" section.
- The shell fallback in `uncle` (`configure_stage`) builds its choices from `uncle_installed_runners`, which does not include `aws-bedrock`, so typing it at the "Runner" prompt is rejected as "Not a ... runner".
- The fallback's model prompt (`m`) and "apply to all stages" (`a`) are gated on `self-hosted` only, so Bedrock stages get no model choice and cannot be applied to all stages.
- Other places that special-case `self-hosted` (e.g. `stage_runner()` handling, per-stage connection/model profile migration, status-line runner mapping in `uncle_tui.py`) should be audited for Bedrock.

## Desired behavior
- Every runner selection surface (TUI, `uncle` shell fallback, any other config or CLI path) offers `aws-bedrock` alongside claude, codex, kimi and self-hosted.
- Selecting Bedrock in any of them behaves the same: model selection from the configured Bedrock models, and "apply to all stages" using the Bedrock connection and token.
- A Bedrock selection made in one surface is shown correctly in the others.

## Acceptance criteria
- [ ] `aws-bedrock` is accepted at the `uncle` shell fallback runner prompt for both agent and reviewer stages.
- [ ] Model choice and apply-to-all-stages work for Bedrock in the fallback, using `aws-bedrock-keys.json`.
- [ ] A grep audit of `self-hosted` special cases is done, and each is either extended to Bedrock or documented as intentionally Self hosted only.
- [ ] Tests cover Bedrock selection (extend `scripts/tests/aws-bedrock-dispatch-test.sh` or similar).
- [ ] `docs/aws-bedrock.md` and `README` runner lists are updated if they mention the available runners.

## Out of scope
Changes to the Bedrock wire protocols or model discovery.

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
