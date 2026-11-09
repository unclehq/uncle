# Branch and worktree policy

## Change Type
Behavior change

## Summary
Uncle should do change work (existing-code changes, issue and PR work, fixes) on a newly created branch. New application builds should run directly in the main branch of the current checkout, with no worktree and no separate branch.

## Motivation
The operator wants a predictable policy. Changes are isolated on a new branch. New application builds land directly in main and do not use a worktree.

## Observed Current Behavior
Worktrees are opt-in for issue runs through `scripts/from-issue.sh --worktree` (see docs/worktrees.md). `scripts/stagegate.sh` can run a new application build in an Uncle-owned worktree and then merge the finished build back into the source checkout's branch (see `worktree_merge_owned` and `worktree_merge_finish_all`). The branch behavior for non-issue change runs is not yet documented. It must be established from `scripts/change-workflow.sh` and `scripts/lib/change-pr.sh`.

## Desired Behavior
1. Change work (`change-workflow.sh`, `from-issue.sh`, and `create_change` / `run_change` / `github_issue` actions from the home agent) creates and switches to a new branch before making any edits, unless the run is already on a non-default branch created for it.
2. New application builds (`stagegate.sh` / `create_app` / `run_app`) run in the main branch of the current checkout. They never create or use a worktree, and they do not create a separate branch.
3. The new application path ignores any worktree option or setting. If one is requested, Uncle reports plainly that it is not used for application builds.
4. Existing opt-in worktree support for issue runs is preserved unless it conflicts with the rules above.

## Reproduction
Start a new application build from a clean checkout on main and observe whether an Uncle-owned worktree is created. Start a change run and observe whether a new branch is created before edits.

## Constraints
- Do not delete or force-modify existing branches or worktrees.
- Do not weaken the approval gates or the verification gates.
- Keep domain logic separate from git plumbing. Keep the policy decision in one place.
- Refuse to start a new application build if the checkout is not on main or has uncommitted changes, and say why.

## Known Relevant Files
- scripts/stagegate.sh
- scripts/change-workflow.sh
- scripts/from-issue.sh
- scripts/lib/worktrees.sh
- scripts/lib/worktree-merge.sh
- scripts/lib/change-pr.sh
- scripts/lib/worktree_runs.py
- scripts/lib/home_actions.py
- prompts/home-agent.md
- docs/worktrees.md
- scripts/README.md

## Out of Scope
- Changing the review, plan, or verification stages.
- Removing worktree support for issue runs.
- Pushing branches or opening pull requests differently than today.

## Success Criteria
- A change run starts on a newly created branch, shown by `git branch --show-current` before the first edit.
- A new application build runs on main with no worktree created, shown by `git worktree list` and `git branch` before and after.
- Tests cover both paths and the refusal case, and the existing worktree tests still pass.
- docs/worktrees.md and prompts/home-agent.md describe the new policy.
