# Change Request

Issue 117

Seeded from [unclehq/uncle#117](https://github.com/unclehq/uncle/issues/117).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Offer sanitized GitHub bug reporting for non-recoverable workflow failures

## Motivation

## Goal

When Uncle encounters a non-recoverable tool or driver failure, let the user file a sanitized bug report directly to `unclehq/uncle` from the recovery UI. The report must identify the exact runner and model involved.

## Current behavior

Triage can create `.uncle/workflow/triage-issue-N.md`, but it is only a local draft. Users must manually find, redact, and file it.

## Proposed flow

```text
Failure classified as tool bug / non-recoverable driver failure
→ Recovery UI offers Report Uncle bug
→ Uncle generates a redacted issue preview
→ User explicitly confirms publication
→ gh issue create --repo unclehq/uncle
```

If `gh` is unavailable, unauthenticated, or the user declines, preserve the sanitized local draft and show a copyable submission command.

## Required issue metadata

- Uncle version, source revision, and install type
- OS/runtime basics
- Application or change workflow
- Current state, failing stage, attempt, role (agent/reviewer/worker), and exit status
- Resolved runner, model, and effort for the failing stage
- Concise error excerpt and canonical JSON/artifact validation error, if applicable
- A reference to locally retained diagnostics, without publishing their absolute paths

Use stage metrics, envelopes, resolved configuration, and the driver state as sources. Do not infer a runner/model from a global default when the stage record has a resolved value.

## Privacy and safety

- Never automatically publish an issue. Require a final user confirmation.
- Do not include API keys, tokens, cookies, model credentials, `.uncle/config`, absolute project paths, raw prompts, source files, or full unredacted logs.
- Offer an optional separate opt-in diagnostic bundle with preview/redaction before upload.
- Preserve the existing local triage draft regardless of publication outcome.

## Acceptance criteria

- The recovery UI offers reporting only for non-recoverable tool/driver failures, not routine test failures or normal recovery proposals.
- The preview shows the resolved runner, model, and effort of the failed stage.
- The published issue contains the required metadata and a useful concise failure summary.
- User cancellation creates no GitHub issue.
- Missing `gh` authentication produces a saved local draft and an actionable next step.
- Tests cover redaction, resolved per-stage runner/model attribution, confirmation/cancellation, authenticated publication, and unauthenticated fallback.

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
