# Change Request

Issue 158

Seeded from [unclehq/uncle#158](https://github.com/unclehq/uncle/issues/158).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Run housekeeping commands in the build window

## Motivation

Housekeeping commands (branch/worktree/label/issue cleanup) do not affect the current build, so they should run during the build window rather than blocking or waiting on the build.

Acceptance:
- Housekeeping can be started while a build is in progress.
- Running housekeeping does not alter build inputs, results, or the working tree under build.

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
