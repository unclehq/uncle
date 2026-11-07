# Change Request

## Change Type
Behavior change (feature)

## Summary
Whenever Uncle does its work in a git worktree, it must open a pull request for that worktree's branch when the build finishes, whether or not the work came from a GitHub issue.

## Motivation
Currently a PR is not guaranteed for worktree work that did not originate from an issue. The operator wants every finished worktree build to end in a PR, no matter what.

## Observed Current Behavior
PR creation appears tied to issue-driven work; worktree builds without an issue may finish with no PR.

## Desired Behavior
When Uncle finishes building in a worktree, it pushes the branch and creates a PR (via gh) against the default branch. This applies to all worktrees, issue-based or not. If a PR already exists for the branch, it is reused rather than duplicated. If PR creation fails, the failure is reported clearly and the run does not claim it is complete.

## Reproduction
Run a build or change in a worktree that is not tied to a GitHub issue. Observe that no PR is created at the end.

## Constraints
No force pushes. Do not alter behavior for non-worktree builds beyond what is needed. Keep existing issue-linked PR behavior working.

## Known Relevant Files
scripts/lib/worktrees.sh, scripts/lib/parallel_steps.py, scripts/tests/worktree-run-test.sh, scripts/README.md (found by search; not yet confirmed as the right places).

## Out of Scope
Auto-merging PRs. Changing review or approval gates. Cleaning up worktrees.

## Success Criteria
A finished worktree build with no associated issue ends with an open PR for its branch. A finished issue-based worktree build still gets exactly one PR. A test covers the no-issue case. A PR creation failure is surfaced, not hidden.