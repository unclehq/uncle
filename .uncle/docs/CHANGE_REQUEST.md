# Change Request

Issue 142

Seeded from [unclehq/uncle#142](https://github.com/unclehq/uncle/issues/142).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Ask before starting a new change request when .uncle/docs/CHANGE_REQUEST.md already exists

## Motivation

## Problem

When a user starts a new change request and \`.uncle/docs/CHANGE_REQUEST.md\` already exists (left over from a previous run), uncle does not tell them. The earlier request may be silently reused or overwritten, or the run may resume from stale state, so the user can end up running a different change than the one they asked for.

## Requested behavior

When a new change request is started and \`.uncle/docs/CHANGE_REQUEST.md\` already exists:

1. Tell the user the file exists, and ask whether they want to proceed with the new change request.
2. If they answer in the affirmative, proceed with the new request.
3. If they decline, stop without modifying \`.uncle/docs/CHANGE_REQUEST.md\` or any other run state.

## Acceptance criteria

- Interactive run, existing file, user answers yes: the run proceeds with the new request.
- Interactive run, existing file, user answers no (or gives no answer): the run stops and the existing file is unchanged.
- No existing file: no prompt, behavior unchanged.
- Unattended runs (\`UNCLE_UNATTENDED=1\`) must not hang on the prompt. Decide and document the default; proposed: stop with a clear message unless an explicit opt-in is set.
- A test covers each case above.

## Open questions

- What counts as "yes" (\`y\`/\`yes\`, case-insensitive), and should an empty answer default to no? Proposed: yes.
- Should the previous request be archived (e.g. to \`.uncle/workflow-history/\`) before it is replaced?

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
