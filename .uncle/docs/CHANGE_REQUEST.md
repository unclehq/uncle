# Change Request

Issue 260

Seeded from [unclehq/uncle#260](https://github.com/unclehq/uncle/issues/260).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Stop uncle from modifying .gitignore after committing code at the end of a build / pushing a PR

## Motivation

## Problem
At the end of a build, after uncle has committed the code and pushed the PR, it updates `.gitignore` in the working tree. This leaves an uncommitted change behind (and, if it lands in the PR, an unplanned file in the diff — see FA-003 in a prior FINAL_AUDIT.md, where `.gitignore` was flagged as outside the plan's change-impact table with no recorded rationale).

## Expected
Once the code is committed and the PR is pushed, uncle must not modify `.gitignore` (or any other tracked file). Any `.gitignore` duties should happen before the commit, be declared in the plan's `Owns:` list, and be part of the committed diff — or not happen at all for existing-repo change requests.

## Acceptance criteria
- After a build finishes and the PR is pushed, `git status` in the working tree is clean of uncle-made `.gitignore` edits.
- A test covers the post-push phase leaving `.gitignore` byte-identical.
- If `.gitignore` needs a change, it appears in the plan and the PR diff, not afterwards.

## Notes
Relevant: `prompts/project-plan-investigate.md` (the `.gitignore` write duty) and `docs/plan-duties.md`. The step that actually writes `.gitignore` after the push still needs to be located.

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
