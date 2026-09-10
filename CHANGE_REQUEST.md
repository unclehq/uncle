# Change Request

Seeded from [unclehq/uncle#6](https://github.com/unclehq/uncle/issues/6).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

When completing a change request make a PR with a comment that closes the change request

## Motivation

Make a pull request when a change request is completed.

1. Show a dialog that asks the user to name the PR and prefill it with a shortened version of the issue name if there is one or if there is a good name in the CHANGE_REQUEST if a change request is how the process started
2. Fill the PR description with a very brief description of the work done and how to manually verify it
3. Have a comment that closes the issue when merged 
4. If there is no .git directory do not do this process

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
