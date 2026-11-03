# Change Request

Issue 141

Seeded from [unclehq/uncle#141](https://github.com/unclehq/uncle/issues/141).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

When no PR is created, remove the worktree and check out the run's branch in the main project

## Motivation

## Problem

A change run in a per-run worktree (for example \`~/src/calculator-change\`, branch \`uncle/change\`) can finish \`COMPLETE\` without a PR being created. The result then sits uncommitted in a sibling worktree, and the original project looks untouched.

Seen with a CSS-only change to \`~/src/calculator\`. The run edited \`styles.css\` in \`calculator-change\` and \`calculator-change-2\`, and the main checkout stayed on \`main\` with no sign of the change. Opening \`~/src/calculator/index.html\` shows the old app. Nothing says where the result went or how to view it.

Related: #119 removes the worktree after a PR is created. This covers the case where no PR is created.

## Desired behavior

When a run completes and no PR is created:

1. Remove the worktree, so the result doesn't pile up on disk.
2. Switch the main project to the branch the run created, so the changed app is what the user sees in their own directory.

## Constraints

- Never discard work. The run's changes must be committed on the branch before the worktree goes. Any uncommitted or untracked output must be committed or the removal refused.
- Don't switch the main project when it has uncommitted changes that would be overwritten, or when it is on another branch the user is working on. Refuse, print the branch name and the manual \`git switch\` command, and keep the worktree.
- Keep the branch after the worktree is removed.
- If removal or the switch fails, keep what remains and print a manual command. The run's exit status doesn't change.
- Say plainly in the final output what happened: the branch name, whether the worktree was removed and whether the project was switched.

## Open questions

- Should the commit be automatic for unattended runs, or only after confirmation?
- Should this apply to attended runs too, or only unattended ones?

## Success criteria

- A completed run with no PR leaves no worktree, and the main project is on the run's branch with the change visible.
- A dirty main project or a failed removal leaves the worktree and prints the recovery command.
- Tests cover the no-PR path, the dirty main project, and a failed removal.

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
